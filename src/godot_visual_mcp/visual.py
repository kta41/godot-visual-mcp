"""Offline visual processing engines for prototyping."""

from __future__ import annotations

import io
from collections.abc import Iterable
from typing import Any

from PIL import Image, ImageChops, ImageEnhance

from .assets import inspect_asset
from .filesystem import GodotProject
from .limits import ensure_image_dimensions, ensure_input_size


def _load(project: GodotProject, path: str) -> Image.Image:
    try:
        data = project.safe_read(path)
        ensure_input_size(len(data))
        with Image.open(io.BytesIO(data)) as image:
            ensure_image_dimensions(image.width, image.height)
            converted = image.convert("RGBA")
            converted.load()
            return converted
    except OSError as exc:
        raise ValueError(f"Unsupported or corrupt image: {path}") from exc


def _save(project: GodotProject, output: str, image: Image.Image, *, overwrite: bool) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return project.safe_write(output, buffer.getvalue(), overwrite=overwrite)


def _result(project: GodotProject, path: str, *, operation: str, before: dict[str, Any]) -> dict[str, Any]:
    after = inspect_asset(project, path)
    return {
        "path": path,
        "operation": operation,
        "before": before,
        "after": after,
        "verification": {
            "alpha_preserved": before["has_alpha"] == after["has_alpha"],
            "output_readable": True,
        },
    }


def resize_asset(
    project: GodotProject,
    source: str,
    output: str,
    width: int,
    height: int,
    *,
    pixel_perfect: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Resize an image using nearest-neighbor by default for pixel art."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    image = _load(project, source)
    before = inspect_asset(project, source)
    resized = image.resize((width, height), Image.Resampling.NEAREST if pixel_perfect else Image.Resampling.LANCZOS)
    return _result(project, _save(project, output, resized, overwrite=overwrite), operation="resize", before=before)


def crop_asset(
    project: GodotProject,
    source: str,
    output: str,
    *,
    padding: int = 0,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Crop transparent borders, optionally retaining pixel padding."""
    if padding < 0:
        raise ValueError("padding must not be negative")
    image = _load(project, source)
    before = inspect_asset(project, source)
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        bbox = (0, 0, image.width, image.height)
    box = (
        max(0, bbox[0] - padding),
        max(0, bbox[1] - padding),
        min(image.width, bbox[2] + padding),
        min(image.height, bbox[3] + padding),
    )
    return _result(project, _save(project, output, image.crop(box), overwrite=overwrite), operation="crop", before=before)


def normalize_asset(
    project: GodotProject,
    source: str,
    output: str,
    *,
    center: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Crop transparent bounds and place the result on the original canvas."""
    image = _load(project, source)
    before = inspect_asset(project, source)
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        normalized = image
    else:
        cropped = image.crop(bbox)
        normalized = Image.new("RGBA", image.size, (0, 0, 0, 0))
        position = ((image.width - cropped.width) // 2, (image.height - cropped.height) // 2) if center else (bbox[0], bbox[1])
        normalized.alpha_composite(cropped, position)
    return _result(project, _save(project, output, normalized, overwrite=overwrite), operation="normalize", before=before)


def generate_thumbnail(
    project: GodotProject,
    source: str,
    output: str,
    size: int = 128,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a bounded thumbnail preserving aspect ratio."""
    if size <= 0 or size > 4096:
        raise ValueError("size must be between 1 and 4096")
    image = _load(project, source)
    before = inspect_asset(project, source)
    image.thumbnail((size, size), Image.Resampling.NEAREST)
    return _result(project, _save(project, output, image, overwrite=overwrite), operation="thumbnail", before=before)


def transform_colors(project: GodotProject, source: str, output: str, operation: str, *, overwrite: bool = False) -> dict[str, Any]:
    """Apply grayscale, contrast, or brightness transforms offline."""
    image = _load(project, source)
    before = inspect_asset(project, source)
    if operation == "grayscale":
        transformed = Image.merge("RGBA", (image.convert("L"),) * 3 + (image.getchannel("A"),))
    elif operation == "contrast":
        transformed = ImageEnhance.Contrast(image).enhance(1.25)
    elif operation == "brightness":
        transformed = ImageEnhance.Brightness(image).enhance(1.15)
    else:
        raise ValueError("operation must be grayscale, contrast, or brightness")
    return _result(project, _save(project, output, transformed, overwrite=overwrite), operation=operation, before=before)


def compare_assets(project: GodotProject, left: str, right: str) -> dict[str, Any]:
    """Compare two images using a normalized pixel difference score."""
    first, second = _load(project, left), _load(project, right)
    if first.size != second.size:
        return {"equal": False, "same_dimensions": False, "difference": 1.0}
    difference = ImageChops.difference(first, second)
    histogram = difference.histogram()
    maximum = first.width * first.height * 4 * 255
    score = sum((index % 256) * value for index, value in enumerate(histogram)) / maximum
    score = min(score, 1.0)
    return {"equal": score == 0, "same_dimensions": True, "difference": round(score, 6)}


def deduplicate_assets(project: GodotProject, paths: Iterable[str]) -> list[list[str]]:
    """Group byte-identical image assets without leaving the project."""
    groups: dict[bytes, list[str]] = {}
    for path in paths:
        groups.setdefault(project.safe_read(path), []).append(project.validate_asset_path(path))
    return [group for group in groups.values() if len(group) > 1]


def flip_asset(project: GodotProject, source: str, output: str, *, horizontal: bool = True, overwrite: bool = False) -> dict[str, Any]:
    """Flip an image horizontally or vertically."""
    image = _load(project, source)
    before = inspect_asset(project, source)
    operation = Image.Transpose.FLIP_LEFT_RIGHT if horizontal else Image.Transpose.FLIP_TOP_BOTTOM
    return _result(project, _save(project, output, image.transpose(operation), overwrite=overwrite), operation="flip", before=before)


def rotate_asset(project: GodotProject, source: str, output: str, degrees: int, *, overwrite: bool = False) -> dict[str, Any]:
    """Rotate an image by a multiple of 90 degrees."""
    if degrees not in {90, 180, 270}:
        raise ValueError("degrees must be 90, 180, or 270")
    image = _load(project, source)
    before = inspect_asset(project, source)
    return _result(project, _save(project, output, image.rotate(degrees, expand=True), overwrite=overwrite), operation="rotate", before=before)
