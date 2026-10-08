import importlib.util
import io
from pathlib import Path

import httpx
import pytest
from PIL import Image

from godot_visual_mcp.comfyui import ComfyUIClient, ComfyUIError, load_workflow
from godot_visual_mcp.filesystem import GodotProject


def image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (4, 3), (255, 0, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


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
