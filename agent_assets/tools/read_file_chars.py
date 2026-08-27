# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: read a bounded UTF-8 character range."""
import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath
_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import (
    json_result, read_utf8, relative_display, require_int, resolve_workspace_path, sha256_text,
)

SCHEMA = {
    "name": "read_file_chars",
    "description": (
        "Read UTF-8 text from a file inside the current project by Unicode character offset. "
        "Offsets count decoded characters rather than encoded bytes. The result includes EOF "
        "state, the next offset, and a SHA-256 digest for conflict-safe writes."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "description": "Workspace-relative or workspace-contained absolute file path."},
            "start_char": {"type": "integer", "minimum": 0, "description": "Zero-based character offset. Defaults to 0."},
            "chars_to_read": {"type": "integer", "minimum": 1, "maximum": 100000, "description": "Maximum decoded characters. Defaults to 2500."},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


def handler(args, **kwargs):
    root, path = resolve_workspace_path(args.get("path"), kwargs, must_exist=True)
    start = require_int(args.get("start_char"), "start_char", 0, 0, 2_147_483_647)
    amount = require_int(args.get("chars_to_read"), "chars_to_read", 2500, 1, 100000)
    text = read_utf8(path)
    selected = text[start:start + amount]
    next_offset = min(len(text), start + len(selected))
    eof = next_offset >= len(text)
    return json_result(
        success=True,
        path=relative_display(root, path),
        start_char=start,
        end_char=next_offset,
        total_chars=len(text),
        eof=eof,
        next_start_char=None if eof else next_offset,
        sha256=sha256_text(text),
        text=selected,
    )


registry.register(name=SCHEMA["name"], toolset="filesystem", schema=SCHEMA, handler=handler)
