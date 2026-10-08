from pathlib import Path

from PIL import Image

from godot_visual_mcp.filesystem import GodotProject
from godot_visual_mcp.visual import (
    compare_assets,
    crop_asset,
    deduplicate_assets,
    generate_thumbnail,
    resize_asset,
)


def save_image(path: Path, size: tuple[int, int], box: tuple[int, int, int, int] | None = None) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    if box:
        image.paste((255, 0, 0, 255), box)
    image.save(path)


def test_resize_crop_and_thumbnail_report_before_after(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    save_image(tmp_path / "source.png", (32, 16), (8, 4, 24, 12))
    resized = resize_asset(project, "res://source.png", "res://resized.png", 64, 32)
    cropped = crop_asset(project, "res://source.png", "res://cropped.png")
    thumbnail = generate_thumbnail(project, "res://source.png", "res://thumb.png", 8)
    assert resized["after"]["width"] == 64
    assert cropped["after"]["width"] == 16
    assert thumbnail["after"]["width"] <= 8


def test_compare_and_deduplicate(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    save_image(tmp_path / "a.png", (4, 4))
    (tmp_path / "b.png").write_bytes((tmp_path / "a.png").read_bytes())
    assert compare_assets(project, "res://a.png", "res://b.png")["equal"] is True
    assert deduplicate_assets(project, ["res://a.png", "res://b.png"]) == [["res://a.png", "res://b.png"]]
