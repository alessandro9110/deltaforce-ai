#!/usr/bin/env bash
#
# DeltaForce AI installer.
#
# Installs everything DeltaForce needs *inside* a target project repository —
# never globally: project-local uv and Databricks CLI, a uv-managed Python, the
# AI Dev Kit MCP server, Databricks agent skills, the project configuration and
# the Claude Code files generated from it. It finishes with a doctor run that
# gates /df-kickoff.
#
# Run from the root of the target repository, in the IDE terminal (see README):
#   bash .deltaforce/framework/install.sh [options]
# When the script runs without its lib/ folder (first install) it downloads
# DeltaForce AI into .deltaforce/framework and continues from there; when it
# runs from .deltaforce/framework it updates that copy first (DF_REF, default main).
#
# Options:
#   --target DIR        Target repository (default: current directory)
#   --advanced          Also ask team options (roles, models, nesting depth, AI Dev Kit ref)
#   --non-interactive   Never prompt: use the existing config or DF_* environment variables
#   -y, --yes           Skip confirmations
#   --dry-run           Ask the first questions, print the plan and exit without changes
#   --doctor            Only run the post-install checks
#   -h, --help          Show this help
#

set -euo pipefail

DF_REPO_URL=${DF_REPO_URL:-https://github.com/alessandro9110/deltaforce-ai.git}
DF_REF=${DF_REF:-main}
DF_FRAMEWORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" && pwd)"

# ─── Bootstrap: keep the framework itself inside the project ───
df_wants_bootstrap() {
    [ -z "${DF_BOOTSTRAPPED:-}" ] || return 1
    [ -f "$DF_FRAMEWORK_DIR/lib/common.sh" ] || return 0
    case " $* " in *" --doctor "*|*" -h "*|*" --help "*) return 1 ;; esac
    [ "$(basename "$(dirname "$DF_FRAMEWORK_DIR")")/$(basename "$DF_FRAMEWORK_DIR")" = .deltaforce/framework ]
}

df_bootstrap() {
    local framework target arg prev=""
    if [ -f "$DF_FRAMEWORK_DIR/lib/common.sh" ]; then
        framework=$DF_FRAMEWORK_DIR
    else
        target=$PWD
        for arg in "$@"; do
            [ "$prev" = --target ] && target=$arg
            prev=$arg
        done
        framework="$target/.deltaforce/framework"
    fi
    command -v git >/dev/null 2>&1 || { echo "DeltaForce AI needs git (Git for Windows)." >&2; exit 1; }

    if [ -d "$framework/.git" ]; then
        printf 'Updating DeltaForce AI (%s)...\n' "$DF_REF"
        git -C "$framework" fetch -q --depth 1 origin "$DF_REF" \
            && git -C "$framework" -c advice.detachedHead=false checkout -q --detach FETCH_HEAD \
            || printf 'Could not update %s — continuing with the current version.\n' "$framework" >&2
    else
        printf 'Downloading DeltaForce AI (%s)...\n' "$DF_REF"
        mkdir -p "$(dirname "$framework")"
        git -c core.longpaths=true -c advice.detachedHead=false \
            clone -q --depth 1 --branch "$DF_REF" "$DF_REPO_URL" "$framework" \
            || { printf 'Could not download %s\n' "$DF_REPO_URL" >&2; exit 1; }
    fi
    DF_BOOTSTRAPPED=1 exec bash "$framework/install.sh" "$@"
}

if df_wants_bootstrap "$@"; then
    df_bootstrap "$@"
fi

# shellcheck source=lib/data/versions.env
source "$DF_FRAMEWORK_DIR/lib/data/versions.env"
# shellcheck source=lib/common.sh
source "$DF_FRAMEWORK_DIR/lib/common.sh"
# shellcheck source=lib/tools.sh
source "$DF_FRAMEWORK_DIR/lib/tools.sh"
# shellcheck source=lib/questions.sh
source "$DF_FRAMEWORK_DIR/lib/questions.sh"
# shellcheck source=lib/databricks.sh
source "$DF_FRAMEWORK_DIR/lib/databricks.sh"
# shellcheck source=lib/runtime.sh
source "$DF_FRAMEWORK_DIR/lib/runtime.sh"
# shellcheck source=lib/project.sh
source "$DF_FRAMEWORK_DIR/lib/project.sh"

usage() {
    sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

parse_args() {
    DF_TARGET_DIR="$PWD"
    DF_ADVANCED=false
    DF_DRY_RUN=false
    DF_DOCTOR_ONLY=false
    while [ $# -gt 0 ]; do
        case $1 in
            --target)          DF_TARGET_DIR="${2:?--target requires a directory}"; shift 2 ;;
            --advanced)        DF_ADVANCED=true; shift ;;
            --non-interactive) DF_INTERACTIVE=false; shift ;;
            -y|--yes)          DF_ASSUME_YES=true; shift ;;
            --dry-run)         DF_DRY_RUN=true; shift ;;
            --doctor)          DF_DOCTOR_ONLY=true; shift ;;
            -h|--help)         usage; exit 0 ;;
            *)                 df_die "Unknown option: $1 (use --help)" ;;
        esac
    done
    [ -d "$DF_TARGET_DIR" ] || df_die "Target directory not found: $DF_TARGET_DIR"
    DF_TARGET_DIR="$(cd "$DF_TARGET_DIR" && pwd)"
    df_has_tty || DF_INTERACTIVE=false
}

main() {
    parse_args "$@"
    df_detect_platform
    df_init_paths

    printf '\n%sDeltaForce AI installer%s\n' "$DF_C_BOLD" "$DF_C_RESET"

    if [ "$DF_DOCTOR_ONLY" = true ]; then
        [ -x "$DF_UV" ] || df_die "DeltaForce is not installed in $DF_TARGET_DIR — run the installer first"
        df_step "Checks"
        df_run_doctor
        return
    fi

    df_step "Preflight"
    df_preflight
    df_load_existing_config

    if [ "$DF_INTERACTIVE" = true ]; then
        df_msg ""
        df_msg "Answer each question and press Enter. To accept the value shown as [Enter = ...],"
        df_msg "just press Enter. Ctrl+C stops the installer at any time without breaking anything."
    fi

    df_step "Project"
    df_ask_project

    df_step "Databricks workspace"
    df_ask_workspace

    df_step "Production workspace (optional, read-only)"
    df_ask_prod

    df_step "Plan"
    df_print_plan
    if [ "$DF_DRY_RUN" = true ]; then
        df_ok "Dry run — nothing was changed"
        return
    fi
    df_confirm "Proceed?" || { df_msg "Cancelled — nothing was changed."; return; }

    df_step "Git"
    df_ensure_dev_branch

    df_step "Project-local tools"
    df_install_tools

    df_step "Authentication"
    df_authenticate

    df_step "Dev target"
    df_ask_target
    df_ask_prod_target

    df_step "Team"
    df_ask_team

    df_step "Configuration"
    df_print_summary
    df_confirm "Write this configuration?" || { df_msg "Cancelled before writing the configuration."; return; }
    df_write_config

    df_step "AI Dev Kit MCP server"
    df_install_ai_dev_kit

    df_step "Databricks skills"
    df_install_skills

    df_step "Project files"
    df_generate

    df_step "Checks"
    df_run_doctor
}

main "$@"
