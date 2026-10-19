import importlib.util
import io
import os
from pathlib import Path

import httpx
import pytest
from PIL import Image

from godot_visual_mcp.comfyui import ComfyUIClient, ComfyUIError, _write_image, load_workflow
from godot_visual_mcp.filesystem import GodotProject


@pytest.fixture(autouse=True)
def configure_comfyui_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYUI_ENDPOINT", "http://comfy")
    monkeypatch.delenv("COMFYUI_ALLOWED_ENDPOINTS", raising=False)


def image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (4, 3), (255, 0, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_comfyui_submit_returns_prompt_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"prompt_id": "job-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        prompt_id = await ComfyUIClient("http://comfy", client=client).submit(
            {"node": {"class_type": "Test"}}, client_id="test-client"
        )

    assert prompt_id == "job-1"
    assert len(requests) == 1
    assert requests[0].url.path == "/prompt"
    assert requests[0].read() == b'{"prompt":{"node":{"class_type":"Test"}},"client_id":"test-client"}'


def test_comfyui_rejects_unconfigured_endpoint() -> None:
    with pytest.raises(ComfyUIError, match="not configured") as error:
        ComfyUIClient("https://attacker.example")
    assert error.value.code == "ENDPOINT_NOT_ALLOWED"


def test_comfyui_allows_explicit_operator_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMFYUI_ALLOWED_ENDPOINTS", "https://gpu.internal:8443/")
    client = ComfyUIClient("https://gpu.internal:8443")
    assert client.endpoint == "https://gpu.internal:8443"


@pytest.mark.parametrize(
    "endpoint",
    ["file:///tmp/comfy", "http://user:secret@comfy:8188", "http://comfy:8188/?token=secret"],
)
def test_comfyui_rejects_unsafe_endpoint_urls(endpoint: str) -> None:
    with pytest.raises(ComfyUIError) as error:
        ComfyUIClient(endpoint)
    assert error.value.code == "ENDPOINT_INVALID"


@pytest.mark.asyncio
async def test_comfyui_submit_poll_and_retrieve() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "job-1"})
        if request.url.path == "/history/job-1":
            return httpx.Response(
                200, json={"job-1": {"outputs": {"9": {"images": [{"filename": "out.png"}]}}}}
            )
        return httpx.Response(200, content=image_bytes(), headers={"content-type": "image/png"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await ComfyUIClient("http://comfy", client=client).generate(
            {"node": {}}, poll_interval=0, timeout=1
        )
    assert result.startswith(b"\x89PNG")
    assert [request.url.path for request in requests] == ["/prompt", "/history/job-1", "/view"]


@pytest.mark.asyncio
async def test_comfyui_returns_all_batch_outputs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "batch-1"})
        if request.url.path == "/history/batch-1":
            return httpx.Response(
                200,
                json={"batch-1": {"outputs": {"9": {"images": [
                    {"filename": "one.png"}, {"filename": "two.png"}
                ]}}}},
            )
        return httpx.Response(200, content=image_bytes())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        images = await ComfyUIClient("http://comfy", client=client).generate_images(
            {}, poll_interval=0, timeout=1
        )
    assert len(images) == 2


@pytest.mark.asyncio
async def test_comfyui_rejects_oversized_generated_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_MAX_INPUT_BYTES", "8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "job-large"})
        if request.url.path == "/history/job-large":
            return httpx.Response(
                200,
                json={"job-large": {"outputs": {"9": {"images": [{"filename": "large.png"}]}}}},
            )
        return httpx.Response(200, content=b"0123456789")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ComfyUIError) as error:
            await ComfyUIClient("http://comfy", client=client).generate_images(
                {}, poll_interval=0, timeout=1
            )

    assert error.value.code == "RESPONSE_TOO_LARGE"


def test_comfyui_rejects_image_over_pixel_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_MAX_PIXELS", "8")
    with pytest.raises(ComfyUIError, match="pixel limit"):
        _write_image(GodotProject(tmp_path), "res://large.png", image_bytes(), overwrite=False)


@pytest.mark.asyncio
async def test_comfyui_cancel_sends_interrupt() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await ComfyUIClient("http://comfy", client=client).cancel("job-1")

    assert requests[0].url.path == "/interrupt"
    assert requests[0].read() == b'{"prompt_id":"job-1"}'


@pytest.mark.asyncio
async def test_comfyui_live_workflow_schema_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = os.environ.get("COMFYUI_INTEGRATION_ENDPOINT")
    if not endpoint:
        pytest.skip("Set COMFYUI_INTEGRATION_ENDPOINT to run live ComfyUI integration")
    monkeypatch.setenv("COMFYUI_ENDPOINT", endpoint)
    validation = await ComfyUIClient().validate_workflow(load_workflow("sprite"))
    assert validation["valid"] is True


@pytest.mark.asyncio
async def test_comfyui_preflight_checks_required_inputs_and_checkpoints() -> None:
    object_info = {
        "CheckpointLoaderSimple": {
            "input": {"required": {"ckpt_name": ["COMBO", {"options": ["base.safetensors"]}]}}
        },
        "KSampler": {"input": {"required": {"seed": ["INT", {"default": 0}]}}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=object_info)

    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "base.safetensors"}},
        "2": {"class_type": "KSampler", "inputs": {"seed": 123}},
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        comfy = ComfyUIClient("http://comfy", client=client)
        assert (await comfy.validate_workflow(workflow))["valid"] is True
        workflow["1"]["inputs"]["ckpt_name"] = "missing.safetensors"
        workflow["2"]["inputs"].pop("seed")
        with pytest.raises(ComfyUIError, match="not installed or supported") as error:
            await comfy.validate_workflow(workflow)

    assert error.value.code == "WORKFLOW_INVALID"


@pytest.mark.asyncio
async def test_comfyui_timeout_is_actionable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "job-1"})
        return httpx.Response(200, json={"job-1": {"outputs": {}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ComfyUIError, match="timed out"):
            await ComfyUIClient("http://comfy", client=client).generate(
                {}, poll_interval=0, timeout=0
            )


def test_workflow_parameters_preserve_types() -> None:
    workflow = load_workflow("sprite")
    assert workflow["4"]["inputs"]["width"] == "${width}"


def test_workflow_rejects_path_escape(tmp_path: Path) -> None:
    (tmp_path / "valid.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ComfyUIError):
        load_workflow("../valid", tmp_path)


def test_remove_background_requires_optional_dependency(tmp_path: Path) -> None:
    if importlib.util.find_spec("rembg") is not None:
        pytest.skip("rembg is installed; the missing-extra path is not applicable")
    project = GodotProject(tmp_path)
    project.safe_write("res://source.png", image_bytes())
    from godot_visual_mcp.comfyui import remove_background

    try:
        remove_background(project, "res://source.png", "res://out.png")
    except ComfyUIError as exc:
        assert "optional 'ai' extra" in str(exc)
