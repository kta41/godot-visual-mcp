# Tool reference

All tools return:

```json
{"status": "ok|error", "data": {}, "warnings": [], "errors": []}
```

All paths are project-relative `res://` paths. `project_root` may be omitted
when `GODOT_PROJECT_ROOT` is configured.

| Tool | Purpose |
| --- | --- |
| `inspect_asset(path)` | Read image format, dimensions, alpha, color mode, and frames. |
| `list_assets(extension?)` | Inventory files under the project boundary. |
| `validate_asset(path)` | Check image integrity and supported format. |
| `create_placeholder(output, width, height, frames?, label?, overwrite?)` | Create a deterministic labeled PNG. |
| `generate_spritesheet(inputs, output, columns, overwrite?)` | Assemble equal-sized frames into a grid. |
| `apply_palette(source, output, palette, distance_metric?, overwrite?)` | Apply an offline palette with RGB or LAB matching. |
| `list_palettes()` | List bundled JSON palettes. |
| `generate_asset(prompt, workflow, output, ...)` | Generate through ComfyUI and validate the result. |
| `remove_background(source, output, overwrite?)` | Optional `rembg` background removal. |
| `inspect_project()` | Inspect `project.godot` and detect the Godot binary. |
| `verify_import()` | Run Godot headless when available and report import diagnostics. |
| `validate_scene(path)` | Validate a `.tscn` and its `res://` references. |
| `create_scene(output, ...)` | Create a controlled Godot scene. |
| `add_sprite_to_scene(scene, texture, ...)` | Add a Sprite2D or AnimatedSprite2D. |
| `create_sprite_frames(output, frames, ...)` | Create a SpriteFrames resource. |
| `find_references(asset)` | Find text resources referencing an asset. |
| `find_unused()` | Find unreferenced image assets. |

Mutating tools include `data.verification` with the resulting path, metadata,
validation status, and import-readiness. `generate_asset` additionally reports
the workflow and post-processing result.
