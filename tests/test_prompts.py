"""The installer's interactive prompts, run through bash as the installer runs them.

`df_choose` reads every answer with `df_read_line` inside a command substitution — a subshell — so the answers of a
case live in a file the replacement pops from, and running out of answers fails instead of looping forever.
"""

import subprocess

from conftest import ROOT

COMMON = (ROOT / "lib" / "common.sh").as_posix()


def choose(answers: list[str], default: str, allow_other: str, *items: str) -> str:
    """Run df_choose with `answers` typed one after the other, and return the value it set."""
    arguments = " ".join(f'"{item}"' for item in items)
    typed = "\\n".join(answers)
    script = f"""
        . "{COMMON}"
        DF_INTERACTIVE=true
        TYPED=$(mktemp); printf '{typed}\\n' > "$TYPED"
        df_read_line() {{
            [ -s "$TYPED" ] || {{ printf 'OUT OF ANSWERS\\n'; kill -TERM $$; }}
            head -n 1 "$TYPED"
            tail -n +2 "$TYPED" > "$TYPED.rest" && mv "$TYPED.rest" "$TYPED"
        }}
        exec 2>/dev/null                      # the prompt and any warning go to /dev/tty, not to us
        df_choose PICKED "Question" "{default}" {allow_other} {arguments}
        printf 'PICKED=%s\\n' "$PICKED"
    """
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    picked = [line for line in result.stdout.splitlines() if line.startswith("PICKED=")]
    assert picked, f"no choice made: {result.stdout!r}"
    return picked[0].split("=", 1)[1]


def test_a_list_with_one_item_accepts_enter():
    # The SQL warehouse question of a fresh install: one warehouse, no default — Enter used to be "Invalid choice".
    assert choose([""], "", "false", "wh-1|Serverless Starter Warehouse") == "wh-1"


def test_a_list_with_several_items_and_no_default_still_needs_an_answer():
    assert choose(["", "2"], "", "false", "a|First", "b|Second") == "b"


def test_the_configured_default_wins_when_there_is_one():
    assert choose([""], "b", "false", "a|First", "b|Second") == "b"


def test_a_value_outside_the_list_is_taken_only_when_allowed():
    assert choose(["my-own"], "", "true", "a|First", "b|Second") == "my-own"
    assert choose(["my-own", "1"], "", "false", "a|First", "b|Second") == "a"
