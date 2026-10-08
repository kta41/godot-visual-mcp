"""Configurable safety limits for expensive and untrusted asset operations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


@dataclass(frozen=True)
class SafetyLimits:
    max_input_bytes: int = 64 * 1024 * 1024
    max_pixels: int = 16_777_216
    max_frames: int = 128
    max_batch: int = 16
    max_operation_seconds: int = 600
    max_project_bytes: int = 2 * 1024 * 1024 * 1024


def safety_limits() -> SafetyLimits:
    """Read limits from environment, using safe defaults."""
    return SafetyLimits(
        max_input_bytes=_positive_env("MCP_MAX_INPUT_BYTES", SafetyLimits.max_input_bytes),
        max_pixels=_positive_env("MCP_MAX_PIXELS", SafetyLimits.max_pixels),
        max_frames=_positive_env("MCP_MAX_FRAMES", SafetyLimits.max_frames),
        max_batch=_positive_env("MCP_MAX_BATCH", SafetyLimits.max_batch),
        max_operation_seconds=_positive_env(
            "MCP_MAX_OPERATION_SECONDS", SafetyLimits.max_operation_seconds
        ),
        max_project_bytes=_positive_env("MCP_MAX_PROJECT_BYTES", SafetyLimits.max_project_bytes),
    )


def ensure_input_size(size: int) -> None:
    """Reject oversized input before decoding it."""
    if size > safety_limits().max_input_bytes:
        raise ValueError(f"Input exceeds the {safety_limits().max_input_bytes} byte limit")


def ensure_image_dimensions(width: int, height: int) -> None:
    """Reject images that could cause excessive decompression memory use."""
    if width <= 0 or height <= 0 or width * height > safety_limits().max_pixels:
        raise ValueError(f"Image exceeds the {safety_limits().max_pixels} pixel limit")


def ensure_batch(batch: int) -> None:
    """Reject oversized generation batches."""
    if batch <= 0 or batch > safety_limits().max_batch:
        raise ValueError(f"batch must be between 1 and {safety_limits().max_batch}")


def ensure_project_quota(root: Path, incoming_bytes: int) -> None:
    """Reject a write that would exceed the configured project quota."""
    used = sum(
        item.stat().st_size
        for item in root.rglob("*")
        if item.is_file() and ".godot" not in item.parts
    )
    limit = safety_limits().max_project_bytes
    if used + incoming_bytes > limit:
        raise ValueError(f"Project quota of {limit} bytes would be exceeded")
