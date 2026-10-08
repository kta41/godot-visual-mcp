# Security model

The server is designed for an untrusted LLM-controlled input surface.

## Filesystem boundary

Every asset path passes through `GodotProject.resolve_res_path()` before any
read or write. Paths are normalized, resolved against the configured project
root, and checked with real-path resolution. Absolute paths, `..` traversal,
and symlink escapes are rejected. Writes create parent directories only inside
the project and never overwrite an existing file unless `overwrite=true` is
explicitly supplied.

The server exposes no shell, arbitrary file, download, or raw HTTP tools.
ComfyUI is called only by the high-level `generate_asset` engine and its
endpoint is configurable; credentials are not accepted or persisted by this
project.

## Godot imports

The server writes assets to `res://` and never creates or edits `.import`
files. Verification means the resulting asset is readable, supported, and
therefore import-ready for Godot. Import completion remains the responsibility
of the Godot editor or headless Godot process.

## Destructive operations

There is no delete operation. Mutations refuse to overwrite by default and
return an explicit error instructing the caller to opt in.
