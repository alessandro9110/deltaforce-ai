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

# Processes running from this project's runtime: the Databricks MCP server and the hooks of an open Claude Code
# session. The monitor does not count — the installer stops it by itself before rebuilding the environment.
df_runtime_processes() {
    [ -d "$DF_RUNTIME_DIR" ] || return 0
    if [ "$DF_OS" = windows ]; then
        DF_RUNTIME_MATCH=$(df_native_path "$DF_RUNTIME_DIR") MSYS2_ARG_CONV_EXCL='*' \
            powershell.exe -NoProfile -NonInteractive -Command \
            '$r = $env:DF_RUNTIME_MATCH.Replace("\", "/").ToLower(); Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Replace("\", "/").ToLower().Contains($r) -and $_.CommandLine -notmatch "monitor.server\.py" } | ForEach-Object { $_.ProcessId }' \
            2>/dev/null | tr -d '\r' | grep -E '^[0-9]+$' || true
    else
        ps -eo pid=,args= 2>/dev/null | grep -F -- "$DF_RUNTIME_DIR" | grep -v -e 'monitor/server.py' -e 'grep ' | awk '{ print $1 }' || true
    fi
}

# Updating with Claude Code open fails half-way on Windows (running executables cannot be replaced) and swaps
# agents and skills under a working session: ask to close it first.
df_check_claude_closed() {
    local pids answer
    pids=$(df_runtime_processes)
    [ -n "$pids" ] || return 0
    df_warn "Claude Code seems to be open on this project: its Databricks MCP server or DeltaForce hooks are running."
    df_msg "  The installer rebuilds that environment and replaces agents and skills: close Claude Code first."
    [ "$DF_INTERACTIVE" = true ] || df_die "Close Claude Code on this project, then run the installer again"
    while [ -n "$pids" ]; do
        df_ask answer "Press Enter when Claude Code is closed, or type 'continue' to go on anyway" ""
        if [ "$answer" = continue ]; then
            df_warn "Continuing with Claude Code open: rebuilding the MCP server environment may fail"
            return 0
        fi
        pids=$(df_runtime_processes)
        [ -z "$pids" ] || df_warn "Still running — close every Claude Code session on this project, including the VS Code extension"
    done
    df_ok "Claude Code is closed"
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
        DF_PROD_ENABLED DF_PROD_HOST DF_PROD_PROFILE DF_PROD_AUTH DF_PROD_WAREHOUSE_ID \
        DF_BUNDLE_TARGET DF_CATALOG DF_MEDALLION_LAYOUT DF_SCHEMA DF_SCHEMA_BRONZE DF_SCHEMA_SILVER DF_SCHEMA_GOLD \
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

# Commit what the installer produced: agents may not commit installed files, so the installer does.
# Keep the path list in sync with INSTALLED_COMMIT_PATHS in lib/py/deltaforce/guardrails.py.
df_commit_install() {
    local -a candidates=(.gitignore CLAUDE.md .claude/settings.json .claude/agents .claude/skills databricks.yml
        resources/deltaforce.variables.yml .deltaforce/config.yaml .deltaforce/conventions.yaml)
    local -a paths=()
    local path branch
    for path in "${candidates[@]}"; do
        [ -e "$DF_TARGET_DIR/$path" ] && paths+=("$path")
    done
    if [ -z "$(git -C "$DF_TARGET_DIR" status --porcelain -- "${paths[@]}")" ]; then
        df_ok "DeltaForce files already committed"
        return 0
    fi
    branch=$(git -C "$DF_TARGET_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
    case ",$DF_PROTECTED_BRANCHES," in
        *",$branch,"*)
            df_warn "Not committing on protected branch '$branch': switch to '$DF_DEV_BRANCH' and re-run the installer"
            return 0
            ;;
    esac
    if ! df_confirm "Commit the DeltaForce files on branch '$branch'? Agents cannot change or commit them"; then
        df_warn "Commit them before /df-kickoff: agents cannot commit files installed by DeltaForce"
        return 0
    fi
    if git -C "$DF_TARGET_DIR" add -- "${paths[@]}" \
        && git -C "$DF_TARGET_DIR" commit -q -m "chore(deltaforce): install DeltaForce AI" -m "DeltaForce-Role: installer"; then
        df_ok "Committed the DeltaForce files on '$branch'"
    else
        df_warn "Could not commit — set git user.name and user.email, then re-run the installer"
    fi
}

df_run_doctor() {
    if df_py doctor --target "$(df_native_path "$DF_TARGET_DIR")"; then
        df_step "DeltaForce is ready"
        df_msg "Open Claude Code in this repository and run /df-kickoff."
    else
        local script=.deltaforce/framework/install.sh
        [ "$DF_FRAMEWORK_DIR" = "$DF_TARGET_DIR/.deltaforce/framework" ] || script="$DF_FRAMEWORK_DIR/install.sh"
        df_step "Not ready yet"
        df_msg "Fix the errors above. Re-running the install command re-checks everything and creates"
        df_msg "missing schemas. To only re-check, from the project folder:"
        if [ "$DF_OS" = windows ]; then
            df_msg "  PowerShell: & \"\$env:ProgramFiles\\Git\\bin\\bash.exe\" -c 'bash $script --doctor'"
            df_msg "  Git Bash:   bash $script --doctor"
        else
            df_msg "  bash $script --doctor"
        fi
        return 1
    fi
}
