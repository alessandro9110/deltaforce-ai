# shellcheck shell=bash
#
# Installer questions. Every answer lands in a DF_* variable; values from an
# existing .deltaforce/config.yaml (or the environment) are offered as defaults.

df_detect_git_provider() {
    local url
    url=$(git -C "$DF_TARGET_DIR" remote get-url origin 2>/dev/null || true)
    case "$url" in
        *dev.azure.com*|*visualstudio.com*) echo azure-devops ;;
        *github.com*)                       echo github ;;
        *)                                  echo other ;;
    esac
}

df_ask_project() {
    local folder_name current_branch default_branch
    folder_name=$(basename "$DF_TARGET_DIR" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9_-')
    df_ask_valid DF_PROJECT_NAME "Project name" "${DF_PROJECT_NAME:-$folder_name}" \
        '^[a-z0-9][a-z0-9_-]*$' "lowercase letters, digits, '-' and '_'"

    current_branch=$(git -C "$DF_TARGET_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
    case "$current_branch" in
        ""|main|master) default_branch=dev ;;
        *)              default_branch=$current_branch ;;
    esac
    df_ask DF_PROTECTED_BRANCHES "Protected branches, never pushed by the team (comma-separated)" \
        "${DF_PROTECTED_BRANCHES:-main,master}"
    DF_PROTECTED_BRANCHES=$(printf '%s' "$DF_PROTECTED_BRANCHES" | tr -d ' ')
    while true; do
        df_ask_valid DF_DEV_BRANCH "Dev branch the team works and pushes on" \
            "${DF_DEV_BRANCH:-$default_branch}" '^[^[:space:]]+$' "a branch name"
        case ",$DF_PROTECTED_BRANCHES," in
            *",$DF_DEV_BRANCH,"*)
                [ "$DF_INTERACTIVE" = true ] || df_die "Dev branch '$DF_DEV_BRANCH' is a protected branch"
                df_warn "The dev branch cannot be a protected branch"
                DF_DEV_BRANCH=""
                ;;
            *) break ;;
        esac
    done

    DF_GIT_PROVIDER=${DF_GIT_PROVIDER:-$(df_detect_git_provider)}
    local default_cicd=${DF_CICD:-}
    if [ -z "$default_cicd" ]; then
        case "$DF_GIT_PROVIDER" in
            github) default_cicd=github ;;
            *)      default_cicd=azure-devops ;;
        esac
    fi
    df_choose DF_CICD "CI/CD provider" "$default_cicd" false \
        "azure-devops|Azure DevOps Pipelines" "github|GitHub Actions" "none|None"
}

# Make sure the dev branch exists and is checked out; asks before every git change.
df_ensure_dev_branch() {
    local root=$DF_TARGET_DIR branch=$DF_DEV_BRANCH current
    current=$(git -C "$root" symbolic-ref --quiet --short HEAD 2>/dev/null || true)

    if git -C "$root" show-ref --verify --quiet "refs/heads/$branch" \
        || git -C "$root" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
        if [ "$current" = "$branch" ]; then
            df_ok "On branch '$branch'"
        elif df_confirm "Switch to branch '$branch'?"; then
            git -C "$root" switch -q "$branch" && df_ok "Switched to '$branch'" \
                || df_warn "Could not switch to '$branch' — commit or stash your changes, then switch"
        fi
        return 0
    fi

    if ! df_confirm "Branch '$branch' does not exist. Create it now?"; then
        df_warn "Create '$branch' before /df-kickoff"
        return 0
    fi
    if ! git -C "$root" rev-parse --verify --quiet HEAD >/dev/null; then
        git -C "$root" commit -q --allow-empty -m "chore: initial commit" \
            || df_die "Could not create the initial commit — set git user.name and user.email, then re-run"
    fi
    git -C "$root" switch -q -c "$branch" || df_die "Could not create branch '$branch'"
    df_ok "Created branch '$branch'"
    if git -C "$root" remote get-url origin >/dev/null 2>&1 \
        && [ "$DF_INTERACTIVE" = true ] && df_confirm "Push '$branch' to origin?"; then
        git -C "$root" push -q -u origin "$branch" && df_ok "Pushed '$branch'" \
            || df_warn "Push failed — push '$branch' later"
    fi
}

