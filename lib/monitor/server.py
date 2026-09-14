"""DeltaForce monitor server: local, read-only, bound to 127.0.0.1.

    python server.py --root <project> [--idle-minutes 30]

Serves the page in static/ and a JSON snapshot of the project's .deltaforce folder. It stops by itself when
no Claude Code session has been active for a while; the DeltaForce hook starts it again when the team works.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import socket
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitor import launcher, model  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}
CHECK_SECONDS = 30
NO_ACTIVITY_LIMIT = dt.timedelta(hours=4)


class MonitorServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second process bind the same port; use exclusive binding instead.
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_handler(root: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "DeltaForceMonitor"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - keep the log quiet
            pass

        def _send(self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, data: Any, status: int = HTTPStatus.OK) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _host_allowed(self) -> bool:
            # Only the local addresses: a web page on another site cannot read the project through DNS tricks.
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            return host in {"127.0.0.1", "localhost"}

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            if not self._host_allowed():
                self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain; charset=utf-8")
                return
            url = urlparse(self.path)
            if url.path == "/api/ping":
                self._json({"app": launcher.APP_ID, "root": str(root), "pid": os.getpid()})
            elif url.path == "/api/snapshot":
                body = json.dumps(model.snapshot(root), ensure_ascii=False).encode("utf-8")
                etag = '"' + hashlib.sha1(body).hexdigest()[:20] + '"'
                if self.headers.get("If-None-Match") == etag:
                    self.send_response(HTTPStatus.NOT_MODIFIED)
                    self.send_header("ETag", etag)
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                else:
                    self._send(HTTPStatus.OK, body, "application/json; charset=utf-8", {"ETag": etag})
            elif url.path == "/api/doc":
                document = model.read_document(root, (parse_qs(url.query).get("path") or [""])[0])
                if document:
                    self._json(document)
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            elif url.path in {"/", "/index.html"}:
                self._static("index.html")
            elif url.path.startswith("/static/"):
                self._static(url.path[len("/static/") :])
            else:
                self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")

        def _static(self, name: str) -> None:
            path = (STATIC_DIR / name).resolve()
            if path.parent != STATIC_DIR.resolve() or not path.is_file() or path.suffix not in CONTENT_TYPES:
                self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")
                return
            self._send(HTTPStatus.OK, path.read_bytes(), CONTENT_TYPES[path.suffix])

    return Handler


def bind(root: Path) -> MonitorServer | None:
    """A server on the project's port, or None when this project's monitor already runs."""
    handler = make_handler(root)
    for port in launcher.candidate_ports(root):
        if launcher.ping(port, root):
            return None
        try:
            return MonitorServer(("127.0.0.1", port), handler)
        except OSError:
            time.sleep(0.3)
            if launcher.ping(port, root):  # another start won the race for the same project
                return None
    raise OSError("no free port for the DeltaForce monitor")


def should_stop(root: Path, started: dt.datetime, idle: dt.timedelta, now: dt.datetime | None = None) -> bool:
    """Stop when no session is open and nothing happened for `idle`, or nothing happened for hours."""
    now = now or dt.datetime.now(dt.timezone.utc)
    activity_file = root / ".deltaforce" / "runtime" / "activity.jsonl"
    try:
        last_change = dt.datetime.fromtimestamp(activity_file.stat().st_mtime, dt.timezone.utc)
    except OSError:
        last_change = started
    quiet_for = now - max(last_change, started)
    if quiet_for > NO_ACTIVITY_LIMIT:
        return True
    if quiet_for <= idle:
        return False
    return not model.snapshot(root, now)["session"]["open"]


def watch(server: MonitorServer, root: Path, started: dt.datetime, idle: dt.timedelta) -> None:
    while True:
        time.sleep(CHECK_SECONDS)
        try:
            if should_stop(root, started, idle):
                server.shutdown()
                return
        except Exception as exc:  # keep serving if a check fails
            print(f"monitor check failed: {exc}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeltaForce monitor server")
    parser.add_argument("--root", required=True, help="project repository root")
    parser.add_argument("--idle-minutes", type=float, default=30.0)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    server = bind(root)
    if server is None:
        return 0
    port = server.server_address[1]
    started = dt.datetime.now(dt.timezone.utc)
    launcher.update_state(root, port=port, pid=os.getpid(), url=launcher.url_for(port), started=started.isoformat(timespec="seconds"))
    print(f"{started.isoformat(timespec='seconds')} DeltaForce monitor on {launcher.url_for(port)} for {root}", flush=True)

    threading.Thread(target=watch, args=(server, root, started, dt.timedelta(minutes=args.idle_minutes)), daemon=True).start()
    try:
        server.serve_forever(poll_interval=1.0)
    finally:
        server.server_close()
        if launcher.read_state(root).get("pid") == os.getpid():
            launcher.update_state(root, port=None, pid=None, url=None, started=None)
        print(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} DeltaForce monitor stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
