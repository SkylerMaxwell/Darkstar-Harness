# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: read a bounded UTF-8 line range."""
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
    "name": "read_file_lines",
    "description": (
        "Read a bounded range of UTF-8 text lines from a file inside the current project. "
        "Line numbers are one-based. The result includes the exact text, total line count, "
        "EOF state, a continuation line when more content remains, and a SHA-256 digest that "
        "can be supplied to writing tools to prevent overwriting a concurrently changed file."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "description": "Workspace-relative or workspace-contained absolute file path."},
            "start_line": {"type": "integer", "minimum": 1, "description": "One-based first line. Defaults to 1."},
            "lines_to_read": {"type": "integer", "minimum": 1, "maximum": 5000, "description": "Maximum number of lines. Defaults to 500."},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


def handler(args, **kwargs):
    root, path = resolve_workspace_path(args.get("path"), kwargs, must_exist=True)
    start_line = require_int(args.get("start_line"), "start_line", 1, 1, 2_147_483_647)
    lines_to_read = require_int(args.get("lines_to_read"), "lines_to_read", 500, 1, 5000)
    text = read_utf8(path)
    lines = text.splitlines(keepends=True)
    total = len(lines)
    start_index = min(start_line - 1, total)
    selected = lines[start_index:start_index + lines_to_read]
    end_line = start_index + len(selected)
    eof = end_line >= total
    return json_result(
        success=True,
        path=relative_display(root, path),
        start_line=start_line,
        end_line=end_line,
        total_lines=total,
        eof=eof,
        next_start_line=None if eof else end_line + 1,
        sha256=sha256_text(text),
        text="".join(selected),
    )


registry.register(name=SCHEMA["name"], toolset="filesystem", schema=SCHEMA, handler=handler)
