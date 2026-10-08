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
| `inspect_aseprite(path)` | Inspect Aseprite-exported JSON frames and tags. |
| `create_animation_manifest(source, output)` | Create a project-local animation manifest. |
| `resize_asset_tool(source, output, width, height)` | Resize with pixel-perfect nearest-neighbor by default. |
| `crop_asset_tool(source, output, padding?)` | Crop transparent borders. |
| `normalize_asset_tool(source, output)` | Normalize content on the original canvas. |
| `generate_thumbnail_tool(source, output, size?)` | Generate a bounded thumbnail. |
| `transform_asset_colors(source, output, operation)` | Apply grayscale, brightness, or contrast. |
| `flip_asset_tool(source, output, horizontal?)` | Flip an image. |
| `rotate_asset_tool(source, output, degrees)` | Rotate by 90, 180, or 270 degrees. |
| `compare_asset_images(left, right)` | Return a normalized pixel difference. |
| `deduplicate_asset_images(paths)` | Group byte-identical images. |
| `list_generation_history()` | List local generation metadata. |
| `discover_projects_tool(search_root, max_depth?)` | Discover nearby Godot projects without following symlinks. |
| `select_project_tool(project_root?, alias?)` | Select a validated project for project-aware operations. |
| `set_project_alias_tool(alias, project_root)` | Register an in-memory project alias. |
| `list_project_aliases_tool()` | List aliases in the current MCP process. |
| `inspect_audio_asset(path)` | Inspect WAV, OGG, or MP3 metadata. |
| `inspect_font_asset(path)` | Inspect TTF or OTF family and style metadata. |
| `inspect_svg_asset(path)` | Validate SVG XML and report dimensions and viewBox. |
| `convert_svg_asset(source, output, overwrite?)` | Convert validated SVG to PNG with optional CairoSVG. |
| `inspect_3d_asset_tool(path)` | Inspect GLTF or GLB structure and references. |
| `inspect_json_asset_tool(path)` | Parse a bounded JSON resource safely. |

MCP resources include `godot://project/assets`, `godot://project/state`,
`godot://catalog/palettes`, `godot://catalog/workflows`,
`godot://project/history`, and `godot://docs/tools`. MCP prompts include
`prototype_character`, `create_ui_pack`, `prepare_sprite_animation`,
`generate_and_validate_asset`, and `audit_godot_project`.

Mutating tools include `data.verification` with the resulting path, metadata,
validation status, and import-readiness. `generate_asset` additionally reports
the workflow and post-processing result.
