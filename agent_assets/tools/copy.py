# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: copy a workspace file or folder."""
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
    ToolInputError, count_tree_entries, ensure_tree_has_no_symlinks, json_result, relative_display,
    require_bool, resolve_workspace_path,
)

SCHEMA = {
    "name": "copy",
    "description": (
        "Copy a file or complete folder tree within the current project while preserving file metadata. "
        "The destination is the exact final path, missing parent folders are created, and existing "
        "destinations are rejected unless overwrite=true. Symbolic-link sources are rejected to prevent "
        "copying data from outside the workspace."
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
    ensure_tree_has_no_symlinks(source)
    if source == destination:
        raise ToolInputError("Source and destination are the same path.")
    source_key = os.path.normcase(str(source))
    destination_key = os.path.normcase(str(destination))
    if source.is_dir() and destination_key.startswith(source_key + os.sep):
        raise ToolInputError("A folder cannot be copied inside itself.")
    destination_existed = destination.exists() or destination.is_symlink()
    if destination_existed and not overwrite:
        raise ToolInputError(f"Destination already exists: {relative_display(root, destination)}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}.copy-{uuid.uuid4().hex}"
    backup = None
    try:
        if source.is_dir():
            shutil.copytree(source, staging, copy_function=shutil.copy2, symlinks=False)
            kind = "directory"
        else:
            shutil.copy2(source, staging)
            kind = "file"
        if destination_existed:
            backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
            shutil.move(str(destination), str(backup))
        shutil.move(str(staging), str(destination))
    except Exception:
        if staging.exists() or staging.is_symlink():
            _remove_existing(staging)
        if backup is not None and (backup.exists() or backup.is_symlink()) and not destination.exists():
            shutil.move(str(backup), str(destination))
        raise
    cleanup_warning = None
    if backup is not None and (backup.exists() or backup.is_symlink()):
        try:
            _remove_existing(backup)
        except OSError as exc:
            cleanup_warning = f"Copy succeeded, but the temporary backup could not be removed: {exc}"
    return json_result(
        success=True,
        source=relative_display(root, source),
        destination=relative_display(root, destination),
        copied_type=kind,
        copied_entries=count_tree_entries(destination),
        replaced_existing=destination_existed,
        cleanup_warning=cleanup_warning,
    )


registry.register(name=SCHEMA["name"], toolset="filesystem", schema=SCHEMA, handler=handler)
