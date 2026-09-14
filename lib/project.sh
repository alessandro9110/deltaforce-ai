# shellcheck shell=bash
#
# Preflight, configuration read/write, file generation and the doctor gate.

df_preflight() {
    [ "${BASH_VERSINFO[0]}" -ge 4 ] || df_die "Bash 4 or newer is required (found $BASH_VERSION)"
    local cmd
    for cmd in git curl tar; do
        command -v "$cmd" >/dev/null 2>&1 || df_die "'$cmd' is required but was not found"
    done
    if [ "$DF_OS" = windows ]; then
        command -v unzip >/dev/null 2>&1 || df_die "'unzip' is required (it ships with Git for Windows)"
    fi

    [ "$DF_TARGET_DIR" != "$DF_FRAMEWORK_DIR" ] \
        || df_die "Run the installer from the target project repository, not from the DeltaForce AI repository"
    if ! git -C "$DF_TARGET_DIR" rev-parse --git-dir >/dev/null 2>&1; then
        [ "$DF_DRY_RUN" != true ] || df_die "$DF_TARGET_DIR is not a git repository (the real run offers to initialise one)"
        df_confirm "$DF_TARGET_DIR is not a git repository. Initialise one here?" \
            || df_die "DeltaForce needs a git repository"
        git -C "$DF_TARGET_DIR" init -q -b main || df_die "git init failed"
        df_ok "Initialised a git repository"
    fi
    local prefix
    # --show-prefix is empty at the repository root; comparing paths breaks on Windows short names.
    prefix=$(git -C "$DF_TARGET_DIR" rev-parse --show-prefix 2>/dev/null) \
        || df_die "$DF_TARGET_DIR is not a git repository"
    [ -z "$prefix" ] \
        || df_die "Run the installer from the repository root ($(git -C "$DF_TARGET_DIR" rev-parse --show-toplevel))"
    df_ok "Target repository: $DF_TARGET_DIR"
    [ "$DF_OS" = windows ] && df_check_windows_path_length


    if command -v claude >/dev/null 2>&1; then
        df_ok "Claude Code $(claude --version 2>/dev/null | head -n 1)"
    else
        df_warn "Claude Code not found on PATH — it is needed before /df-kickoff"
    fi
    [ -z "$DF_ENV_CONFLICTS" ] || df_warn "Ignoring ${DF_ENV_CONFLICTS//,/, } from the environment for this install"
}

# Python, uv and pip break once a file path exceeds 260 characters unless Windows long
# paths are enabled; the deepest files under .deltaforce/runtime add ~110 characters.
df_check_windows_path_length() {
    local target length enabled
    target=$(cygpath -w -l "$DF_TARGET_DIR" 2>/dev/null || df_native_path "$DF_TARGET_DIR")
    length=${#target}
    enabled=$(MSYS_NO_PATHCONV=1 reg query 'HKLM\SYSTEM\CurrentControlSet\Control\FileSystem' /v LongPathsEnabled 2>/dev/null \
        | awk '/LongPathsEnabled/ { print $NF }')
    [ "$enabled" = 0x1 ] && return 0
    if [ "$length" -gt 140 ]; then
        df_die "The repository path is $length characters and Windows long paths are disabled. Move the repository to a shorter path (≤ 140) or enable LongPathsEnabled (requires admin)."
    elif [ "$length" -gt 100 ]; then
        df_warn "The repository path is $length characters and Windows long paths are disabled — deep Python packages may fail. A shorter path is safer."
    fi
}

df_load_existing_config() {
    DF_ADK_REPO=${DF_ADK_REPO:-}
    DF_ADK_REF=${DF_ADK_REF:-}
    if [ -f "$DF_CONFIG_FILE" ]; then
        if [ -x "$DF_UV" ]; then
            local exports
            if exports=$(df_py export-env --target "$(df_native_path "$DF_TARGET_DIR")"); then
                eval "$exports"
                df_ok "Existing configuration loaded — its values are the defaults"
            else
                df_warn "Existing configuration is invalid — starting from defaults"
            fi
        else
            df_warn "Existing configuration found but project tools are missing — starting from defaults"
        fi
    fi
    DF_ADK_REPO=${DF_ADK_REPO:-$DF_ADK_DEFAULT_REPO}
    DF_ADK_REF=${DF_ADK_REF:-$DF_ADK_DEFAULT_REF}
}

df_write_config() {
    export DF_PROJECT_NAME DF_DEV_BRANCH DF_PROTECTED_BRANCHES DF_GIT_PROVIDER DF_CICD \
        DF_DB_HOST DF_DB_PROFILE DF_DB_AUTH DF_WAREHOUSE_ID DF_COMPUTE DF_CLUSTER_ID \
        DF_CATALOG DF_MEDALLION_LAYOUT DF_SCHEMA DF_SCHEMA_BRONZE DF_SCHEMA_SILVER DF_SCHEMA_GOLD \
        DF_ROLES DF_MODEL_DEFAULT DF_MAX_SPAWN_DEPTH DF_ADK_REPO DF_ADK_REF
    df_py write-config --target "$(df_native_path "$DF_TARGET_DIR")" \
        || df_die "The configuration is invalid — see the errors above"
    df_ok "Wrote .deltaforce/config.yaml"
}

df_generate() {
    local -a written=()
    local file
    mapfile -t written < <(df_py generate --target "$(df_native_path "$DF_TARGET_DIR")")
    [ ${#written[@]} -gt 0 ] || df_die "File generation failed"
    for file in "${written[@]}"; do
        df_ok "$file"
    done
}

df_run_doctor() {
    if df_py doctor --target "$(df_native_path "$DF_TARGET_DIR")"; then
        df_step "DeltaForce is ready"
        df_msg "Open Claude Code in this repository and run /df-kickoff."
    else
        df_step "Not ready yet"
        df_msg "Fix the errors above, then re-check with:"
        df_msg "  bash \"$DF_FRAMEWORK_DIR/install.sh\" --doctor"
        return 1
    fi
}
