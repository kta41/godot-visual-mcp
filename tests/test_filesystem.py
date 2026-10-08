from pathlib import Path

import pytest

from godot_visual_mcp.filesystem import FileAlreadyExistsError, GodotProject, ProjectPathError


def test_valid_res_path(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    assert project.validate_asset_path("res://assets/a.png") == "res://assets/a.png"


def test_reject_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(ProjectPathError):
        GodotProject(tmp_path).resolve_res_path("/tmp/a.png")


def test_reject_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ProjectPathError):
        GodotProject(tmp_path).resolve_res_path("res://assets/../a.png")


def test_reject_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-godot-test"
    outside.mkdir()
    (tmp_path / "assets").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectPathError):
        GodotProject(tmp_path).resolve_res_path("res://assets/file.png")


def test_write_inside_project_and_no_overwrite(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    assert project.safe_write("res://assets/a.bin", b"one") == "res://assets/a.bin"
    with pytest.raises(FileAlreadyExistsError):
        project.safe_write("res://assets/a.bin", b"two")
    assert project.safe_read("res://assets/a.bin") == b"one"

