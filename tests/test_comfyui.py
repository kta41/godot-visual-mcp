import importlib.util
import io
import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from godot_visual_mcp.comfyui import (
    WORKFLOW_CATALOG,
    ComfyUIClient,
    ComfyUIError,
    _write_image,
    generate_asset,
    list_workflows,
    load_workflow,
    prepare_workflow,
)
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


def test_all_28_workflows_are_synced_and_cataloged() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    root_workflows_dir = repo_root / "workflows"
    package_workflows_dir = repo_root / "src" / "godot_visual_mcp" / "resources" / "workflows"

    root_files = sorted(path.name for path in root_workflows_dir.glob("*.json"))
    package_files = sorted(path.name for path in package_workflows_dir.glob("*.json"))

    assert len(root_files) == 28
    assert root_files == package_files
    assert {name.removesuffix(".json") for name in root_files} == set(WORKFLOW_CATALOG.keys())

    for filename in root_files:
        root_payload = json.loads((root_workflows_dir / filename).read_text(encoding="utf-8"))
        pkg_payload = json.loads((package_workflows_dir / filename).read_text(encoding="utf-8"))
        assert root_payload == pkg_payload
        assert "2" in root_payload
        assert root_payload["2"]["class_type"] == "LoraLoader"

    all_entries = list_workflows()
    assert len(all_entries) == 28
    lora_entries = list_workflows(category="advanced_lora_and_control")
    assert len(lora_entries) == 5


def test_prepare_workflow_handles_lora_bypass_and_activation() -> None:
    # Without LoRA: LoraLoader node "2" is bypassed and rewired to CheckpointLoaderSimple "1"
    without_lora = prepare_workflow("sprite", prompt="iron shield", width=256, height=256, seed=42)
    assert "2" not in without_lora
    assert without_lora["3"]["inputs"]["clip"] == ["1", 1]
    assert without_lora["6"]["inputs"]["model"] == ["1", 0]
    assert without_lora["4"]["inputs"]["width"] == 256
    assert without_lora["6"]["inputs"]["seed"] == 42

    # With LoRA: LoraLoader node "2" stays active with configured weights
    with_lora = prepare_workflow(
        "sprite",
        prompt="iron shield",
        lora_name="pixel_art_v1.safetensors",
        lora_strength_model=0.85,
        lora_strength_clip=0.75,
    )
    assert "2" in with_lora
    assert with_lora["2"]["class_type"] == "LoraLoader"
    assert with_lora["2"]["inputs"]["lora_name"] == "pixel_art_v1.safetensors"
    assert with_lora["2"]["inputs"]["strength_model"] == 0.85
    assert with_lora["2"]["inputs"]["strength_clip"] == 0.75
    assert with_lora["3"]["inputs"]["clip"] == ["2", 1]
    assert with_lora["6"]["inputs"]["model"] == ["2", 0]

    # Dual-LoRA workflow chains both LoraLoader nodes "2" and "2b"
    dual_lora = prepare_workflow(
        "lora_dual_style_character",
        prompt="arcane knight",
        lora_name="style_pixel.safetensors",
        secondary_lora_name="knight_palette.safetensors",
    )
    assert "2" in dual_lora and "2b" in dual_lora
    assert dual_lora["2b"]["inputs"]["model"] == ["2", 0]
    assert dual_lora["2b"]["inputs"]["clip"] == ["2", 1]
    assert dual_lora["6"]["inputs"]["model"] == ["2b", 0]


@pytest.mark.asyncio
async def test_all_prepared_workflows_pass_preflight_validation() -> None:
    object_info = {
        "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": ["STRING", {}]}}},
        "LoraLoader": {
            "input": {
                "required": {
                    "model": ["MODEL"],
                    "clip": ["CLIP"],
                    "lora_name": ["STRING", {}],
                    "strength_model": ["FLOAT", {}],
                    "strength_clip": ["FLOAT", {}],
                }
            }
        },
        "CLIPTextEncode": {"input": {"required": {"text": ["STRING", {}], "clip": ["CLIP"]}}},
        "EmptyLatentImage": {
            "input": {
                "required": {
                    "width": ["INT", {}],
                    "height": ["INT", {}],
                    "batch_size": ["INT", {}],
                }
            }
        },
        "KSampler": {
            "input": {
                "required": {
                    "model": ["MODEL"],
                    "seed": ["INT", {}],
                    "steps": ["INT", {}],
                    "cfg": ["FLOAT", {}],
                    "sampler_name": ["STRING", {}],
                    "scheduler": ["STRING", {}],
                    "positive": ["CONDITIONING"],
                    "negative": ["CONDITIONING"],
                    "latent_image": ["LATENT"],
                    "denoise": ["FLOAT", {}],
                }
            }
        },
        "VAEDecode": {"input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}}},
        "SaveImage": {"input": {"required": {"images": ["IMAGE"], "filename_prefix": ["STRING", {}]}}},
        "LoadImage": {"input": {"required": {"image": ["STRING", {}]}}},
        "ImageScale": {
            "input": {
                "required": {
                    "image": ["IMAGE"],
                    "upscale_method": ["STRING", {}],
                    "width": ["INT", {}],
                    "height": ["INT", {}],
                    "crop": ["STRING", {}],
                }
            }
        },
        "VAEEncode": {"input": {"required": {"pixels": ["IMAGE"], "vae": ["VAE"]}}},
        "ControlNetLoader": {"input": {"required": {"control_net_name": ["STRING", {}]}}},
        "ControlNetApplyAdvanced": {
            "input": {
                "required": {
                    "positive": ["CONDITIONING"],
                    "negative": ["CONDITIONING"],
                    "control_net": ["CONTROL_NET"],
                    "image": ["IMAGE"],
                    "strength": ["FLOAT", {}],
                    "start_percent": ["FLOAT", {}],
                    "end_percent": ["FLOAT", {}],
                }
            }
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=object_info)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        comfy = ComfyUIClient("http://comfy", client=client)
        for name in WORKFLOW_CATALOG:
            prepared = prepare_workflow(name, prompt="test asset", lora_name="test_lora.safetensors")
            serialized = json.dumps(prepared)
            assert "${" not in serialized, f"Unresolved placeholder in workflow {name}"
            result = await comfy.validate_workflow(prepared)
            assert result["valid"] is True


@pytest.mark.asyncio
async def test_generate_asset_with_lora_downscale_and_palette(tmp_path: Path) -> None:
    submitted_prompts: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            body = json.loads(request.read().decode("utf-8"))
            submitted_prompts.append(body["prompt"])
            return httpx.Response(200, json={"prompt_id": "job-lora"})
        if request.url.path == "/history/job-lora":
            return httpx.Response(
                200,
                json={"job-lora": {"outputs": {"8": {"images": [{"filename": "out.png"}]}}}},
            )
        buffer = io.BytesIO()
        Image.new("RGBA", (16, 16), (250, 10, 10, 255)).save(buffer, format="PNG")
        return httpx.Response(200, content=buffer.getvalue(), headers={"content-type": "image/png"})

    project = GodotProject(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await generate_asset(
            project,
            "crimson potion",
            "item_loot",
            "res://potion.png",
            width=64,
            height=64,
            lora_name="pixel_items.safetensors",
            lora_strength_model=0.9,
            target_width=8,
            target_height=8,
            palette="pico8",
            crop=False,
            client=client,
        )

    assert result["validation"]["valid"] is True
    assert submitted_prompts[0]["2"]["inputs"]["lora_name"] == "pixel_items.safetensors"
    with Image.open(tmp_path / "potion.png") as output_img:
        assert output_img.size == (8, 8)
