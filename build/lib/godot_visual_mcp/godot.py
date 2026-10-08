"""Controlled Godot project discovery and headless verification."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .filesystem import GodotProject, ProjectPathError


class GodotError(RuntimeError):
    """Raised when a Godot project cannot be inspected or verified."""


class GodotHeadlessVerifier:
    """Reusable verifier for controlled Godot headless project checks."""

    def __init__(self, godot_binary: str | None = None, timeout: float = 120.0) -> None:
        self.godot_binary = godot_binary
        self.timeout = timeout

    def verify(self, project_root: str | os.PathLike[str]) -> dict[str, Any]:
        return verify_godot_import(
            project_root, godot_binary=self.godot_binary, timeout=self.timeout
        )


def discover_project(root: str | os.PathLike[str]) -> dict[str, Any]:
    """Inspect a project root without invoking the Godot editor."""
    project = GodotProject(root)
    project_file = project.root / "project.godot"
    if not project_file.is_file():
        raise ProjectPathError(f"Not a Godot project: {project.root}")
    content = project_file.read_text(encoding="utf-8", errors="replace")
    config = _parse_project_config(content)
    return {
        "root": str(project.root),
        "name": config.get("config/name"),
        "config_version": config.get("config_version"),
        "project_file": "res://project.godot",
        "godot_binary": find_godot_binary(),
    }


def find_godot_binary(explicit: str | None = None) -> str | None:
    """Find a configured Godot executable without executing it."""
    candidate = explicit or os.environ.get("GODOT_BIN")
    if candidate:
        return candidate if Path(candidate).is_file() else shutil.which(candidate)
    return shutil.which("godot") or shutil.which("godot4")


def verify_godot_import(
    project_root: str | os.PathLike[str],
    *,
    godot_binary: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Open a project with Godot headlessly and return import diagnostics."""
    project = GodotProject(project_root)
    discovered = discover_project(project.root)
    binary = find_godot_binary(godot_binary)
    if not binary:
        return {
            "ready": False,
            "skipped": True,
            "code": "GODOT_NOT_INSTALLED",
            "message": "Godot executable was not found; install Godot or set GODOT_BIN",
            "project": discovered,
        }
    command = [binary, "--headless", "--path", str(project.root), "--editor", "--quit"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GodotError(f"Godot headless verification failed: {exc}") from exc
    stderr = completed.stderr.strip()
    stdout = completed.stdout.strip()
    return {
        "ready": completed.returncode == 0,
        "skipped": False,
        "code": "GODOT_IMPORT_OK" if completed.returncode == 0 else "GODOT_IMPORT_FAILED",
        "returncode": completed.returncode,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "project": discovered,
    }


def _parse_project_config(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in content.splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_./-]+)\s*=\s*(.+?)\s*$", line)
        if not match:
            continue
        value = match.group(2).strip().strip('"')
        values[match.group(1)] = value
    return values


def validate_scene(project: GodotProject, scene_path: str) -> dict[str, Any]:
    """Perform safe structural checks on a text Godot scene."""
    path = project.resolve_res_path(scene_path)
    if path.suffix != ".tscn":
        raise ValueError("Scene path must have a .tscn extension")
    content = project.safe_read(scene_path).decode("utf-8", errors="replace")
    errors: list[str] = []
    if "[gd_scene" not in content:
        errors.append("Missing [gd_scene] header")
    if "[node" not in content:
        errors.append("Scene has no nodes")
    external_paths = re.findall(r'path="(res://[^"]+)"', content)
    missing = [item for item in external_paths if not project.resolve_res_path(item).is_file()]
    if missing:
        errors.append(f"Missing referenced resources: {', '.join(missing)}")
    return {
        "valid": not errors,
        "path": project.validate_asset_path(scene_path),
        "nodes": content.count("[node "),
        "external_resources": external_paths,
        "errors": errors,
    }


def find_asset_references(project: GodotProject, asset_path: str) -> list[str]:
    """Find text resources that reference one asset inside the project."""
    canonical = project.validate_asset_path(asset_path)
    matches: list[str] = []
    for candidate in project.root.rglob("*"):
        if not candidate.is_file() or ".godot" in candidate.parts or candidate.name.endswith(".import"):
            continue
        try:
            if canonical in candidate.read_text(encoding="utf-8", errors="ignore"):
                matches.append("res://" + candidate.relative_to(project.root).as_posix())
        except OSError:
            continue
    return sorted(matches)


def find_unused_assets(project: GodotProject) -> list[str]:
    """Find image assets not referenced by text resources in the project."""
    assets = [
        path for path in project.iter_assets()
        if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}
    ]
    referenced = {item for asset in assets for item in find_asset_references(project, asset)}
    return [asset for asset in assets if asset not in referenced]