df_ask_workspace() {
    # A URL copied from the browser (path, ?o=<workspace-id>, #fragment) is accepted; only the host is kept.
    df_ask_valid DF_DB_HOST "Databricks workspace URL" "${DF_DB_HOST:-}" \
        '^https://[^/?#[:space:]]+([/?#][^[:space:]]*)?$' "https://<workspace-host>"
    [[ $DF_DB_HOST =~ ^(https://[^/?#[:space:]]+) ]] && DF_DB_HOST=${BASH_REMATCH[1]}
    df_ok "Workspace: $DF_DB_HOST"
    local default_profile="deltaforce-$DF_PROJECT_NAME"
    case "$DF_PROJECT_NAME" in deltaforce*) default_profile=$DF_PROJECT_NAME ;; esac
    while true; do
        df_ask_valid DF_DB_PROFILE "Databricks CLI profile name" "${DF_DB_PROFILE:-$default_profile}" \
            '^[A-Za-z0-9_-]+$' "letters, digits, '-' and '_'"
        [ "$DF_DB_PROFILE" != DEFAULT ] && break
        [ "$DF_INTERACTIVE" = true ] || df_die "The profile name DEFAULT is reserved"
        df_warn "DEFAULT is reserved — choose a project-specific name"
        DF_DB_PROFILE=""
    done
    df_choose DF_DB_AUTH "Authentication method" "${DF_DB_AUTH:-oauth}" false \
        "oauth|OAuth in the browser (recommended)" \
        "pat|Personal access token" \
        "service-principal|Service principal (OAuth client ID and secret)"
}

df_ask_target() {
    local -a items=()

    mapfile -t items < <(df_databricks_items warehouses warehouses list)
    if [ ${#items[@]} -gt 0 ]; then
        df_choose DF_WAREHOUSE_ID "SQL warehouse" "${DF_WAREHOUSE_ID:-}" true "${items[@]}"
    else
        df_warn "Could not list SQL warehouses — enter the ID manually"
        df_ask DF_WAREHOUSE_ID "SQL warehouse ID" "${DF_WAREHOUSE_ID:-}"
    fi
    [[ $DF_WAREHOUSE_ID =~ ^[A-Za-z0-9]+$ ]] || df_die "Invalid SQL warehouse ID: '$DF_WAREHOUSE_ID'"

    df_choose DF_COMPUTE "Compute for notebooks and Python code" "${DF_COMPUTE:-serverless}" false \
        "serverless|Serverless (recommended)" "cluster|Existing cluster"
    if [ "$DF_COMPUTE" = cluster ]; then
        mapfile -t items < <(df_databricks_items clusters clusters list)
        if [ ${#items[@]} -gt 0 ]; then
            df_choose DF_CLUSTER_ID "Cluster" "${DF_CLUSTER_ID:-}" true "${items[@]}"
        else
            df_ask DF_CLUSTER_ID "Cluster ID" "${DF_CLUSTER_ID:-}"
        fi
        [[ $DF_CLUSTER_ID =~ ^[A-Za-z0-9-]+$ ]] || df_die "Invalid cluster ID: '$DF_CLUSTER_ID'"
    else
        DF_CLUSTER_ID=""
    fi

    mapfile -t items < <(df_databricks_items catalogs catalogs list)
    while true; do
        if [ ${#items[@]} -gt 0 ]; then
            df_choose DF_CATALOG "Dev catalog (number, or type a catalog name)" "${DF_CATALOG:-}" true "${items[@]}"
        else
            df_ask DF_CATALOG "Dev catalog" "${DF_CATALOG:-}"
        fi
        if [[ $DF_CATALOG =~ ^[A-Za-z0-9_-]+$ ]] && df_databricks_exists catalogs get "$DF_CATALOG"; then
            df_ok "Catalog '$DF_CATALOG'"
            break
        fi
        [ "$DF_INTERACTIVE" = true ] || df_die "Catalog '$DF_CATALOG' does not exist or is not accessible"
        df_warn "Catalog '$DF_CATALOG' does not exist or you cannot access it — choose another one"
        DF_CATALOG=""
    done

    df_choose DF_MEDALLION_LAYOUT "Medallion layout" "${DF_MEDALLION_LAYOUT:-single_schema}" false \
        "single_schema|One schema; table names prefixed bronze_, silver_, gold_" \
        "multi_schema|One schema per layer"
    local schema_re='^[A-Za-z0-9_-]+$' schema_hint="letters, digits, '-' and '_'"
    if [ "$DF_MEDALLION_LAYOUT" = single_schema ]; then
        df_ask_valid DF_SCHEMA "Dev schema" "${DF_SCHEMA:-}" "$schema_re" "$schema_hint"
        DF_SCHEMA_BRONZE="" DF_SCHEMA_SILVER="" DF_SCHEMA_GOLD=""
    else
        df_ask_valid DF_SCHEMA_BRONZE "Bronze schema" "${DF_SCHEMA_BRONZE:-}" "$schema_re" "$schema_hint"
        df_ask_valid DF_SCHEMA_SILVER "Silver schema" "${DF_SCHEMA_SILVER:-}" "$schema_re" "$schema_hint"
        df_ask_valid DF_SCHEMA_GOLD "Gold schema" "${DF_SCHEMA_GOLD:-}" "$schema_re" "$schema_hint"
        DF_SCHEMA=""
    fi
    df_ensure_schemas
}

# Create missing dev schemas; the catalog must already exist.
df_ensure_schemas() {
    local -a schemas=()
    local schema full output
    if [ "$DF_MEDALLION_LAYOUT" = single_schema ]; then
        schemas=("$DF_SCHEMA")
    else
        schemas=("$DF_SCHEMA_BRONZE" "$DF_SCHEMA_SILVER" "$DF_SCHEMA_GOLD")
    fi
    for schema in $(printf '%s\n' "${schemas[@]}" | awk '!seen[$0]++'); do
        full="$DF_CATALOG.$schema"
        if df_databricks_exists schemas get "$full"; then
            df_ok "Schema '$full'"
        elif output=$("$DF_DATABRICKS" schemas create "$schema" "$DF_CATALOG" -p "$DF_DB_PROFILE" -o json 2>&1); then
            df_ok "Created schema '$full'"
        else
            df_warn "Could not create '$full' ($(printf '%s\n' "$output" | grep -m 1 -i '^error' || printf '%s\n' "$output" | head -n 1)) — ask for CREATE SCHEMA on '$DF_CATALOG' or choose an existing schema"
        fi
    done
}

df_ask_team() {
    local -a roles=()
    local all_roles
    mapfile -t roles < <(df_py roles)
    [ ${#roles[@]} -gt 0 ] || df_die "Could not read lib/data/roles.yaml"
    all_roles=$(printf '%s\n' "${roles[@]}" | cut -d'|' -f1 | paste -sd, -)

    DF_ROLES=${DF_ROLES:-$all_roles}
    DF_MODEL_DEFAULT=${DF_MODEL_DEFAULT:-sonnet}
    DF_MAX_SPAWN_DEPTH=${DF_MAX_SPAWN_DEPTH:-3}

    if [ "$DF_ADVANCED" = true ]; then
        df_msg "Available roles: ${all_roles//,/, }"
        df_ask_valid DF_ROLES "Roles to enable (comma-separated; pm is always enabled)" "$DF_ROLES" \
            '^[a-z-]+(,[a-z-]+)*$' "comma-separated role ids"
        df_choose DF_MODEL_DEFAULT "Default model for roles without a specific one" "$DF_MODEL_DEFAULT" true \
            "sonnet|Sonnet" "opus|Opus" "haiku|Haiku"
        df_ask_valid DF_MAX_SPAWN_DEPTH "Max subagent nesting depth" "$DF_MAX_SPAWN_DEPTH" '^[1-5]$' "1-5"
        df_ask_valid DF_ADK_REF "AI Dev Kit git ref (tag or branch)" "$DF_ADK_REF" '^[^[:space:]]+$' "a git ref"
    fi
    case ",$DF_ROLES," in
        *,pm,*) ;;
        *) DF_ROLES="pm,$DF_ROLES" ;;
    esac
    df_ok "Roles: ${DF_ROLES//,/, }"
}

df_ask_prod() {
    df_choose DF_PROD_ENABLED "Does the team need to read data from a separate production workspace?" \
        "${DF_PROD_ENABLED:-false}" false \
        "false|No" \
        "true|Yes — read-only: SQL queries, model and vector search calls, Genie"
    if [ "$DF_PROD_ENABLED" != true ]; then
        DF_PROD_HOST="" DF_PROD_PROFILE="" DF_PROD_AUTH="" DF_PROD_WAREHOUSE_ID=""
        return 0
    fi
    while true; do
        df_ask_valid DF_PROD_HOST "Production workspace URL" "${DF_PROD_HOST:-}" \
            '^https://[^/?#[:space:]]+([/?#][^[:space:]]*)?$' "https://<workspace-host>"
        [[ $DF_PROD_HOST =~ ^(https://[^/?#[:space:]]+) ]] && DF_PROD_HOST=${BASH_REMATCH[1]}
        [ "${DF_PROD_HOST,,}" != "${DF_DB_HOST,,}" ] && break
        [ "$DF_INTERACTIVE" = true ] || df_die "The production workspace must be different from the dev workspace"
        df_warn "Production must be a different workspace from dev"
        DF_PROD_HOST=""
    done
    df_ok "Production workspace: $DF_PROD_HOST"
    while true; do
        df_ask_valid DF_PROD_PROFILE "Production CLI profile name" "${DF_PROD_PROFILE:-$DF_DB_PROFILE-prod}" \
            '^[A-Za-z0-9_-]+$' "letters, digits, '-' and '_'"
        [ "$DF_PROD_PROFILE" != DEFAULT ] && [ "$DF_PROD_PROFILE" != "$DF_DB_PROFILE" ] && break
        [ "$DF_INTERACTIVE" = true ] || df_die "The production profile must differ from DEFAULT and from the dev profile"
        df_warn "Use a name different from DEFAULT and from the dev profile"
        DF_PROD_PROFILE=""
    done
    df_choose DF_PROD_AUTH "Production authentication method" "${DF_PROD_AUTH:-oauth}" false \
        "oauth|OAuth in the browser (recommended)" \
        "pat|Personal access token" \
        "service-principal|Service principal (OAuth client ID and secret)"
}

df_ask_prod_target() {
    [ "${DF_PROD_ENABLED:-false}" = true ] || return 0
    local -a items=()
    mapfile -t items < <(DF_LIST_PROFILE="$DF_PROD_PROFILE" df_databricks_items warehouses warehouses list)
    if [ ${#items[@]} -gt 0 ]; then
        df_choose DF_PROD_WAREHOUSE_ID "Production SQL warehouse for read queries" "${DF_PROD_WAREHOUSE_ID:-}" true "${items[@]}"
    else
        df_warn "Could not list production SQL warehouses — enter the ID manually"
        df_ask DF_PROD_WAREHOUSE_ID "Production SQL warehouse ID" "${DF_PROD_WAREHOUSE_ID:-}"
    fi
    [[ $DF_PROD_WAREHOUSE_ID =~ ^[A-Za-z0-9]+$ ]] || df_die "Invalid production SQL warehouse ID: '$DF_PROD_WAREHOUSE_ID'"
}

df_print_plan() {
    df_msg "Everything below is installed inside $DF_TARGET_DIR — nothing global:"
    df_msg "  • Git branch '$DF_DEV_BRANCH' checked out (created if missing, after asking)"
    df_msg "  • uv $DF_UV_VERSION and Databricks CLI $DF_DATABRICKS_CLI_VERSION → .deltaforce/bin"
    df_msg "  • Python $DF_PYTHON_VERSION and AI Dev Kit MCP server ($DF_ADK_REF) → .deltaforce/runtime"
    df_msg "  • Profile '$DF_DB_PROFILE' ($DF_DB_AUTH) for $DF_DB_HOST → .deltaforce/.databrickscfg"
    if [ "${DF_PROD_ENABLED:-false}" = true ]; then
        df_msg "  • Read-only production profile '$DF_PROD_PROFILE' ($DF_PROD_AUTH) for $DF_PROD_HOST"
    fi
    df_msg "  • Guardrail and audit hooks → .claude/settings.local.json"
    df_msg "  • Missing dev schemas in the chosen catalog created on Databricks"
    df_msg "  • Databricks agent skills for the enabled roles → .claude/skills"
    df_msg "  • .deltaforce/config.yaml, .mcp.json, .claude/settings*.json, CLAUDE.md block,"
    df_msg "    bundle variables and a .gitignore block"
}

df_print_summary() {
    local schemas
    if [ "$DF_MEDALLION_LAYOUT" = single_schema ]; then
        schemas="$DF_SCHEMA (prefixes bronze_, silver_, gold_)"
    else
        schemas="bronze=$DF_SCHEMA_BRONZE silver=$DF_SCHEMA_SILVER gold=$DF_SCHEMA_GOLD"
    fi
    df_msg "Project:    $DF_PROJECT_NAME — dev branch $DF_DEV_BRANCH, protected $DF_PROTECTED_BRANCHES, CI/CD $DF_CICD"
    df_msg "Workspace:  $DF_DB_HOST — profile $DF_DB_PROFILE ($DF_DB_AUTH)"
    if [ "${DF_PROD_ENABLED:-false}" = true ]; then
        df_msg "Production: $DF_PROD_HOST — profile $DF_PROD_PROFILE ($DF_PROD_AUTH), warehouse $DF_PROD_WAREHOUSE_ID, read-only"
    else
        df_msg "Production: none"
    fi
    df_msg "Warehouse:  $DF_WAREHOUSE_ID — compute $DF_COMPUTE${DF_CLUSTER_ID:+ ($DF_CLUSTER_ID)}"
    df_msg "Dev target: catalog $DF_CATALOG — $schemas"
    df_msg "Team:       ${DF_ROLES//,/, } — default model $DF_MODEL_DEFAULT, nesting depth $DF_MAX_SPAWN_DEPTH"
    df_msg "AI Dev Kit: $DF_ADK_REF"
}
