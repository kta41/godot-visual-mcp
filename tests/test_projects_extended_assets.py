import json
import struct
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from godot_visual_mcp.extended_assets import (
    convert_svg_to_png,
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


def test_wav_duration_limit_is_configurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio_path = tmp_path / "long.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(1)
        audio.writeframes(b"\0\0" * 2)
    monkeypatch.setenv("MCP_MAX_AUDIO_SECONDS", "1")

    with pytest.raises(ValueError, match="duration exceeds"):
        inspect_audio(GodotProject(tmp_path), "res://long.wav")


def test_ogg_duration_limit_is_configurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packet = b"\x01vorbis" + b"\0" * 4 + b"\x01" + struct.pack("<I", 8000) + b"\0" * 8
    page = (
        b"OggS"
        + bytes((0, 4))
        + struct.pack("<QII", 16000, 1, 0)
        + b"\0" * 4
        + bytes((1, len(packet)))
        + packet
    )
    project = GodotProject(tmp_path)
    project.safe_write("res://long.ogg", page)
    monkeypatch.setenv("MCP_MAX_AUDIO_SECONDS", "1")

    with pytest.raises(ValueError, match="duration exceeds"):
        inspect_audio(project, "res://long.ogg")


def test_mp3_duration_limit_is_configurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame_header = bytes.fromhex("fffb9064")
    frame = frame_header + b"\0" * (417 - len(frame_header))
    project = GodotProject(tmp_path)
    project.safe_write("res://long.mp3", frame * 100)
    monkeypatch.setenv("MCP_MAX_AUDIO_SECONDS", "1")

    with pytest.raises(ValueError, match="duration exceeds"):
        inspect_audio(project, "res://long.mp3")


def test_glb_header_is_inspected(tmp_path: Path) -> None:
    project = GodotProject(tmp_path)
    project.safe_write("res://model.glb", b"glTF" + struct.pack("<II", 2, 20))
    assert inspect_3d_asset(project, "res://model.glb")["version"] == 2


@pytest.mark.parametrize(
    "svg",
    [
        b"<svg><image href='https://example.com/a.png'/></svg>",
        b'<svg><image href="file:///etc/passwd"/></svg>',
        b'<svg><rect style="fill:url(https://example.com/p.svg#x)"/></svg>',
        b'<svg><style>@import "https://example.com/a.css";</style></svg>',
        b'<svg><image href="texture.png"/></svg>',
        b'<svg><rect style="fill:u/**/rl(https://example.com/p.svg#x)"/></svg>',
        b'<svg><rect style="fill:u\\72l(https://example.com/p.svg#x)"/></svg>',
    ],
)
def test_svg_rejects_external_references(tmp_path: Path, svg: bytes) -> None:
    project = GodotProject(tmp_path)
    project.safe_write("res://unsafe.svg", svg)
    with pytest.raises(ValueError, match="External SVG references"):
        inspect_svg(project, "res://unsafe.svg")


def test_svg_conversion_bounds_raster_dimensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dimensions: dict[str, int] = {}

    def fake_svg2png(**kwargs: object) -> bytes:
        dimensions["width"] = int(kwargs["output_width"])
        dimensions["height"] = int(kwargs["output_height"])
        return b"bounded-png"

    monkeypatch.setenv("MCP_MAX_PIXELS", "100")
    monkeypatch.setitem(sys.modules, "cairosvg", SimpleNamespace(svg2png=fake_svg2png))
    project = GodotProject(tmp_path)
    project.safe_write(
        "res://large.svg",
        b'<svg width="100000" height="100000" viewBox="0 0 100000 100000"/>',
    )

    convert_svg_to_png(project, "res://large.svg", "res://bounded.png")

    assert dimensions["width"] * dimensions["height"] <= 100


def test_svg_conversion_preserves_declared_dimensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dimensions: dict[str, int] = {}

    def fake_svg2png(**kwargs: object) -> bytes:
        dimensions["width"] = int(kwargs["output_width"])
        dimensions["height"] = int(kwargs["output_height"])
        return b"bounded-png"

    monkeypatch.setenv("MCP_MAX_PIXELS", "1_000_000")
    monkeypatch.setitem(sys.modules, "cairosvg", SimpleNamespace(svg2png=fake_svg2png))
    project = GodotProject(tmp_path)
    project.safe_write(
        "res://icon.svg",
        b'<svg width="512" height="512" viewBox="0 0 24 24"/>',
    )

    convert_svg_to_png(project, "res://icon.svg", "res://icon.png")

    assert dimensions == {"width": 512, "height": 512}
