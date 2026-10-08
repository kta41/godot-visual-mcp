"""Safe high-level generation of Godot text scenes and SpriteFrames."""

from __future__ import annotations

from .assets import inspect_asset
from .filesystem import GodotProject


def create_scene(
    project: GodotProject,
    output: str,
    *,
    root_type: str = "Node2D",
    root_name: str = "Main",
    overwrite: bool = False,
) -> dict[str, object]:
    """Create a minimal scene with a validated root node type."""
    allowed = {"Node2D", "Node", "Control", "CanvasLayer", "Area2D"}
    if root_type not in allowed:
        raise ValueError(f"Unsupported root node type: {root_type}")
    if not root_name.isidentifier():
        raise ValueError("root_name must be a valid identifier")
    content = f'[gd_scene format=3]\n\n[node name="{root_name}" type="{root_type}"]\n'
    path = project.safe_write(output, content.encode(), overwrite=overwrite)
    return {"path": path, "root_type": root_type, "root_name": root_name}


def add_sprite_to_scene(
    project: GodotProject,
    scene: str,
    texture: str,
    *,
    node_name: str = "Sprite2D",
    animated: bool = False,
    overwrite: bool = False,
) -> dict[str, object]:
    """Add a Sprite2D or AnimatedSprite2D node referencing a texture."""
    if not node_name.isidentifier():
        raise ValueError("node_name must be a valid identifier")
    if not overwrite:
        raise ValueError("Modifying a scene requires overwrite=true")
    scene_path = project.resolve_res_path(scene)
    if scene_path.suffix != ".tscn":
        raise ValueError("Scene path must have a .tscn extension")
    project.safe_read(texture)
    original = project.safe_read(scene).decode("utf-8")
    node_type = "AnimatedSprite2D" if animated else "Sprite2D"
    if f'name="{node_name}"' in original:
        raise ValueError(f"Scene already contains a node named {node_name}")
    ext_id = "1_texture"
    resource = f'\n[ext_resource type="Texture2D" path="{project.validate_asset_path(texture)}" id="{ext_id}"]\n'
    node = (
        f'\n[node name="{node_name}" type="{node_type}" parent="."]\n'
        f'texture = ExtResource("{ext_id}")\n'
    )
    if "[ext_resource " not in original:
        updated = original.replace("\n\n[node ", resource + "\n[node ", 1) + node
    else:
        updated = original + node
    path = project.safe_write(scene, updated.encode(), overwrite=overwrite)
    return {"path": path, "node_name": node_name, "node_type": node_type, "texture": project.validate_asset_path(texture)}


def create_sprite_frames(
    project: GodotProject,
    output: str,
    frames: list[str],
    *,
    animation: str = "default",
    fps: float = 8.0,
    loop: bool = True,
    overwrite: bool = False,
) -> dict[str, object]:
    """Create a SpriteFrames resource from texture paths."""
    if not frames:
        raise ValueError("At least one frame is required")
    if fps <= 0 or not animation.isidentifier():
        raise ValueError("animation must be an identifier and fps must be positive")
    resources: list[str] = []
    dimensions: list[tuple[int, int]] = []
    for index, frame in enumerate(frames, start=1):
        project.safe_read(frame)
        metadata = inspect_asset(project, frame)
        dimensions.append((int(metadata["width"]), int(metadata["height"])))
        resource_id = f"{index}_texture"
        resources.append(
            f'[ext_resource type="Texture2D" path="{project.validate_asset_path(frame)}" id="{resource_id}"]'
        )
    if len(set(dimensions)) != 1:
        raise ValueError("All SpriteFrames textures must have identical dimensions")
    frame_entries = ", ".join(
        f'{{"duration": 1.0, "texture": ExtResource("{index}_texture")}}'
        for index in range(1, len(frames) + 1)
    )
    content = (
        "[gd_resource type=\"SpriteFrames\" format=3]\n\n"
        + "\n".join(resources)
        + "\n\n[resource]\n"
        + f'animations = [{{"frames": [{frame_entries}], "loop": {str(loop).lower()}, "name": &"{animation}", "speed": {fps}}}]\n'
    )
    path = project.safe_write(output, content.encode(), overwrite=overwrite)
    return {"path": path, "animation": animation, "frames": len(frames), "fps": fps, "loop": loop}
