# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: move or rename a workspace file or folder."""
import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath
_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

import os
import shutil
import uuid
from tools.registry import registry
from _darkstar_tool_common import (
    ToolInputError, json_result, relative_display, require_bool, resolve_workspace_path,
)

SCHEMA = {
    "name": "move",
    "description": (
        "Move or rename one file or folder within the current project. The destination is interpreted "
        "as the exact final path, missing parent folders are created, and existing destinations are "
        "rejected unless overwrite=true. The project root and paths outside it cannot be moved."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "source": {"type": "string", "minLength": 1, "description": "Existing source path inside the current project."},
            "destination": {"type": "string", "minLength": 1, "description": "Exact final destination path inside the current project."},
            "overwrite": {"type": "boolean", "description": "Replace an existing destination. Defaults to false."},
        },
        "required": ["source", "destination"],
        "additionalProperties": False,
    },
}


def _remove_existing(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def handler(args, **kwargs):
    root, source = resolve_workspace_path(args.get("source"), kwargs, must_exist=True, allow_root=False)
    _, destination = resolve_workspace_path(args.get("destination"), kwargs, must_exist=False, allow_root=False)
    overwrite = require_bool(args.get("overwrite"), "overwrite", False)
    if source == destination:
        raise ToolInputError("Source and destination are the same path.")
    source_key = os.path.normcase(str(source))
    destination_key = os.path.normcase(str(destination))
    if source.is_dir() and not source.is_symlink() and destination_key.startswith(source_key + os.sep):
        raise ToolInputError("A folder cannot be moved inside itself.")
    destination_existed = destination.exists() or destination.is_symlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if destination_existed:
        if not overwrite:
            raise ToolInputError(f"Destination already exists: {relative_display(root, destination)}")
        backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
        shutil.move(str(destination), str(backup))
    try:
        shutil.move(str(source), str(destination))
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            shutil.move(str(backup), str(destination))
        raise
    cleanup_warning = None
    if backup is not None and (backup.exists() or backup.is_symlink()):
        try:
            _remove_existing(backup)
        except OSError as exc:
            cleanup_warning = f"Move succeeded, but the temporary backup could not be removed: {exc}"
    return json_result(
        success=True,
        source=relative_display(root, source),
        destination=relative_display(root, destination),
        replaced_existing=destination_existed,
        cleanup_warning=cleanup_warning,
    )


registry.register(name=SCHEMA["name"], toolset="filesystem", schema=SCHEMA, handler=handler)
