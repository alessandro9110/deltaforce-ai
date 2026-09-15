"""Token use of the team, read from the Claude Code session files on this computer — no model calls.

Claude Code keeps one transcript per session in ~/.claude/projects/<project path>/<session>.jsonl and one per
subagent in <session>/subagents/agent-*.jsonl, with a .meta.json naming the agent type. Every assistant message
carries its token usage. This module adds them up per role, feature, phase, session and model. Only counts leave
this module: prompts and answers are never returned.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

import yaml

TOKEN_FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
# Relative weight of each kind of token against a plain input token, as Anthropic prices them.
WEIGHTS = {"input_tokens": 1.0, "cache_creation_input_tokens": 1.25, "cache_read_input_tokens": 0.1, "output_tokens": 5.0}
PRICE_KEYS = {"input_tokens": "input", "cache_creation_input_tokens": "cache_write", "cache_read_input_tokens": "cache_read", "output_tokens": "output"}
FEATURE_REF = re.compile(r"\bF-(\d{3,})\b")
TASK_REF = re.compile(r"\bT-(\d{3,})\.\d+\b")
MAIN_ROLE = "pm"


def claude_projects_dir() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "projects"


def transcripts_dir(root: Path) -> Path:
    """Claude Code names a project's folder after its path, every character but letters and digits turned into '-'."""
    return claude_projects_dir() / re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))


class _Transcript:
    __slots__ = ("offset", "messages", "prompt", "mtime")

    def __init__(self) -> None:
        self.offset = 0
        self.messages: dict[str, tuple[str, str, dict[str, int]]] = {}
        self.prompt: str | None = None
        self.mtime = 0.0


class TranscriptCache:
    """Reads each transcript once and then only what was appended: the active session grows while the team works."""

    def __init__(self) -> None:
        self._files: dict[Path, _Transcript] = {}
        self._lock = threading.Lock()

    def read(self, path: Path) -> _Transcript:
        with self._lock:
            state = self._files.setdefault(path, _Transcript())
            try:
                stat = path.stat()
            except OSError:
                return state
            if stat.st_size < state.offset:  # rewritten: start again
                state = self._files[path] = _Transcript()
            if stat.st_size == state.offset:
                return state
            with path.open("rb") as handle:
                handle.seek(state.offset)
                chunk = handle.read()
            end = chunk.rfind(b"\n")
            if end == -1:
                return state  # an unfinished line: wait for the rest
            state.offset += end + 1
            state.mtime = stat.st_mtime
            for line in chunk[:end].split(b"\n"):
                self._record(state, line)
            return state

    @staticmethod
    def _record(state: _Transcript, line: bytes) -> None:
        try:
            record = json.loads(line)
        except ValueError:
            return
        if not isinstance(record, dict):
            return
        message = record.get("message") if isinstance(record.get("message"), dict) else {}
        if record.get("type") == "user" and state.prompt is None and not record.get("isMeta"):
            content = message.get("content")
            if isinstance(content, str):
                state.prompt = content[:4000]
            elif isinstance(content, list):
                texts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
                if texts:
                    state.prompt = " ".join(texts)[:4000]
        usage = message.get("usage")
        if record.get("type") == "assistant" and isinstance(usage, dict):
            key = str(message.get("id") or record.get("uuid") or len(state.messages))
            # A message is written once per content block with the same id: the last line holds the final usage.
            state.messages[key] = (
                str(record.get("timestamp") or ""),
                str(message.get("model") or "unknown"),
                {field: int(usage.get(field) or 0) for field in TOKEN_FIELDS},
            )


CACHE = TranscriptCache()


def weighted(tokens: dict[str, int]) -> float:
    return sum(WEIGHTS[field] * tokens.get(field, 0) for field in TOKEN_FIELDS)


def load_pricing(root: Path) -> dict[str, Any] | None:
    """Optional prices per million tokens in .deltaforce/pricing.yaml; without it the view shows tokens only."""
    path = root / ".deltaforce" / "pricing.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        return None
    return {"currency": str(data.get("currency") or "USD"), "models": data["models"]}


