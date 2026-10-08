# godot-visual-mcp

Secure, offline-first asset tools for Godot exposed through a Model Context
Protocol (MCP) server.

## v0.2 quickstart

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
`list_palettes`. Their responses use the envelope
`status / data / warnings / errors` and never expose stack traces to the agent.

Spritesheets are assembled offline from equal-sized frames. Palette processing
ships with Game Boy, PICO-8, and custom JSON palettes and supports RGB or LAB
distance matching while preserving alpha values.

Run tests and lint:

```bash
python -m pytest
ruff check .
```
