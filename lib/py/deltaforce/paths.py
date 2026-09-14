"""Where DeltaForce keeps its files inside a target repository."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

IS_WINDOWS = os.name == "nt"
EXE = ".exe" if IS_WINDOWS else ""

FRAMEWORK_DIR = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    # ─── .deltaforce ───────────────────────────────────────────

    @property
    def state(self) -> Path:
        return self.root / ".deltaforce"

    @property
    def config(self) -> Path:
        return self.state / "config.yaml"

    @property
    def conventions(self) -> Path:
        return self.state / "conventions.yaml"

    @property
    def state_yaml(self) -> Path:
        return self.state / "state.yaml"

    @property
    def backlog(self) -> Path:
        return self.state / "backlog"

    @property
    def events(self) -> Path:
        return self.state / "events.jsonl"

    @property
    def status(self) -> Path:
        return self.state / "status.json"

    @property
    def databricks_cfg(self) -> Path:
        return self.state / ".databrickscfg"

    @property
    def bin(self) -> Path:
        return self.state / "bin"

    @property
    def uv(self) -> Path:
        return self.bin / f"uv{EXE}"

    @property
    def databricks_cli(self) -> Path:
        return self.bin / f"databricks{EXE}"

    @property
    def df_wrapper(self) -> Path:
        return self.bin / "df"

    @property
    def runtime(self) -> Path:
        return self.state / "runtime"

    @property
    def venv_python(self) -> Path:
        venv = self.runtime / "venv"
        return venv / "Scripts" / "python.exe" if IS_WINDOWS else venv / "bin" / "python"

    @property
    def mcp_entry(self) -> Path:
        return self.runtime / "ai-dev-kit" / "databricks-mcp-server" / "run_server.py"

    # ─── Claude Code ───────────────────────────────────────────

    @property
    def agents(self) -> Path:
        return self.root / ".claude" / "agents"

    @property
    def skills(self) -> Path:
        return self.root / ".claude" / "skills"

    @property
    def claude_settings(self) -> Path:
        return self.root / ".claude" / "settings.json"

    @property
    def claude_settings_local(self) -> Path:
        return self.root / ".claude" / "settings.local.json"

    @property
    def mcp_json(self) -> Path:
        return self.root / ".mcp.json"

    @property
    def claude_md(self) -> Path:
        return self.root / "CLAUDE.md"

    # ─── repository ────────────────────────────────────────────

    @property
    def gitignore(self) -> Path:
        return self.root / ".gitignore"

    @property
    def bundle(self) -> Path:
        return self.root / "databricks.yml"

    @property
    def bundle_variables(self) -> Path:
        return self.root / "resources" / "deltaforce.variables.yml"
