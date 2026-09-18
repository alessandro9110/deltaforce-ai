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

# Hugging Face skills follow fast-moving libraries: every install takes the latest main of the official repository,
# copies the skills of the enabled roles and records the commit it installed. The clone goes to a short temporary
# folder outside the project: its deepest files (~100 characters) under the project runtime would exceed the Windows
# path limit when long paths are disabled.
df_install_hf_skills() {
    df_install_external_skills "Hugging Face" hf-skills install-hf-skills "$DF_HF_SKILLS_REPO"
}

# LangChain, LangGraph and Deep Agents skills for the roles that ask for them.
df_install_langchain_skills() {
    df_install_external_skills "LangChain" lc-skills install-lc-skills "$DF_LC_SKILLS_REPO"
}

# Copy the skills of the enabled roles from a repository that follows a fast-moving library: always its latest main,
# with the commit recorded in .deltaforce/runtime so an update can be told apart from a change of our own.
df_install_external_skills() {
    local label=$1 list_command=$2 install_command=$3 repo=$4
    local skills commit staging
    skills=$(df_py "$list_command" --target "$(df_native_path "$DF_TARGET_DIR")")         || df_die "Could not resolve the $label skills for the enabled roles"
    if [ -z "$skills" ]; then
        df_ok "No $label skills for the enabled roles"
        return 0
    fi
    staging=$(mktemp -d)
    git -c core.longpaths=true clone --quiet --depth 1 "$repo" "$staging/skills"         || { rm -rf "$staging"; df_die "Could not download the $label skills from $repo"; }
    commit=$(git -C "$staging/skills" rev-parse --short HEAD)
    if ! df_py "$install_command" --target "$(df_native_path "$DF_TARGET_DIR")" --source "$(df_native_path "$staging/skills")"         --repo "$repo" --commit "$commit" >/dev/null; then
        rm -rf "$staging"
        df_die "Could not copy the $label skills into .claude/skills"
    fi
    rm -rf "$staging"
    df_ok "${skills//,/, } (commit $commit) → .claude/skills"
}
