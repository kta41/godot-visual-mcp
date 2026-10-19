"""Offline inspection for common non-image Godot assets."""

from __future__ import annotations

import io
import json
import math
import re
import struct
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PIL import ImageFont

from .filesystem import GodotProject
from .limits import (
    ensure_audio_duration,
    ensure_image_dimensions,
    ensure_input_size,
    safety_limits,
)

_CSS_URL = re.compile(r"url\s*\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
_CSS_URL_START = re.compile(r"url\s*\(", re.IGNORECASE)
_CSS_IMPORT = re.compile(r"@import\b", re.IGNORECASE)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SVG_LENGTH = re.compile(r"^\s*(\d+(?:\.\d*)?|\.\d+)(?:px)?\s*$", re.IGNORECASE)


def _read(project: GodotProject, path: str) -> bytes:
    data = project.safe_read(path)
    ensure_input_size(len(data))
    return data


def inspect_audio(project: GodotProject, path: str) -> dict[str, Any]:
    """Inspect WAV and parse basic OGG/MP3 metadata without external binaries."""
    data = _read(project, path)
    suffix = Path(path).suffix.lower()
    if suffix == ".wav":
        try:
            with wave.open(io.BytesIO(data)) as source:
                duration = source.getnframes() / source.getframerate()
                ensure_audio_duration(duration)
                return {
                    "path": project.validate_asset_path(path),
                    "format": "WAV",
                    "duration_seconds": duration,
                    "channels": source.getnchannels(),
                    "sample_rate": source.getframerate(),
                    "sample_width": source.getsampwidth(),
                    "frames": source.getnframes(),
                }
        except (wave.Error, EOFError, ZeroDivisionError) as exc:
            raise ValueError("Invalid WAV audio") from exc
    if suffix == ".ogg" and data.startswith(b"OggS"):
        sample_rate, duration = _ogg_audio_metadata(data)
        if duration is not None:
            ensure_audio_duration(duration)
        return {
            "path": project.validate_asset_path(path),
            "format": "OGG",
            "sample_rate": sample_rate,
            "duration_seconds": duration,
        }
    if suffix == ".mp3" and (data.startswith(b"ID3") or _has_mp3_sync(data)):
        sample_rate, duration = _mp3_audio_metadata(data)
        if duration is not None:
            ensure_audio_duration(duration)
        return {
            "path": project.validate_asset_path(path),
            "format": "MP3",
            "sample_rate": sample_rate,
            "duration_seconds": duration,
        }
    raise ValueError("Unsupported or corrupt audio; expected WAV, OGG, or MP3")


def _has_mp3_sync(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0


def _ogg_audio_metadata(data: bytes) -> tuple[int | None, float | None]:
    sample_rate: int | None = None
    pre_skip = 0
    is_opus = False
    last_granule: int | None = None
    offset = 0
    while offset + 27 <= len(data):
        if data[offset:offset + 4] != b"OggS":
            break
        page = offset
        segment_count = data[page + 26]
        table_end = page + 27 + segment_count
        if table_end > len(data):
            break
        body_length = sum(data[page + 27:table_end])
        page_end = table_end + body_length
        if page_end > len(data):
            break
        packet = data[table_end:page_end]
        if sample_rate is None:
            vorbis = packet.find(b"\x01vorbis")
            opus = packet.find(b"OpusHead")
            if vorbis >= 0 and len(packet) >= vorbis + 16:
                sample_rate = struct.unpack_from("<I", packet, vorbis + 12)[0]
            elif opus >= 0 and len(packet) >= opus + 12:
                is_opus = True
                pre_skip = struct.unpack_from("<H", packet, opus + 10)[0]
                sample_rate = 48000
        granule = struct.unpack_from("<Q", data, page + 6)[0]
        if granule != 0xFFFFFFFFFFFFFFFF:
            last_granule = granule
        offset = page_end
    if sample_rate is None or sample_rate <= 0 or last_granule is None:
        return sample_rate, None
    samples = max(0, last_granule - pre_skip) if is_opus else last_granule
    return sample_rate, samples / sample_rate


def _mp3_audio_metadata(data: bytes) -> tuple[int | None, float | None]:
    offset = 0
    if data.startswith(b"ID3") and len(data) >= 10:
        tag_size = sum((data[index] & 0x7F) << shift for index, shift in zip(range(6, 10), (21, 14, 7, 0)))
        offset = 10 + tag_size + (10 if data[5] & 0x10 else 0)

    sample_rates = (44100, 48000, 32000)
    mpeg1_bitrates = {
        1: (0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448),
        2: (0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384),
        3: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
    }
    mpeg2_bitrates = {
        1: (0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256),
        2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
        3: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
    }
    duration = 0.0
    max_audio_seconds = safety_limits().max_audio_seconds
    detected_rate: int | None = None
    frames = 0
    while offset + 4 <= len(data):
        header = int.from_bytes(data[offset:offset + 4], "big")
        version = (header >> 19) & 0x03
        layer = (header >> 17) & 0x03
        bitrate_index = (header >> 12) & 0x0F
        rate_index = (header >> 10) & 0x03
        if (header >> 21) & 0x7FF != 0x7FF or version == 1 or layer == 0 or rate_index == 3:
            offset += 1
            continue
        layer_number = 4 - layer
        bitrate_table = mpeg1_bitrates if version == 3 else mpeg2_bitrates
        bitrates = bitrate_table[layer_number]
        if bitrate_index == 0 or bitrate_index >= len(bitrates):
            offset += 1
            continue
        rate = sample_rates[rate_index]
        if version == 2:
            rate //= 2
        elif version == 0:
            rate //= 4
        bitrate = bitrates[bitrate_index] * 1000
        padding = (header >> 9) & 1
        if layer_number == 1:
            frame_size = (12 * bitrate // rate + padding) * 4
            samples_per_frame = 384
        elif layer_number == 3:
            frame_size = ((144 if version == 3 else 72) * bitrate // rate) + padding
            samples_per_frame = 1152 if version == 3 else 576
        else:
            frame_size = (144 * bitrate // rate) + padding
            samples_per_frame = 1152
        if frame_size < 4 or offset + frame_size > len(data):
            break
        duration += samples_per_frame / rate
        detected_rate = detected_rate or rate
        frames += 1
        if duration > max_audio_seconds:
            ensure_audio_duration(duration)
        offset += frame_size
    return detected_rate, duration if frames else None


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
    for element in root.iter():
        values = list(element.attrib.items())
        if element.tag.rsplit("}", 1)[-1].lower() == "style" and element.text:
            values.append(("style", element.text))
        for attribute, value in values:
            name = attribute.rsplit("}", 1)[-1].lower()
            reference = value.strip()
            if name in {"href", "src"} and reference and not reference.startswith("#"):
                raise ValueError("External SVG references are not allowed")
            if "\\" in value:
                raise ValueError("External SVG references with CSS escapes are not allowed")
            css = _CSS_COMMENT.sub("", value)
            if _CSS_IMPORT.search(css):
                raise ValueError("External SVG references are not allowed")
            starts = list(_CSS_URL_START.finditer(css))
            urls = list(_CSS_URL.finditer(css))
            if len(starts) != len(urls) or any(
                not match.group(2).strip().startswith("#") for match in urls
            ):
                raise ValueError("External SVG references are not allowed")
    return {
        "path": project.validate_asset_path(path),
        "format": "SVG",
        "width": root.attrib.get("width"),
        "height": root.attrib.get("height"),
        "view_box": root.attrib.get("viewBox"),
        "root": root.tag.rsplit("}", 1)[-1],
    }


def _bounded_svg_size(root: ET.Element) -> tuple[int, int]:
    view_box = root.attrib.get("viewBox", "")
    try:
        view_values = [float(value) for value in re.split(r"[\s,]+", view_box.strip())]
    except ValueError:
        view_values = []
    view_size = None
    if (
        len(view_values) == 4
        and math.isfinite(view_values[2])
        and math.isfinite(view_values[3])
        and view_values[2] > 0
        and view_values[3] > 0
    ):
        view_size = (view_values[2], view_values[3])

    dimensions = []
    for key in ("width", "height"):
        match = _SVG_LENGTH.fullmatch(root.attrib.get(key, ""))
        dimension = float(match.group(1)) if match else None
        dimensions.append(dimension if dimension and math.isfinite(dimension) else None)
    width, height = dimensions
    if width is None and height is None:
        width, height = view_size or (300.0, 150.0)
    elif width is None:
        assert height is not None
        width = height * view_size[0] / view_size[1] if view_size else height * 2
    elif height is None:
        assert width is not None
        height = width * view_size[1] / view_size[0] if view_size else width / 2
    assert width is not None and height is not None

    max_pixels = safety_limits().max_pixels
    max_dimension = min(4096, max(1, int(math.sqrt(max_pixels))))
    scale = min(
        1.0,
        max_dimension / max(width, height),
        math.sqrt(max_pixels / width / height),
    )
    output_width = max(1, int(width * scale))
    output_height = max(1, int(height * scale))
    ensure_image_dimensions(output_width, output_height)
    return output_width, output_height


def convert_svg_to_png(
    project: GodotProject, source: str, output: str, *, overwrite: bool = False
) -> dict[str, Any]:
    """Convert a validated SVG using the optional, offline CairoSVG library."""
    inspect_svg(project, source)
    try:
        import cairosvg
    except ImportError as exc:
        raise RuntimeError("SVG conversion requires the optional 'cairosvg' package") from exc
    data = _read(project, source)
    root = ET.fromstring(data)
    output_width, output_height = _bounded_svg_size(root)
    png = cairosvg.svg2png(
        bytestring=data, output_width=output_width, output_height=output_height
    )
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
