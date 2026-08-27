# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: return the project folder currently used as workspace."""
import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath
_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import get_working_directory, json_result

SCHEMA = {
    "name": "get_current_project_working_directory",
    "description": (
        "Return the absolute path of the project folder currently opened in Darkstar. "
        "Use this before filesystem work when the active workspace location is unknown. "
        "The tool accepts no arguments and performs no filesystem modification."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


def handler(args, **kwargs):
    root, source = get_working_directory(kwargs)
    return json_result(success=True, working_directory=str(root), source=source)


registry.register(name=SCHEMA["name"], toolset="workspace", schema=SCHEMA, handler=handler)
