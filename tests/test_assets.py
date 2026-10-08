from pathlib import Path

from PIL import Image

from godot_visual_mcp.assets import create_placeholder, inspect_asset, validate_asset, verify_asset
from godot_visual_mcp.filesystem import GodotProject


def test_placeholder_dimensions_and_frames(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    result = create_placeholder(project, "res://assets/p.png", 32, 16, 3, "ITEM")
    assert result["frames"] == 3
    with Image.open(tmp_path / "assets/p.png") as image:
        assert image.size == (96, 16)
        assert image.mode == "RGBA"


def test_inspection_detects_alpha_and_sprite_frames(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    create_placeholder(project, "res://p.png", 16, 16, 4)
    metadata = inspect_asset(project, "res://p.png")
    assert metadata["has_alpha"] is True
    assert metadata["sprite_frames"] == 4


def test_validation_reports_corrupt_asset(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    project.safe_write("res://bad.png", b"not an image")
    result = validate_asset(project, "res://bad.png")
    assert result["valid"] is False
    assert result["errors"]


def test_verification_reports_import_readiness(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    create_placeholder(project, "res://verified.png", 8, 8)
    result = verify_asset(project, "res://verified.png")
    assert result["ready"] is True
    assert result["import_verification"] == "readable_and_supported"
    assert result["validation"]["metadata"]["width"] == 8
