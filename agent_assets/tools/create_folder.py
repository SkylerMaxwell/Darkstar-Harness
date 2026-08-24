# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: create a workspace folder and its parents."""
import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath
_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import ToolInputError, json_result, relative_display, resolve_workspace_path

SCHEMA = {
    "name": "create_folder",
    "description": (
        "Create a folder inside the current project, including any missing parent folders. Existing "
        "folders are treated as success; an existing non-folder at the target path is rejected."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "description": "Folder path inside the current project."},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


def handler(args, **kwargs):
    root, path = resolve_workspace_path(args.get("path"), kwargs, must_exist=False, allow_root=True)
    existed = path.exists()
    if existed and not path.is_dir():
        raise ToolInputError(f"A non-folder already exists at {relative_display(root, path)}")
    path.mkdir(parents=True, exist_ok=True)
    return json_result(success=True, path=relative_display(root, path), created=not existed)


registry.register(name=SCHEMA["name"], toolset="filesystem", schema=SCHEMA, handler=handler)
