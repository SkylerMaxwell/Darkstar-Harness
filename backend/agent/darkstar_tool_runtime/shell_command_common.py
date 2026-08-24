# SPDX-License-Identifier: GPL-3.0-only
"""Shared execution helpers for Darkstar's operating-system command tools.

This module registers no tools. It provides consistent validation, workspace path
handling, environment sanitization, output limits, and process-tree termination
for the Windows cmd.exe and Linux terminal providers.
"""
from __future__ import annotations

import hashlib
import locale
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

from .tool_common import ToolInputError, get_working_directory, is_within, json_result, relative_display

MAX_COMMAND_CHARS = 32_000
MAX_STDIN_BYTES = 1_000_000
MAX_ENVIRONMENT_ITEMS = 64
MAX_ENVIRONMENT_VALUE_CHARS = 8_192
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 600
DEFAULT_OUTPUT_LIMIT_CHARS = 200_000
MAX_OUTPUT_LIMIT_CHARS = 1_000_000
_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SENSITIVE_ENVIRONMENT = re.compile(
    r"(?:^|_)(?:API[_-]?KEY|AUTH|BEARER|COOKIE|CREDENTIAL|PRIVATE[_-]?KEY|PASS(?:WORD|WD)?|SECRET|SESSION|TOKEN)(?:$|_)",
    re.IGNORECASE,
)
_SENSITIVE_PREFIX = re.compile(
    r"^(?:ANTHROPIC|AWS|AZURE|GCP|GITHUB|GITLAB|GOOGLE|HF|HUGGINGFACE|NPM|OPENAI|PYPI|STRIPE|VERCEL)_",
    re.IGNORECASE,
)


