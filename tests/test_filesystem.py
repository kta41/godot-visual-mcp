from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, local

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


def test_reject_nested_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "nested-outside"
    outside.mkdir()
    nested = tmp_path / "assets" / "nested"
    nested.mkdir(parents=True)
    (nested / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProjectPathError):
        GodotProject(tmp_path).resolve_res_path("res://assets/nested/link/file.png")


def test_unicode_res_path_round_trip(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    path = "res://art/niño/éxito.png"
    assert project.safe_write(path, b"png") == path
    assert project.safe_read(path) == b"png"


def test_safe_read_enforces_input_byte_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = GodotProject(tmp_path)
    project.safe_write("res://large.bin", b"1234")
    monkeypatch.setenv("MCP_MAX_INPUT_BYTES", "3")
    with pytest.raises(ValueError, match="byte limit"):
        project.safe_read("res://large.bin")


def test_write_inside_project_and_no_overwrite(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    assert project.safe_write("res://assets/a.bin", b"one") == "res://assets/a.bin"
    with pytest.raises(FileAlreadyExistsError):
        project.safe_write("res://assets/a.bin", b"two")
    assert project.safe_read("res://assets/a.bin") == b"one"


def test_concurrent_non_overwrite_writes_are_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = GodotProject(tmp_path)
    barrier = Barrier(2)
    thread_state = local()
    ensure_inside = project.ensure_inside_project

    def synchronized_ensure(path: Path) -> Path:
        calls = getattr(thread_state, "calls", 0) + 1
        thread_state.calls = calls
        if calls == 2:
            barrier.wait()
        return ensure_inside(path)

    monkeypatch.setattr(project, "ensure_inside_project", synchronized_ensure)

    def write(content: bytes) -> str:
        try:
            project.safe_write("res://shared.bin", content)
            return "written"
        except FileAlreadyExistsError:
            return "exists"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(write, (b"first", b"second")))

    assert results.count("written") == 1
    assert results.count("exists") == 1
    assert project.safe_read("res://shared.bin") in {b"first", b"second"}

