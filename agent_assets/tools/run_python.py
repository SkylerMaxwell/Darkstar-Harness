# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: execute Python in a constrained per-call subprocess."""
from __future__ import annotations

import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath
_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

import ast
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from tools.registry import registry
from _darkstar_tool_common import ToolInputError, get_working_directory, require_int

ALLOWED_IMPORT_ROOTS = {
    "PIL", "pypdf", "reportlab", "docx", "pptx", "openpyxl",
    "array", "base64", "binascii", "bisect", "calendar", "collections", "csv",
    "dataclasses", "datetime", "decimal", "enum", "fractions", "functools", "hashlib",
    "heapq", "html", "io", "itertools", "json", "math", "operator", "random", "re",
    "statistics", "string", "struct", "textwrap", "time", "typing", "unicodedata",
    "uuid", "xml", "zipfile", "pathlib",
}
BLOCKED_NAMES = {
    "breakpoint", "compile", "delattr", "eval", "exec", "exit", "getattr", "globals",
    "help", "input", "locals", "memoryview", "quit", "setattr", "type", "vars", "__import__",
}
BLOCKED_ATTRIBUTE_PARTS = {
    "__bases__", "__builtins__", "__class__", "__code__", "__closure__", "__dict__",
    "__func__", "__globals__", "__loader__", "__mro__", "__reduce__", "__reduce_ex__",
    "__subclasses__", "__traceback__",
}

SCHEMA = {
    "name": "run_python",
    "description": (
        "Execute Python code in a fresh, isolated subprocess rooted in a per-call folder under the "
        "current project. Network and child-process operations are blocked, writes are confined to the "
        "run folder, execution has a timeout and output limits, and generated files are returned. "
        "Available document libraries include Pillow, pypdf, ReportLab, python-docx, python-pptx, and "
        "openpyxl. This is a constrained application sandbox, not a hardened virtual machine."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "code": {"type": "string", "minLength": 1, "description": "Python source code to execute."},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60, "description": "Wall-clock timeout. Defaults to 30 seconds."},
        },
        "required": ["code"],
        "additionalProperties": False,
    },
}


