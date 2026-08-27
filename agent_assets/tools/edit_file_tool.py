# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: apply exact, atomic UTF-8 replacements."""
import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath
_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import (
    ToolInputError, atomic_write_utf8, json_result, read_utf8, relative_display,
    resolve_workspace_path, sha256_text, verify_expected_hash,
)

SCHEMA = {
    "name": "edit_file_tool",
    "description": (
        "Edit an existing UTF-8 text file inside the current project by applying one or more exact "
        "string replacements atomically. Each edit defaults to requiring exactly one match; set "
        "replace_all=true to replace every occurrence. If any edit is missing or ambiguous, nothing "
        "is written. Supply expected_sha256 from a prior read for conflict-safe editing."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "description": "Existing text file inside the current project."},
            "edits": {
                "type": "array", "minItems": 1, "maxItems": 200,
                "description": "Ordered exact replacements applied to an in-memory copy before one atomic write.",
                "items": {
                    "type": "object",
                    "properties": {
                        "search": {"type": "string", "minLength": 1, "description": "Exact text to find."},
                        "replace": {"type": "string", "description": "Replacement text."},
                        "replace_all": {"type": "boolean", "description": "Replace every match instead of requiring exactly one. Defaults to false."},
                    },
                    "required": ["search", "replace"],
                    "additionalProperties": False,
                },
            },
            "expected_sha256": {"type": "string", "description": "Optional SHA-256 digest returned by a prior read."},
        },
        "required": ["path", "edits"],
        "additionalProperties": False,
    },
}


def handler(args, **kwargs):
    root, path = resolve_workspace_path(args.get("path"), kwargs, must_exist=True, allow_root=False)
    original = read_utf8(path)
    verify_expected_hash(original, args.get("expected_sha256"))
    edits = args.get("edits")
    if not isinstance(edits, list) or not edits or len(edits) > 200:
        raise ToolInputError("edits must contain between 1 and 200 replacements.")
    updated = original
    applied = []
    for index, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            raise ToolInputError(f"Edit {index} must be an object.")
        search = edit.get("search")
        replace = edit.get("replace")
        replace_all = edit.get("replace_all", False)
        if not isinstance(search, str) or not search:
            raise ToolInputError(f"Edit {index} search must be a non-empty string.")
        if not isinstance(replace, str):
            raise ToolInputError(f"Edit {index} replace must be a string.")
        if not isinstance(replace_all, bool):
            raise ToolInputError(f"Edit {index} replace_all must be a boolean.")
        matches = updated.count(search)
        if matches == 0:
            raise ToolInputError(f"Edit {index} search text was not found; no changes were written.")
        if not replace_all and matches != 1:
            raise ToolInputError(
                f"Edit {index} matched {matches} times. Use a more specific search string or set replace_all=true."
            )
        updated = updated.replace(search, replace) if replace_all else updated.replace(search, replace, 1)
        applied.append({"index": index, "replacements": matches if replace_all else 1})
    atomic_write_utf8(path, updated)
    return json_result(
        success=True,
        path=relative_display(root, path),
        edits_applied=applied,
        previous_sha256=sha256_text(original),
        sha256=sha256_text(updated),
        characters_before=len(original),
        characters_after=len(updated),
    )


registry.register(name=SCHEMA["name"], toolset="filesystem", schema=SCHEMA, handler=handler)
