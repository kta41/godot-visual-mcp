"""Sandboxed generation history and deterministic cache keys."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .filesystem import GodotProject


def cache_key(parameters: dict[str, Any]) -> str:
    """Create a stable key from JSON-compatible generation parameters."""
    encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _history_path(project: GodotProject) -> str:
    return "res://.godot/mcp-history.json"


def read_history(project: GodotProject) -> list[dict[str, Any]]:
    """Read local history; a missing history is an empty history."""
    try:
        payload = json.loads(project.safe_read(_history_path(project)).decode("utf-8"))
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise TypeError("Generation history must be a list of objects")
        return payload
    except FileNotFoundError:
        return []
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Generation history is corrupt") from exc


def record_generation(project: GodotProject, parameters: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Record a generation without storing credentials or raw binary data."""
    key = cache_key(parameters)
    record = {"key": key, "created_at": int(time.time()), "parameters": parameters, "result": result}
    entries = [item for item in read_history(project) if item.get("key") != key]
    entries.append(record)
    project.safe_write(_history_path(project), (json.dumps(entries, indent=2) + "\n").encode(), overwrite=True)
    return record


def find_cached_generation(project: GodotProject, parameters: dict[str, Any]) -> dict[str, Any] | None:
    """Return a cached result only when its output still exists."""
    key = cache_key(parameters)
    for record in reversed(read_history(project)):
        if record.get("key") == key:
            result = record.get("result")
            if isinstance(result, dict) and isinstance(result.get("path"), str):
                try:
                    project.safe_read(result["path"])
                except FileNotFoundError:
                    return None
                return record
    return None
