"""Image inspection, validation, and deterministic placeholder generation."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from .filesystem import GodotProject

SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP", "BMP", "GIF", "TIFF"}


def _frame_count(width: int, height: int) -> int:
    """Estimate uniform horizontal/vertical sprite frames from image geometry."""
    if width >= height * 2 and width % height == 0:
        return width // height
    if height >= width * 2 and height % width == 0:
        return height // width
    return 1


def inspect_asset(project: GodotProject, path: str) -> dict[str, Any]:
    """Return compact metadata suitable for an agent."""
    data = project.safe_read(path)
    try:
        with Image.open(io.BytesIO(data)) as image:
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            return {
                "path": project.validate_asset_path(path),
                "format": image.format,
                "width": image.width,
                "height": image.height,
                "has_alpha": has_alpha,
                "frames": getattr(image, "n_frames", 1),
                "sprite_frames": _frame_count(image.width, image.height),
                "color_mode": image.mode,
            }
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Unsupported or corrupt image: {path}") from exc


def list_assets(project: GodotProject, extension: str | None = None) -> list[str]:
    """List project assets, optionally filtered by extension."""
    assets = project.iter_assets()
    if extension:
        suffix = extension.lower()
        if not suffix.startswith("."):
            suffix = "." + suffix
        assets = [path for path in assets if path.lower().endswith(suffix)]
    return assets


def validate_asset(project: GodotProject, path: str) -> dict[str, Any]:
    """Check that an image is readable and provide actionable diagnostics."""
    try:
        metadata = inspect_asset(project, path)
    except (FileNotFoundError, ValueError) as exc:
        return {"valid": False, "path": project.validate_asset_path(path), "errors": [str(exc)]}
    errors: list[str] = []
    if metadata["format"] not in SUPPORTED_FORMATS:
        errors.append(f"Format {metadata['format']} is not supported")
    if metadata["width"] <= 0 or metadata["height"] <= 0:
        errors.append("Image dimensions must be positive")
    return {
        "valid": not errors,
        "path": metadata["path"],
        "errors": errors,
        "metadata": metadata,
    }


def verify_asset(project: GodotProject, path: str) -> dict[str, Any]:
    """Verify that an output is present and import-ready without reading `.import` files."""
    validation = validate_asset(project, path)
    if not validation["valid"]:
        return {
            "ready": False,
            "path": validation["path"],
            "import_verification": "failed_validation",
            "validation": validation,
        }
    return {
        "ready": True,
        "path": validation["path"],
        "import_verification": "readable_and_supported",
        "validation": validation,
    }


def create_placeholder(
    project: GodotProject,
    output: str,
    width: int,
    height: int,
    frames: int = 1,
    label: str = "PLACEHOLDER",
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a labeled, deterministic RGBA placeholder spritesheet."""
    if width <= 0 or height <= 0 or frames <= 0:
        raise ValueError("width, height, and frames must be positive integers")
    if frames > 128:
        raise ValueError("frames must be 128 or fewer")
    image = Image.new("RGBA", (width * frames, height), (38, 42, 54, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for index in range(frames):
        left = index * width
        draw.rectangle((left, 0, left + width - 1, height - 1), outline=(235, 220, 120, 255), width=2)
        text = label[:32]
        bounds = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (left + (width - (bounds[2] - bounds[0])) / 2, (height - (bounds[3] - bounds[1])) / 2),
            text,
            fill=(235, 220, 120, 255),
            font=font,
        )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    written = project.safe_write(output, buffer.getvalue(), overwrite=overwrite)
    return {"path": written, "width": width, "height": height, "frames": frames, "has_alpha": True}