def validate_code(code: str) -> None:
    if not isinstance(code, str) or not code.strip():
        raise ToolInputError("code must be a non-empty string.")
    if len(code) > 200_000:
        raise ToolInputError("code exceeds the 200,000-character limit.")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ToolInputError(f"Python syntax error at line {exc.lineno}: {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                root = name.split(".", 1)[0]
                if root not in ALLOWED_IMPORT_ROOTS:
                    raise ToolInputError(f"Import is not allowed in the Python sandbox: {name}")
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise ToolInputError(f"Built-in is not allowed in the Python sandbox: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in BLOCKED_ATTRIBUTE_PARTS:
            raise ToolInputError(f"Attribute is not allowed in the Python sandbox: {node.attr}")


WORKER = r'''
import builtins, contextlib, io, json, os, pathlib, site, socket, subprocess, sys, traceback
sandbox = pathlib.Path(sys.argv[1]).resolve()
workspace = pathlib.Path(sys.argv[2]).resolve()
code_path = sandbox / "program.py"
allowed_read_roots = [sandbox, workspace, pathlib.Path(sys.base_prefix).resolve(), pathlib.Path(sys.prefix).resolve()]
for package_root in [*site.getsitepackages(), site.getusersitepackages()]:
    if package_root:
        candidate = pathlib.Path(package_root).resolve(strict=False)
        if candidate.exists() and candidate not in allowed_read_roots:
            allowed_read_roots.append(candidate)
for optional_root in (
    "/usr/share/fonts", "/usr/share/mime", "/usr/share/zoneinfo",
    os.path.join(os.environ.get("SYSTEMROOT", ""), "Fonts") if os.environ.get("SYSTEMROOT") else "",
):
    if optional_root:
        candidate = pathlib.Path(optional_root).resolve(strict=False)
        if candidate.exists(): allowed_read_roots.append(candidate)
allowed_read_files = {pathlib.Path("/etc/mime.types").resolve(strict=False)}

def inside(root, candidate):
    try:
        return os.path.commonpath([os.path.normcase(str(root)), os.path.normcase(str(candidate))]) == os.path.normcase(str(root))
    except ValueError:
        return False

def checked_path(raw):
    p = pathlib.Path(raw)
    if not p.is_absolute(): p = sandbox / p
    return p.resolve(strict=False)

real_open = builtins.open
def guarded_open(file, mode="r", *args, **kwargs):
    p = checked_path(file)
    writing = any(flag in mode for flag in "wax+")
    if writing and not inside(sandbox, p):
        raise PermissionError(f"Sandbox write denied: {p}")
    if not writing and p not in allowed_read_files and not any(inside(root, p) for root in allowed_read_roots):
        raise PermissionError(f"Sandbox read denied: {p}")
    return real_open(p, mode, *args, **kwargs)

builtins.open = guarded_open
io.open = guarded_open

def sandbox_write_path(raw):
    p = checked_path(raw)
    if not inside(sandbox, p):
        raise PermissionError(f"Sandbox mutation denied: {p}")
    return p

real_remove = os.remove
real_unlink = os.unlink
real_rmdir = os.rmdir
real_mkdir = os.mkdir
real_rename = os.rename
real_replace = os.replace
real_chdir = os.chdir
real_os_open = os.open

def read_path(raw):
    p = checked_path(raw)
    if p in allowed_read_files or any(inside(root, p) for root in allowed_read_roots):
        return p
    raise PermissionError(f"Sandbox read denied: {p}")

def guarded_os_open(path, flags, *args, **kwargs):
    writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
    p = sandbox_write_path(path) if writing else read_path(path)
    return real_os_open(p, flags, *args, **kwargs)

def guarded_remove(path, *args, **kwargs): return real_remove(sandbox_write_path(path), *args, **kwargs)
def guarded_unlink(path, *args, **kwargs): return real_unlink(sandbox_write_path(path), *args, **kwargs)
def guarded_rmdir(path, *args, **kwargs): return real_rmdir(sandbox_write_path(path), *args, **kwargs)
def guarded_mkdir(path, *args, **kwargs): return real_mkdir(sandbox_write_path(path), *args, **kwargs)
def guarded_rename(src, dst, *args, **kwargs): return real_rename(sandbox_write_path(src), sandbox_write_path(dst), *args, **kwargs)
def guarded_replace(src, dst, *args, **kwargs): return real_replace(sandbox_write_path(src), sandbox_write_path(dst), *args, **kwargs)
def guarded_chdir(path): return real_chdir(sandbox_write_path(path))
real_chmod = os.chmod
real_truncate = os.truncate
real_utime = os.utime
def guarded_chmod(path, *args, **kwargs): return real_chmod(sandbox_write_path(path), *args, **kwargs)
def guarded_truncate(path, *args, **kwargs): return real_truncate(sandbox_write_path(path), *args, **kwargs)
def guarded_utime(path, *args, **kwargs): return real_utime(sandbox_write_path(path), *args, **kwargs)
os.remove = guarded_remove
os.unlink = guarded_unlink
os.rmdir = guarded_rmdir
os.mkdir = guarded_mkdir
os.rename = guarded_rename
os.replace = guarded_replace
os.chdir = guarded_chdir
os.open = guarded_os_open
os.chmod = guarded_chmod
os.truncate = guarded_truncate
os.utime = guarded_utime

def blocked(*args, **kwargs):
    raise PermissionError("Network and child-process operations are disabled in this sandbox.")
socket.socket = blocked
socket.create_connection = blocked
subprocess.Popen = blocked
subprocess.run = blocked
subprocess.call = blocked
subprocess.check_call = blocked
subprocess.check_output = blocked
os.system = blocked
os.popen = blocked
os.symlink = blocked
os.link = blocked

try:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
    if hasattr(resource, "RLIMIT_AS"):
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 * 1024 * 1024, 2 * 1024 * 1024 * 1024))
    if hasattr(resource, "RLIMIT_NPROC"):
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
except Exception:
    pass

os.chdir(sandbox)
class LimitedBuffer(io.StringIO):
    limit = 2_000_000
    def write(self, value):
        if self.tell() + len(value) > self.limit:
            raise RuntimeError("Python output exceeded the 2 MB limit.")
        return super().write(value)

stdout = LimitedBuffer(); stderr = LimitedBuffer()
namespace = {
    "__name__": "__main__",
    "__file__": str(code_path),
    "OUTPUT_DIR": str(sandbox),
    "WORKSPACE_DIR": str(workspace),
}
try:
    source = code_path.read_text(encoding="utf-8")
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exec(compile(source, str(code_path), "exec"), namespace, namespace)
    payload = {"success": True, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}
except BaseException:
    payload = {"success": False, "stdout": stdout.getvalue(), "stderr": stderr.getvalue(), "traceback": traceback.format_exc(limit=20)}
sys.__stdout__.write(json.dumps(payload, ensure_ascii=False))
sys.__stdout__.flush()
raise SystemExit(0 if payload.get("success") else 1)
'''


def _list_outputs(run_dir: Path):
    outputs = []
    for path in sorted(run_dir.rglob("*"), key=lambda value: value.as_posix().casefold()):
        if not path.is_file() or path.name in {"program.py", "_runner.py"}:
            continue
        outputs.append({"path": path.relative_to(run_dir).as_posix(), "size_bytes": path.stat().st_size})
        if len(outputs) >= 500:
            break
    return outputs


def handler(args, **kwargs):
    code = args.get("code")
    validate_code(code)
    timeout = require_int(args.get("timeout_seconds"), "timeout_seconds", 30, 1, 60)
    root, _source = get_working_directory(kwargs)
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = root / ".darkstar" / "python_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "program.py").write_text(code, encoding="utf-8", newline="")
    (run_dir / "_runner.py").write_text(WORKER, encoding="utf-8", newline="")
    command = [sys.executable, "-B", str(run_dir / "_runner.py"), str(run_dir), str(root)]
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "TEMP": str(run_dir),
        "TMP": str(run_dir),
        "TMPDIR": str(run_dir),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    environment = {**os.environ, **environment}
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=run_dir,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolInputError(f"Python execution exceeded the {timeout}-second timeout.") from exc
    duration_ms = round((time.monotonic() - started) * 1000)
    if len(completed.stdout) > 2_000_000 or len(completed.stderr) > 2_000_000:
        raise ToolInputError("Python execution exceeded the 2 MB output limit.")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "success": False,
            "stdout": "",
            "stderr": completed.stderr,
            "traceback": "Sandbox runner returned malformed output.",
        }
    payload.update({
        "exit_code": completed.returncode,
        "duration_ms": duration_ms,
        "run_directory": run_dir.relative_to(root).as_posix(),
        "files": _list_outputs(run_dir),
    })
    if completed.stderr and not payload.get("stderr"):
        payload["stderr"] = completed.stderr
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


registry.register(name=SCHEMA["name"], toolset="python", schema=SCHEMA, handler=handler)
