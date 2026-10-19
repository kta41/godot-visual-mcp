import json
from pathlib import Path

import pytest

from godot_visual_mcp.aseprite import create_animation_manifest, inspect_aseprite_json
from godot_visual_mcp.filesystem import GodotProject
from godot_visual_mcp.history import find_cached_generation, record_generation


def test_aseprite_tags_are_preserved(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    payload = {
        "frames": {"idle 0": {}, "idle 1": {}},
        "meta": {"frameTags": [{"name": "idle", "from": 0, "to": 1, "direction": "forward"}]},
    }
    project.safe_write("res://hero.json", json.dumps(payload).encode())
    metadata = inspect_aseprite_json(project, "res://hero.json")
    manifest = create_animation_manifest(project, "res://hero.json", "res://hero.manifest.json")
    assert metadata["frames"] == 2
    assert manifest["animations"][0]["name"] == "idle"


def test_aseprite_inspection_obeys_frame_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_MAX_FRAMES", "1")
    project = GodotProject(tmp_path)
    project.safe_write(
        "res://many.json",
        json.dumps({"frames": {"frame-1": {}, "frame-2": {}}}).encode(),
    )
    with pytest.raises(ValueError, match="frame limit"):
        inspect_aseprite_json(project, "res://many.json")


def test_aseprite_inspection_obeys_input_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_MAX_INPUT_BYTES", "8")
    project = GodotProject(tmp_path)
    project.safe_write("res://export.json", b'{"frames": []}')
    with pytest.raises(ValueError, match="byte limit"):
        inspect_aseprite_json(project, "res://export.json")


def test_generation_history_cache_only_returns_existing_output(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    project.safe_write("res://generated.png", b"image")
    parameters = {"prompt": "hero", "seed": 1}
    record_generation(project, parameters, {"path": "res://generated.png"})
    cached = find_cached_generation(project, parameters)
    assert cached is not None
    assert cached["result"]["path"] == "res://generated.png"
