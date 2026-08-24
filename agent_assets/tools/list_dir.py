# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: list one workspace directory."""
import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath
_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import (
    MAX_DIRECTORY_ENTRIES, ToolInputError, json_result, relative_display, require_bool,
    require_int, resolve_workspace_path,
)

SCHEMA = {
    "name": "list_dir",
    "description": (
        "List the immediate contents of a directory inside the current project. Entries are sorted "
        "with folders first and include type, size, and symbolic-link status. Hidden entries can be "
        "included explicitly, and max_entries bounds the result size."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path inside the project. Defaults to the project root."},
            "include_hidden": {"type": "boolean", "description": "Include names beginning with a dot. Defaults to false."},
            "max_entries": {"type": "integer", "minimum": 1, "maximum": 10000, "description": "Maximum returned entries. Defaults to 1000."},
        },
        "additionalProperties": False,
    },
}


def handler(args, **kwargs):
    raw_path = args.get("path") or "."
    root, directory = resolve_workspace_path(raw_path, kwargs, must_exist=True)
    if not directory.is_dir():
        raise ToolInputError(f"Path is not a directory: {relative_display(root, directory)}")
    include_hidden = require_bool(args.get("include_hidden"), "include_hidden", False)
    maximum = require_int(args.get("max_entries"), "max_entries", 1000, 1, MAX_DIRECTORY_ENTRIES)
    all_entries = []
    for entry in directory.iterdir():
        if not include_hidden and entry.name.startswith("."):
            continue
        try:
            info = entry.lstat()
            is_link = entry.is_symlink()
            if is_link:
                kind = "symlink"
            elif entry.is_dir():
                kind = "directory"
            elif entry.is_file():
                kind = "file"
            else:
                kind = "other"
            all_entries.append({
                "name": entry.name,
                "path": relative_display(root, entry),
                "type": kind,
                "size_bytes": info.st_size if kind == "file" else None,
                "is_symlink": is_link,
            })
        except OSError as exc:
            all_entries.append({"name": entry.name, "path": relative_display(root, entry), "type": "unreadable", "error": str(exc)})
    all_entries.sort(key=lambda item: (item.get("type") != "directory", item["name"].casefold(), item["name"]))
    truncated = len(all_entries) > maximum
    return json_result(
        success=True,
        path=relative_display(root, directory),
        entries=all_entries[:maximum],
        returned_entries=min(len(all_entries), maximum),
        total_entries=len(all_entries),
        truncated=truncated,
    )


registry.register(name=SCHEMA["name"], toolset="filesystem", schema=SCHEMA, handler=handler)
