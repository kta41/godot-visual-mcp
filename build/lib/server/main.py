"""FastMCP stdio server for the v1.1 Godot project tools."""

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
from godot_visual_mcp.godot import (
    discover_project,
    find_asset_references,
    find_unused_assets,
    verify_godot_import,
)
from godot_visual_mcp.godot import (
    validate_scene as validate_godot_scene,
)
from godot_visual_mcp.processing import apply_palette as apply_palette_asset
from godot_visual_mcp.processing import generate_spritesheet as generate_spritesheet_asset
from godot_visual_mcp.processing import list_palettes as list_available_palettes
from godot_visual_mcp.scenes import add_sprite_to_scene as add_sprite_scene
from godot_visual_mcp.scenes import create_scene as create_scene_asset
from godot_visual_mcp.scenes import create_sprite_frames as create_frames_asset

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
def inspect_project(project_root: str | None = None) -> dict[str, Any]:
    """Inspect a Godot project and report its configuration and Godot binary."""
    try:
        return _success(discover_project(_project(project_root).root))
    except (OSError, ValueError, RuntimeError) as exc:
        return _failure(exc)


@mcp.tool
def verify_import(
    godot_binary: str | None = None,
    timeout: float = 120.0,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Open the project with Godot headlessly and report import readiness."""
    try:
        return _success(verify_godot_import(
            _project(project_root).root, godot_binary=godot_binary, timeout=timeout
        ))
    except (OSError, ValueError, RuntimeError) as exc:
        return _failure(exc)


@mcp.tool
def validate_scene(path: str, project_root: str | None = None) -> dict[str, Any]:
    """Validate a Godot .tscn structure and its referenced project resources."""
    try:
        return _success(validate_godot_scene(_project(project_root), path))
    except (OSError, ValueError, RuntimeError) as exc:
        return _failure(exc)


@mcp.tool
def find_references(asset: str, project_root: str | None = None) -> dict[str, Any]:
    """Find project text resources that reference an asset."""
    try:
        return _success({"asset": asset, "references": find_asset_references(_project(project_root), asset)})
    except (OSError, ValueError, RuntimeError) as exc:
        return _failure(exc)


@mcp.tool
def find_unused(project_root: str | None = None) -> dict[str, Any]:
    """Find image assets that are not referenced by project text resources."""
    try:
        return _success({"assets": find_unused_assets(_project(project_root))})
    except (OSError, ValueError, RuntimeError) as exc:
        return _failure(exc)


@mcp.tool
def create_scene(
    output: str,
    root_type: str = "Node2D",
    root_name: str = "Main",
    overwrite: bool = False,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Create a minimal validated Godot scene under res://."""
    try:
        project = _project(project_root)
        return _success(_verified_scene(project, create_scene_asset(
            project, output, root_type=root_type, root_name=root_name, overwrite=overwrite
        )))
    except (OSError, ValueError, RuntimeError) as exc:
        return _failure(exc)


@mcp.tool
def add_sprite_to_scene(
    scene: str,
    texture: str,
    node_name: str = "Sprite2D",
    animated: bool = False,
    overwrite: bool = False,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Add a Sprite2D or AnimatedSprite2D with a sandboxed texture reference."""
    try:
        project = _project(project_root)
        return _success(_verified_scene(project, add_sprite_scene(
            project, scene, texture, node_name=node_name, animated=animated, overwrite=overwrite
        )))
    except (OSError, ValueError, RuntimeError) as exc:
        return _failure(exc)


@mcp.tool
def create_sprite_frames(
    output: str,
    frames: list[str],
    animation: str = "default",
    fps: float = 8.0,
    loop: bool = True,
    overwrite: bool = False,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Create a SpriteFrames resource from texture frames under res://."""
    try:
        project = _project(project_root)
        return _success(_verified_scene(project, create_frames_asset(
            project, output, frames, animation=animation, fps=fps, loop=loop, overwrite=overwrite
        )))
    except (OSError, ValueError, RuntimeError) as exc:
        return _failure(exc)


def _verified_scene(project: GodotProject, data: dict[str, object]) -> dict[str, object]:
    path = data.get("path")
    if not isinstance(path, str):
        raise TypeError("Scene operation did not return a path")
    result = dict(data)
    if path.endswith(".tscn"):
        result["verification"] = validate_godot_scene(project, path)
    else:
        result["verification"] = {"ready": project.resolve_res_path(path).is_file(), "path": path}
    return result


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
    retries: int = 0,
    validate_workflow: bool = False,
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
                retries=retries,
                validate_workflow=validate_workflow,
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
