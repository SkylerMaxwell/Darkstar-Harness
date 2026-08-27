# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: permanently delete a workspace file or directory tree."""
import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath
_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

import shutil
from tools.registry import registry
from _darkstar_tool_common import count_tree_entries, json_result, relative_display, resolve_workspace_path

SCHEMA = {
    "name": "delete",
    "description": (
        "Permanently delete a file or directory tree inside the current project. Directories are "
        "removed recursively. The project root itself and paths outside it are always rejected. "
        "This operation is irreversible and should be used only when deletion is explicitly needed."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "description": "File or folder inside the current project to delete recursively."},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


def handler(args, **kwargs):
    root, path = resolve_workspace_path(args.get("path"), kwargs, must_exist=True, allow_root=False)
    display = relative_display(root, path)
    entries = count_tree_entries(path)
    kind = "directory" if path.is_dir() and not path.is_symlink() else "file"
    if kind == "directory":
        shutil.rmtree(path)
    else:
        path.unlink()
    return json_result(success=True, path=display, deleted_type=kind, deleted_entries=entries)


registry.register(name=SCHEMA["name"], toolset="filesystem", schema=SCHEMA, handler=handler)