def require_command(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError("command must be a non-empty string.")
    if "\x00" in value:
        raise ToolInputError("command cannot contain a NUL character.")
    if len(value) > MAX_COMMAND_CHARS:
        raise ToolInputError(f"command exceeds the {MAX_COMMAND_CHARS:,}-character limit.")
    return value.strip()


def require_integer(value: Any, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInputError(f"{name} must be an integer.")
    if value < minimum or value > maximum:
        raise ToolInputError(f"{name} must be between {minimum} and {maximum}.")
    return value


def require_boolean(value: Any, name: str, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ToolInputError(f"{name} must be a boolean.")
    return value


def resolve_command_directory(raw: Any, kwargs: dict[str, Any]) -> tuple[Path, Path]:
    root, _source = get_working_directory(kwargs)
    if raw in (None, ""):
        directory = root
    else:
        if not isinstance(raw, str) or not raw.strip():
            raise ToolInputError("working_directory must be a non-empty workspace-relative path.")
        supplied = Path(raw.strip()).expanduser()
        candidate = supplied if supplied.is_absolute() else root / supplied
        directory = candidate.resolve(strict=False)
    if not is_within(root, directory):
        raise ToolInputError("working_directory escapes the current project workspace.")
    if not directory.exists():
        raise ToolInputError(f"working_directory does not exist: {raw}")
    if not directory.is_dir():
        raise ToolInputError(f"working_directory is not a folder: {raw}")
    return root, directory


def _minimal_environment(root: Path, temporary: Path) -> dict[str, str]:
    keep = (
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC",
        "LANG", "LC_ALL", "LC_CTYPE", "TERM", "COLORTERM",
    )
    environment: dict[str, str] = {}
    for key in keep:
        value = os.environ.get(key)
        if value:
            environment[key] = str(value)
    environment.update({
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "TMPDIR": str(temporary),
        "DARKSTAR_WORKSPACE": str(root),
        "NO_COLOR": "1",
    })
    return environment


def _pin_application_python(environment: dict[str, str]) -> dict[str, str]:
    venv_root = os.environ.get("DARKSTAR_PYTHON_VENV") or os.environ.get("VIRTUAL_ENV")
    if not venv_root:
        return environment
    root = Path(venv_root).resolve(strict=False)
    bin_dir = root / ("Scripts" if os.name == "nt" else "bin")
    current = environment.get("PATH", "")
    parts = [part for part in current.split(os.pathsep) if part and os.path.normcase(part) != os.path.normcase(str(bin_dir))]
    environment["PATH"] = os.pathsep.join([str(bin_dir), *parts])
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment["VIRTUAL_ENV"] = str(root)
    environment["DARKSTAR_PYTHON_VENV"] = str(root)
    environment["DARKSTAR_PYTHON"] = os.environ.get("DARKSTAR_PYTHON", str(bin_dir / ("python.exe" if os.name == "nt" else "python")))
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def build_environment(root: Path, additions: Any) -> tuple[dict[str, str], list[str]]:
    temporary = root / ".darkstar" / "command_temp"
    temporary.mkdir(parents=True, exist_ok=True)
    environment = _minimal_environment(root, temporary)
    if additions is None:
        return _pin_application_python(environment), []
    if not isinstance(additions, dict):
        raise ToolInputError("environment must be an object containing string values.")
    if len(additions) > MAX_ENVIRONMENT_ITEMS:
        raise ToolInputError(f"environment cannot contain more than {MAX_ENVIRONMENT_ITEMS} entries.")
    added: list[str] = []
    for raw_key, raw_value in additions.items():
        key = str(raw_key)
        if not _ENVIRONMENT_NAME.fullmatch(key):
            raise ToolInputError(f"Invalid environment variable name: {key}")
        if _SENSITIVE_ENVIRONMENT.search(key) or _SENSITIVE_PREFIX.search(key):
            raise ToolInputError(f"Sensitive environment variable names are not accepted: {key}")
        if not isinstance(raw_value, str):
            raise ToolInputError(f"Environment value for {key} must be a string.")
        if "\x00" in raw_value or len(raw_value) > MAX_ENVIRONMENT_VALUE_CHARS:
            raise ToolInputError(f"Environment value for {key} is invalid or too long.")
        environment[key] = raw_value
        added.append(key)
    return _pin_application_python(environment), sorted(added)


def require_stdin(value: Any) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolInputError("stdin must be a string.")
    encoded = value.encode("utf-8")
    if len(encoded) > MAX_STDIN_BYTES:
        raise ToolInputError(f"stdin exceeds the {MAX_STDIN_BYTES:,}-byte limit.")
    return encoded


def decode_output(data: bytes, *, windows: bool) -> str:
    if not data:
        return ""
    encodings: list[str] = []
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)
    encodings.extend(["utf-8", "cp65001"])
    if windows:
        encodings.extend(["mbcs", "cp1252", "cp437"])
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def truncate_output(text: str, limit: int) -> tuple[str, bool, int]:
    original = len(text)
    if original <= limit:
        return text, False, original
    head = max(1, int(limit * 0.7))
    tail = max(1, limit - head)
    omitted = original - head - tail
    marker = f"\n... [{omitted:,} characters omitted] ...\n"
    return text[:head] + marker + text[-tail:], True, original


def _terminate_process_tree(process: subprocess.Popen[bytes], *, windows: bool) -> None:
    if process.poll() is not None:
        return
    if windows:
        taskkill = shutil.which("taskkill") or os.path.join(os.environ.get("SYSTEMROOT", r"C:\\Windows"), "System32", "taskkill.exe")
        try:
            subprocess.run(
                [taskkill, "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def command_digest(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def run_command(
    *,
    argv: list[str],
    command: str,
    root: Path,
    directory: Path,
    environment: dict[str, str],
    environment_keys: list[str],
    stdin_bytes: bytes | None,
    timeout_seconds: int,
    output_limit_chars: int,
    windows: bool,
    shell_name: str,
) -> str:
    creationflags = 0
    popen_kwargs: dict[str, Any] = {}
    if windows:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    started = time.monotonic()
    process = subprocess.Popen(
        argv,
        cwd=str(directory),
        env=environment,
        stdin=subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        **popen_kwargs,
    )
    timed_out = False
    try:
        stdout_bytes, stderr_bytes = process.communicate(input=stdin_bytes, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process, windows=windows)
        stdout_bytes, stderr_bytes = process.communicate()
    duration_ms = round((time.monotonic() - started) * 1000)
    stdout, stdout_decode_warning = decode_output(stdout_bytes, windows=windows), False
    stderr, stderr_decode_warning = decode_output(stderr_bytes, windows=windows), False
    stdout, stdout_truncated, stdout_chars = truncate_output(stdout, output_limit_chars)
    stderr, stderr_truncated, stderr_chars = truncate_output(stderr, output_limit_chars)
    return json_result(
        success=(not timed_out and process.returncode == 0),
        exit_code=process.returncode,
        timed_out=timed_out,
        timeout_seconds=timeout_seconds,
        duration_ms=duration_ms,
        shell=shell_name,
        working_directory=relative_display(root, directory),
        command_sha256=command_digest(command),
        environment_keys=environment_keys,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        stdout_characters=stdout_chars,
        stderr_characters=stderr_chars,
    )


def common_properties(command_description: str) -> dict[str, Any]:
    return {
        "command": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_COMMAND_CHARS,
            "description": command_description,
        },
        "working_directory": {
            "type": "string",
            "description": "Optional folder relative to the current project workspace. Defaults to the workspace root.",
        },
        "stdin": {
            "type": "string",
            "description": "Optional UTF-8 text sent to the command's standard input.",
        },
        "timeout_seconds": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_TIMEOUT_SECONDS,
            "description": f"Wall-clock timeout. Defaults to {DEFAULT_TIMEOUT_SECONDS} seconds.",
        },
        "output_limit_chars": {
            "type": "integer",
            "minimum": 1_000,
            "maximum": MAX_OUTPUT_LIMIT_CHARS,
            "description": f"Maximum characters retained separately for stdout and stderr. Defaults to {DEFAULT_OUTPUT_LIMIT_CHARS:,}.",
        },
        "environment": {
            "type": "object",
            "maxProperties": MAX_ENVIRONMENT_ITEMS,
            "additionalProperties": {"type": "string"},
            "description": "Optional non-secret environment variables for this command only. The inherited environment is sanitized.",
        },
        "allow_destructive": {
            "type": "boolean",
            "description": "Set true only when the requested command intentionally deletes or overwrites files. System-destruction commands remain blocked.",
        },
    }


def common_inputs(args: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    command = require_command(args.get("command"))
    root, directory = resolve_command_directory(args.get("working_directory"), kwargs)
    environment, environment_keys = build_environment(root, args.get("environment"))
    return {
        "command": command,
        "root": root,
        "directory": directory,
        "environment": environment,
        "environment_keys": environment_keys,
        "stdin_bytes": require_stdin(args.get("stdin")),
        "timeout_seconds": require_integer(
            args.get("timeout_seconds"), "timeout_seconds", DEFAULT_TIMEOUT_SECONDS, 1, MAX_TIMEOUT_SECONDS
        ),
        "output_limit_chars": require_integer(
            args.get("output_limit_chars"), "output_limit_chars", DEFAULT_OUTPUT_LIMIT_CHARS, 1_000, MAX_OUTPUT_LIMIT_CHARS
        ),
        "allow_destructive": require_boolean(args.get("allow_destructive"), "allow_destructive", False),
    }


def reject_command(command: str, *, hard_patterns: Iterable[tuple[re.Pattern[str], str]], destructive_patterns: Iterable[tuple[re.Pattern[str], str]], allow_destructive: bool) -> None:
    for pattern, reason in hard_patterns:
        if pattern.search(command):
            raise ToolInputError(f"Command is blocked: {reason}")
    if allow_destructive:
        return
    for pattern, reason in destructive_patterns:
        if pattern.search(command):
            raise ToolInputError(f"Command appears destructive ({reason}). Set allow_destructive=true only when this operation is intentional.")
