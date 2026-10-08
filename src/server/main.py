"""FastMCP stdio server for the v0.2 Godot asset tools."""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

from godot_visual_mcp.assets import create_placeholder as create_placeholder_asset
from godot_visual_mcp.assets import inspect_asset as inspect_image
from godot_visual_mcp.assets import list_assets as list_project_assets
from godot_visual_mcp.assets import validate_asset as validate_image
from godot_visual_mcp.filesystem import GodotProject, ProjectPathError
from godot_visual_mcp.processing import apply_palette as apply_palette_asset
from godot_visual_mcp.processing import generate_spritesheet as generate_spritesheet_asset
from godot_visual_mcp.processing import list_palettes as list_available_palettes

mcp = FastMCP("godot-visual-mcp")


def _project(root: str | None) -> GodotProject:
    project_root = root or os.environ.get("GODOT_PROJECT_ROOT")
    if not project_root:
        raise ProjectPathError("project_root is required or GODOT_PROJECT_ROOT must be set")
    return GodotProject(project_root)


def _success(data: Any) -> dict[str, Any]:
    return {"status": "ok", "data": data, "warnings": [], "errors": []}


def _failure(exc: Exception) -> dict[str, Any]:
    return {"status": "error", "data": None, "warnings": [], "errors": [str(exc)]}


@mcp.tool
def inspect_asset(path: str, project_root: str | None = None) -> dict[str, Any]:
    """Inspect a PNG or other image under res:// and return dimensions, alpha, and frames."""
    try:
        return _success(inspect_image(_project(project_root), path))
    except (OSError, ValueError) as exc:
        return _failure(exc)


@mcp.tool
def list_assets(extension: str | None = None, project_root: str | None = None) -> dict[str, Any]:
    """List assets under res://, optionally filtered by extension."""
    try:
        return _success(list_project_assets(_project(project_root), extension))
    except (OSError, ValueError) as exc:
        return _failure(exc)


@mcp.tool
def validate_asset(path: str, project_root: str | None = None) -> dict[str, Any]:
    """Validate an image under res:// and return actionable errors."""
    try:
        return _success(validate_image(_project(project_root), path))
    except (OSError, ValueError) as exc:
        return _failure(exc)


@mcp.tool
def create_placeholder(
    output: str,
    width: int,
    height: int,
    frames: int = 1,
    label: str = "PLACEHOLDER",
    overwrite: bool = False,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Create a deterministic labeled PNG spritesheet inside res://."""
    try:
        return _success(
            create_placeholder_asset(
                _project(project_root), output, width, height, frames, label, overwrite=overwrite
            )
        )
    except (OSError, ValueError) as exc:
        return _failure(exc)


@mcp.tool
def generate_spritesheet(
    inputs: list[str],
    output: str,
    columns: int,
    overwrite: bool = False,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Assemble equal-sized res:// frames into a uniform-grid PNG spritesheet."""
    try:
        return _success(
            generate_spritesheet_asset(
                _project(project_root), inputs, output, columns, overwrite=overwrite
            )
        )
    except (OSError, ValueError) as exc:
        return _failure(exc)


@mcp.tool
def apply_palette(
    source: str,
    output: str,
    palette: str,
    distance_metric: str = "rgb",
    overwrite: bool = False,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Map an image to a built-in offline palette while preserving alpha."""
    try:
        return _success(
            apply_palette_asset(
                _project(project_root),
                source,
                output,
                palette,
                distance_metric=distance_metric,
                overwrite=overwrite,
            )
        )
    except (OSError, ValueError) as exc:
        return _failure(exc)


@mcp.tool
def list_palettes() -> dict[str, Any]:
    """List the built-in offline palettes available for asset processing."""
    try:
        return _success(list_available_palettes())
    except (OSError, ValueError) as exc:
        return _failure(exc)


def main() -> None:
    """Run the server over stdio for MCP clients."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
