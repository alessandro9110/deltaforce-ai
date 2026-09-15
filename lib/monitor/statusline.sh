# shellcheck shell=bash
# DeltaForce status line for Claude Code: the monitor's link, the phase and what waits for the PO.
#
#   . statusline.sh <project root> <python>
#
# Claude Code sources this file in its own shell on every refresh. It uses bash builtins only — it reads the
# monitor's port and asks the monitor for the line over /dev/tcp — because on Windows every extra process
# costs a second or more. When the monitor is not running it starts it in the background. No model calls.

DF_STATUSLINE_COMMANDS='/df-status where we are · /df-approve approve · /df-changes ask for changes · /df-conventions project rules · /clear fresh session'

df_statusline() {
    local root=$1 python=$2 state="" port="" reply="" line="" printed=false
    read -r -d '' state < "$root/.deltaforce/runtime/monitor.json" 2>/dev/null
    [[ $state =~ \"port\":\ ([0-9]+) ]] && port=${BASH_REMATCH[1]}

    if [ -n "$port" ] && { exec 3<>"/dev/tcp/127.0.0.1/$port"; } 2>/dev/null; then
        printf 'GET /api/statusline HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n' >&3
        IFS= read -r -t 3 reply <&3
        if [[ $reply == HTTP/1.?" 200"* ]]; then
            while IFS= read -r -t 3 reply <&3; do
                [ -z "${reply%$'\r'}" ] && break
            done
            # The body is the status line: one row per line (project and link, then the commands).
            while IFS= read -r -t 3 line <&3 || [ -n "$line" ]; do
                printf '%s\n' "$line"
                printed=true
                line=""
            done
        fi
        exec 3<&-
    fi
    $printed && return 0

    case "${DELTAFORCE_MONITOR:-}" in
        off | OFF | 0 | false | no)
            printf '\033[2mDeltaForce · monitor off\033[0m\n\033[2m%s\033[0m\n' "$DF_STATUSLINE_COMMANDS"
            return 0
            ;;
    esac
    "$python" "${BASH_SOURCE[0]%/*}/statusline.py" --root "$root" --start </dev/null >/dev/null 2>&1 &
    printf '\033[2mDeltaForce · monitor starting…\033[0m\n\033[2m%s\033[0m\n' "$DF_STATUSLINE_COMMANDS"
}

df_statusline "$@"
