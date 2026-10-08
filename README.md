<div align="center">
  
# godot-visual-mcp

> Secure, offline-first asset tools for Godot exposed through a Model Context Protocol (MCP) server.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg) ![Godot](https://img.shields.io/badge/Godot-4.x-478CBF?logo=godotengine&logoColor=white) ![Protocol](https://img.shields.io/badge/Protocol-MCP-8A2BE2) ![License](https://img.shields.io/badge/license-MIT-green.svg)

Empower your LLM agents (Cline, Roo Code, Copilot) to inspect, generate, and transform visual assets directly within your Godot Engine project. Engineered with strict filesystem sandboxing, this server securely translates agent reasoning into your game's `res://` pipeline.
</div>

## 🚀 Quickstart

Requires Python 3.11+. The core profile runs entirely offline and has no heavy AI or GPU dependencies.

```bash
# Install core tools and development dependencies
python -m pip install -e ".[dev]"

# Run the server (requires Godot project path)
GODOT_PROJECT_ROOT=/path/to/my-godot-project python -m server.main
```

### Client Configuration (stdio)
Configure your MCP client to launch the server via `stdio`. Every asset path provided by the agent is automatically interpreted as relative to the `res://` directory and resolved against your configured `GODOT_PROJECT_ROOT`.

```json
{
  "mcpServers": {
    "godot-visual-mcp": {
      "command": "python",
      "args": ["-m", "server.main"],
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

## 🧠 ComfyUI Integration (Optional)

The core installation intentionally omits heavy AI dependencies. To enable generative workflows and background removal, install the `[ai]` profile:

```bash
python -m pip install -e ".[ai]"
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

## 🛠️ Development & Testing

Run the test suite and code quality checks using standard Python tooling:

```bash
# Run unit tests
python -m pytest

# Run linter
ruff check .
```

---

**Documentation:** [Security Model](SECURITY.md) | [Tool Reference](TOOL_REFERENCE.md) | [Changelog](CHANGELOG.md)
