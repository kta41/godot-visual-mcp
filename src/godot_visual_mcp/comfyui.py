"""ComfyUI adapter and offline post-processing pipeline."""

from __future__ import annotations

import io
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from PIL import Image

from .assets import inspect_asset, validate_asset
from .filesystem import GodotProject


class ComfyUIError(RuntimeError):
    """Raised for actionable ComfyUI adapter failures."""


def _replace_parameters(value: Any, parameters: Mapping[str, object]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_parameters(item, parameters) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_parameters(item, parameters) for item in value]
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}") and value[2:-1] in parameters:
            return parameters[value[2:-1]]
        result = value
        for key, parameter in parameters.items():
            result = result.replace("${" + key + "}", str(parameter))
        return result
    return value


def load_workflow(name: str, workflow_root: Path | None = None) -> dict[str, Any]:
    """Load a workflow resource without allowing paths outside workflows/."""
    root = workflow_root or Path(__file__).parents[2] / "workflows"
    candidate = Path(name)
    if candidate.name != name or candidate.suffix.lower() != ".json":
        candidate = root / f"{name}.json"
    else:
        candidate = root / candidate.name
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ComfyUIError(f"Workflow not found or invalid: {name}") from exc
    if not isinstance(payload, dict):
        raise ComfyUIError(f"Workflow must be a JSON object: {name}")
    return payload


class ComfyUIClient:
    """Small asynchronous adapter for ComfyUI's prompt/history/view API."""

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.endpoint = (endpoint or os.environ.get("COMFYUI_ENDPOINT", "http://127.0.0.1:8188")).rstrip("/")
        self.client = client
        self.timeout = timeout

    async def generate(
        self,
        workflow: dict[str, Any],
        *,
        client_id: str = "godot-visual-mcp",
        poll_interval: float = 1.0,
        timeout: float = 300.0,
    ) -> bytes:
        """Submit a workflow, poll until completion, and retrieve its first image."""
        owns_client = self.client is None
        http_client = self.client or httpx.AsyncClient(timeout=self.timeout)
        try:
            try:
                response = await http_client.post(
                    f"{self.endpoint}/prompt", json={"prompt": workflow, "client_id": client_id}
                )
                response.raise_for_status()
                prompt_id = response.json()["prompt_id"]
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                raise ComfyUIError(f"Could not submit workflow to ComfyUI: {exc}") from exc

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    history_response = await http_client.get(f"{self.endpoint}/history/{prompt_id}")
                    history_response.raise_for_status()
                    history = history_response.json().get(prompt_id)
                except (httpx.HTTPError, TypeError, ValueError) as exc:
                    raise ComfyUIError(f"Could not read ComfyUI job status: {exc}") from exc
                if history and history.get("status", {}).get("status_str") == "error":
                    raise ComfyUIError("ComfyUI rejected the workflow")
                if history and history.get("outputs"):
                    image = _first_output_image(history["outputs"])
                    if image:
                        query = urlencode(
                            {
                                "filename": image["filename"],
                                "subfolder": image.get("subfolder", ""),
                                "type": image.get("type", "output"),
                            }
                        )
                        try:
                            result = await http_client.get(f"{self.endpoint}/view?{query}")
                            result.raise_for_status()
                            return result.content
                        except httpx.HTTPError as exc:
                            raise ComfyUIError(f"Could not retrieve generated image: {exc}") from exc
                await _sleep(poll_interval)
            raise ComfyUIError(f"ComfyUI generation timed out after {timeout:g} seconds")
        finally:
            if owns_client:
                await http_client.aclose()


def _first_output_image(outputs: Any) -> dict[str, Any] | None:
    if not isinstance(outputs, dict):
        return None
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        images = node_output.get("images")
        if isinstance(images, list):
            for image in images:
                if isinstance(image, dict) and isinstance(image.get("filename"), str):
                    return image
    return None


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(max(0.0, seconds))


def _write_image(project: GodotProject, output: str, data: bytes, *, overwrite: bool) -> str:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            png = image.convert("RGBA")
            buffer = io.BytesIO()
            png.save(buffer, format="PNG", optimize=False)
    except (OSError, ValueError) as exc:
        raise ComfyUIError(f"Generated response is not a valid image: {exc}") from exc
    return project.safe_write(output, buffer.getvalue(), overwrite=overwrite)


def _remove_transparent_border(project: GodotProject, path: str, *, overwrite: bool) -> None:
    try:
        with Image.open(io.BytesIO(project.safe_read(path))) as source:
            image = source.convert("RGBA")
            bbox = image.getchannel("A").getbbox()
            if bbox:
                image = image.crop(bbox)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=False)
    except (OSError, ValueError) as exc:
        raise ComfyUIError(f"Could not crop generated image: {exc}") from exc
    project.safe_write(path, buffer.getvalue(), overwrite=overwrite)


def remove_background(project: GodotProject, source: str, output: str, *, overwrite: bool = False) -> dict[str, Any]:
    """Remove a background through optional rembg, preserving a sandboxed output path."""
    try:
        from rembg import remove
    except ImportError as exc:
        raise ComfyUIError("Background removal requires the optional 'ai' extra: pip install .[ai]") from exc
    try:
        result = remove(project.safe_read(source))
    except (OSError, RuntimeError, ValueError) as exc:
        raise ComfyUIError(f"Background removal failed: {exc}") from exc
    written = _write_image(project, output, result, overwrite=overwrite)
    return {"path": written, **inspect_asset(project, output)}


async def generate_asset(
    project: GodotProject,
    prompt: str,
    workflow_name: str,
    output: str,
    *,
    endpoint: str | None = None,
    width: int = 512,
    height: int = 512,
    seed: int | None = None,
    batch: int = 1,
    remove_background_enabled: bool = False,
    crop: bool = True,
    overwrite: bool = False,
    timeout: float = 300.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Generate one asset, optionally post-process it, and validate the res:// result."""
    if not prompt.strip():
        raise ValueError("prompt must be non-empty")
    if width <= 0 or height <= 0 or batch <= 0:
        raise ValueError("width, height, and batch must be positive")
    workflow = _replace_parameters(
        load_workflow(workflow_name),
        {"prompt": prompt, "width": width, "height": height, "seed": seed or 0, "batch": batch},
    )
    generated = await ComfyUIClient(endpoint, client=client).generate(workflow, timeout=timeout)
    written = _write_image(project, output, generated, overwrite=overwrite)
    if remove_background_enabled:
        remove_background_result = globals()["remove_background"]
        remove_background_result(project, written, written, overwrite=True)
    if crop:
        _remove_transparent_border(project, written, overwrite=True)
    validation = validate_asset(project, written)
    if not validation["valid"]:
        raise ComfyUIError(f"Generated asset failed validation: {validation['errors']}")
    return {"path": written, "validation": validation, "workflow": workflow_name}
