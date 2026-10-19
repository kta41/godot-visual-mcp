"""ComfyUI adapter and offline post-processing pipeline."""

from __future__ import annotations

import io
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from PIL import Image

from .assets import inspect_asset, validate_asset
from .filesystem import GodotProject
from .limits import ensure_batch, ensure_image_dimensions, ensure_input_size, safety_limits

DEFAULT_COMFYUI_ENDPOINT = "http://127.0.0.1:8188"


def _normalize_endpoint(endpoint: str) -> str:
    try:
        parsed = urlsplit(endpoint.strip())
        port = parsed.port
    except (AttributeError, ValueError) as exc:
        raise ComfyUIError("Invalid ComfyUI endpoint URL", code="ENDPOINT_INVALID") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ComfyUIError(
            "ComfyUI endpoint must be an HTTP(S) URL without credentials, query, or fragment",
            code="ENDPOINT_INVALID",
        )
    hostname = parsed.hostname.lower()
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 80 if parsed.scheme.lower() == "http" else 443
    if port is not None and port != default_port:
        netloc = f"{netloc}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _resolve_comfyui_endpoint(requested: str | None) -> str:
    configured = os.environ.get("COMFYUI_ENDPOINT", DEFAULT_COMFYUI_ENDPOINT)
    configured_endpoint = _normalize_endpoint(configured)
    allowed = {configured_endpoint}
    allowed.update(
        _normalize_endpoint(item)
        for item in os.environ.get("COMFYUI_ALLOWED_ENDPOINTS", "").split(",")
        if item.strip()
    )
    if requested is None:
        return configured_endpoint
    requested_endpoint = _normalize_endpoint(requested)
    if requested_endpoint not in allowed:
        raise ComfyUIError(
            "ComfyUI endpoint is not configured; set COMFYUI_ENDPOINT or add it to "
            "COMFYUI_ALLOWED_ENDPOINTS",
            code="ENDPOINT_NOT_ALLOWED",
        )
    return requested_endpoint


