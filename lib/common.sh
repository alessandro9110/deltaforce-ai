# shellcheck shell=bash
#
# Shared installer helpers: output, prompts, platform detection and paths.

if [ -t 1 ]; then
    DF_C_GREEN=$'\033[0;32m' DF_C_YELLOW=$'\033[1;33m' DF_C_RED=$'\033[0;31m'
    DF_C_BOLD=$'\033[1m' DF_C_DIM=$'\033[2m' DF_C_RESET=$'\033[0m'
else
    DF_C_GREEN="" DF_C_YELLOW="" DF_C_RED="" DF_C_BOLD="" DF_C_DIM="" DF_C_RESET=""
fi

DF_INTERACTIVE=true
DF_ASSUME_YES=false

df_msg()  { printf '  %s\n' "$*"; }
df_ok()   { printf '  %s✓%s %s\n' "$DF_C_GREEN" "$DF_C_RESET" "$*"; }
df_warn() { printf '  %s!%s %s\n' "$DF_C_YELLOW" "$DF_C_RESET" "$*"; }
df_die()  { printf '  %s✗%s %s\n' "$DF_C_RED" "$DF_C_RESET" "$*" >&2; exit 1; }
df_step() { printf '\n%s%s%s\n' "$DF_C_BOLD" "$*" "$DF_C_RESET"; }

# ─── Prompts ────────────────────────────────────────────────────
# Prompts read from /dev/tty so they work when the script itself is piped.
# Setter functions take the name of the variable to assign as first argument.

df_has_tty() { ( : </dev/tty ) 2>/dev/null; }

df_read_line() {
    local __line=""
    printf '%s' "$1" >/dev/tty
    IFS= read -r __line </dev/tty || true
    printf '%s' "$__line"
}

df_in_list() {
    local needle=$1 item
    shift
    for item in "$@"; do
        [ "$item" = "$needle" ] && return 0
    done
    return 1
}

# df_ask VAR "Question" [default]
df_ask() {
    local __var=$1 __question=$2 __default=${3-} __answer
    if [ "$DF_INTERACTIVE" = true ]; then
        if [ -n "$__default" ]; then
            __answer=$(df_read_line "  $__question [Enter = $__default]: ")
        else
            __answer=$(df_read_line "  $__question: ")
        fi
        [ -n "$__answer" ] || __answer=$__default
    else
        __answer=$__default
    fi
    printf -v "$__var" '%s' "$__answer"
}

# df_ask_valid VAR "Question" default regex ["hint"]
df_ask_valid() {
    local __var=$1 __question=$2 __default=$3 __regex=$4 __hint=${5-} __value
    while true; do
        df_ask __value "$__question" "$__default"
        if [[ $__value =~ $__regex ]]; then
            printf -v "$__var" '%s' "$__value"
            return 0
        fi
        [ "$DF_INTERACTIVE" = true ] \
            || df_die "$__question: invalid or missing value '$__value'${__hint:+ (expected: $__hint)}"
        df_warn "Invalid value${__hint:+ — expected: $__hint}"
    done
}

# df_ask_secret VAR "Question" — hidden input, never has a default
df_ask_secret() {
    local __var=$1 __question=$2 __answer=""
    [ "$DF_INTERACTIVE" = true ] || df_die "$__question: cannot prompt in non-interactive mode"
    printf '  %s: ' "$__question" >/dev/tty
    IFS= read -rs __answer </dev/tty || true
    printf '\n' >/dev/tty
    [ -n "$__answer" ] || df_die "$__question: a value is required"
    printf -v "$__var" '%s' "$__answer"
}

# df_choose VAR "Question" default allow_other "value|label"...
# Accepts a menu number, or any literal value when allow_other is true.
df_choose() {
    local __var=$1 __question=$2 __default=$3 __allow_other=$4
    shift 4
    local -a __values=() __labels=()
    local __item __i __answer __default_index="" __hint="number"
    for __item in "$@"; do
        __values+=("${__item%%|*}")
        __labels+=("${__item#*|}")
    done
    for __i in "${!__values[@]}"; do
        [ "${__values[$__i]}" = "$__default" ] && __default_index=$((__i + 1))
    done

    if [ "$DF_INTERACTIVE" != true ]; then
        [ -n "$__default" ] || df_die "$__question: no value configured"
        printf -v "$__var" '%s' "$__default"
        return 0
    fi

    printf '  %s\n' "$__question" >/dev/tty
    for __i in "${!__values[@]}"; do
        printf '    %s%2d)%s %s\n' "$DF_C_BOLD" $((__i + 1)) "$DF_C_RESET" "${__labels[$__i]}" >/dev/tty
    done
    [ "$__allow_other" = true ] && __hint="number or value"

    while true; do
        if [ -n "$__default" ]; then
            __answer=$(df_read_line "  Choose ($__hint) [Enter = ${__default_index:-$__default}]: ")
            [ -n "$__answer" ] || __answer=${__default_index:-$__default}
        else
            __answer=$(df_read_line "  Choose ($__hint): ")
        fi
        if [[ $__answer =~ ^[0-9]+$ ]] && [ "$__answer" -ge 1 ] && [ "$__answer" -le "${#__values[@]}" ]; then
            printf -v "$__var" '%s' "${__values[$((__answer - 1))]}"
            return 0
        fi
        if [ -n "$__answer" ] && { [ "$__allow_other" = true ] || df_in_list "$__answer" "${__values[@]}"; }; then
            printf -v "$__var" '%s' "$__answer"
            return 0
        fi
        df_warn "Invalid choice"
    done
}

