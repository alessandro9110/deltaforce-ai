"""Parse Databricks CLI JSON output and write project-local CLI profiles."""

from __future__ import annotations

import configparser
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _clean(text: str) -> str:
    return " ".join(str(text).replace("|", "/").split())


COMMENT_MAX = 60


def _with_comment(item: dict[str, Any]) -> str:
    comment = " ".join(str(item.get("comment") or "").split())
    if not comment:
        return item["name"]
    if len(comment) > COMMENT_MAX:
        comment = comment[: COMMENT_MAX - 1].rstrip() + "…"
    return f"{item['name']} — {comment}"


# kind -> (value field, label builder, wrapper keys the CLI may nest the list under)
LISTINGS: dict[str, tuple[str, Callable[[dict[str, Any]], str], tuple[str, ...]]] = {
    "warehouses": ("id", lambda i: f"{i.get('name', '?')} ({i['id']}, {i.get('state', 'UNKNOWN')})", ("warehouses",)),
    "clusters": (
        "cluster_id",
        lambda i: f"{i.get('cluster_name', '?')} ({i['cluster_id']}, {i.get('state', 'UNKNOWN')})",
        ("clusters",),
    ),
    "catalogs": ("name", _with_comment, ("catalogs",)),
    "user": ("userName", lambda i: i.get("displayName", i["userName"]), ()),
}


def parse_listing(kind: str, raw: str, limit: int = 60) -> list[tuple[str, str]]:
    key, label, wrappers = LISTINGS[kind]
    raw = raw.strip()
    if not raw:
        return []
    data: Any = json.loads(raw)
    if isinstance(data, dict):
        nested = next((data[w] for w in wrappers if isinstance(data.get(w), list)), None)
        data = nested if nested is not None else [data]
    items = [item for item in data if isinstance(item, dict) and item.get(key)]
    if kind == "catalogs":
        items.sort(key=lambda i: i["name"])
    return [(_clean(item[key]), _clean(label(item))) for item in items[:limit]]


def write_profile(path: Path, profile: str, values: dict[str, str]) -> None:
    """Create or replace one profile section, keeping the others."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # keep key case as the CLI writes it
    if path.exists():
        parser.read(path, encoding="utf-8")
    if parser.has_section(profile):
        parser.remove_section(profile)
    parser.add_section(profile)
    for key, value in values.items():
        parser.set(profile, key, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        parser.write(f)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
