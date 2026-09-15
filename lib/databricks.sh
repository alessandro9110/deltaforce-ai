# shellcheck shell=bash
#
# Databricks authentication against project-local profiles and workspace listings.

# df_profile_works [PROFILE] — defaults to the dev profile
df_profile_works() {
    "$DF_DATABRICKS" current-user me -p "${1:-$DF_DB_PROFILE}" -o json >/dev/null 2>&1
}

df_databricks_exists() {
    "$DF_DATABRICKS" "$@" -p "$DF_DB_PROFILE" -o json >/dev/null 2>&1
}

# df_databricks_items KIND CLI-ARGS... — "value|label" lines for menus; empty on failure.
# Lists from the dev profile unless DF_LIST_PROFILE is set.
df_databricks_items() {
    local kind=$1
    shift
    "$DF_DATABRICKS" "$@" -p "${DF_LIST_PROFILE:-$DF_DB_PROFILE}" -o json 2>/dev/null \
        | df_py list --kind "$kind" 2>/dev/null || true
}

# df_authenticate_profile HOST PROFILE AUTH LABEL
df_authenticate_profile() {
    local host=$1 profile=$2 auth=$3 label=$4

    if df_profile_works "$profile"; then
        df_ok "The $label profile '$profile' is already authenticated"
    else
        [ "$DF_INTERACTIVE" = true ] \
            || df_die "The $label profile '$profile' is not authenticated and the installer cannot prompt. Run it interactively once."
        case "$auth" in
            oauth)
                df_msg "A browser window opens to sign in to $host..."
                "$DF_DATABRICKS" auth login --host "$host" --profile "$profile" || df_die "OAuth login failed ($label)"
                ;;
            pat)
                local token
                df_ask_secret token "Personal access token for $host"
                printf '%s\n' "$token" | "$DF_DATABRICKS" configure --host "$host" --profile "$profile" \
                    || df_die "Could not store the personal access token ($label)"
                unset token
                ;;
            service-principal)
                local client_id client_secret
                df_ask_valid client_id "Service principal client ID for $host" "" '^[^[:space:]]+$' "an application (client) ID"
                df_ask_secret client_secret "Service principal client secret"
                DF_SP_CLIENT_ID=$client_id DF_SP_CLIENT_SECRET=$client_secret \
                    df_py write-sp-profile --file "$DATABRICKS_CONFIG_FILE" --profile "$profile" --host "$host" \
                    || df_die "Could not write the service principal profile ($label)"
                unset client_secret
                ;;
        esac
        df_profile_works "$profile" || df_die "Authentication failed for the $label profile '$profile'. Re-run the installer to retry."
        df_ok "The $label profile '$profile' is authenticated"
    fi

    local user
    user=$("$DF_DATABRICKS" current-user me -p "$profile" -o json 2>/dev/null | df_py list --kind user 2>/dev/null | cut -d'|' -f1 || true)
    [ -n "$user" ] && df_ok "Signed in to $label as $user"
    return 0
}

df_authenticate() {
    export DATABRICKS_CONFIG_PROFILE="$DF_DB_PROFILE"
    mkdir -p "$DF_STATE_DIR"
    touch "$DF_DATABRICKS_CFG"
    chmod 600 "$DF_DATABRICKS_CFG" 2>/dev/null || true

    df_authenticate_profile "$DF_DB_HOST" "$DF_DB_PROFILE" "$DF_DB_AUTH" dev
    if [ "${DF_PROD_ENABLED:-false}" = true ]; then
        df_authenticate_profile "$DF_PROD_HOST" "$DF_PROD_PROFILE" "$DF_PROD_AUTH" production
    fi
    # The CLI keeps a copy of the previous file when it rewrites it; the copy can hold tokens.
    rm -f "$DF_DATABRICKS_CFG".bak
    return 0
}
