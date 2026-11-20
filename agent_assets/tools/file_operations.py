# SPDX-License-Identifier: LicenseRef-Darkstar-3.0
"""Darkstar file operations: create, edit, and read within the existing workspace scope."""
from __future__ import annotations

from tools.registry import registry

# ---------------------------------------------------------------------------
# Self-contained helpers. Darkstar tools are self-sufficient: this file imports
# no shared Darkstar helper module, so it can be read, copied or moved on its own.
# ---------------------------------------------------------------------------
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Iterable

MAX_TEXT_FILE_BYTES = 32 * 1024 * 1024
MAX_EDITS = 100


class ToolInputError(ValueError):
    """Raised when a tool request is invalid or unsafe."""


def json_result(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _mapping_candidates(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for key in ("context", "execution_context", "executionContext", "workspace"):
            nested = value.get(key)
            if isinstance(nested, dict):
                yield from _mapping_candidates(nested)


def _path_from_context(kwargs: dict[str, Any]) -> tuple[str | None, str | None]:
    keys = (
        "working_directory",
        "workingDirectory",
        "workspace",
        "workspace_directory",
        "workspaceDirectory",
        "workspace_root",
        "workspaceRoot",
        "workspace_dir",
        "workspaceDir",
        "project_directory",
        "projectDirectory",
        "project_path",
        "projectPath",
        "cwd",
        "root",
        "root_path",
        "rootPath",
        "path",
    )
    for mapping in _mapping_candidates(kwargs):
        for key in keys:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), f"context.{key}"
    for key in (
        "DARKSTAR_WORKING_DIRECTORY",
        "DARKSTAR_WORKSPACE_DIRECTORY",
        "DARKSTAR_PROJECT_DIRECTORY",
    ):
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip(), f"environment.{key}"
    return None, None


def get_working_directory(kwargs: dict[str, Any], *, must_exist: bool = True) -> tuple[Path, str]:
    """Return the project directory from the host execution context."""
    raw, source = _path_from_context(kwargs)
    if not raw:
        raw = os.getcwd()
        source = "process.cwd"
    root = Path(raw).expanduser().resolve(strict=False)
    if must_exist and not root.exists():
        raise ToolInputError(f"The current project working directory does not exist: {root}")
    if root.exists() and not root.is_dir():
        raise ToolInputError(f"The current project working directory is not a folder: {root}")
    return root, source or "unknown"


def get_attached_roots(kwargs: dict[str, Any]) -> tuple[Path, ...]:
    """Directories attached to the current project by Core."""
    raw = kwargs.get("attached_roots")
    if not isinstance(raw, (list, tuple)):
        for mapping in _mapping_candidates(kwargs):
            candidate = mapping.get("attached_roots")
            if isinstance(candidate, (list, tuple)):
                raw = candidate
                break
    return tuple(
        Path(value).expanduser().resolve(strict=False)
        for value in (raw if isinstance(raw, (list, tuple)) else [])
        if isinstance(value, str) and value.strip()
    )


def _normcase(path: Path) -> str:
    return os.path.normcase(str(path))


def is_within(root: Path, candidate: Path) -> bool:
    try:
        common = os.path.commonpath([_normcase(root), _normcase(candidate)])
    except ValueError:
        return False
    return common == _normcase(root)


def _attached_root_by_name(attached_roots: tuple[Path, ...], name: str) -> Path | None:
    """Return the attached directory whose folder name matches (case-insensitive)."""
    lowered = str(name or "").casefold()
    if not lowered:
        return None
    for attached in attached_roots:
        if attached.name.casefold() == lowered:
            return attached
    return None


def resolve_workspace_path(
    raw_path: Any,
    kwargs: dict[str, Any],
    *,
    must_exist: bool = False,
    allow_root: bool = True,
) -> tuple[Path, Path]:
    workspace, _ = get_working_directory(kwargs)
    attached_roots = () if kwargs.get("explicit_shared_paths") is True else get_attached_roots(kwargs)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ToolInputError("A non-empty path is required.")
    supplied = Path(raw_path.strip()).expanduser()
    owner: Path | None = None
    if supplied.is_absolute():
        candidate = Path(os.path.abspath(os.path.normpath(str(supplied))))
    else:
        candidate = Path(os.path.abspath(os.path.normpath(str(workspace / supplied))))
        # Relative paths address the project directory first. A leading segment
        # matching an attached directory name resolves into that directory when
        # the project directory does not own the path: existing project paths win,
        # then existing attached paths, then the project directory (where new
        # files are created).
        segments = [segment for segment in str(supplied).replace("\\", "/").split("/") if segment]
        attached = _attached_root_by_name(attached_roots, segments[0] if segments else "")
        if attached is not None:
            remaining = "/".join(segments[1:])
            attached_candidate = Path(os.path.normpath(str(attached / remaining))) if remaining else attached
            if must_exist:
                if not (candidate.exists() or candidate.is_symlink()) and (attached_candidate.exists() or attached_candidate.is_symlink()):
                    candidate = attached_candidate
                    owner = attached
            elif attached_candidate.parent.exists() and attached_candidate.parent.is_dir():
                candidate = attached_candidate
                owner = attached

    if owner is not None:
        if _normcase(candidate) == _normcase(owner):
            resolved = owner
        else:
            resolved = candidate.parent.resolve(strict=False) / candidate.name
        if not is_within(owner, resolved):
            raise ToolInputError(f"Path resolves outside the attached directory: {raw_path}")
    else:
        resolved = candidate
    if not allow_root and _normcase(resolved) == _normcase(workspace):
        raise ToolInputError("This operation cannot target the project working directory itself.")
    if must_exist and not (resolved.exists() or resolved.is_symlink()):
        raise ToolInputError(f"Path does not exist: {raw_path}")
    # Display paths are relative to the project directory; anything outside it (an attached
    # directory) is reported by absolute path, which every tool accepts as input.
    return workspace, resolved


def relative_display(root: Path, path: Path) -> str:
    if _normcase(root) == _normcase(path):
        return "."
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def ensure_regular_text_file(path: Path, *, max_bytes: int = MAX_TEXT_FILE_BYTES) -> None:
    if not path.exists():
        raise ToolInputError(f"File does not exist: {path}")
    if path.is_symlink():
        raise ToolInputError(f"Symbolic links are not accepted as text files: {path}")
    if not path.is_file():
        raise ToolInputError(f"Path is not a regular file: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise ToolInputError(f"Text file is too large ({size} bytes; maximum {max_bytes} bytes).")


def read_utf8(path: Path, *, max_bytes: int = MAX_TEXT_FILE_BYTES) -> str:
    ensure_regular_text_file(path, max_bytes=max_bytes)
    data = path.read_bytes()
    if b"\x00" in data:
        raise ToolInputError(f"File appears to be binary and cannot be read as UTF-8 text: {path}")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ToolInputError(
            f"File is not valid UTF-8 at byte {exc.start}: {path}"
        ) from exc


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_utf8(path: Path, text: str) -> None:
    if not isinstance(text, str):
        raise ToolInputError("Text content must be a string.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise ToolInputError(f"Refusing to replace a symbolic link: {path}")
    mode = None
    if path.exists():
        mode = stat.S_IMODE(path.stat().st_mode)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        finally:
            raise

def require_int(value: Any, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInputError(f"{name} must be an integer.")
    if value < minimum or value > maximum:
        raise ToolInputError(f"{name} must be between {minimum} and {maximum}.")
    return value

def create_file(args, **kwargs):
    root, target = resolve_workspace_path(args.get("path"), kwargs, must_exist=False, allow_root=False)
    shown = relative_display(root, target)
    if target.exists() or target.is_symlink():
        kind = "folder" if target.is_dir() and not target.is_symlink() else "file"
        raise ToolInputError(
            f"Cannot create {shown}: a {kind} already exists at that path. The create action only creates new "
            "empty files and never modifies existing ones. Choose a different path, or edit the existing file "
            "with an editing tool. Nothing was changed."
        )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError) as error:
        raise ToolInputError(
            f"Cannot create {shown}: a parent of this path is an existing file, not a folder."
        ) from error

    # Exclusive creation fails atomically if the path appears between the check above and this
    # call (including a symlink, which is never followed), so existing data cannot be overwritten.
    try:
        descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    except FileExistsError as error:
        raise ToolInputError(
            f"Cannot create {shown}: something already exists at that path. Nothing was changed."
        ) from error
    os.close(descriptor)

    return json_result(
        success=True,
        created=True,
        path=shown,
    )

def read_lines(args, **kwargs):
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


def edit_file(args: dict[str, Any], **kwargs: Any) -> str:
    root, path = resolve_workspace_path(args.get("path"), kwargs, must_exist=True, allow_root=False)
    original = read_utf8(path)

    edits = args.get("edits")
    if not isinstance(edits, list) or not edits or len(edits) > MAX_EDITS:
        raise ToolInputError(f"edits must contain between 1 and {MAX_EDITS} replacements.")

    contents, endings, offsets = _split_file_lines(original)
    if not contents:
        # An empty file has no line to match, so it is filled by one edit with an empty target: the replacement
        # becomes the whole file, written exactly as given.
        only = edits[0] if len(edits) == 1 and isinstance(edits[0], dict) else None
        if only is None or only.get("target") not in ("", None) or "before" in only or "after" in only:
            raise ToolInputError(
                "The file is empty, so there is no line to match. Send exactly one edit with target set to an empty "
                "string and the new content as replacement (no before/after anchors); no changes were written."
            )
        replacement = only.get("replacement")
        if not isinstance(replacement, str) or not replacement:
            raise ToolInputError("Edit 1 replacement must be the non-empty content to write into the empty file.")
        atomic_write_utf8(path, replacement)
        return json_result(
            success=True,
            path=relative_display(root, path),
            filled_empty_file=True,
            edits_applied=[{
                "index": 1, "start_line": 1, "end_line": 1, "characters_before": 0, "characters_after": len(replacement),
                "used_before_anchor": False, "used_after_anchor": False,
            }],
            previous_sha256=sha256_text(original),
            sha256=sha256_text(replacement),
            characters_before=0,
            characters_after=len(replacement),
            total_lines_before=0,
            total_lines_after=len(replacement.splitlines()),
        )
    dominant_ending = _dominant_line_ending(endings)
    validated: list[dict[str, Any]] = []

    for index, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            raise ToolInputError(f"Edit {index} must be an object.")

        if edit.get("target") in ("", None):
            raise ToolInputError(f"Edit {index} target must be a non-empty complete line or line block (an empty target is only for filling an empty file).")
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

SCHEMA = {
    "name": "file_operations",
    "description": (
        "File operations within the current project's existing workspace scope. "
        "Choose exactly one action: create makes a new ZERO-BYTE file only (never overwrites), "
        "edit applies exact whole-line replacements to an EXISTING UTF-8 file atomically "
        "(an empty file is filled with one edit whose target is an empty string), "
        "or read returns bounded UTF-8 lines with line numbers, EOF, and SHA-256. "
        "Create may make missing parent directories; edit never creates files. "
        "Each action retains its own input limits and path restrictions."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "edit", "read"],
                       "description": "create a new empty file; edit an existing file; or read existing file lines."},
            "path": {"type": "string", "minLength": 1,
                     "description": "Workspace-relative or workspace-contained absolute path, subject to the current scope."},
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
                            "description": (
                                "Exact complete line or consecutive line block to replace. Indentation matters. "
                                "Do not include a trailing newline; if one is included it is ignored for matching. "
                                "Use an empty string only when the file is empty: the replacement then becomes the file's content."
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
            "start_line": {"type": "integer", "minimum": 1,
                           "description": "read only: first line, one-based; defaults to 1."},
            "lines_to_read": {"type": "integer", "minimum": 1, "maximum": 5000,
                              "description": "read only: number of lines; defaults to 500."},
        },
        "required": ["action", "path"],
        "additionalProperties": False,
    },
}

_ACTION_ARGUMENTS = {
    "create": frozenset(("action", "path")),
    "edit": frozenset(("action", "path", "edits")),
    "read": frozenset(("action", "path", "start_line", "lines_to_read")),
}


def handler(args: dict[str, Any], *, explicit_shared_paths: bool = False, **kwargs: Any) -> str:
    kwargs["explicit_shared_paths"] = explicit_shared_paths
    if not isinstance(args, dict):
        raise ToolInputError("Tool arguments must be an object.")
    action = args.get("action")
    if not isinstance(action, str) or action not in _ACTION_ARGUMENTS:
        raise ToolInputError("action must be create, edit, or read.")
    unexpected = args.keys() - _ACTION_ARGUMENTS[action]
    if unexpected:
        raise ToolInputError(f"The {action} action does not accept: {', '.join(sorted(unexpected))}.")
    if action == "create":
        return create_file(args, **kwargs)
    if action == "edit":
        return edit_file(args, **kwargs)
    return read_lines(args, **kwargs)


registry.register(
    name=SCHEMA["name"],
    toolset="filesystem",
    schema=SCHEMA,
    handler=handler,
    description=SCHEMA["description"],
    writes=["path"],
)
