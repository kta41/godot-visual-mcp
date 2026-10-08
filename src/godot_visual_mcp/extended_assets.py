"""Offline inspection for common non-image Godot assets."""

from __future__ import annotations

import io
import json
import struct
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PIL import ImageFont

from .filesystem import GodotProject


def _read(project: GodotProject, path: str) -> bytes:
    data = project.safe_read(path)
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("Asset exceeds the 64 MiB inspection limit")
    return data


def inspect_audio(project: GodotProject, path: str) -> dict[str, Any]:
    """Inspect WAV and parse basic OGG/MP3 metadata without external binaries."""
    data = _read(project, path)
    suffix = Path(path).suffix.lower()
    if suffix == ".wav":
        try:
            with wave.open(io.BytesIO(data)) as source:
                return {
                    "path": project.validate_asset_path(path),
                    "format": "WAV",
                    "duration_seconds": source.getnframes() / source.getframerate(),
                    "channels": source.getnchannels(),
                    "sample_rate": source.getframerate(),
                    "sample_width": source.getsampwidth(),
                    "frames": source.getnframes(),
                }
        except (wave.Error, EOFError) as exc:
            raise ValueError("Invalid WAV audio") from exc
    if suffix == ".ogg" and data.startswith(b"OggS"):
        sample_rate = None
        if data[0:4] == b"OggS":
            vorbis = data.find(b"\x01vorbis")
            if vorbis >= 0 and len(data) >= vorbis + 16:
                sample_rate = struct.unpack_from("<I", data, vorbis + 12)[0]
        return {"path": project.validate_asset_path(path), "format": "OGG", "sample_rate": sample_rate}
    if suffix == ".mp3" and (data.startswith(b"ID3") or _has_mp3_sync(data)):
        return {"path": project.validate_asset_path(path), "format": "MP3", "sample_rate": _mp3_sample_rate(data)}
    raise ValueError("Unsupported or corrupt audio; expected WAV, OGG, or MP3")


def _has_mp3_sync(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0


def _mp3_sample_rate(data: bytes) -> int | None:
    offset = 10 if data.startswith(b"ID3") and len(data) >= 10 else 0
    if len(data) < offset + 4 or data[offset] != 0xFF:
        return None
    version = (data[offset + 1] >> 3) & 0x03
    index = (data[offset + 2] >> 2) & 0x03
    tables = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}
    return tables.get(version, [])[index] if index < 3 else None


def inspect_font(project: GodotProject, path: str) -> dict[str, Any]:
    """Validate a TTF/OTF and return metrics available through Pillow."""
    data = _read(project, path)
    if Path(path).suffix.lower() not in {".ttf", ".otf"}:
        raise ValueError("Unsupported font; expected TTF or OTF")
    try:
        font = ImageFont.truetype(io.BytesIO(data), 16)
        return {
            "path": project.validate_asset_path(path),
            "format": Path(path).suffix[1:].upper(),
            "family": font.getname()[0],
            "style": font.getname()[1],
            "bbox": font.getbbox("Ag"),
        }
    except (OSError, ValueError) as exc:
        raise ValueError("Invalid TTF or OTF font") from exc


def inspect_svg(project: GodotProject, path: str) -> dict[str, Any]:
    """Validate SVG XML and reject external references."""
    data = _read(project, path)
    if Path(path).suffix.lower() != ".svg":
        raise ValueError("Expected an SVG asset")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("Invalid SVG XML") from exc
    serialized = data.decode("utf-8", errors="ignore").lower()
    external_markers = ("href=\"http://", "href=\"https://", "href=\"file:", "href=\"data:")
    if any(marker in serialized for marker in external_markers):
        raise ValueError("External SVG references are not allowed")
    return {
        "path": project.validate_asset_path(path),
        "format": "SVG",
        "width": root.attrib.get("width"),
        "height": root.attrib.get("height"),
        "view_box": root.attrib.get("viewBox"),
        "root": root.tag.rsplit("}", 1)[-1],
    }


def convert_svg_to_png(
    project: GodotProject, source: str, output: str, *, overwrite: bool = False
) -> dict[str, Any]:
    """Convert a validated SVG using the optional, offline CairoSVG library."""
    inspect_svg(project, source)
    try:
        import cairosvg
    except ImportError as exc:
        raise RuntimeError("SVG conversion requires the optional 'cairosvg' package") from exc
    png = cairosvg.svg2png(bytestring=_read(project, source))
    written = project.safe_write(output, png, overwrite=overwrite)
    return {"path": written, "source": project.validate_asset_path(source), "format": "PNG"}


def inspect_3d_asset(project: GodotProject, path: str) -> dict[str, Any]:
    """Inspect GLTF JSON or GLB containers and validate internal references."""
    data = _read(project, path)
    suffix = Path(path).suffix.lower()
    if suffix == ".gltf":
        try:
            document = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid glTF JSON") from exc
        if not isinstance(document, dict):
            raise ValueError("glTF root must be an object")
        references = [item.get("uri") for item in document.get("buffers", []) if isinstance(item, dict)]
        references += [item.get("uri") for item in document.get("images", []) if isinstance(item, dict)]
        base = Path(path.removeprefix("res://")).parent
        missing = [
            ref for ref in references
            if isinstance(ref, str)
            and not ref.startswith("data:")
            and not project.resolve_res_path("res://" + (base / ref).as_posix()).is_file()
        ]
        return _gltf_summary(project, path, document, missing)
    if suffix == ".glb" and data[:4] == b"glTF" and len(data) >= 12:
        version, length = struct.unpack_from("<II", data, 4)
        return {"path": project.validate_asset_path(path), "format": "GLB", "version": version, "bytes": length}
    raise ValueError("Unsupported 3D asset; expected GLTF or GLB")


def _gltf_summary(project: GodotProject, path: str, document: dict[str, Any], missing: list[str]) -> dict[str, Any]:
    return {
        "path": project.validate_asset_path(path),
        "format": "GLTF",
        "version": document.get("asset", {}).get("version") if isinstance(document.get("asset"), dict) else None,
        "meshes": len(document.get("meshes", [])),
        "materials": len(document.get("materials", [])),
        "animations": len(document.get("animations", [])),
        "textures": len(document.get("images", [])),
        "missing_references": missing,
        "valid": not missing,
    }


def inspect_json_asset(project: GodotProject, path: str) -> dict[str, Any]:
    """Parse a bounded JSON resource without executing or resolving references."""
    try:
        payload = json.loads(_read(project, path))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON asset") from exc
    return {
        "path": project.validate_asset_path(path),
        "format": "JSON",
        "root_type": type(payload).__name__,
        "keys": sorted(payload) if isinstance(payload, dict) else [],
    }
