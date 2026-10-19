from pathlib import Path

import pytest

from godot_visual_mcp.filesystem import ProjectPathError
from server import main


def test_mcp_project_root_must_be_a_godot_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GODOT_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(ProjectPathError, match="Not a Godot project"):
        main._project(str(tmp_path))


def test_mcp_project_accepts_valid_selected_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project.godot").write_text('[application]\nconfig/name="Test"\n', encoding="utf-8")
    monkeypatch.setenv("GODOT_PROJECT_ROOT", str(tmp_path))
    assert main._project(str(tmp_path)).root == tmp_path.resolve()


def test_mcp_project_config_obeys_input_byte_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.setenv("GODOT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MCP_MAX_INPUT_BYTES", "3")

    with pytest.raises(ValueError, match="byte limit"):
        main._project(str(tmp_path))


def test_verify_import_cannot_run_agent_selected_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    executable = tmp_path / "untrusted-binary"
    executable.write_text("not a Godot executable", encoding="utf-8")
    monkeypatch.setenv("GODOT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(main, "find_godot_binary", lambda explicit=None: str(executable) if explicit else None)

    result = main.verify_import(godot_binary=str(executable), project_root=str(tmp_path))

    assert result["status"] == "error"
    assert "cannot select executables" in result["errors"][0]["message"]


def test_verify_import_obeys_operation_timeout_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.setenv("GODOT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MCP_MAX_OPERATION_SECONDS", "5")

    result = main.verify_import(timeout=6, project_root=str(tmp_path))

    assert result["status"] == "error"
    assert "timeout must be between" in result["errors"][0]["message"]


def test_mcp_rejects_project_outside_configured_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "configured"
    other = tmp_path / "other"
    configured.mkdir()
    other.mkdir()
    (configured / "project.godot").write_text("[application]\n", encoding="utf-8")
    (other / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.setenv("GODOT_PROJECT_ROOT", str(configured))

    with pytest.raises(ProjectPathError, match="outside the operator-configured"):
        main._project(str(other))


def test_mcp_allows_additional_operator_configured_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "configured"
    extra = tmp_path / "shared-games"
    project = extra / "game"
    configured.mkdir()
    project.mkdir(parents=True)
    (configured / "project.godot").write_text("[application]\n", encoding="utf-8")
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.setenv("GODOT_PROJECT_ROOT", str(configured))
    monkeypatch.setenv("GODOT_ALLOWED_PROJECT_ROOTS", str(extra))

    assert main._project(str(project)).root == project.resolve()


def test_project_discovery_selection_and_alias_respect_allowed_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "allowed"
    external = tmp_path / "external"
    allowed.mkdir()
    external.mkdir()
    (allowed / "project.godot").write_text("[application]\n", encoding="utf-8")
    (external / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.setenv("GODOT_PROJECT_ROOT", str(allowed))

    discovery = main.discover_projects_tool(str(external))
    selection = main.select_project_tool(project_root=str(external))
    alias = main.set_project_alias_tool("external", str(external))

    for result in (discovery, selection, alias):
        assert result["status"] == "error"
        assert "outside the operator-configured" in result["errors"][0]["message"]