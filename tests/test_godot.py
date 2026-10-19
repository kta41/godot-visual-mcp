from pathlib import Path

import pytest
from PIL import Image

from godot_visual_mcp.filesystem import GodotProject
from godot_visual_mcp.godot import (
    discover_project,
    find_asset_references,
    find_godot_binary,
    find_unused_assets,
    validate_scene,
    verify_godot_import,
)
from godot_visual_mcp.scenes import add_sprite_to_scene, create_scene, create_sprite_frames


def write_png(path: Path) -> None:
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(path)


def test_project_discovery_and_scene_composition(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text(
        '[application]\nconfig/name="Test Project"\nconfig_version=5\n',
        encoding="utf-8",
    )
    project = GodotProject(tmp_path)
    write_png(tmp_path / "frame.png")
    create_scene(project, "res://main.tscn")
    add_sprite_to_scene(project, "res://main.tscn", "res://frame.png", overwrite=True)
    result = validate_scene(project, "res://main.tscn")
    assert result["valid"] is True
    assert result["nodes"] == 2
    assert discover_project(tmp_path)["name"] == "Test Project"


def test_sprite_frames_and_references(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    for name in ("a.png", "b.png"):
        write_png(tmp_path / name)
    create_sprite_frames(project, "res://frames.tres", ["res://a.png", "res://b.png"])
    create_scene(project, "res://scene.tscn")
    add_sprite_to_scene(project, "res://scene.tscn", "res://a.png", overwrite=True)
    assert find_asset_references(project, "res://a.png") == ["res://frames.tres", "res://scene.tscn"]
    assert "res://b.png" in find_unused_assets(project)


def test_sprite_frames_obey_configured_frame_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_MAX_FRAMES", "1")
    with pytest.raises(ValueError, match="frame limit"):
        create_sprite_frames(
            GodotProject(tmp_path), "res://frames.tres", ["res://a.png", "res://b.png"]
        )


def test_headless_verification_is_explicit_when_godot_missing(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    result = verify_godot_import(tmp_path, godot_binary="/definitely/missing")
    assert result["skipped"] is True
    assert result["code"] == "GODOT_NOT_INSTALLED"


def test_headless_import_runs_when_godot_is_available(tmp_path: Path) -> None:
    godot_binary = find_godot_binary()
    if godot_binary is None:
        pytest.skip("Install Godot 4 or set GODOT_BIN to run the integration test")
    (tmp_path / "project.godot").write_text(
        '[application]\nconfig/name="Headless Test"\nconfig_version=5\n', encoding="utf-8"
    )

    result = verify_godot_import(tmp_path, godot_binary=godot_binary, timeout=60)

    assert result["skipped"] is False
    assert result["ready"] is True, result.get("stderr")
