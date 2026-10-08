"""Offline asset transformation engines for v0.2."""

from __future__ import annotations

import io
import json
import math
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import cast

from PIL import Image

from .assets import inspect_asset
from .filesystem import GodotProject

RGB = tuple[int, int, int]
Palette = list[RGB]
DistanceMetric = Callable[[tuple[float, float, float], tuple[float, float, float]], float]


def _load_image(project: GodotProject, path: str) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(project.safe_read(path)))
        return image.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unsupported or corrupt image: {path}") from exc


def _save_png(project: GodotProject, output: str, image: Image.Image, *, overwrite: bool) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return project.safe_write(output, buffer.getvalue(), overwrite=overwrite)


def _rgb_to_lab(color: tuple[float, float, float]) -> tuple[float, float, float]:
    """Convert sRGB to CIE L*a*b* (D65) without an additional dependency."""
    channels = []
    for value in color:
        normalized = value / 255
        channels.append(
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )
    r, g, b = channels
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722)
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def pivot(value: float) -> float:
        return value ** (1 / 3) if value > 0.008856 else 7.787 * value + 16 / 116

    fx, fy, fz = pivot(x), pivot(y), pivot(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _euclidean(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def _metric(name: str) -> DistanceMetric:
    if name == "rgb":
        return _euclidean
    if name == "lab":
        return _euclidean
    raise ValueError("distance_metric must be 'rgb' or 'lab'")


def load_palette(name: str, palette_root: Path | None = None) -> Palette:
    """Load a built-in or custom JSON palette and validate its schema."""
    root = palette_root or Path(__file__).parents[2] / "palettes"
    path = Path(name)
    if path.name != name or path.suffix.lower() != ".json":
        path = root / f"{name}.json"
    else:
        path = root / path.name
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        colors = payload["colors"]
        palette = [tuple(color) for color in colors]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid palette: {name}") from exc
    if not palette or any(len(color) != 3 or any(not 0 <= value <= 255 for value in color) for color in palette):
        raise ValueError(f"Invalid palette colors: {name}")
    return cast(Palette, palette)


def list_palettes(palette_root: Path | None = None) -> list[str]:
    """List available JSON palettes by their names."""
    root = palette_root or Path(__file__).parents[2] / "palettes"
    return sorted(path.stem for path in root.glob("*.json"))


def generate_spritesheet(
    project: GodotProject,
    inputs: Iterable[str],
    output: str,
    columns: int,
    *,
    overwrite: bool = False,
) -> dict[str, object]:
    """Assemble equal-sized source frames into a row-major uniform-grid sheet."""
    paths = list(inputs)
    if not paths:
        raise ValueError("At least one input frame is required")
    if columns <= 0:
        raise ValueError("columns must be positive")
    images = [_load_image(project, path) for path in paths]
    size = images[0].size
    if any(image.size != size for image in images):
        raise ValueError("All input frames must have identical dimensions")
    rows = math.ceil(len(images) / columns)
    sheet = Image.new("RGBA", (size[0] * columns, size[1] * rows), (0, 0, 0, 0))
    for index, image in enumerate(images):
        sheet.paste(image, ((index % columns) * size[0], (index // columns) * size[1]))
    written = _save_png(project, output, sheet, overwrite=overwrite)
    return {
        "path": written,
        "width": sheet.width,
        "height": sheet.height,
        "frames": len(images),
        "columns": columns,
        "rows": rows,
        "has_alpha": True,
    }


def apply_palette(
    project: GodotProject,
    source: str,
    output: str,
    palette_name: str,
    *,
    distance_metric: str = "rgb",
    overwrite: bool = False,
) -> dict[str, object]:
    """Map opaque RGB pixels to a palette while preserving alpha exactly."""
    image = _load_image(project, source)
    palette = load_palette(palette_name)
    metric = _metric(distance_metric)
    transformed = Image.new("RGBA", image.size)
    source_pixels = list(image.getdata())
    output_pixels: list[tuple[int, int, int, int]] = []
    converted_palette = [
        _rgb_to_lab(color)
        if distance_metric == "lab"
        else (float(color[0]), float(color[1]), float(color[2]))
        for color in palette
    ]
    for red, green, blue, alpha in source_pixels:
        if alpha == 0:
            output_pixels.append((red, green, blue, alpha))
            continue
        color = (float(red), float(green), float(blue))
        comparable = _rgb_to_lab(color) if distance_metric == "lab" else color
        index = min(
            range(len(palette)),
            key=lambda palette_index: metric(comparable, converted_palette[palette_index]),
        )
        output_pixels.append((*palette[index], alpha))
    transformed.putdata(output_pixels)
    written = _save_png(project, output, transformed, overwrite=overwrite)
    return {
        "path": written,
        "width": transformed.width,
        "height": transformed.height,
        "has_alpha": True,
        "palette": palette_name,
        "distance_metric": distance_metric,
        "palette_colors": len(palette),
        "source_frames": inspect_asset(project, source)["frames"],
    }
