# godot-visual-mcp

Secure, offline-first asset tools for Godot exposed through a Model Context
Protocol (MCP) server.

## v0.3 quickstart

Install the core profile with Python 3.11+:

```bash
python -m pip install -e ".[dev]"
GODOT_PROJECT_ROOT=/path/to/my-godot-project python -m server.main
```

The server uses stdio, so configure an MCP client to launch
`python -m server.main`. Every asset path is interpreted as `res://...` and is
resolved and checked against the configured project root. Absolute paths,
parent traversal, and symlink escapes are rejected. Existing files are not
overwritten unless a tool explicitly receives `overwrite=true`.

The v0.2 tools are `inspect_asset`, `list_assets`, `validate_asset`,
`create_placeholder`, `generate_spritesheet`, `apply_palette`, and
`list_palettes`. v0.3 adds `generate_asset` and `remove_background`.
Their responses use the envelope
`status / data / warnings / errors` and never expose stack traces to the agent.

Spritesheets are assembled offline from equal-sized frames. Palette processing
ships with Game Boy, PICO-8, and custom JSON palettes and supports RGB or LAB
distance matching while preserving alpha values.

### ComfyUI

The core installation does not install AI dependencies. Configure ComfyUI with
`COMFYUI_ENDPOINT` (default `http://127.0.0.1:8188`) or pass `endpoint` to
`generate_asset`. Workflows are local JSON resources in `workflows/`; prompts,
dimensions, seed, and batch are injected without storing credentials.

```bash
python -m pip install -e ".[dev]"
python -m pip install -e ".[ai]"  # optional, only for remove_background
```

Generation submits a workflow, polls without a fixed completion assumption,
retrieves the first output image, optionally removes its background, crops
transparent borders, writes to `res://`, and validates the result. CPU-only
machines can use ComfyUI's configured CPU backend; no CUDA dependency is
required by this project.

Run tests and lint:

```bash
python -m pytest
ruff check .
```
