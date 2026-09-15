# shellcheck shell=bash
#
# AI Dev Kit MCP server runtime and Databricks agent skills, both project-local.

df_venv_python() {
    if [ "$DF_OS" = windows ]; then
        printf '%s\n' "$DF_RUNTIME_DIR/venv/Scripts/python.exe"
    else
        printf '%s\n' "$DF_RUNTIME_DIR/venv/bin/python"
    fi
}

df_install_ai_dev_kit() {
    local source_dir="$DF_RUNTIME_DIR/ai-dev-kit" marker="$DF_RUNTIME_DIR/ai-dev-kit.ref"
    local venv="$DF_RUNTIME_DIR/venv" python

    if [ -d "$source_dir/.git" ] && [ "$(cat "$marker" 2>/dev/null)" = "$DF_ADK_REPO@$DF_ADK_REF" ]; then
        df_ok "AI Dev Kit source already at $DF_ADK_REF"
    else
        rm -rf "$source_dir" "$marker"
        mkdir -p "$DF_RUNTIME_DIR"
        df_msg "Fetching AI Dev Kit $DF_ADK_REF (MCP server and tools core only)..."
        # Long paths are required on Windows; the sparse checkout keeps the tree small.
        git -c core.longpaths=true -c advice.detachedHead=false clone --quiet --depth 1 --filter=blob:none --sparse \
            --branch "$DF_ADK_REF" "$DF_ADK_REPO" "$source_dir" \
            || df_die "Could not clone $DF_ADK_REPO at $DF_ADK_REF"
        git -C "$source_dir" config core.longpaths true
        git -C "$source_dir" sparse-checkout set databricks-mcp-server databricks-tools-core \
            || df_die "Sparse checkout of the AI Dev Kit failed"
        printf '%s\n' "$DF_ADK_REPO@$DF_ADK_REF" > "$marker"
        df_ok "AI Dev Kit $DF_ADK_REF → $(df_rel "$source_dir")"
    fi

    df_msg "Building the MCP server environment..."
    # The monitor runs with this environment's interpreter, and Windows refuses to replace a running executable.
    df_py monitor --stop --target "$(df_native_path "$DF_TARGET_DIR")" >/dev/null 2>&1 || true
    "$DF_UV" venv --quiet --allow-existing --python "$DF_PYTHON_VERSION" "$(df_native_path "$venv")" \
        || df_die "Could not create the MCP server virtual environment"
    python=$(df_venv_python)
    # PyYAML is also used by the DeltaForce monitor, which runs with this interpreter.
    "$DF_UV" pip install --quiet --python "$(df_native_path "$python")" "pyyaml>=6" \
        -e "$(df_native_path "$source_dir/databricks-tools-core")" \
        -e "$(df_native_path "$source_dir/databricks-mcp-server")" \
        || df_die "Could not install the MCP server packages"
    "$python" -c "import databricks_mcp_server" 2>/dev/null || df_die "The MCP server package cannot be imported"
    df_ok "MCP server environment → $(df_rel "$venv")"
}

df_install_skills() {
    local skills skill output staging attempt installed dest="$DF_TARGET_DIR/.claude/skills"
    skills=$(df_py skills --target "$(df_native_path "$DF_TARGET_DIR")") || df_die "Could not resolve skills for the enabled roles"
    mkdir -p "$dest"
    rm -rf "$dest"/.databricks-*.tmp 2>/dev/null || true

    # --path writes plain skill folders (no symlinks, no global state), which is what Windows needs.
    # aitools moves each freshly written folder into place with a rename, which Windows intermittently
    # refuses (Access is denied) while antivirus or indexers scan the new files. Install one skill at a
    # time with retries, in a temporary folder outside the project, then copy the files over.
    staging=$(mktemp -d)
    for skill in ${skills//,/ }; do
        installed=false
        for attempt in 1 2 3 4 5; do
            if output=$("$DF_DATABRICKS" aitools install --path "$(df_native_path "$staging")" --skills "$skill" 2>&1); then
                installed=true
                break
            fi
            rm -rf "${staging:?}/$skill" "$staging"/."$skill"-*.tmp 2>/dev/null || true
            sleep "$attempt"
        done
        $installed || { printf '%s\n' "$output" >&2; rm -rf "$staging"; df_die "databricks aitools install failed for $skill"; }
    done
    cp -R "$staging"/. "$dest"/ || { rm -rf "$staging"; df_die "Could not copy the Databricks skills into .claude/skills"; }
    rm -rf "$staging"
    df_ok "${skills//,/, } → .claude/skills"
}