# df_confirm "Question" — defaults to yes; never blocks non-interactive runs
df_confirm() {
    local answer
    [ "$DF_ASSUME_YES" = true ] && return 0
    [ "$DF_INTERACTIVE" = true ] || return 0
    answer=$(df_read_line "  $1 [Y/n, Enter = yes]: ")
    case "$answer" in
        ""|[yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

# ─── Platform and paths ─────────────────────────────────────────

df_detect_platform() {
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) DF_OS=windows DF_EXE=".exe" ;;
        Linux)                DF_OS=linux   DF_EXE="" ;;
        Darwin)               DF_OS=darwin  DF_EXE="" ;;
        *) df_die "Unsupported operating system: $(uname -s)" ;;
    esac
    case "$(uname -m)" in
        x86_64|amd64)  DF_ARCH=x86_64 ;;
        aarch64|arm64) DF_ARCH=aarch64 ;;
        *) df_die "Unsupported CPU architecture: $(uname -m)" ;;
    esac
}

# Paths handed to native Windows programs (uv, python, databricks) must not be MSYS-style.
df_native_path() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -m "$1"
    else
        printf '%s\n' "$1"
    fi
}

df_init_paths() {
    DF_STATE_DIR="$DF_TARGET_DIR/.deltaforce"
    DF_BIN_DIR="$DF_STATE_DIR/bin"
    DF_RUNTIME_DIR="$DF_STATE_DIR/runtime"
    DF_CONFIG_FILE="$DF_STATE_DIR/config.yaml"
    DF_DATABRICKS_CFG="$DF_STATE_DIR/.databrickscfg"
    DF_UV="$DF_BIN_DIR/uv$DF_EXE"
    DF_DATABRICKS="$DF_BIN_DIR/databricks$DF_EXE"

    # uv-managed Python, caches and ephemeral environments stay inside the project.
    UV_PYTHON_INSTALL_DIR=$(df_native_path "$DF_RUNTIME_DIR/python")
    UV_CACHE_DIR=$(df_native_path "$DF_RUNTIME_DIR/uv-cache")
    export UV_PYTHON_INSTALL_DIR UV_CACHE_DIR
    export UV_PYTHON_PREFERENCE=only-managed UV_NO_CONFIG=1 PYTHONUTF8=1
    # OneDrive and other cloud-synced folders reject hardlinks (os error 396).
    export UV_LINK_MODE=copy

    # The Databricks CLI profile lives in the project, not in ~/.databrickscfg.
    DATABRICKS_CONFIG_FILE=$(df_native_path "$DF_DATABRICKS_CFG")
    export DATABRICKS_CONFIG_FILE

    # Credentials in the environment would silently override the project profile.
    DF_ENV_CONFLICTS=""
    local name
    for name in DATABRICKS_HOST DATABRICKS_TOKEN DATABRICKS_CLIENT_ID DATABRICKS_CLIENT_SECRET; do
        if [ -n "${!name:-}" ]; then
            DF_ENV_CONFLICTS="${DF_ENV_CONFLICTS:+$DF_ENV_CONFLICTS,}$name"
            unset "$name"
        fi
    done
    export DF_ENV_CONFLICTS
}

# Run the Python helper CLI with the project-local uv and Python.
df_py() {
    "$DF_UV" run --quiet --no-project --python "$DF_PYTHON_VERSION" \
        --with pyyaml --with jsonschema \
        python "$(df_native_path "$DF_FRAMEWORK_DIR/lib/py/dfcli.py")" "$@"
}

df_rel() {
    printf '%s\n' "${1#"$DF_TARGET_DIR"/}"
}
