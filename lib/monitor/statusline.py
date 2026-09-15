"""DeltaForce status line for Claude Code — standard library only, no model calls.

Claude Code sources `statusline.sh`, which asks the running monitor for the line (`/api/statusline`) with bash
builtins only. This module formats that line for the server and starts the monitor when it is not running:

    python statusline.py --root <project> --start   # start the monitor in the background, print nothing
    python statusline.py --root <project>           # print the line (for shells without /dev/tcp)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitor import launcher  # noqa: E402

DIM, ORANGE, RESET = "\x1b[2m", "\x1b[38;5;208m", "\x1b[0m"


def link(url: str, text: str) -> str:
    """An OSC 8 terminal hyperlink: Ctrl+click opens the URL."""
    return f"\x1b]8;;{url}\a{text}\x1b]8;;\a"


COMMANDS = "/df-status where we are · /df-approve approve · /df-changes ask for changes · /df-conventions project rules · /clear fresh session"


def command_hint(status: dict[str, Any] | None) -> str:
    """The PO commands, led by the one to use now when something waits for the PO."""
    status = status or {}
    review = status.get("review") or []
    if status and not status.get("started"):
        lead = "Start: /df-kickoff <what to build>"
    elif status.get("phase_key") == "awaiting_g1":
        lead = "Your turn: /df-approve or /df-changes <what to change>"
    elif review:
        lead = f"Your turn: /df-approve {review[0]} or /df-changes {review[0]} <what to change>"
    else:
        return f"{DIM}{COMMANDS}{RESET}"
    return f"{ORANGE}{lead}{RESET}{DIM} · /df-status · /df-conventions · /clear{RESET}"


def format_line(url: str, status: dict[str, Any] | None) -> str:
    """Two status line rows: the project and the monitor link, then the commands."""
    parts = [f"{DIM}DeltaForce{RESET}"]
    if status:
        parts.append(str(status.get("phase", "")))
        if status.get("features"):
            parts.append(f"{status.get('done', 0)}/{status['features']} features done")
        if status.get("waiting"):
            parts.append(f"{ORANGE}{status['waiting']} waiting for you{RESET}")
    parts.append(link(url, f"monitor {url}"))
    return " · ".join(part for part in parts if part) + "\n" + command_hint(status)


def fetch_status(url: str, timeout: float = 0.8) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"{url}api/status", timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def render(root: Path, python: Path, autostart: bool = True) -> str:
    url = launcher.start_in_background(root, python) if autostart else launcher.running_url(root)
    if not url:
        return f"{DIM}DeltaForce · monitor {'starting…' if autostart else 'off'}{RESET}\n{command_hint(None)}"
    return format_line(url, fetch_status(url))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeltaForce status line")
    parser.add_argument("--root", required=True, help="project repository root")
    parser.add_argument("--start", action="store_true", help="only start the monitor in the background")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    autostart = os.environ.get("DELTAFORCE_MONITOR", "").strip().lower() not in {"off", "0", "false", "no"}
    if args.start:
        if autostart:
            launcher.start_in_background(root, Path(sys.executable))
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.stdin.read()  # Claude Code sends the session as JSON; the line does not need it
    except (OSError, ValueError):
        pass
    try:
        print(render(root, Path(sys.executable), autostart))
    except Exception:  # never break the status line
        print("DeltaForce")
    return 0


if __name__ == "__main__":
    sys.exit(main())
