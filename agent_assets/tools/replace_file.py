# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: atomically replace or append UTF-8 file content."""
import hashlib
import os
import sys as _darkstar_sys
import tempfile
from pathlib import Path as _DarkstarPath
_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import (
    ToolInputError, atomic_write_utf8, json_result, read_utf8, relative_display,
    resolve_workspace_path, sha256_text, verify_expected_hash,
)

MAX_TOTAL_CONTENT_CHARS = 8 * 1024 * 1024

SCHEMA = {
    "name": "replace_file",
    "description": (
        "Atomically write UTF-8 text to a file inside the current project. "
        "Complete file contents are accepted in one valid tool call; Darkstar transports large "
        "payloads to the Python provider through a private file-backed channel. For exceptionally large "
        "model outputs, mode='replace' followed by mode='append' remains available. "
        "Use expected_sha256 from the previous result when appending or replacing an existing file. "
        "The parent folder is created when needed; symbolic-link targets and paths outside the "
        "workspace are rejected."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "description": "Target file path inside the current project."},
            "new_content": {
                "type": "string",
                "description": "UTF-8 content to write. Large valid payloads are transported safely by Darkstar.",
            },
            "mode": {
                "type": "string",
                "enum": ["replace", "append"],
                "description": "Use replace for the first chunk and append for subsequent chunks. Defaults to replace.",
            },
            "expected_sha256": {
                "type": "string",
                "description": "Optional SHA-256 digest returned by a prior read or write for conflict detection.",
            },
        },
        "required": ["path", "new_content"],
        "additionalProperties": False,
    },
}


def _file_backed_transfer(args):
    darkstar_path = args.get("__darkstar_content_file")
    legacy_path = args.get("__blacksun_content_file")
    if darkstar_path not in (None, ""):
        return darkstar_path, args.get("__darkstar_content_sha256"), ("darkstar-replace-",)
    if legacy_path not in (None, ""):
        # Compatibility for persisted/older hosts. New Darkstar hosts always use the canonical keys.
        return legacy_path, args.get("__blacksun_content_sha256"), ("blacksun-replace-",)
    return None, None, ()


def _load_content(args):
    transfer_path, expected, accepted_prefixes = _file_backed_transfer(args)
    if transfer_path in (None, ""):
        return args.get("new_content"), False
    if args.get("new_content") not in (None, ""):
        raise ToolInputError("Internal file-backed content cannot be combined with inline new_content.")
    if not isinstance(transfer_path, str):
        raise ToolInputError("Internal file-backed content path is invalid.")

    candidate = _DarkstarPath(transfer_path).expanduser().resolve(strict=True)
    temp_root = _DarkstarPath(tempfile.gettempdir()).resolve(strict=True)
    try:
        common = os.path.commonpath([str(temp_root), str(candidate)])
    except ValueError as exc:
        raise ToolInputError("Internal file-backed content path is invalid.") from exc
    if (
        common != str(temp_root)
        or not any(candidate.parent.name.startswith(prefix) for prefix in accepted_prefixes)
        or candidate.name != "payload.txt"
    ):
        raise ToolInputError("Internal file-backed content path is outside Darkstar's transfer area.")
    if not candidate.is_file() or candidate.is_symlink():
        raise ToolInputError("Internal file-backed content is not a regular file.")
    if candidate.stat().st_size > 32 * 1024 * 1024:
        raise ToolInputError("Internal file-backed content exceeds the 32 MiB transfer limit.")

    raw = candidate.read_bytes()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolInputError("Internal file-backed content is not valid UTF-8.") from exc
    actual = hashlib.sha256(raw).hexdigest()
    if not isinstance(expected, str) or expected.lower() != actual:
        raise ToolInputError("Internal file-backed content failed its SHA-256 integrity check.")
    return content, True


def handler(args, **kwargs):
    root, path = resolve_workspace_path(args.get("path"), kwargs, must_exist=False, allow_root=False)
    new_content, file_backed = _load_content(args)
    if not isinstance(new_content, str):
        raise ToolInputError("new_content must be a string.")
    if len(new_content) > MAX_TOTAL_CONTENT_CHARS:
        raise ToolInputError(
            f"new_content contains {len(new_content)} characters; the safety maximum is "
            f"{MAX_TOTAL_CONTENT_CHARS} characters. Split extremely large files across replace/append calls."
        )

    mode = args.get("mode", "replace")
    if mode not in ("replace", "append"):
        raise ToolInputError("mode must be either 'replace' or 'append'.")

    existed = path.exists()
    if mode == "append" and not existed:
        raise ToolInputError("Cannot append because the target file does not exist. Start with mode='replace'.")

    old_text = read_utf8(path) if existed else ""
    verify_expected_hash(old_text, args.get("expected_sha256"))
    updated = new_content if mode == "replace" else old_text + new_content
    atomic_write_utf8(path, updated)
    return json_result(
        success=True,
        path=relative_display(root, path),
        mode=mode,
        created=not existed,
        previous_sha256=sha256_text(old_text),
        sha256=sha256_text(updated),
        characters_written=len(new_content),
        total_characters=len(updated),
        bytes_written=len(new_content.encode("utf-8")),
        transport="file-backed" if file_backed else "inline",
    )


registry.register(name=SCHEMA["name"], toolset="filesystem", schema=SCHEMA, handler=handler)
