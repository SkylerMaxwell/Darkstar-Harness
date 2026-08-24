# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: apply exact, anchor-based, atomic UTF-8 edits."""
from __future__ import annotations

import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath
from typing import Any

_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import (
    ToolInputError,
    atomic_write_utf8,
    json_result,
    read_utf8,
    relative_display,
    resolve_workspace_path,
    sha256_text,
)

PROVIDER_ID = "safe-edit-tool"
PROVIDER_NAME = "Safe Edit Tool"
MAX_EDITS = 100

SCHEMA = {
    "name": "safe_edit_tool",
    "description": (
        "Safely replace exact whole lines or line blocks in an existing UTF-8 file. "
        "For each edit, copy the exact target line/block without needing line numbers or a trailing newline. "
        "If the target is repeated, add exact unchanged before and/or after line blocks as alignment anchors. "
        "A target plus its anchors must identify exactly one location. The tool never uses fuzzy matching, "
        "never guesses an occurrence, preserves the file's line endings automatically, and applies every edit "
        "atomically or writes nothing."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "description": "Existing UTF-8 file inside the current project.",
            },
            "edits": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_EDITS,
                "description": (
                    "Exact, non-overlapping line-block replacements. All edits are resolved against the original "
                    "file before any replacement in this call."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "minLength": 1,
                            "description": (
                                "Exact complete line or consecutive line block to replace. Indentation matters. "
                                "Do not include a trailing newline; if one is included it is ignored for matching."
                            ),
                        },
                        "replacement": {
                            "type": "string",
                            "description": (
                                "Replacement line or line block. The tool automatically uses and preserves the "
                                "file's existing line-ending style. Use an empty string to delete the target lines."
                            ),
                        },
                        "before": {
                            "type": "string",
                            "minLength": 1,
                            "description": (
                                "Optional exact unchanged line or line block immediately before target. "
                                "Use this alignment anchor when target is not unique. No trailing newline is required."
                            ),
                        },
                        "after": {
                            "type": "string",
                            "minLength": 1,
                            "description": (
                                "Optional exact unchanged line or line block immediately after target. "
                                "Use this alignment anchor when target is not unique. No trailing newline is required."
                            ),
                        },
                    },
                    "required": ["target", "replacement"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["path", "edits"],
        "additionalProperties": False,
    },
}


def _split_file_lines(text: str) -> tuple[list[str], list[str], list[int]]:
    raw_lines = text.splitlines(keepends=True)
    contents: list[str] = []
    endings: list[str] = []
    offsets: list[int] = []
    cursor = 0
    for raw in raw_lines:
        offsets.append(cursor)
        cursor += len(raw)
        if raw.endswith("\r\n"):
            contents.append(raw[:-2])
            endings.append("\r\n")
        elif raw.endswith("\n") or raw.endswith("\r"):
            contents.append(raw[:-1])
            endings.append(raw[-1:])
        else:
            contents.append(raw)
            endings.append("")
    return contents, endings, offsets


def _logical_lines(value: Any, field: str, index: int, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, str):
        raise ToolInputError(f"Edit {index} {field} must be a string.")
    if not value and not allow_empty:
        raise ToolInputError(f"Edit {index} {field} must be a non-empty complete line or line block.")

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    had_terminal_newline = normalized.endswith("\n")
    if had_terminal_newline:
        normalized = normalized[:-1]

    if not normalized:
        if allow_empty:
            return [""] if had_terminal_newline else []
        if had_terminal_newline:
            return [""]
        raise ToolInputError(f"Edit {index} {field} must contain at least one logical line.")
    return normalized.split("\n")


def _dominant_line_ending(endings: list[str]) -> str:
    counts: dict[str, int] = {}
    for ending in endings:
        if ending:
            counts[ending] = counts.get(ending, 0) + 1
    if not counts:
        return "\n"
    return max(counts.items(), key=lambda item: (item[1], item[0] == "\r\n"))[0]


def _candidate_starts(contents: list[str], target: list[str]) -> list[int]:
    width = len(target)
    if width == 0 or width > len(contents):
        return []
    return [
        start
        for start in range(0, len(contents) - width + 1)
        if contents[start:start + width] == target
    ]


def _matches_before(contents: list[str], start: int, before: list[str]) -> bool:
    if not before:
        return True
    anchor_start = start - len(before)
    return anchor_start >= 0 and contents[anchor_start:start] == before


def _matches_after(contents: list[str], start: int, width: int, after: list[str]) -> bool:
    if not after:
        return True
    anchor_start = start + width
    return contents[anchor_start:anchor_start + len(after)] == after


def _render_replacement(
    replacement_lines: list[str],
    preferred_ending: str,
    original_terminal_ending: str,
) -> str:
    if not replacement_lines:
        return ""
    rendered = preferred_ending.join(replacement_lines)
    if original_terminal_ending:
        rendered += original_terminal_ending
    return rendered


def _short_block(lines: list[str], limit: int = 180) -> str:
    rendered = repr("\n".join(lines))
    return rendered if len(rendered) <= limit else f"{rendered[:limit - 3]}..."


