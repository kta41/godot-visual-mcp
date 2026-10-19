---
name: godot-visual-mcp
description: Guides safe Godot project asset workflows using the godot-visual-mcp server. Use when inspecting, generating, transforming, organizing, or validating visual assets and scenes in a Godot project.
license: MIT
---

# Godot Visual MCP

Use this Skill when the `godot-visual-mcp` MCP server is available. The server
provides sandboxed, high-level Godot asset operations; it is not a general
filesystem or shell interface.

## Start safely

1. Check whether the MCP server is connected and which tools it exposes. Do
   not claim to have run a tool that is unavailable.
2. Identify the intended Godot project. Use `inspect_project` for a known
   project or `discover_projects_tool` followed by `select_project_tool` when
  discovery is needed. Discovery is limited to operator-configured roots. If
  the target is ambiguous or outside those roots, ask the user to choose or
  configure an allowed root.
3. Use `res://` paths inside the selected project. Never try to bypass the
   server sandbox with direct filesystem or shell operations for asset work.
4. Inspect relevant inputs before transforming them. Preserve existing files;
   only request overwrite when the user explicitly wants replacement.

## Common workflows

- Inspect assets with `inspect_asset`, `validate_asset`, and `list_assets`.
- Create placeholders with `create_placeholder`, or assemble frames with
  `generate_spritesheet`.
- Generate an asset with `generate_asset` only when ComfyUI is configured;
  mention this requirement if generation is unavailable. `remove_background`
  additionally requires the optional `[ai]` dependencies.
- Transform existing images with `resize_asset_tool`, `crop_asset_tool`,
  `normalize_asset_tool`, `flip_asset_tool`, `rotate_asset_tool`,
  `transform_asset_colors`, or `apply_palette`.
- Compose scenes with `create_scene`, `add_sprite_to_scene`, and
  `create_sprite_frames`; then run `validate_scene` and, when Godot is
  installed, `verify_import`.
- Use the relevant inspectors for Aseprite JSON, audio, fonts, SVG, 3D, and
  JSON instead of guessing at resource metadata.

## Verify and report

After a mutation, check the tool response for its status, output path,
verification data, warnings, and errors. Run a relevant validation tool when
available. Report optional prerequisites and incomplete verification plainly;
never imply that a file was generated, imported, or validated when it was not.

Keep explanations in the user's language. For server installation and
client-specific configuration, refer to the repository README; this Skill does
not install or configure MCP servers automatically.