def _price(pricing: dict[str, Any] | None, model: str, tokens: dict[str, int]) -> float | None:
    if not pricing:
        return None
    matches = [name for name in pricing["models"] if model.startswith(str(name))]
    if not matches:
        return None
    prices = pricing["models"][max(matches, key=len)] or {}
    try:
        return sum(float(prices.get(PRICE_KEYS[field], 0)) * tokens.get(field, 0) for field in TOKEN_FIELDS) / 1_000_000
    except (TypeError, ValueError):
        return None


def _bucket() -> dict[str, Any]:
    return {**{field: 0 for field in TOKEN_FIELDS}, "calls": 0, "runs": 0, "weighted": 0.0, "cost": None}


def _add(bucket: dict[str, Any], tokens: dict[str, int], cost: float | None) -> None:
    for field in TOKEN_FIELDS:
        bucket[field] += tokens[field]
    bucket["calls"] += 1
    bucket["weighted"] += weighted(tokens)
    if cost is not None:
        bucket["cost"] = (bucket["cost"] or 0.0) + cost


def _feature_of(text: str) -> str | None:
    if feature := FEATURE_REF.search(text):
        return f"F-{feature.group(1)}"
    if task := TASK_REF.search(text):
        return f"F-{task.group(1)}"
    return None


def usage(root: Path, phases: list[tuple[str, str]], cache: TranscriptCache = CACHE) -> dict[str, Any]:
    """Token use per role, feature, phase, model and session. `phases` are (start time, phase) pairs in order."""
    folder = transcripts_dir(root)
    if not folder.is_dir():
        return {"available": False, "folder": str(folder)}
    pricing = load_pricing(root)

    def phase_at(timestamp: str) -> str:
        current = "before kickoff"
        for start, phase in phases:
            if timestamp >= start:
                current = phase
        return current

    by_role: dict[str, dict[str, Any]] = {}
    by_feature: dict[str, dict[str, Any]] = {}
    by_phase: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    total = _bucket()
    sessions = []

    for session_file in sorted(folder.glob("*.jsonl")):
        runs: list[tuple[str, _Transcript, str | None]] = [(MAIN_ROLE, cache.read(session_file), None)]
        subagents = folder / session_file.stem / "subagents"
        for agent_file in sorted(subagents.glob("agent-*.jsonl")) if subagents.is_dir() else []:
            try:
                meta = json.loads(agent_file.with_suffix(".meta.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
            state = cache.read(agent_file)
            feature = _feature_of(f"{meta.get('description', '')}\n{state.prompt or ''}")
            runs.append((str(meta.get("agentType") or "unknown"), state, feature))

        session = {**_bucket(), "id": session_file.stem[:8], "start": None, "end": None, "agents": 0, "pm_peak_context": 0}
        for role, state, feature in runs:
            if not state.messages:
                continue
            if role != MAIN_ROLE:
                session["agents"] += 1
            for bucket in (by_role.setdefault(role, _bucket()), by_feature.setdefault(feature or ("coordination" if role == MAIN_ROLE else "unlinked"), _bucket())):
                bucket["runs"] += 1
            for timestamp, model, tokens in state.messages.values():
                cost = _price(pricing, model, tokens)
                for bucket in (
                    total, session, by_role[role],
                    by_feature[feature or ("coordination" if role == MAIN_ROLE else "unlinked")],
                    by_phase.setdefault(phase_at(timestamp), _bucket()),
                    by_model.setdefault(model, _bucket()),
                ):
                    _add(bucket, tokens, cost)
                if timestamp:
                    session["start"] = min(session["start"] or timestamp, timestamp)
                    session["end"] = max(session["end"] or timestamp, timestamp)
                if role == MAIN_ROLE:
                    context = tokens["input_tokens"] + tokens["cache_creation_input_tokens"] + tokens["cache_read_input_tokens"]
                    session["pm_peak_context"] = max(session["pm_peak_context"], context)
        if session["calls"]:
            sessions.append(session)

    def rows(groups: dict[str, dict[str, Any]], key: str) -> list[dict[str, Any]]:
        return sorted(({key: name, **values} for name, values in groups.items()), key=lambda row: -row["weighted"])

    sessions.sort(key=lambda item: str(item["start"] or ""))
    return {
        "available": True,
        "currency": pricing["currency"] if pricing else None,
        "total": total,
        "sessions": sessions,
        "roles": rows(by_role, "role"),
        "features": rows(by_feature, "feature"),
        "phases": rows(by_phase, "phase"),
        "models": rows(by_model, "model"),
    }
