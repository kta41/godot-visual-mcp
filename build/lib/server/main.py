"""FastMCP stdio server for the v0.3 Godot asset tools."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP

from godot_visual_mcp.assets import create_placeholder as create_placeholder_asset
from godot_visual_mcp.assets import inspect_asset as inspect_image
from godot_visual_mcp.assets import list_assets as list_project_assets
from godot_visual_mcp.assets import validate_asset as validate_image
from godot_visual_mcp.assets import verify_asset as verify_image
from godot_visual_mcp.comfyui import generate_asset as generate_asset_engine
from godot_visual_mcp.comfyui import remove_background as remove_background_engine
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


def _verified(project: GodotProject, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("path"), str):
        raise TypeError("Mutating operation did not return a verifiable asset path")
    path = data["path"]
    verification = verify_image(project, path)
    result = dict(data)
    result["verification"] = verification
    return result


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
        project = _project(project_root)
        return _success(_verified(
            project,
            create_placeholder_asset(project, output, width, height, frames, label, overwrite=overwrite),
        ))
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
        project = _project(project_root)
        return _success(_verified(
            project,
            generate_spritesheet_asset(project, inputs, output, columns, overwrite=overwrite),
        ))
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
        project = _project(project_root)
        return _success(_verified(
            project,
            apply_palette_asset(
                project,
                source,
                output,
                palette,
                distance_metric=distance_metric,
                overwrite=overwrite,
            ),
        ))
    except (OSError, ValueError) as exc:
        return _failure(exc)


@mcp.tool
def list_palettes() -> dict[str, Any]:
    """List the built-in offline palettes available for asset processing."""
    try:
        return _success(list_available_palettes())
    except (OSError, ValueError) as exc:
        return _failure(exc)


@mcp.tool
async def generate_asset(
    prompt: str,
    workflow: str,
    output: str,
    width: int = 512,
    height: int = 512,
    seed: int | None = None,
    batch: int = 1,
    remove_background: bool = False,
    crop: bool = True,
    overwrite: bool = False,
    timeout: float = 300.0,
    endpoint: str | None = None,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Generate an asset through ComfyUI, post-process it, and validate res:// output."""
    try:
        project = _project(project_root)
        return _success(_verified(
            project,
            await generate_asset_engine(
                project,
                prompt,
                workflow,
                output,
                endpoint=endpoint,
                width=width,
                height=height,
                seed=seed,
                batch=batch,
                remove_background_enabled=remove_background,
                crop=crop,
                overwrite=overwrite,
                timeout=timeout,
            ),
        ))
    except (OSError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        return _failure(exc)


@mcp.tool
def remove_background(
    source: str,
    output: str,
    overwrite: bool = False,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Remove an image background using the optional rembg AI extra."""
    try:
        project = _project(project_root)
        return _success(_verified(
            project,
            remove_background_engine(project, source, output, overwrite=overwrite),
        ))
    except (OSError, ValueError, RuntimeError) as exc:
        return _failure(exc)


def main() -> None:
    """Run the server over stdio for MCP clients."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
