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
    "$DF_UV" venv --quiet --allow-existing --python "$DF_PYTHON_VERSION" "$(df_native_path "$venv")" \
        || df_die "Could not create the MCP server virtual environment"
    python=$(df_venv_python)
    "$DF_UV" pip install --quiet --python "$(df_native_path "$python")" \
        -e "$(df_native_path "$source_dir/databricks-tools-core")" \
        -e "$(df_native_path "$source_dir/databricks-mcp-server")" \
        || df_die "Could not install the MCP server packages"
    "$python" -c "import databricks_mcp_server" 2>/dev/null || df_die "The MCP server package cannot be imported"
    df_ok "MCP server environment → $(df_rel "$venv")"
}

df_install_skills() {
    local skills output dest="$DF_TARGET_DIR/.claude/skills" staging="$DF_RUNTIME_DIR/tmp/skills-$$"
    skills=$(df_py skills --target "$(df_native_path "$DF_TARGET_DIR")") || df_die "Could not resolve skills for the enabled roles"
    mkdir -p "$dest" "$staging"
    # --path writes plain skill folders (no symlinks, no global state), which is what Windows needs.
    # It replaces folders by renaming, which fails when an editor or Claude Code watches .claude/skills,
    # so write into a private staging folder and copy the files over.
    output=$("$DF_DATABRICKS" aitools install --path "$(df_native_path "$staging")" --skills "$skills" 2>&1) \
        || { printf '%s\n' "$output" >&2; rm -rf "$staging"; df_die "databricks aitools install failed"; }
    cp -R "$staging"/. "$dest"/ || df_die "Could not copy the Databricks skills into .claude/skills"
    rm -rf "$staging" "$dest"/.databricks-*.tmp 2>/dev/null || true
    df_ok "${skills//,/, } → .claude/skills"
}