def handler(args: dict[str, Any], **kwargs: Any) -> str:
    root, path = resolve_workspace_path(args.get("path"), kwargs, must_exist=True, allow_root=False)
    original = read_utf8(path)

    edits = args.get("edits")
    if not isinstance(edits, list) or not edits or len(edits) > MAX_EDITS:
        raise ToolInputError(f"edits must contain between 1 and {MAX_EDITS} replacements.")

    contents, endings, offsets = _split_file_lines(original)
    if not contents:
        raise ToolInputError("The file is empty. Safe Edit Tool only replaces existing lines.")
    dominant_ending = _dominant_line_ending(endings)
    validated: list[dict[str, Any]] = []

    for index, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            raise ToolInputError(f"Edit {index} must be an object.")

        target_lines = _logical_lines(edit.get("target"), "target", index, allow_empty=False)
        replacement_lines = _logical_lines(edit.get("replacement"), "replacement", index, allow_empty=True)
        before_lines = (
            _logical_lines(edit.get("before"), "before", index, allow_empty=False)
            if "before" in edit
            else []
        )
        after_lines = (
            _logical_lines(edit.get("after"), "after", index, allow_empty=False)
            if "after" in edit
            else []
        )

        raw_candidates = _candidate_starts(contents, target_lines)
        candidates = [
            start
            for start in raw_candidates
            if _matches_before(contents, start, before_lines)
            and _matches_after(contents, start, len(target_lines), after_lines)
        ]

        if not candidates:
            if raw_candidates and (before_lines or after_lines):
                raise ToolInputError(
                    f"Edit {index} found the target at {len(raw_candidates)} location(s), but none had the exact "
                    "immediately adjacent before/after anchors. No changes were written. Read the target with its "
                    "neighboring lines and copy those anchors exactly."
                )
            raise ToolInputError(
                f"Edit {index} target was not found as an exact whole-line block; no changes were written. "
                f"Target begins with {_short_block(target_lines)}. Read the relevant lines again and copy the "
                "complete line text, including indentation but not the trailing newline."
            )
        if len(candidates) > 1:
            line_numbers = ", ".join(str(start + 1) for start in candidates[:8])
            suffix = "" if len(candidates) <= 8 else f", and {len(candidates) - 8} more"
            raise ToolInputError(
                f"Edit {index} is ambiguous: the target and supplied anchors match {len(candidates)} locations "
                f"(starting at lines {line_numbers}{suffix}). No changes were written. Add an exact unchanged "
                "before and/or after line block that makes the location unique."
            )

        start = candidates[0]
        end = start + len(target_lines) - 1
        start_offset = offsets[start]
        end_offset = offsets[end + 1] if end + 1 < len(offsets) else len(original)
        actual_raw = original[start_offset:end_offset]
        original_terminal_ending = endings[end]
        preferred_ending = next((ending for ending in endings[start:end + 1] if ending), dominant_ending)
        replacement_raw = _render_replacement(
            replacement_lines,
            preferred_ending,
            original_terminal_ending,
        )
        if replacement_raw == actual_raw:
            raise ToolInputError(f"Edit {index} replacement is identical to the current target; no edit is needed.")

        validated.append({
            "index": index,
            "start_line": start + 1,
            "end_line": end + 1,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "replacement": replacement_raw,
            "characters_before": len(actual_raw),
            "characters_after": len(replacement_raw),
            "used_before_anchor": bool(before_lines),
            "used_after_anchor": bool(after_lines),
        })

    by_position = sorted(validated, key=lambda item: (item["start_offset"], item["end_offset"]))
    for previous, current in zip(by_position, by_position[1:]):
        if current["start_offset"] < previous["end_offset"]:
            raise ToolInputError(
                f"Edits {previous['index']} and {current['index']} overlap. Use one combined target and replacement "
                "for that region; no changes were written."
            )

    updated = original
    for edit in sorted(validated, key=lambda item: item["start_offset"], reverse=True):
        updated = (
            updated[:edit["start_offset"]]
            + edit["replacement"]
            + updated[edit["end_offset"]:]
        )

    atomic_write_utf8(path, updated)
    applied = [
        {
            "index": edit["index"],
            "start_line": edit["start_line"],
            "end_line": edit["end_line"],
            "characters_before": edit["characters_before"],
            "characters_after": edit["characters_after"],
            "used_before_anchor": edit["used_before_anchor"],
            "used_after_anchor": edit["used_after_anchor"],
        }
        for edit in sorted(validated, key=lambda item: item["index"])
    ]
    return json_result(
        success=True,
        path=relative_display(root, path),
        edits_applied=applied,
        previous_sha256=sha256_text(original),
        sha256=sha256_text(updated),
        characters_before=len(original),
        characters_after=len(updated),
        total_lines_before=len(contents),
        total_lines_after=len(updated.splitlines()),
    )


registry.register(
    name=SCHEMA["name"],
    toolset="filesystem",
    schema=SCHEMA,
    handler=handler,
)
