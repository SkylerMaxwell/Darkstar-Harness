# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: change the active project workspace."""
from __future__ import annotations

import os
import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath

_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import ToolInputError, get_filesystem_access, get_working_directory, is_within, request_attention

PROVIDER_ID = "change-working-directory"
PROVIDER_NAME = "Change Working Directory"
ATTENTION_KIND = "workspace.change-directory"

SCHEMA = {
    "name": "change_working_directory",
    "description": (
        "Change Darkstar's current project working directory. "
        "Use an absolute path or a path relative to the current project workspace."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "description": "Absolute directory path, or a path relative to the current project workspace.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


def handler(args, **context):
    requested_path = args.get("path")
    if not isinstance(requested_path, str) or not requested_path.strip():
        raise ToolInputError("path must be a non-empty string.")
    requested_path = requested_path.strip()
    if "\x00" in requested_path:
        raise ToolInputError("path contains an invalid null byte.")
    root, _source = get_working_directory(context)
    # abspath/normpath are lexical only: the requested target is not stat'd,
    # realpath'd, opened, or otherwise probed until the user chooses Allow.
    target_path = os.path.abspath(os.path.normpath(requested_path))
    access = get_filesystem_access(context)
    boundary = access.get('root')
    if access.get('configured') and boundary is not None and not is_within(boundary, _DarkstarPath(target_path)):
        raise ToolInputError(f"Requested directory is outside Filesystem Access Level {access['level']}.")
    if os.path.normcase(target_path) == os.path.normcase(str(root)):
        return {
            "success": True,
            "changed": False,
            "path": target_path,
            "message": "The requested directory is already the active workspace.",
        }
    return request_attention(
        kind=ATTENTION_KIND,
        title="Permission required",
        prompt=f'Allow the model to change the working directory to "{target_path}"?',
        payload={"targetPath": target_path},
    )


registry.register(
    name=SCHEMA["name"],
    toolset="workspace",
    schema=SCHEMA,
    handler=handler,
    description=SCHEMA["description"],
    permission={"risk": "external"},
    filesystem="scoped",
)
