# shellcheck shell=bash
#
# Databricks authentication against the project-local profile and workspace listings.

df_profile_works() {
    "$DF_DATABRICKS" current-user me -p "$DF_DB_PROFILE" -o json >/dev/null 2>&1
}

# df_databricks_items KIND CLI-ARGS... — "value|label" lines for menus; empty on failure
df_databricks_items() {
    local kind=$1
    shift
    "$DF_DATABRICKS" "$@" -p "$DF_DB_PROFILE" -o json 2>/dev/null | df_py list --kind "$kind" 2>/dev/null || true
}

df_authenticate() {
    export DATABRICKS_CONFIG_PROFILE="$DF_DB_PROFILE"
    mkdir -p "$DF_STATE_DIR"
    touch "$DF_DATABRICKS_CFG"
    chmod 600 "$DF_DATABRICKS_CFG" 2>/dev/null || true

    if df_profile_works; then
        df_ok "Profile '$DF_DB_PROFILE' is already authenticated"
    else
        [ "$DF_INTERACTIVE" = true ] \
            || df_die "Profile '$DF_DB_PROFILE' is not authenticated and the installer cannot prompt. Run it interactively once."
        case "$DF_DB_AUTH" in
            oauth)
                df_msg "A browser window opens to sign in to $DF_DB_HOST..."
                "$DF_DATABRICKS" auth login --host "$DF_DB_HOST" --profile "$DF_DB_PROFILE" \
                    || df_die "OAuth login failed"
                ;;
            pat)
                local token
                df_ask_secret token "Personal access token"
                printf '%s\n' "$token" | "$DF_DATABRICKS" configure --host "$DF_DB_HOST" --profile "$DF_DB_PROFILE" \
                    || df_die "Could not store the personal access token"
                unset token
                ;;
            service-principal)
                local client_id client_secret
                df_ask_valid client_id "Service principal client ID" "" '^[^[:space:]]+$' "an application (client) ID"
                df_ask_secret client_secret "Service principal client secret"
                DF_SP_CLIENT_ID=$client_id DF_SP_CLIENT_SECRET=$client_secret \
                    df_py write-sp-profile --file "$DATABRICKS_CONFIG_FILE" --profile "$DF_DB_PROFILE" --host "$DF_DB_HOST" \
                    || df_die "Could not write the service principal profile"
                unset client_secret
                ;;
        esac
        df_profile_works || df_die "Authentication failed for profile '$DF_DB_PROFILE'. Re-run the installer to retry."
        df_ok "Profile '$DF_DB_PROFILE' authenticated"
    fi

    local user
    user=$("$DF_DATABRICKS" current-user me -p "$DF_DB_PROFILE" -o json 2>/dev/null | df_py list --kind user 2>/dev/null | cut -d'|' -f1 || true)
    [ -n "$user" ] && df_ok "Signed in as $user"
    return 0
}
