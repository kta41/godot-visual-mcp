import json
import struct
import wave
from pathlib import Path

from godot_visual_mcp.extended_assets import (
    inspect_3d_asset,
    inspect_audio,
    inspect_json_asset,
    inspect_svg,
)
from godot_visual_mcp.filesystem import GodotProject
from godot_visual_mcp.projects import discover_projects, select_project


def test_project_discovery_and_selection(tmp_path: Path) -> None:
    project_root = tmp_path / "game"
    project_root.mkdir()
    (project_root / "project.godot").write_text('[application]\nconfig/name="Game"\n', encoding="utf-8")
    found = discover_projects(tmp_path)
    assert found[0]["name"] == "Game"
    assert select_project(project_root)["selected"]["name"] == "Game"


def test_audio_svg_gltf_and_json_inspection(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    with wave.open(str(tmp_path / "sound.wav"), "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(8000)
        sound.writeframes(b"\0\0" * 80)
    project.safe_write("res://shape.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 3"/>')
    project.safe_write("res://mesh.gltf", json.dumps({
        "asset": {"version": "2.0"}, "meshes": [{}], "materials": [], "animations": []
    }).encode())
    project.safe_write("res://data.json", b'{"ok": true}')
    assert inspect_audio(project, "res://sound.wav")["sample_rate"] == 8000
    assert inspect_svg(project, "res://shape.svg")["view_box"] == "0 0 2 3"
    assert inspect_3d_asset(project, "res://mesh.gltf")["valid"] is True
    assert inspect_json_asset(project, "res://data.json")["root_type"] == "dict"


def test_glb_header_is_inspected(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    project.safe_write("res://model.glb", b"glTF" + struct.pack("<II", 2, 20))
    assert inspect_3d_asset(project, "res://model.glb")["version"] == 2
