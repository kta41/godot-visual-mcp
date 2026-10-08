"""Safe project discovery and in-process project selection."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .filesystem import GodotProject, ProjectPathError
from .godot import discover_project

_selected_project: Path | None = None
_aliases: dict[str, Path] = {}


def _project_info(path: Path) -> dict[str, Any]:
    return discover_project(path)


def discover_projects(search_root: str | os.PathLike[str], max_depth: int = 2) -> list[dict[str, Any]]:
    """Find Godot projects below a bounded directory without following symlinks."""
    root = Path(search_root).expanduser().resolve()
    if not root.is_dir():
        raise ProjectPathError(f"Search directory does not exist: {search_root}")
    if max_depth < 0 or max_depth > 8:
        raise ValueError("max_depth must be between 0 and 8")
    candidates: list[dict[str, Any]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        directories[:] = [item for item in directories if not item.startswith(".") and not (current_path / item).is_symlink()]
        if depth > max_depth:
            directories[:] = []
            continue
        if "project.godot" in files:
            candidates.append(_project_info(current_path))
            directories[:] = []
    return sorted(candidates, key=lambda item: str(item["root"]))


def select_project(project_root: str | os.PathLike[str] | None = None, alias: str | None = None) -> dict[str, Any]:
    """Select a validated project for subsequent resources and prompts."""
    global _selected_project
    if alias is not None:
        if alias not in _aliases:
            raise ProjectPathError(f"Unknown project alias: {alias}")
        candidate = _aliases[alias]
    elif project_root is not None:
        candidate = Path(project_root).expanduser().resolve()
    else:
        raise ProjectPathError("project_root or alias is required")
    info = _project_info(candidate)
    _selected_project = candidate
    return {"selected": info, "alias": alias}


def set_project_alias(alias: str, project_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Register an in-memory alias after validating the Godot project."""
    if not alias or any(character.isspace() for character in alias):
        raise ValueError("alias must be non-empty and contain no whitespace")
    candidate = Path(project_root).expanduser().resolve()
    info = _project_info(candidate)
    _aliases[alias] = candidate
    return {"alias": alias, "project": info}


def list_project_aliases() -> dict[str, str]:
    """Return aliases without exposing credentials or file contents."""
    return {alias: str(path) for alias, path in sorted(_aliases.items())}


def selected_project_root() -> Path | None:
    """Return the selected project, if one exists in this server process."""
    return _selected_project


def project_for_resources() -> GodotProject:
    """Resolve the selected project, falling back to the environment."""
    root = _selected_project or os.environ.get("GODOT_PROJECT_ROOT")
    if not root:
        raise ProjectPathError("Select a project or set GODOT_PROJECT_ROOT")
    return GodotProject(root)
