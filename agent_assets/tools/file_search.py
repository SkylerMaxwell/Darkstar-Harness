# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: recursively search project text files for matching lines.

This provider is self-contained and requires only the ``tools.registry`` module
supplied by Darkstar's Python tool host. It performs literal text search rather
than executing a shell command, so search strings cannot become shell input.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

from tools.registry import registry


DEFAULT_MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_ALLOWED_FILE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ALLOWED_TOTAL_BYTES = 1024 * 1024 * 1024
DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
    }
)


class ToolInputError(ValueError):
    """Raised when a request is invalid or would escape the active workspace."""


def _json_result(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _mapping_candidates(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for key in ("context", "execution_context", "executionContext", "workspace"):
            nested = value.get(key)
            if isinstance(nested, dict):
                yield from _mapping_candidates(nested)


def _working_directory(kwargs: dict[str, Any]) -> Path:
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
    raw: str | None = None
    for mapping in _mapping_candidates(kwargs):
        for key in keys:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                raw = value.strip()
                break
        if raw:
            break

    if not raw:
        for key in (
            "DARKSTAR_WORKING_DIRECTORY",
            "DARKSTAR_WORKSPACE_DIRECTORY",
            "DARKSTAR_PROJECT_DIRECTORY",
            # Legacy environment names remain accepted for older custom hosts.
            "BLACKSUN_WORKING_DIRECTORY",
            "BLACKSUN_WORKSPACE_DIRECTORY",
            "BLACKSUN_PROJECT_DIRECTORY",
        ):
            value = os.environ.get(key)
            if value and value.strip():
                raw = value.strip()
                break

    root = Path(raw or os.getcwd()).expanduser().resolve(strict=False)
    if not root.exists():
        raise ToolInputError(f"The current project working directory does not exist: {root}")
    if not root.is_dir():
        raise ToolInputError(f"The current project working directory is not a folder: {root}")
    return root


def _normcase(path: Path) -> str:
    return os.path.normcase(str(path))


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        common = os.path.commonpath([_normcase(root), _normcase(candidate)])
    except ValueError:
        return False
    return common == _normcase(root)


def _resolve_search_path(raw_path: Any, kwargs: dict[str, Any]) -> tuple[Path, Path]:
    root = _working_directory(kwargs)
    if raw_path in (None, ""):
        raw_path = "."
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ToolInputError("path must be a non-empty string when supplied.")

    supplied = Path(raw_path.strip()).expanduser()
    lexical = supplied if supplied.is_absolute() else root / supplied
    lexical = Path(os.path.abspath(os.path.normpath(str(lexical))))
    if not _is_within(root, lexical):
        raise ToolInputError(f"Path escapes the current project working directory: {raw_path}")

    if _normcase(lexical) == _normcase(root):
        candidate = root
    else:
        candidate = lexical.parent.resolve(strict=False) / lexical.name
    if not _is_within(root, candidate):
        raise ToolInputError(f"Path escapes the current project working directory: {raw_path}")
    if not (candidate.exists() or candidate.is_symlink()):
        raise ToolInputError(f"Search path does not exist: {raw_path}")
    if candidate.is_symlink():
        raise ToolInputError("Symbolic links cannot be used as file_search roots.")
    if not (candidate.is_file() or candidate.is_dir()):
        raise ToolInputError(f"Search path is not a regular file or directory: {raw_path}")
    return root, candidate


def _relative_display(root: Path, path: Path) -> str:
    if _normcase(root) == _normcase(path):
        return "."
    return path.relative_to(root).as_posix()


def _require_bool(value: Any, name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ToolInputError(f"{name} must be a boolean.")
    return value


def _require_int(
    value: Any,
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInputError(f"{name} must be an integer.")
    if value < minimum or value > maximum:
        raise ToolInputError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _require_globs(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ToolInputError(f"{name} must be an array of glob strings.")
    if len(value) > 100:
        raise ToolInputError(f"{name} accepts at most 100 glob patterns.")
    patterns: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ToolInputError(f"{name}[{index}] must be a non-empty string.")
        pattern = item.strip().replace("\\", "/")
        if len(pattern) > 500:
            raise ToolInputError(f"{name}[{index}] is longer than 500 characters.")
        patterns.append(pattern)
    return patterns


def _glob_matches(relative_path: str, pattern: str) -> bool:
    """Match project-relative paths while making ``**/x`` include root-level ``x``."""
    path = relative_path.replace("\\", "/")
    if fnmatch.fnmatchcase(path, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]):
        return True
    return "/" not in pattern and fnmatch.fnmatchcase(Path(path).name, pattern)


def _matches_any(relative_path: str, patterns: list[str]) -> bool:
    return any(_glob_matches(relative_path, pattern) for pattern in patterns)


def _is_hidden_relative(root: Path, path: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part.startswith(".") and part not in (".", "..") for part in parts)


def _iter_candidate_files(
    workspace_root: Path,
    search_path: Path,
    *,
    include_hidden: bool,
    include_common_excluded_directories: bool,
    include_globs: list[str],
    exclude_globs: list[str],
) -> Iterator[Path]:
    if search_path.is_file():
        yield search_path
        return

    for current, directories, files in os.walk(search_path, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_directories: list[str] = []
        for name in sorted(directories, key=lambda item: (item.casefold(), item)):
            candidate = current_path / name
            if candidate.is_symlink():
                continue
            if not include_hidden and name.startswith("."):
                continue
            if (
                not include_common_excluded_directories
                and name in DEFAULT_EXCLUDED_DIRECTORIES
            ):
                continue
            relative = _relative_display(workspace_root, candidate)
            if exclude_globs and _matches_any(relative, exclude_globs):
                continue
            kept_directories.append(name)
        directories[:] = kept_directories

        for name in sorted(files, key=lambda item: (item.casefold(), item)):
            candidate = current_path / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if not include_hidden and _is_hidden_relative(search_path, candidate):
                continue
            relative = _relative_display(workspace_root, candidate)
            if include_globs and not _matches_any(relative, include_globs):
                continue
            if exclude_globs and _matches_any(relative, exclude_globs):
                continue
            yield candidate


def _line_snippet(line: str, match_start: int, maximum: int) -> dict[str, Any]:
    if len(line) <= maximum:
        return {
            "line": line,
            "line_length": len(line),
            "line_truncated": False,
            "snippet_start_column": 1,
            "snippet_end_column": len(line),
        }

    left_context = maximum // 3
    start = max(0, match_start - left_context)
    end = min(len(line), start + maximum)
    start = max(0, end - maximum)
    return {
        "line": line[start:end],
        "line_length": len(line),
        "line_truncated": True,
        "snippet_start_column": start + 1,
        "snippet_end_column": end,
    }


def _read_searchable_text(path: Path, maximum_bytes: int) -> tuple[str | None, str | None, int]:
    try:
        size = path.stat().st_size
    except OSError:
        return None, "unreadable", 0
    if size > maximum_bytes:
        return None, "too_large", size
    try:
        data = path.read_bytes()
    except OSError:
        return None, "unreadable", size
    if b"\x00" in data:
        return None, "binary", len(data)
    try:
        return data.decode("utf-8-sig"), None, len(data)
    except UnicodeDecodeError:
        return None, "non_utf8", len(data)


SCHEMA = {
    "name": "file_search",
    "description": (
        "Search recursively across UTF-8 text files in the current project for an exact text "
        "fragment. Use this to locate function or class definitions, identifiers, error messages, "
        "configuration keys, imports, and other strings without reading files one by one. Results "
        "are deterministic and include each matching project-relative file path, one-based line "
        "number, first matching column, occurrence count, and a bounded copy of the matching line. "
        "The search is literal, not shell or regular-expression execution. By default it skips "
        "binary files, symbolic links, hidden paths, .git/.hg/.svn, node_modules, virtual "
        "environments, and __pycache__. Use include_globs or exclude_globs to narrow the search, "
        "and offset with max_results to continue a truncated result set. After locating a match, "
        "use read_file_lines to inspect its surrounding code."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 1,
                "maxLength": 10000,
                "description": "Exact text fragment to find. Newline characters are not accepted.",
            },
            "path": {
                "type": "string",
                "description": "File or directory inside the project to search. Defaults to the project root.",
                "default": ".",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Match letter case exactly. Defaults to true.",
                "default": True,
            },
            "whole_word": {
                "type": "boolean",
                "description": "Require identifier-style word boundaries around the exact query. Defaults to false.",
                "default": False,
            },
            "include_globs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "maxItems": 100,
                "description": "Optional project-relative file globs to include, such as ['**/*.py', '**/*.js'].",
            },
            "exclude_globs": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "maxItems": 100,
                "description": "Optional project-relative file or directory globs to exclude, such as ['dist/**', '**/*.min.js'].",
            },
            "include_hidden": {
                "type": "boolean",
                "description": "Search dotfiles and dot-directories. Defaults to false.",
                "default": False,
            },
            "include_common_excluded_directories": {
                "type": "boolean",
                "description": "Also search .git, .hg, .svn, node_modules, virtual environments, and __pycache__. Defaults to false.",
                "default": False,
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "maximum": 1000000,
                "description": "Skip this many matching lines before returning results. Defaults to 0.",
                "default": 0,
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000,
                "description": "Maximum matching lines to return. Defaults to 200.",
                "default": 200,
            },
            "max_line_chars": {
                "type": "integer",
                "minimum": 80,
                "maximum": 10000,
                "description": "Maximum characters returned from each matching line. Long lines are centered near the first match. Defaults to 1200.",
                "default": 1200,
            },
            "max_file_bytes": {
                "type": "integer",
                "minimum": 1024,
                "maximum": MAX_ALLOWED_FILE_BYTES,
                "description": "Skip individual files larger than this many bytes. Defaults to 8388608 (8 MiB).",
                "default": DEFAULT_MAX_FILE_BYTES,
            },
            "max_files": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100000,
                "description": "Maximum candidate files to inspect. Defaults to 20000.",
                "default": 20000,
            },
            "max_total_bytes": {
                "type": "integer",
                "minimum": 1024,
                "maximum": MAX_ALLOWED_TOTAL_BYTES,
                "description": "Maximum aggregate file bytes to inspect. Defaults to 268435456 (256 MiB).",
                "default": DEFAULT_MAX_TOTAL_BYTES,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


def handler(args: dict[str, Any], **kwargs: Any) -> str:
    if not isinstance(args, dict):
        raise ToolInputError("file_search arguments must be an object.")

    query = args.get("query")
    if not isinstance(query, str) or not query:
        raise ToolInputError("query must be a non-empty string.")
    if len(query) > 10_000:
        raise ToolInputError("query cannot exceed 10,000 characters.")
    if "\n" in query or "\r" in query:
        raise ToolInputError("file_search is line-based; query cannot contain newline characters.")

    workspace_root, search_path = _resolve_search_path(args.get("path", "."), kwargs)
    case_sensitive = _require_bool(args.get("case_sensitive"), "case_sensitive", True)
    whole_word = _require_bool(args.get("whole_word"), "whole_word", False)
    include_hidden = _require_bool(args.get("include_hidden"), "include_hidden", False)
    include_common = _require_bool(
        args.get("include_common_excluded_directories"),
        "include_common_excluded_directories",
        False,
    )
    include_globs = _require_globs(args.get("include_globs"), "include_globs")
    exclude_globs = _require_globs(args.get("exclude_globs"), "exclude_globs")
    offset = _require_int(args.get("offset"), "offset", 0, 0, 1_000_000)
    max_results = _require_int(args.get("max_results"), "max_results", 200, 1, 1000)
    max_line_chars = _require_int(args.get("max_line_chars"), "max_line_chars", 1200, 80, 10_000)
    max_file_bytes = _require_int(
        args.get("max_file_bytes"),
        "max_file_bytes",
        DEFAULT_MAX_FILE_BYTES,
        1024,
        MAX_ALLOWED_FILE_BYTES,
    )
    max_files = _require_int(args.get("max_files"), "max_files", 20_000, 1, 100_000)
    max_total_bytes = _require_int(
        args.get("max_total_bytes"),
        "max_total_bytes",
        DEFAULT_MAX_TOTAL_BYTES,
        1024,
        MAX_ALLOWED_TOTAL_BYTES,
    )

    escaped = re.escape(query)
    expression = rf"(?<!\w){escaped}(?!\w)" if whole_word else escaped
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(expression, flags)

    matches: list[dict[str, Any]] = []
    matching_lines_seen = 0
    files_considered = 0
    files_scanned = 0
    bytes_scanned = 0
    skipped = {
        "binary": 0,
        "non_utf8": 0,
        "too_large": 0,
        "unreadable": 0,
    }
    truncated = False
    limit_reason: str | None = None

    candidates = _iter_candidate_files(
        workspace_root,
        search_path,
        include_hidden=include_hidden,
        include_common_excluded_directories=include_common,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
    )

    for candidate in candidates:
        if files_considered >= max_files:
            truncated = True
            limit_reason = "max_files"
            break
        files_considered += 1

        text, skip_reason, byte_count = _read_searchable_text(candidate, max_file_bytes)
        if skip_reason:
            skipped[skip_reason] += 1
            continue
        if bytes_scanned + byte_count > max_total_bytes:
            truncated = True
            limit_reason = "max_total_bytes"
            break

        files_scanned += 1
        bytes_scanned += byte_count
        assert text is not None
        relative_path = _relative_display(workspace_root, candidate)

        for line_number, line in enumerate(text.splitlines(), start=1):
            first_match = pattern.search(line)
            if first_match is None:
                continue
            if matching_lines_seen < offset:
                matching_lines_seen += 1
                continue
            if len(matches) >= max_results:
                truncated = True
                limit_reason = "max_results"
                break

            occurrence_count = 0
            occurrence_count_capped = False
            for _match in pattern.finditer(line):
                occurrence_count += 1
                if occurrence_count >= 10_000:
                    occurrence_count_capped = True
                    break

            result = {
                "path": relative_path,
                "line_number": line_number,
                "column": first_match.start() + 1,
                "match_end_column": first_match.end(),
                "occurrences_in_line": occurrence_count,
                "occurrences_capped": occurrence_count_capped,
            }
            result.update(_line_snippet(line, first_match.start(), max_line_chars))
            matches.append(result)
            matching_lines_seen += 1

        if truncated and limit_reason == "max_results":
            break

    next_offset = offset + len(matches) if truncated and limit_reason == "max_results" else None
    return _json_result(
        success=True,
        query=query,
        search_path=_relative_display(workspace_root, search_path),
        case_sensitive=case_sensitive,
        whole_word=whole_word,
        matches=matches,
        returned_matches=len(matches),
        offset=offset,
        truncated=truncated,
        limit_reason=limit_reason,
        next_offset=next_offset,
        files_considered=files_considered,
        files_scanned=files_scanned,
        bytes_scanned=bytes_scanned,
        skipped_files=skipped,
        default_excluded_directories=(
            [] if include_common else sorted(DEFAULT_EXCLUDED_DIRECTORIES)
        ),
    )


registry.register(
    name=SCHEMA["name"],
    toolset="filesystem",
    schema=SCHEMA,
    handler=handler,
)
