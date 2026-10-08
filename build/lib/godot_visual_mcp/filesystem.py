"""Sandboxed access to a Godot project's ``res://`` filesystem."""

from __future__ import annotations

import os
from pathlib import Path


class ProjectPathError(ValueError):
    """Raised when a path cannot be safely mapped into the project."""


class FileAlreadyExistsError(FileExistsError):
    """Raised when a write would overwrite an existing file."""


class GodotProject:
    """Resolve and access paths while enforcing the project boundary."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        root_path = Path(root).expanduser()
        if not root_path.is_dir():
            raise ProjectPathError(f"Godot project does not exist: {root}")
        self.root = root_path.resolve()

    def resolve_res_path(self, res_path: str) -> Path:
        """Resolve a relative path or ``res://`` path without escaping root."""
        if not isinstance(res_path, str) or not res_path.strip():
            raise ProjectPathError("Asset path must be a non-empty string")
        raw = res_path.strip()
        relative = raw.removeprefix("res://")
        if raw.startswith("res:/") and not raw.startswith("res://"):
            raise ProjectPathError("Use the res:// path prefix")
        candidate = Path(relative)
        if candidate.is_absolute() or relative.startswith(("/", "\\")):
            raise ProjectPathError("Absolute paths are not allowed")
        if any(part == ".." for part in candidate.parts):
            raise ProjectPathError("Parent traversal is not allowed")
        if any(part == "" for part in candidate.parts):
            raise ProjectPathError("Invalid empty path component")

        resolved = (self.root / candidate).resolve(strict=False)
        self.ensure_inside_project(resolved)
        return resolved

    def ensure_inside_project(self, path: Path) -> Path:
        """Verify a resolved path is inside the project, including symlinks."""
        try:
            path.resolve(strict=False).relative_to(self.root)
        except ValueError as exc:
            raise ProjectPathError("Path resolves outside the Godot project") from exc
        return path

    def validate_asset_path(self, res_path: str) -> str:
        """Validate a path and return its canonical ``res://`` representation."""
        resolved = self.resolve_res_path(res_path)
        return "res://" + resolved.relative_to(self.root).as_posix()

    def safe_read(self, res_path: str) -> bytes:
        """Read a project file only after resolving and checking its real path."""
        path = self.resolve_res_path(res_path)
        if not path.is_file():
            raise FileNotFoundError(f"Asset does not exist: {self.validate_asset_path(res_path)}")
        return path.read_bytes()

    def safe_write(self, res_path: str, content: bytes, *, overwrite: bool = False) -> str:
        """Write bytes inside the project; overwriting requires explicit opt-in."""
        path = self.resolve_res_path(res_path)
        if path.exists() and not overwrite:
            raise FileAlreadyExistsError(
                f"Asset already exists: {self.validate_asset_path(res_path)}; set overwrite=true"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_inside_project(path)
        path.write_bytes(content)
        return self.validate_asset_path(res_path)

    def iter_assets(self) -> list[str]:
        """Return non-imported files under the project as sorted ``res://`` paths."""
        assets: list[str] = []
        for path in self.root.rglob("*"):
            if path.is_file() and ".godot" not in path.parts and not path.name.endswith(".import"):
                assets.append("res://" + path.relative_to(self.root).as_posix())
        return sorted(assets)
