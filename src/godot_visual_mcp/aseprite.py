"""Aseprite JSON metadata and animation import helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .filesystem import GodotProject


def inspect_aseprite_json(project: GodotProject, source: str) -> dict[str, Any]:
    """Inspect a `.json` export produced by Aseprite."""
    if Path(source).suffix.lower() != ".json":
        raise ValueError("Aseprite metadata must be a .json file")
    try:
        payload = json.loads(project.safe_read(source).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid Aseprite JSON: {source}") from exc
    frames = payload.get("frames")
    if isinstance(frames, dict):
        frame_names = list(frames)
    elif isinstance(frames, list):
        frame_names = [str(item.get("filename", index)) for index, item in enumerate(frames)]
    else:
        raise TypeError("Aseprite JSON has no frames")
    tags = payload.get("meta", {}).get("frameTags", [])
    if not isinstance(tags, list):
        raise TypeError("Aseprite frameTags must be a list")
    animations = [
        {"name": tag.get("name"), "from": tag.get("from"), "to": tag.get("to"), "direction": tag.get("direction", "forward")}
        for tag in tags
        if isinstance(tag, dict) and isinstance(tag.get("name"), str)
    ]
    return {"path": project.validate_asset_path(source), "frames": len(frame_names), "frame_names": frame_names, "animations": animations}


def create_animation_manifest(project: GodotProject, source: str, output: str, *, overwrite: bool = False) -> dict[str, Any]:
    """Convert Aseprite frame tags into a stable JSON manifest for later import."""
    metadata = inspect_aseprite_json(project, source)
    content = json.dumps({"source": metadata["path"], "animations": metadata["animations"]}, indent=2) + "\n"
    written = project.safe_write(output, content.encode("utf-8"), overwrite=overwrite)
    return {"path": written, "animations": metadata["animations"], "frames": metadata["frames"]}
