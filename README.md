<div align="center">
  
# godot-visual-mcp

> Secure, offline-first asset tools for Godot exposed through a Model Context Protocol (MCP) server.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg) ![Godot](https://img.shields.io/badge/Godot-4.x-478CBF?logo=godotengine&logoColor=white) ![Protocol](https://img.shields.io/badge/Protocol-MCP-8A2BE2) ![License](https://img.shields.io/badge/license-MIT-green.svg)

Empower your LLM agents (Cline, Roo Code, Copilot) to inspect, generate, and transform visual assets directly within your Godot Engine project. Engineered with strict filesystem sandboxing, this server securely translates agent reasoning into your game's `res://` pipeline.
</div>

## 🚀 Quickstart

Requires Python 3.11+. The core profile runs entirely offline and has no heavy AI or GPU dependencies.

The project uses `uv.lock` for reproducible environments. Configurable safety
limits include `MCP_MAX_INPUT_BYTES`, `MCP_MAX_PIXELS`, `MCP_MAX_FRAMES`,
`MCP_MAX_BATCH`, `MCP_MAX_OPERATION_SECONDS`, and `MCP_MAX_PROJECT_BYTES`.

```bash
# Install core tools and development dependencies
uv sync

# Run the server (requires Godot project path)
GODOT_PROJECT_ROOT=/path/to/my-godot-project uv run python -m server.main
```

### Client Configuration (stdio)
Configure your MCP client to launch the server via `stdio`. Every asset path provided by the agent is automatically interpreted as relative to the `res://` directory and resolved against your configured `GODOT_PROJECT_ROOT`.

```json
{
  "mcpServers": {
    "godot-visual-mcp": {
      "command": "uv",
      "args": ["run", "--no-dev", "python", "-m", "server.main"],
      "env": {
        "GODOT_PROJECT_ROOT": "/path/to/my-godot-project"
      }
    }
  }
}
```

## 🧰 Available Tools

All tool responses use a standard envelope format (`status` / `data` / `warnings` / `errors`) ensuring LLM agents never receive raw, unhandled stack traces. 

**Core Tools (v0.2):**
*   **Inspection:** `inspect_asset`, `list_assets`, `validate_asset`
*   **Prototyping:** `create_placeholder`, `generate_spritesheet` (assembled offline from equal-sized frames)
*   **Palette Engine:** `apply_palette`, `list_palettes` (ships with Game Boy, PICO-8, and custom JSON palettes. Supports RGB/LAB distance matching while preserving alpha channels).

**Generative AI Tools (v0.3):**
*   **Generation & Cleaning:** `generate_asset`, `remove_background`

## 🧰 Tool Reference

All tools return the same envelope:

```json
{
  "status": "ok",
  "data": {},
  "warnings": [],
  "errors": []
}
```

Paths use Godot's `res://` notation and are always checked against the selected
project. Mutating tools do not overwrite existing files unless
`overwrite=true` is provided. Generated or transformed images include
verification data. Errors include a stable code, a retryability flag, a
suggestion, and a correlation ID.

### Project and image inspection

| Tool | Main parameters | Capabilities |
| --- | --- | --- |
| `inspect_asset` | `path` | Reads image format, dimensions, alpha, color mode, frame count, and sprite-frame geometry. |
| `list_assets` | `extension?` | Lists files inside the project sandbox, optionally filtered by extension; excludes `.godot` and `.import`. |
| `validate_asset` | `path` | Checks that an image exists, can be decoded, has valid dimensions, and uses a supported format. |
| `inspect_project` | `project_root?` | Reads `project.godot`, returns project name/configuration, and detects a Godot executable without launching it. |
| `verify_import` | `godot_binary?`, `timeout?` | Opens the project with Godot headlessly when available and reports import diagnostics. |
| `validate_scene` | `path` | Checks `.tscn` structure, nodes, external resources, and missing `res://` references. |
| `find_references` | `asset` | Finds project text resources that reference a given asset. |
| `find_unused` | — | Reports unreferenced image assets that may be candidates for cleanup. |

Example:

```json
{
  "name": "inspect_asset",
  "arguments": {"path": "res://characters/hero.png"}
}
```

### Offline image creation and palettes

| Tool | Main parameters | Capabilities |
| --- | --- | --- |
| `create_placeholder` | `output`, `width`, `height`, `frames?`, `label?` | Creates a deterministic labeled RGBA PNG or spritesheet for rapid prototyping. |
| `generate_spritesheet` | `inputs`, `output`, `columns` | Arranges equal-sized frames into a uniform-grid PNG spritesheet. |
| `list_palettes` | — | Lists bundled Game Boy, PICO-8, and custom palettes. |
| `apply_palette` | `source`, `output`, `palette`, `distance_metric?` | Maps colors to a built-in palette using RGB or LAB distance while preserving alpha. |

These operations are offline and do not require ComfyUI, CUDA, or a GPU.

### Godot scenes and animation

| Tool | Main parameters | Capabilities |
| --- | --- | --- |
| `create_scene` | `output`, `root_type?`, `root_name?` | Creates a minimal validated `.tscn` scene. |
| `add_sprite_to_scene` | `scene`, `texture`, `node_name?`, `animated?` | Adds a sandboxed `Sprite2D` or `AnimatedSprite2D` texture reference. |
| `create_sprite_frames` | `output`, `frames`, `animation?`, `fps?`, `loop?` | Generates a Godot `SpriteFrames` resource from project textures. |

Scene tools validate references after writing and never edit `.import` files.

### Aseprite and animation manifests

| Tool | Main parameters | Capabilities |
| --- | --- | --- |
| `inspect_aseprite` | `path` | Reads exported Aseprite JSON, frame count, metadata, and animation tags. |
| `create_animation_manifest` | `source`, `output` | Converts Aseprite `frameTags` into a stable project-local animation manifest while preserving order and direction. |

The current integration consumes Aseprite-exported JSON and PNG files; it does
not execute the Aseprite binary or accept arbitrary shell commands.

### Offline visual transformations

| Tool | Main parameters | Capabilities |
| --- | --- | --- |
| `resize_asset_tool` | `source`, `output`, `width`, `height`, `pixel_perfect?` | Resizes with nearest-neighbor pixel-perfect scaling by default; Lanczos is available for smooth images. |
| `crop_asset_tool` | `source`, `output`, `padding?` | Crops transparent borders and optionally retains transparent padding. |
| `normalize_asset_tool` | `source`, `output`, `center?` | Re-centers visible content on the original canvas without changing canvas dimensions. |
| `generate_thumbnail_tool` | `source`, `output`, `size?` | Creates a bounded aspect-preserving thumbnail. |
| `transform_asset_colors` | `source`, `output`, `operation` | Applies grayscale, brightness, or contrast transformations. |
| `flip_asset_tool` | `source`, `output`, `horizontal?` | Flips horizontally or vertically. |
| `rotate_asset_tool` | `source`, `output`, `degrees` | Rotates by 90, 180, or 270 degrees. |
| `compare_asset_images` | `left`, `right` | Compares two images and returns a normalized pixel-difference metric. |
| `deduplicate_asset_images` | `paths` | Groups byte-identical image files to identify duplicates. |

Transformation responses contain `before`, `after`, dimension changes,
alpha-preservation information, and output verification.

### ComfyUI generation and history

| Tool | Main parameters | Capabilities |
| --- | --- | --- |
| `generate_asset` | `prompt`, `workflow`, `output`, `width?`, `height?`, `seed?`, `batch?` | Submits a local workflow to ComfyUI, polls jobs, retrieves all batch outputs, optionally removes backgrounds/crops, validates, and records metadata. |
| `remove_background` | `source`, `output` | Uses the optional `[ai]`/`rembg` profile to remove a background without leaving the project sandbox. |
| `list_generation_history` | — | Lists local generation metadata and cache records without storing credentials or binary data. |

`generate_asset` also supports `timeout`, `retries`, `validate_workflow`,
`use_cache`, `overwrite`, and an explicit `endpoint`. The core installation
does not install ComfyUI or `rembg`.

### Project discovery and MCP ergonomics

| Tool | Main parameters | Capabilities |
| --- | --- | --- |
| `discover_projects_tool` | `search_root`, `max_depth?` | Finds nearby Godot projects without following symlinks and marks ambiguous results. |
| `select_project_tool` | `project_root?`, `alias?` | Selects a validated project for subsequent project-aware operations and resources. |
| `set_project_alias_tool` | `alias`, `project_root` | Registers an in-memory alias for a validated project. |
| `list_project_aliases_tool` | — | Lists aliases configured in the current MCP process. |

The selected project can also come from `GODOT_PROJECT_ROOT`. Project aliases
are process-local and do not write global configuration.

### Audio, fonts, SVG, 3D, and JSON

| Tool | Main parameters | Capabilities |
| --- | --- | --- |
| `inspect_audio_asset` | `path` | Inspects WAV metadata and validates basic OGG/MP3 headers; reports duration/channels/sample rate when available. |
| `inspect_font_asset` | `path` | Inspects TTF/OTF family, style, and basic font metrics using Pillow. |
| `inspect_svg_asset` | `path` | Validates SVG XML, dimensions, and `viewBox`; rejects external references. |
| `convert_svg_asset` | `source`, `output` | Converts a validated SVG to PNG through optional offline CairoSVG support. |
| `inspect_3d_asset_tool` | `path` | Inspects GLTF/GLB headers, meshes, materials, animations, textures, and missing internal references. |
| `inspect_json_asset_tool` | `path` | Parses bounded JSON resources without executing contents and reports root type/keys. |

All extended-asset inspections enforce the configured input-size limit. No
external URL is downloaded by these tools.

## 🧠 ComfyUI Integration (Optional)

The core installation intentionally omits heavy AI dependencies. To enable generative workflows and background removal, install the `[ai]` profile:

```bash
uv sync --extra ai
```

Configure your local ComfyUI instance via environment variables or pass the endpoint directly to the `generate_asset` tool:
`COMFYUI_ENDPOINT=http://127.0.0.1:8188`

**How generation works:**
1. The tool submits a local JSON workflow (located in `workflows/`).
2. Prompts, dimensions, seeds, and batch sizes are injected dynamically (credentials are never stored).
3. The MCP polls without fixed completion assumptions.
4. The output is retrieved, background is removed (if requested), transparent borders are cropped, and the final asset is written safely to `res://`.
5. *Note: CPU-only machines can use ComfyUI's CPU backend; this project does not strictly require CUDA.*

## 🛡️ Security Model

Security and directory integrity are core design principles:
*   **Strict Sandboxing:** All operations are strictly bound to the configured `GODOT_PROJECT_ROOT`.
*   **Path Validation:** Absolute paths, parent directory traversal (`../`), and symlink escapes are aggressively rejected.
*   **Non-Destructive by Default:** Existing files are never overwritten unless a tool explicitly receives the `overwrite=true` parameter from the agent.

## 🐳 Docker Deployment

The project includes an optional `Dockerfile` and `compose.yaml` to provide an isolated core container and an opt-in ComfyUI profile. The default core container has no GPU or AI runtime requirements, keeping the footprint minimal.

## 📦 Releases

Development happens on `develop`. Changes reach the protected `main` branch
through a pull request from `develop`, with one approving review and all
Python 3.11, 3.12, and 3.13 checks passing. Merging that pull request starts
the release workflow automatically. Before merging, update the package version
and changelog; the workflow refuses to republish an existing release version.

Releases are created by pushing a tag that matches the package version, for
example:

```bash
git tag v1.6.0
git push origin v1.6.0
```

The release workflow for future merges creates the version tag automatically.
The manual tag commands above are only a fallback for releases that are not
created through the `develop` → `main` pull request flow. It builds the wheel and source distribution with `uv`,
validates installation in Python 3.11, generates SHA-256 checksums and an SPDX
SBOM, publishes the package to PyPI through trusted publishing, and publishes
the container to GHCR. Configure a PyPI trusted publisher for the
`pypi` environment before using the workflow.

## 🛠️ Development & Testing

Run the test suite and code quality checks using standard Python tooling:

```bash
# Run unit tests
uv run pytest

# Run linter
uv run ruff check .
```

---

**Documentation:** [Security Model](SECURITY.md) | [Tool Reference](TOOL_REFERENCE.md) | [Changelog](CHANGELOG.md)
