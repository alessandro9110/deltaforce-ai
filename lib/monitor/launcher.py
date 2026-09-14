"""Start a project's monitor in the background and open it in the system browser — standard library only.

The DeltaForce hook calls `ensure` when a Claude Code session starts (server only) and on the team's first
work in a session (server and browser page); `df monitor` calls `start` and `open_browser` on request.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

APP_ID = "deltaforce-monitor"
SERVER_SCRIPT = Path(__file__).resolve().parent / "server.py"
PORT_BASE = 8700
PORT_SPAN = 100
PORT_ATTEMPTS = 20
START_WAIT_SECONDS = 8.0
REMEMBERED_SESSIONS = 50


def state_file(root: Path) -> Path:
    return root / ".deltaforce" / "runtime" / "monitor.json"


def log_file(root: Path) -> Path:
    return root / ".deltaforce" / "runtime" / "monitor.log"


def same_root(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def preferred_port(root: Path) -> int:
    """The same port for a project every time, so its address can be bookmarked."""
    key = os.path.normcase(os.path.abspath(str(root))).encode("utf-8")
    return PORT_BASE + int.from_bytes(hashlib.sha1(key).digest()[:2], "big") % PORT_SPAN


def candidate_ports(root: Path) -> list[int]:
    first = preferred_port(root)
    return [PORT_BASE + (first - PORT_BASE + step) % PORT_SPAN for step in range(PORT_ATTEMPTS)]


def url_for(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def read_state(root: Path) -> dict[str, Any]:
    try:
        data = json.loads(state_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(root: Path, data: dict[str, Any]) -> None:
    path = state_file(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass


def update_state(root: Path, **changes: Any) -> dict[str, Any]:
    data = read_state(root)
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    write_state(root, data)
    return data


def ping(port: int, root: Path, timeout: float = 0.6) -> bool:
    """True when this project's monitor answers on the port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("app") == APP_ID and same_root(data.get("root", ""), root)


def running_url(root: Path) -> str | None:
    port = read_state(root).get("port")
    return url_for(port) if isinstance(port, int) and ping(port, root) else None


def _python_without_console(python: Path) -> Path:
    if os.name == "nt":
        windowless = python.with_name("pythonw.exe")
        if windowless.exists():
            return windowless
    return python


def _spawn(root: Path, python: Path) -> None:
    log = log_file(root)
    log.parent.mkdir(parents=True, exist_ok=True)
    argv = [str(_python_without_console(python)), str(SERVER_SCRIPT), "--root", str(root)]
    with log.open("ab") as output:
        options: dict[str, Any] = {
            "stdin": subprocess.DEVNULL, "stdout": output, "stderr": subprocess.STDOUT, "cwd": str(root), "close_fds": True,
        }
        if os.name != "nt":
            subprocess.Popen(argv, start_new_session=True, **options)
            return
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            # Outlive the Claude Code process tree when it runs hooks inside a job object.
            subprocess.Popen(argv, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **options)
        except OSError:
            subprocess.Popen(argv, creationflags=flags, **options)


def start(root: Path, python: Path, wait: float = START_WAIT_SECONDS) -> str | None:
    """The monitor's address, starting the server first when it is not running."""
    url = running_url(root)
    if url:
        return url
    _spawn(root, python)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(0.2)
        url = running_url(root)
        if url:
            return url
    return None


def open_browser(url: str) -> bool:
    try:
        return webbrowser.open(url, new=2)
    except webbrowser.Error:
        return False


def ensure(root: Path, python: Path, session_id: str | None = None, open_page: bool = False) -> str | None:
    """Keep the monitor running; open it once per session when the team starts working."""
    data = read_state(root)
    seen = data.get("opened_sessions") if isinstance(data.get("opened_sessions"), list) else []
    port = data.get("port")
    if open_page and session_id in seen and isinstance(port, int):
        return url_for(port)  # fast path: every tool call of a session that already has the page
    url = start(root, python)
    if url and open_page and session_id and session_id not in seen:
        open_browser(url)
        latest = read_state(root).get("opened_sessions")
        latest = latest if isinstance(latest, list) else []
        update_state(root, opened_sessions=[*latest, session_id][-REMEMBERED_SESSIONS:])
    return url