async def _read_bounded_response(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> bytes:
    limit = safety_limits().max_input_bytes
    async with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise ComfyUIError(
                    "ComfyUI returned an invalid content length", code="RESPONSE_INVALID"
                ) from exc
            if declared_size > limit:
                raise ComfyUIError(
                    f"ComfyUI response exceeds the {limit} byte limit",
                    code="RESPONSE_TOO_LARGE",
                )
        content = bytearray()
        async for chunk in response.aiter_bytes():
            if len(content) + len(chunk) > limit:
                raise ComfyUIError(
                    f"ComfyUI response exceeds the {limit} byte limit",
                    code="RESPONSE_TOO_LARGE",
                )
            content.extend(chunk)
        return bytes(content)


class ComfyUIError(RuntimeError):
    """Raised for actionable ComfyUI adapter failures."""

    def __init__(self, message: str, *, code: str = "COMFYUI_ERROR", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


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
    root = workflow_root or Path(__file__).parent / "resources" / "workflows"
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
        self.endpoint = _resolve_comfyui_endpoint(endpoint)
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
        images = await self.generate_images(
            workflow,
            client_id=client_id,
            poll_interval=poll_interval,
            timeout=timeout,
        )
        if not images:
            raise ComfyUIError("ComfyUI completed without image outputs", code="NO_OUTPUT")
        return images[0]

    async def validate_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """Validate node class names against ComfyUI when its schema endpoint exists."""
        http_client, owns_client = self._client()
        try:
            try:
                response_content = await _read_bounded_response(
                    http_client, "GET", f"{self.endpoint}/object_info"
                )
                object_info = json.loads(response_content)
            except (httpx.HTTPError, ValueError) as exc:
                raise ComfyUIError(
                    f"Could not validate workflow against ComfyUI: {exc}",
                    code="WORKFLOW_SCHEMA_UNAVAILABLE",
                    retryable=True,
                ) from exc
            if not isinstance(object_info, dict):
                raise ComfyUIError(
                    "ComfyUI returned an invalid workflow schema",
                    code="WORKFLOW_SCHEMA_INVALID",
                )
            issues: list[str] = []
            for node_id, node in workflow.items():
                if not isinstance(node, dict) or not isinstance(node.get("class_type"), str):
                    issues.append(f"{node_id}: missing class_type")
                    continue
                class_type = node["class_type"]
                node_schema = object_info.get(class_type)
                if not isinstance(node_schema, dict):
                    issues.append(f"{node_id}: unavailable node {class_type}")
                    continue
                node_inputs = node.get("inputs")
                if not isinstance(node_inputs, dict):
                    issues.append(f"{node_id}: inputs must be an object")
                    continue
                input_schema = node_schema.get("input", {})
                required_inputs = input_schema.get("required", {}) if isinstance(input_schema, dict) else {}
                if not isinstance(required_inputs, dict):
                    issues.append(f"{node_id}: invalid required-input schema")
                    continue
                for input_name, specification in required_inputs.items():
                    if input_name not in node_inputs or node_inputs[input_name] is None:
                        issues.append(f"{node_id}: missing required input {input_name}")
                        continue
                    if isinstance(specification, list) and len(specification) > 1:
                        details = specification[1]
                        options = details.get("options") if isinstance(details, dict) else None
                        value = node_inputs[input_name]
                        if isinstance(options, list) and not isinstance(value, list) and value not in options:
                            issues.append(
                                f"{node_id}: {input_name} value {value!r} is not installed or supported"
                            )
            if issues:
                raise ComfyUIError(
                    f"Workflow preflight failed: {'; '.join(issues[:20])}",
                    code="WORKFLOW_INVALID",
                )
            return {"valid": True, "nodes": len(workflow)}
        finally:
            if owns_client:
                await http_client.aclose()

    async def submit(self, workflow: dict[str, Any], *, client_id: str = "godot-visual-mcp") -> str:
        """Submit a workflow and return its prompt id."""
        http_client, owns_client = self._client()
        try:
            try:
                response_content = await _read_bounded_response(
                    http_client,
                    "POST",
                    f"{self.endpoint}/prompt",
                    json={"prompt": workflow, "client_id": client_id},
                )
                prompt_id = json.loads(response_content)["prompt_id"]
                if not isinstance(prompt_id, str) or not prompt_id:
                    raise TypeError("prompt_id must be a non-empty string")
                return prompt_id
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                raise ComfyUIError(
                    f"Could not submit workflow to ComfyUI: {exc}",
                    code="SUBMIT_FAILED",
                    retryable=True,
                ) from exc
        finally:
            if owns_client:
                await http_client.aclose()

    async def cancel(self, prompt_id: str) -> None:
        """Interrupt a running ComfyUI prompt."""
        http_client, owns_client = self._client()
        try:
            try:
                await _read_bounded_response(
                    http_client,
                    "POST",
                    f"{self.endpoint}/interrupt",
                    json={"prompt_id": prompt_id},
                )
            except httpx.HTTPError as exc:
                raise ComfyUIError(f"Could not cancel ComfyUI job: {exc}", code="CANCEL_FAILED") from exc
        finally:
            if owns_client:
                await http_client.aclose()

    async def generate_images(
        self,
        workflow: dict[str, Any],
        *,
        client_id: str = "godot-visual-mcp",
        poll_interval: float = 1.0,
        timeout: float = 300.0,
        retries: int = 0,
        on_progress: Any = None,
    ) -> list[bytes]:
        """Submit, poll, and retrieve all image outputs from a workflow."""
        http_client, owns_client = self._client()
        try:
            attempt = 0
            while True:
                try:
                    response_content = await _read_bounded_response(
                        http_client,
                        "POST",
                        f"{self.endpoint}/prompt",
                        json={"prompt": workflow, "client_id": client_id},
                    )
                    prompt_id = json.loads(response_content)["prompt_id"]
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        try:
                            history_content = await _read_bounded_response(
                                http_client, "GET", f"{self.endpoint}/history/{prompt_id}"
                            )
                            history = json.loads(history_content).get(prompt_id)
                        except (httpx.HTTPError, AttributeError, TypeError, ValueError) as exc:
                            raise ComfyUIError(
                                f"Could not read ComfyUI job status: {exc}",
                                code="STATUS_FAILED",
                                retryable=True,
                            ) from exc
                        if on_progress is not None and history:
                            on_progress(history)
                        if history and history.get("status", {}).get("status_str") == "error":
                            raise ComfyUIError("ComfyUI rejected the workflow", code="WORKFLOW_FAILED")
                        if history and history.get("outputs"):
                            images = _all_output_images(history["outputs"])
                            return [
                                await self._retrieve(http_client, image)
                                for image in images
                            ]
                        await _sleep(poll_interval)
                    raise ComfyUIError(
                        f"ComfyUI generation timed out after {timeout:g} seconds",
                        code="COMFYUI_TIMEOUT",
                        retryable=True,
                    )
                except httpx.HTTPError as exc:
                    if attempt >= retries:
                        raise ComfyUIError(
                            f"ComfyUI request failed: {exc}",
                            code="COMFYUI_REQUEST_FAILED",
                            retryable=True,
                        ) from exc
                    attempt += 1
                    await _sleep(min(2**attempt, 10))
                except ComfyUIError as exc:
                    if not exc.retryable or attempt >= retries:
                        raise
                    attempt += 1
                    await _sleep(min(2**attempt, 10))
        finally:
            if owns_client:
                await http_client.aclose()

    def _client(self) -> tuple[httpx.AsyncClient, bool]:
        return self.client or httpx.AsyncClient(timeout=self.timeout), self.client is None

    async def _retrieve(self, client: httpx.AsyncClient, image: dict[str, Any]) -> bytes:
        query = urlencode(
            {
                "filename": image["filename"],
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            }
        )
        try:
            return await _read_bounded_response(
                client, "GET", f"{self.endpoint}/view?{query}"
            )
        except httpx.HTTPError as exc:
            raise ComfyUIError(f"Could not retrieve generated image: {exc}", code="RETRIEVE_FAILED") from exc


def _first_output_image(outputs: Any) -> dict[str, Any] | None:
    images = _all_output_images(outputs)
    return images[0] if images else None


def _all_output_images(outputs: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(outputs, dict):
        return result
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        images = node_output.get("images")
        if isinstance(images, list):
            for image in images:
                if isinstance(image, dict) and isinstance(image.get("filename"), str):
                    result.append(image)
    return result


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(max(0.0, seconds))


def _write_image(project: GodotProject, output: str, data: bytes, *, overwrite: bool) -> str:
    ensure_input_size(len(data))
    try:
        with Image.open(io.BytesIO(data)) as image:
            ensure_image_dimensions(image.width, image.height)
            image.load()
            png = image.convert("RGBA")
            buffer = io.BytesIO()
            png.save(buffer, format="PNG", optimize=False)
    except (OSError, ValueError) as exc:
        raise ComfyUIError(f"Generated response is not a valid image: {exc}") from exc
    return project.safe_write(output, buffer.getvalue(), overwrite=overwrite)


def _remove_transparent_border(project: GodotProject, path: str, *, overwrite: bool) -> None:
    try:
        data = project.safe_read(path)
        ensure_input_size(len(data))
        with Image.open(io.BytesIO(data)) as source:
            ensure_image_dimensions(source.width, source.height)
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
        raise ComfyUIError("Background removal requires the optional 'ai' extra: uv sync --extra ai") from exc
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
    retries: int = 0,
    validate_workflow: bool = False,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Generate one asset, optionally post-process it, and validate the res:// result."""
    if not prompt.strip():
        raise ValueError("prompt must be non-empty")
    ensure_image_dimensions(width, height)
    ensure_batch(batch)
    if timeout <= 0 or timeout > safety_limits().max_operation_seconds:
        raise ValueError(
            f"timeout must be between 0 and {safety_limits().max_operation_seconds} seconds"
        )
    workflow = _replace_parameters(
        load_workflow(workflow_name),
        {"prompt": prompt, "width": width, "height": height, "seed": seed or 0, "batch": batch},
    )
    comfy = ComfyUIClient(endpoint, client=client)
    workflow_validation: dict[str, Any] | None = None
    if validate_workflow:
        workflow_validation = await comfy.validate_workflow(workflow)
    generated_images = await comfy.generate_images(workflow, timeout=timeout, retries=retries)
    output_path = Path(output.removeprefix("res://"))
    generated_paths: list[str] = []
    for index, generated in enumerate(generated_images, start=1):
        candidate = output if index == 1 else str(
            output_path.with_name(f"{output_path.stem}-{index}{output_path.suffix or '.png'}")
        )
        generated_paths.append(_write_image(project, candidate, generated, overwrite=overwrite))
    written = generated_paths[0]
    if remove_background_enabled:
        remove_background_result = globals()["remove_background"]
        remove_background_result(project, written, written, overwrite=True)
    if crop:
        _remove_transparent_border(project, written, overwrite=True)
    validation = validate_asset(project, written)
    if not validation["valid"]:
        raise ComfyUIError(f"Generated asset failed validation: {validation['errors']}")
    return {
        "path": written,
        "outputs": generated_paths,
        "output_count": len(generated_paths),
        "validation": validation,
        "workflow": workflow_name,
        "workflow_validation": workflow_validation,
    }
