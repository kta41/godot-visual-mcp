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
from .processing import apply_palette
from .visual import resize_asset

DEFAULT_COMFYUI_ENDPOINT = "http://127.0.0.1:8188"
DEFAULT_CHECKPOINT_NAME = "v1-5-pruned-emaonly.safetensors"
DEFAULT_CONTROLNET_NAME = "control_v11p_sd15_openpose.pth"

WORKFLOW_CATALOG: dict[str, dict[str, Any]] = {
    "character": {
        "category": "characters",
        "description": "Full-body 2D hero or NPC character with readable silhouette on solid background.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "character_portrait": {
        "category": "characters",
        "description": "Expressive 2D bust portrait for RPG dialogue boxes and character avatars.",
        "godot_target_node": "TextureRect",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [128, 128],
        "recommended_remove_background": True,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "character_turnaround": {
        "category": "characters",
        "description": "Multi-view 2D character turnaround sheet (front, side, back) with aligned height.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [768, 512],
        "recommended_target_size": [384, 256],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "enemy_monster": {
        "category": "characters",
        "description": "2D enemy creature or boss sprite with high contrast and action-ready silhouette.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [96, 96],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "sprite": {
        "category": "sprites_and_vfx",
        "description": "General-purpose 2D / pixel-art entity or object sprite isolated on flat background.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "spritesheet_strip": {
        "category": "sprites_and_vfx",
        "description": "Horizontal strip of sequential 2D animation frames for SpriteFrames resources.",
        "godot_target_node": "AnimatedSprite2D",
        "recommended_generation_size": [1024, 256],
        "recommended_target_size": [256, 64],
        "recommended_remove_background": True,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "vfx_effect": {
        "category": "sprites_and_vfx",
        "description": "Stylized 2D combat VFX, slash, explosion, fire, or magic impact effect.",
        "godot_target_node": "AnimatedSprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [128, 128],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "projectile_hazard": {
        "category": "sprites_and_vfx",
        "description": "Directional 2D projectile, bullet, spell bolt, or stage hazard for Area2D hitboxes.",
        "godot_target_node": "Area2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [32, 32],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "particle_mask_alpha": {
        "category": "sprites_and_vfx",
        "description": "Monochrome white-on-black alpha mask texture for Godot GPUParticles2D color ramps.",
        "godot_target_node": "GPUParticles2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": False,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "background": {
        "category": "environments_and_tiles",
        "description": "Full 2D scenic environment background with depth separation and no characters.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [1024, 576],
        "recommended_target_size": [640, 360],
        "recommended_remove_background": False,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "parallax_layer": {
        "category": "environments_and_tiles",
        "description": "Horizontally repeatable 2D depth layer designed for Godot Parallax2D scrolling.",
        "godot_target_node": "Parallax2D",
        "recommended_generation_size": [1024, 512],
        "recommended_target_size": [640, 320],
        "recommended_remove_background": True,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "tileset_topdown": {
        "category": "environments_and_tiles",
        "description": "Orthogonal 90-degree overhead 2D tileset for RPG and roguelike TileMapLayer.",
        "godot_target_node": "TileMapLayer",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [128, 128],
        "recommended_remove_background": False,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "tileset_platformer": {
        "category": "environments_and_tiles",
        "description": "Side-scroller platformer terrain block with clear top collision edge.",
        "godot_target_node": "TileMapLayer",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": True,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "tileset_autotile_3x3": {
        "category": "environments_and_tiles",
        "description": "3x3 terrain autotile patch (corners, edges, center fill) for Godot TileSet terrains.",
        "godot_target_node": "TileMapLayer",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [96, 96],
        "recommended_remove_background": True,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "isometric_tile_prop": {
        "category": "environments_and_tiles",
        "description": "2:1 dimetric / isometric tile block or building prop for tactical and strategy games.",
        "godot_target_node": "TileMapLayer",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [128, 128],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "environment_prop": {
        "category": "environments_and_tiles",
        "description": "Isolated decorative 2D world prop (tree, chest, rock, lamp, shrine) for Node2D scenes.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "icon": {
        "category": "ui_and_items",
        "description": "High-contrast 2D skill, buff/debuff status, or achievement UI icon.",
        "godot_target_node": "TextureRect",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": False,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "item_loot": {
        "category": "ui_and_items",
        "description": "Isolated RPG inventory item, weapon, potion, or relic with bold contour.",
        "godot_target_node": "TextureRect",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "ui_ninepatch_panel": {
        "category": "ui_and_items",
        "description": "Symmetrical 9-slice HUD frame with ornate corners and flat center for NinePatchRect.",
        "godot_target_node": "NinePatchRect",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [128, 128],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "game_logo_title": {
        "category": "ui_and_items",
        "description": "Stylized 2D game emblem and crest graphic for main menu title screens.",
        "godot_target_node": "TextureRect",
        "recommended_generation_size": [768, 512],
        "recommended_target_size": [384, 256],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "seamless_texture": {
        "category": "materials_and_shaders",
        "description": "Tileable orthographic 2D surface texture for Polygon2D or repeating shaders.",
        "godot_target_node": "Polygon2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [256, 256],
        "recommended_remove_background": False,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "normal_map_2d": {
        "category": "materials_and_shaders",
        "description": "Tangent-space XYZ normal map texture for 2D dynamic lighting with PointLight2D.",
        "godot_target_node": "CanvasTexture",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": False,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "shader_noise_mask": {
        "category": "materials_and_shaders",
        "description": "Full-range grayscale noise/dissolve mask texture for Godot .gdshader effects.",
        "godot_target_node": "ShaderMaterial",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [256, 256],
        "recommended_remove_background": False,
        "recommended_crop": False,
        "capabilities": ["txt2img", "lora_optional"],
    },
    "lora_pixel_art": {
        "category": "advanced_lora_and_control",
        "description": "Dedicated LoRA workflow tuned for crisp 16-bit pixel-art sprites and strict grid alignment.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora"],
        "default_lora_name": "pixel_art.safetensors",
    },
    "lora_hand_drawn_2d": {
        "category": "advanced_lora_and_control",
        "description": "Dedicated LoRA workflow for cel-shaded hand-drawn 2D indie game art.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [256, 256],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora"],
        "default_lora_name": "hand_drawn_2d.safetensors",
    },
    "lora_dual_style_character": {
        "category": "advanced_lora_and_control",
        "description": "Dual-LoRA workflow chaining a primary art-style LoRA and a secondary character/palette LoRA.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [128, 128],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "lora", "dual_lora"],
        "default_lora_name": "pixel_art.safetensors",
        "default_secondary_lora_name": "character_style.safetensors",
    },
    "sprite_variation_img2img": {
        "category": "advanced_lora_and_control",
        "description": "Img2Img workflow (LoadImage + ImageScale + VAEEncode) for damage states, item tiers, and silhouette-preserving variations.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["img2img", "lora_optional"],
        "default_denoise": 0.55,
    },
    "controlnet_pose_guide": {
        "category": "advanced_lora_and_control",
        "description": "ControlNet workflow (ControlNetLoader + ControlNetApplyAdvanced) for pose-locked or collision-aligned 2D assets.",
        "godot_target_node": "Sprite2D",
        "recommended_generation_size": [512, 512],
        "recommended_target_size": [64, 64],
        "recommended_remove_background": True,
        "recommended_crop": True,
        "capabilities": ["txt2img", "controlnet", "lora_optional"],
    },
}


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
        while result.endswith(", "):
            result = result[:-2].rstrip()
        return result
    return value


def _rewire_connection(value: Any, source_node_id: str, output_map: Mapping[int, Any]) -> Any:
    if isinstance(value, dict):
        return {
            key: _rewire_connection(item, source_node_id, output_map)
            for key, item in value.items()
        }
    if isinstance(value, list):
        if (
            len(value) == 2
            and value[0] == source_node_id
            and isinstance(value[1], int)
            and value[1] in output_map
        ):
            return list(output_map[value[1]])
        return [_rewire_connection(item, source_node_id, output_map) for item in value]
    return value


def _apply_lora_configuration(workflow: dict[str, Any]) -> dict[str, Any]:
    """Bypass LoraLoader nodes whose lora_name is empty while keeping active LoRAs wired."""
    updated: dict[str, Any] = json.loads(json.dumps(workflow))
    lora_node_ids = [
        node_id
        for node_id, node in updated.items()
        if isinstance(node, dict) and node.get("class_type") == "LoraLoader"
    ]
    for node_id in lora_node_ids:
        node = updated.get(node_id)
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        lora_name = inputs.get("lora_name")
        if isinstance(lora_name, str) and lora_name.strip() and not (
            lora_name.startswith("${") and lora_name.endswith("}")
        ):
            continue
        output_map: dict[int, Any] = {}
        if isinstance(inputs.get("model"), list):
            output_map[0] = inputs["model"]
        if isinstance(inputs.get("clip"), list):
            output_map[1] = inputs["clip"]
        updated.pop(node_id, None)
        if output_map:
            updated = _rewire_connection(updated, node_id, output_map)
    return updated


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


def list_workflows(
    workflow_root: Path | None = None,
    *,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """List available ComfyUI 2D workflow templates with Godot metadata."""
    root = workflow_root or Path(__file__).parent / "resources" / "workflows"
    names = sorted(path.stem for path in root.glob("*.json"))
    entries: list[dict[str, Any]] = []
    for name in names:
        meta = dict(
            WORKFLOW_CATALOG.get(
                name,
                {
                    "category": "custom",
                    "description": f"Custom ComfyUI 2D workflow '{name}'.",
                    "godot_target_node": "Sprite2D",
                    "recommended_generation_size": [512, 512],
                    "recommended_target_size": [64, 64],
                    "recommended_remove_background": False,
                    "recommended_crop": False,
                    "capabilities": ["txt2img"],
                },
            )
        )
        if category is not None and meta.get("category") != category:
            continue
        entries.append({"name": name, **meta})
    return entries


def prepare_workflow(
    workflow_name: str,
    *,
    prompt: str,
    width: int = 512,
    height: int = 512,
    seed: int | None = None,
    batch: int = 1,
    negative_prompt: str = "",
    ckpt_name: str | None = None,
    lora_name: str | None = None,
    lora_strength_model: float = 1.0,
    lora_strength_clip: float = 1.0,
    secondary_lora_name: str | None = None,
    secondary_lora_strength_model: float = 0.8,
    secondary_lora_strength_clip: float = 0.8,
    steps: int = 24,
    cfg: float = 7.0,
    sampler_name: str = "euler",
    scheduler: str = "normal",
    denoise: float | None = None,
    input_image: str | None = None,
    controlnet_name: str | None = None,
    controlnet_strength: float = 1.0,
    workflow_root: Path | None = None,
) -> dict[str, Any]:
    """Load, parameterize, and wire LoRA/ControlNet/Img2Img nodes for a workflow."""
    raw = load_workflow(workflow_name, workflow_root=workflow_root)
    stem = Path(workflow_name).stem
    meta = WORKFLOW_CATALOG.get(stem, {})
    resolved_ckpt = (
        ckpt_name
        or os.environ.get("COMFYUI_DEFAULT_CHECKPOINT")
        or DEFAULT_CHECKPOINT_NAME
    )
    resolved_lora = (
        lora_name
        if lora_name is not None
        else (os.environ.get("COMFYUI_DEFAULT_LORA") or meta.get("default_lora_name", ""))
    )
    resolved_secondary_lora = (
        secondary_lora_name
        if secondary_lora_name is not None
        else (
            os.environ.get("COMFYUI_SECONDARY_LORA")
            or meta.get("default_secondary_lora_name", "")
        )
    )
    resolved_denoise = (
        denoise
        if denoise is not None
        else float(meta.get("default_denoise", 1.0))
    )
    resolved_controlnet = (
        controlnet_name
        or os.environ.get("COMFYUI_DEFAULT_CONTROLNET")
        or DEFAULT_CONTROLNET_NAME
    )
    parameters: dict[str, object] = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "seed": seed if seed is not None else 0,
        "batch": batch,
        "ckpt_name": resolved_ckpt,
        "lora_name": resolved_lora,
        "lora_strength_model": float(lora_strength_model),
        "lora_strength_clip": float(lora_strength_clip),
        "secondary_lora_name": resolved_secondary_lora,
        "secondary_lora_strength_model": float(secondary_lora_strength_model),
        "secondary_lora_strength_clip": float(secondary_lora_strength_clip),
        "steps": int(steps),
        "cfg": float(cfg),
        "sampler_name": sampler_name,
        "scheduler": scheduler,
        "denoise": float(resolved_denoise),
        "input_image": input_image or "input.png",
        "controlnet_name": resolved_controlnet,
        "controlnet_strength": float(controlnet_strength),
    }
    substituted = _replace_parameters(raw, parameters)
    return _apply_lora_configuration(substituted)


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
                        is_placeholder = (
                            isinstance(value, str)
                            and value.startswith("${")
                            and value.endswith("}")
                        )
                        if (
                            isinstance(options, list)
                            and not isinstance(value, list)
                            and not is_placeholder
                            and value not in options
                        ):
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
    negative_prompt: str = "",
    ckpt_name: str | None = None,
    lora_name: str | None = None,
    lora_strength_model: float = 1.0,
    lora_strength_clip: float = 1.0,
    secondary_lora_name: str | None = None,
    secondary_lora_strength_model: float = 0.8,
    secondary_lora_strength_clip: float = 0.8,
    steps: int = 24,
    cfg: float = 7.0,
    sampler_name: str = "euler",
    scheduler: str = "normal",
    denoise: float | None = None,
    input_image: str | None = None,
    controlnet_name: str | None = None,
    controlnet_strength: float = 1.0,
    remove_background_enabled: bool = False,
    crop: bool = True,
    target_width: int | None = None,
    target_height: int | None = None,
    pixel_perfect: bool = True,
    palette: str | None = None,
    palette_distance_metric: str = "rgb",
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
    if (target_width is None) != (target_height is None):
        raise ValueError("target_width and target_height must both be set when resizing output")
    if target_width is not None and target_height is not None:
        ensure_image_dimensions(target_width, target_height)
    ensure_batch(batch)
    if timeout <= 0 or timeout > safety_limits().max_operation_seconds:
        raise ValueError(
            f"timeout must be between 0 and {safety_limits().max_operation_seconds} seconds"
        )
    workflow = prepare_workflow(
        workflow_name,
        prompt=prompt,
        width=width,
        height=height,
        seed=seed,
        batch=batch,
        negative_prompt=negative_prompt,
        ckpt_name=ckpt_name,
        lora_name=lora_name,
        lora_strength_model=lora_strength_model,
        lora_strength_clip=lora_strength_clip,
        secondary_lora_name=secondary_lora_name,
        secondary_lora_strength_model=secondary_lora_strength_model,
        secondary_lora_strength_clip=secondary_lora_strength_clip,
        steps=steps,
        cfg=cfg,
        sampler_name=sampler_name,
        scheduler=scheduler,
        denoise=denoise,
        input_image=input_image,
        controlnet_name=controlnet_name,
        controlnet_strength=controlnet_strength,
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
    for candidate_path in generated_paths:
        if remove_background_enabled:
            remove_background_result = globals()["remove_background"]
            remove_background_result(project, candidate_path, candidate_path, overwrite=True)
        if crop:
            _remove_transparent_border(project, candidate_path, overwrite=True)
        if target_width is not None and target_height is not None:
            resize_asset(
                project,
                candidate_path,
                candidate_path,
                target_width,
                target_height,
                pixel_perfect=pixel_perfect,
                overwrite=True,
            )
        if palette is not None:
            apply_palette(
                project,
                candidate_path,
                candidate_path,
                palette,
                distance_metric=palette_distance_metric,
                overwrite=True,
            )
    written = generated_paths[0]
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
