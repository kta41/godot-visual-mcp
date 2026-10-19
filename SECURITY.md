# Security model

The server is designed for an untrusted LLM-controlled input surface.

## Filesystem boundary

Every MCP operation validates that its root contains `project.godot`. Every
asset path passes through `GodotProject.resolve_res_path()` before any read or
write. Paths are normalized, resolved against the selected project root, and
checked with real-path resolution. Absolute paths, `..` traversal, and symlink
escapes are rejected. Non-overwrite writes use exclusive file creation so two
concurrent requests cannot silently replace each other's output.

Project discovery, selection, aliases, and operations are limited to
`GODOT_PROJECT_ROOT` and optional comma-separated `GODOT_ALLOWED_PROJECT_ROOTS`
configured by the operator. A tool argument cannot expand that allowlist.

The server exposes no shell, arbitrary file, download, or raw HTTP tools.
ComfyUI is called only by the high-level `generate_asset` engine. Its endpoint
must match `COMFYUI_ENDPOINT` or an entry in `COMFYUI_ALLOWED_ENDPOINTS`; the
tool cannot redirect requests to arbitrary hosts. HTTP response bodies are
bounded while streaming, and URLs containing credentials are rejected.

Image inputs and outputs are bounded by byte and pixel limits. Frame counts,
batches, project size, and ComfyUI/Godot operation timeouts also have
configurable limits. Known WAV/OGG/MP3 durations are checked against
`MCP_MAX_AUDIO_SECONDS`. SVG parsing rejects external references, including
CSS `url()` and `@import` resources, and caps raster output dimensions.

## Godot imports

The server writes assets to `res://` and never creates or edits `.import`
files. Verification means the resulting asset is readable, supported, and
therefore import-ready for Godot. Import completion remains the responsibility
of the Godot editor or headless Godot process. Headless verification runs only
the server-configured or PATH-discovered Godot executable with fixed
arguments; a tool call cannot select an arbitrary executable. `GODOT_BIN` is
operator configuration and must point to a trusted binary.

## Destructive operations

There is no delete operation. Mutations refuse to overwrite by default and
return an explicit error instructing the caller to opt in.
