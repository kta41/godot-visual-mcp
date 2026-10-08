from pathlib import Path

import pytest

from godot_visual_mcp.filesystem import GodotProject
from godot_visual_mcp.limits import safety_limits


def test_limits_can_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_MAX_BATCH", "3")
    monkeypatch.setenv("MCP_MAX_PIXELS", "100")
    limits = safety_limits()
    assert limits.max_batch == 3
    assert limits.max_pixels == 100


def test_project_quota_rejects_large_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MCP_MAX_PROJECT_BYTES", "3")
    project = GodotProject(tmp_path)
    with pytest.raises(ValueError, match="quota"):
        project.safe_write("res://asset.bin", b"1234")
