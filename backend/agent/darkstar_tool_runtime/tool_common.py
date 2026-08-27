# SPDX-License-Identifier: Apache-2.0
"""Shared, non-tool helpers for Darkstar workspace Python tools.

This module intentionally registers no callable tool.  Individual providers in this
folder import it so every filesystem operation uses the same path-confinement,
UTF-8, atomic-write, and result conventions.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Iterable

MAX_TEXT_FILE_BYTES = 32 * 1024 * 1024
MAX_DIRECTORY_ENTRIES = 10_000


class ToolInputError(ValueError):
    """Raised when a tool request is invalid or unsafe."""


def json_result(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def request_yes_no(question: str) -> dict[str, Any]:
    """Ask the user a Yes/No question while the current tool invocation remains in flight."""
    text = str(question or "").strip()
    if not text:
        raise ToolInputError("A Yes/No question is required.")
    return {"__darkstarAction": "ask_user_yes_no", "question": text}


def request_attention(
    *,
    kind: str,
    payload: dict[str, Any] | None = None,
    title: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Request a privileged Darkstar action through the generic user-attention gate.

    The Python tool itself performs no privileged action. Core keeps the current
    tool invocation in flight, asks the user, and dispatches the registered action
    handler only when the user chooses Allow. Reject terminates that same call.
    """
    normalized_kind = str(kind or "").strip().lower()
    if not normalized_kind:
        raise ToolInputError("Attention request kind is required.")
    request: dict[str, Any] = {
        "__darkstarAction": "request_attention",
        "kind": normalized_kind,
        "payload": dict(payload or {}),
    }
    if title is not None:
        request["title"] = str(title)
    if prompt is not None:
        request["prompt"] = str(prompt)
    return request


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
    """Return Darkstar's project directory.

    The generic Python host should pass the sidebar workspace path as execution
    context.  Environment variables are supported for host implementations that
    set process-level context.  ``cwd`` is the final compatibility fallback because
    Darkstar historically launched providers with the workspace as their cwd.
    """
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


def get_filesystem_access(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return the Core-issued filesystem boundary for the current tool call."""
    raw = kwargs.get("filesystem_access")
    configured = isinstance(raw, dict)
    if not configured:
        for mapping in _mapping_candidates(kwargs):
            candidate = mapping.get("filesystem_access")
            if isinstance(candidate, dict):
                raw = candidate
                configured = True
                break
    raw = raw if isinstance(raw, dict) else {}
    level = str(raw.get("level") or "3").strip()
    if level not in {"1", "2", "3"}:
        level = "3"
    workspace, _source = get_working_directory(kwargs)
    root_value = str(raw.get("root") or "").strip()
    if level == "1":
        boundary = None
    else:
        boundary = Path(root_value).expanduser().resolve(strict=False) if root_value else workspace
    return {
        "level": level,
        "mode": str(raw.get("mode") or ("unrestricted" if level == "1" else "working-directory")),
        "root": boundary,
        "working_directory": workspace,
        "home_root": str(raw.get("homeRoot") or raw.get("home_root") or ""),
        "unrestricted": level == "1",
        "allow_subprocess": bool(raw.get("allowSubprocess") or raw.get("allow_subprocess")),
        "internal_roots": tuple(
            Path(value).expanduser().resolve(strict=False)
            for value in (raw.get("internalRoots") or raw.get("internal_roots") or [])
            if isinstance(value, str) and value.strip()
        ),
        "configured": configured,
    }


def filesystem_path_allowed(candidate: Path, kwargs: dict[str, Any]) -> bool:
    access = get_filesystem_access(kwargs)
    if access["unrestricted"]:
        return True
    boundary = access["root"]
    return bool(boundary and is_within(boundary, candidate))


def _normcase(path: Path) -> str:
    return os.path.normcase(str(path))


def is_within(root: Path, candidate: Path) -> bool:
    try:
        common = os.path.commonpath([_normcase(root), _normcase(candidate)])
    except ValueError:
        return False
    return common == _normcase(root)


def resolve_workspace_path(
    raw_path: Any,
    kwargs: dict[str, Any],
    *,
    must_exist: bool = False,
    allow_root: bool = True,
) -> tuple[Path, Path]:
    workspace, _ = get_working_directory(kwargs)
    access = get_filesystem_access(kwargs)
    boundary = access["root"]
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ToolInputError("A non-empty path is required.")
    supplied = Path(raw_path.strip()).expanduser()
    lexical = supplied if supplied.is_absolute() else workspace / supplied
    lexical = Path(os.path.abspath(os.path.normpath(str(lexical))))
    if boundary is not None and not is_within(boundary, lexical):
        raise ToolInputError(f"Path is outside Filesystem Access Level {access['level']}: {raw_path}")

    # Resolve parent links but deliberately do not follow a final symlink. This
    # preserves safe deletion of an allowed symlink while preventing parent-link escapes.
    if boundary is not None:
        if _normcase(lexical) == _normcase(boundary):
            candidate = boundary
        else:
            parent = lexical.parent.resolve(strict=False)
            candidate = parent / lexical.name
        if not is_within(boundary, candidate):
            raise ToolInputError(f"Path resolves outside Filesystem Access Level {access['level']}: {raw_path}")
    else:
        candidate = lexical
    if not allow_root and _normcase(candidate) == _normcase(workspace):
        raise ToolInputError("This operation cannot target the project working directory itself.")
    if must_exist and not (candidate.exists() or candidate.is_symlink()):
        raise ToolInputError(f"Path does not exist: {raw_path}")
    return workspace, candidate


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


def verify_expected_hash(current_text: str, expected_sha256: Any) -> None:
    if expected_sha256 in (None, ""):
        return
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ToolInputError("expected_sha256 must be a 64-character SHA-256 hex digest.")
    actual = sha256_text(current_text)
    if actual.lower() != expected_sha256.lower():
        raise ToolInputError(
            "The file changed since it was read. Read it again before writing. "
            f"Expected {expected_sha256.lower()}, found {actual}."
        )


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


def require_bool(value: Any, name: str, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ToolInputError(f"{name} must be a boolean.")
    return value


def require_int(value: Any, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInputError(f"{name} must be an integer.")
    if value < minimum or value > maximum:
        raise ToolInputError(f"{name} must be between {minimum} and {maximum}.")
    return value


def ensure_tree_has_no_symlinks(path: Path) -> None:
    """Reject a directory tree containing any symbolic link."""
    if path.is_symlink():
        raise ToolInputError(f"Symbolic-link sources cannot be copied: {path}")
    if not path.is_dir():
        return
    for current_root, directories, files in os.walk(path, followlinks=False):
        base = Path(current_root)
        for name in [*directories, *files]:
            candidate = base / name
            if candidate.is_symlink():
                raise ToolInputError(
                    f"Directory copy rejected because it contains a symbolic link: {candidate}"
                )


def count_tree_entries(path: Path, limit: int = 100_000) -> int:
    if not path.is_dir() or path.is_symlink():
        return 1
    count = 1
    for _root, dirs, files in os.walk(path, followlinks=False):
        count += len(dirs) + len(files)
        if count >= limit:
            return limit
    return count
