from pathlib import Path

import pytest
from PIL import Image

from godot_visual_mcp.assets import create_placeholder, verify_asset
from godot_visual_mcp.filesystem import GodotProject
from godot_visual_mcp.processing import apply_palette, generate_spritesheet, list_palettes


def test_generate_spritesheet_rejects_mismatched_frames(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    create_placeholder(project, "res://a.png", 8, 8)
    create_placeholder(project, "res://b.png", 4, 8)
    with pytest.raises(ValueError, match="identical dimensions"):
        generate_spritesheet(project, ["res://a.png", "res://b.png"], "res://sheet.png", 2)


def test_generate_spritesheet_creates_uniform_grid(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    for name in ("a", "b", "c"):
        create_placeholder(project, f"res://{name}.png", 8, 8)
    result = generate_spritesheet(
        project, ["res://a.png", "res://b.png", "res://c.png"], "res://sheet.png", 2
    )
    assert result["frames"] == 3
    assert result["rows"] == 2
    with Image.open(tmp_path / "sheet.png") as image:
        assert image.size == (16, 16)


def test_apply_palette_preserves_alpha_and_uses_palette(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    source = Image.new("RGBA", (2, 1), ((120, 120, 120, 255)))
    source.putpixel((1, 0), (10, 10, 10, 0))
    source.save(tmp_path / "source.png")
    result = apply_palette(project, "res://source.png", "res://mapped.png", "custom", distance_metric="lab")
    assert result["has_alpha"] is True
    with Image.open(tmp_path / "mapped.png") as image:
        assert image.getpixel((0, 0)) in ((0, 0, 0, 255), (255, 255, 255, 255))
        assert image.getpixel((1, 0)) == (10, 10, 10, 0)


def test_list_palettes() -> None:
    assert list_palettes() == ["custom", "gameboy", "pico8"]


def test_transform_result_is_import_ready(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    create_placeholder(project, "res://source.png", 8, 8)
    apply_palette(project, "res://source.png", "res://mapped.png", "gameboy")
    assert verify_asset(project, "res://mapped.png")["ready"] is True
