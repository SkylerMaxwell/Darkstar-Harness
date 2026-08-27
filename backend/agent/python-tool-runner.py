#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generic host for trusted registry-based Python tool files.

The selected file is imported in a child Python process. During import this host
provides a minimal ``tools.registry`` module so files that call
``registry.register(...)`` can declare schemas and handlers without requiring an
external agent installation.
"""

from __future__ import annotations

import argparse
import asyncio
import builtins
import contextlib
import contextvars
import io
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import types
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolEntry:
    name: str
    toolset: str
    schema: dict[str, Any]
    handler: Callable[..., Any]
    check_fn: Callable[..., Any] | None = None
    requires_env: list[str] | None = None
    is_async: bool = False
    description: str = ""
    emoji: str = ""
    permission: dict[str, Any] | str | None = None
    filesystem: str | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def register(
        self,
        name: str,
        toolset: str = "custom",
        schema: dict[str, Any] | None = None,
        handler: Callable[..., Any] | None = None,
        check_fn: Callable[..., Any] | None = None,
        requires_env: list[str] | None = None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "",
        permission: dict[str, Any] | str | None = None,
        filesystem: str | None = None,
        override: bool = False,
        **_metadata: Any,
    ) -> None:
        tool_name = str(name or "").strip()
        if not tool_name:
            raise ValueError("registry.register() requires a non-empty name")
        if not callable(handler):
            raise TypeError(f"Tool {tool_name} requires a callable handler")
        if tool_name in self._tools and not override:
            raise ValueError(f"Duplicate tool registration: {tool_name}")
        self._tools[tool_name] = ToolEntry(
            name=tool_name,
            toolset=str(toolset or "custom"),
            schema=dict(schema or {}),
            handler=handler,
            check_fn=check_fn,
            requires_env=list(requires_env or []),
            is_async=bool(is_async),
            description=str(description or ""),
            emoji=str(emoji or ""),
            permission=permission,
            filesystem=str(filesystem).strip().lower() if filesystem is not None else None,
        )

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def entries(self) -> list[ToolEntry]:
        return list(self._tools.values())


registry = ToolRegistry()
_provider_metadata: dict[str, str] = {}
_BUNDLED_VENDOR_DIR = Path(__file__).resolve().parent / "python_vendor"


def _install_bundled_python_dependencies() -> None:
    """Prefer Darkstar's application-local pure-Python dependencies."""
    if not _BUNDLED_VENDOR_DIR.is_dir():
        return
    vendor = str(_BUNDLED_VENDOR_DIR)
    while vendor in sys.path:
        sys.path.remove(vendor)
    sys.path.insert(0, vendor)
    # Child sandboxes receive the same offline dependency root explicitly.
    os.environ["DARKSTAR_PYTHON_VENDOR"] = vendor


def tool_error(message: Any, **details: Any) -> str:
    payload: dict[str, Any] = {"error": str(message)}
    payload.update(details)
    return json.dumps(payload, ensure_ascii=False)


def _install_runtime_compatibility_modules() -> None:
    """Expose legacy helper module names without placing files in the tool catalog."""
    from darkstar_tool_runtime import shell_command_common, tool_common

    sys.modules.setdefault("_darkstar_tool_common", tool_common)
    legacy_common_name = "_" + "black" + "sun_tool_common"
    legacy_runtime_name = "black" + "sun_tool_runtime"
    sys.modules.setdefault(legacy_common_name, tool_common)
    sys.modules.setdefault(legacy_runtime_name, sys.modules["darkstar_tool_runtime"])
    sys.modules.setdefault(legacy_runtime_name + ".tool_common", tool_common)
    sys.modules.setdefault(legacy_runtime_name + ".shell_command_common", shell_command_common)
    sys.modules.setdefault("_shell_command_common", shell_command_common)


def _install_registry_modules(tool_file: Path) -> None:
    tools_package = sys.modules.get("tools")
    if tools_package is None:
        tools_package = types.ModuleType("tools")
        tools_package.__path__ = [str(tool_file.parent)]  # type: ignore[attr-defined]
        sys.modules["tools"] = tools_package
    else:
        package_path = list(getattr(tools_package, "__path__", []))
        if str(tool_file.parent) not in package_path:
            package_path.insert(0, str(tool_file.parent))
        tools_package.__path__ = package_path  # type: ignore[attr-defined]

    registry_module = types.ModuleType("tools.registry")
    registry_module.registry = registry
    registry_module.ToolRegistry = ToolRegistry
    registry_module.ToolEntry = ToolEntry
    registry_module.tool_error = tool_error
    sys.modules["tools.registry"] = registry_module
    setattr(tools_package, "registry", registry_module)


def _normalize_definition(entry: ToolEntry) -> dict[str, Any]:
    schema = dict(entry.schema or {})
    if schema.get("type") == "function" and isinstance(schema.get("function"), dict):
        function = dict(schema["function"])
    else:
        function = dict(schema)

    function.setdefault("name", entry.name)
    if not function.get("description"):
        function["description"] = entry.description or f"Run {entry.name}."
    parameters = function.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {"type": "object", "properties": {}, "additionalProperties": True}
    parameters.setdefault("type", "object")
    function["parameters"] = parameters
    if entry.permission is not None:
        function["x-darkstar-permission"] = entry.permission
    if entry.filesystem is not None:
        if entry.filesystem not in {"none", "scoped", "unrestricted"}:
            raise ValueError(f"Tool {entry.name} has an invalid filesystem contract: {entry.filesystem}")
        function["x-darkstar-filesystem"] = entry.filesystem
    return {"type": "function", "function": function}


def _is_available(entry: ToolEntry) -> tuple[bool, str | None]:
    missing = [name for name in entry.requires_env or [] if not os.environ.get(name)]
    if missing:
        return False, f"Missing environment variables: {', '.join(missing)}"
    if entry.check_fn is None:
        return True, None
    try:
        value = entry.check_fn()
        if inspect.isawaitable(value):
            value = asyncio.run(value)
        return bool(value), None if value else "Availability check returned false"
    except Exception as exc:  # trusted provider error; report it without killing other tools
        return False, f"Availability check failed: {exc}"


def _provider_description(tool_file: Path) -> dict[str, Any]:
    tools: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    for entry in registry.entries():
        available, reason = _is_available(entry)
        if available:
            tools.append(_normalize_definition(entry))
        else:
            unavailable.append({"name": entry.name, "reason": reason or "Unavailable"})
    provider_id = _provider_metadata.get("id") or tool_file.stem
    provider_name = _provider_metadata.get("name") or (
        tool_file.stem.replace("_", " ").replace("-", " ").strip().title() or tool_file.stem
    )
    return {
        "id": provider_id,
        "name": provider_name,
        "path": str(tool_file),
        "tools": tools,
        "unavailable": unavailable,
    }


def _load_tool_file(tool_file: Path) -> None:
    _install_runtime_compatibility_modules()
    _install_registry_modules(tool_file)
    for directory in (str(tool_file.parent), str(tool_file.parent.parent)):
        if directory not in sys.path:
            sys.path.insert(0, directory)
    module_name = f"darkstar_tool_{tool_file.stem}_{abs(hash(str(tool_file)))}"
    spec = importlib.util.spec_from_file_location(module_name, tool_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import Python tool file: {tool_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    # Provider prints are diagnostic output. Keep stdout exclusively for IPC.
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
    provider_id = str(getattr(module, "PROVIDER_ID", "") or "").strip()
    provider_name = str(getattr(module, "PROVIDER_NAME", "") or "").strip()
    if provider_id:
        _provider_metadata["id"] = provider_id
    if provider_name:
        _provider_metadata["name"] = provider_name


def _call_handler(entry: ToolEntry, arguments: dict[str, Any], context: dict[str, Any]) -> Any:
    kwargs = {
        "task_id": context.get("task_id"),
        "user_task": context.get("user_task"),
        "enabled_tools": context.get("enabled_tools"),
        "workspace": context.get("workspace"),
        "skills_root": context.get("skills_root"),
        "filesystem_access": context.get("filesystem_access"),
    }
    kwargs = {key: value for key, value in kwargs.items() if value is not None}
    with contextlib.redirect_stdout(sys.stderr):
        result = entry.handler(arguments, **kwargs)
        if entry.is_async or inspect.isawaitable(result):
            result = asyncio.run(result)
    return result


_active_filesystem_scope: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("darkstar_filesystem_scope", default=None)
_guard_bypass: contextvars.ContextVar[bool] = contextvars.ContextVar("darkstar_filesystem_guard_bypass", default=False)
_original_open = builtins.open
_original_io_open = io.open
_original_os_open = os.open
_original_stat = os.stat
_original_lstat = os.lstat
_original_listdir = os.listdir
_original_scandir = os.scandir
_original_readlink = os.readlink
_original_access = os.access
_original_chdir = os.chdir
_original_remove = os.remove
_original_unlink = os.unlink
_original_rmdir = os.rmdir
_original_mkdir = os.mkdir
_original_rename = os.rename
_original_replace = os.replace
_original_chmod = os.chmod
_original_truncate = os.truncate
_original_utime = os.utime
_original_symlink = os.symlink
_original_link = os.link
_original_fchdir = getattr(os, 'fchdir', None)
_original_exec_functions = {name: getattr(os, name) for name in ('execl', 'execle', 'execlp', 'execlpe', 'execv', 'execve', 'execvp', 'execvpe') if hasattr(os, name)}
_original_spawn_functions = {name: getattr(os, name) for name in ('spawnl', 'spawnle', 'spawnlp', 'spawnlpe', 'spawnv', 'spawnve', 'spawnvp', 'spawnvpe') if hasattr(os, name)}
_original_popen = subprocess.Popen
_original_run = subprocess.run
_original_call = subprocess.call
_original_check_call = subprocess.check_call
_original_check_output = subprocess.check_output
_original_os_system = os.system
_original_os_popen = os.popen


def _scope_from_context(context: dict[str, Any]) -> dict[str, Any]:
    raw = context.get("filesystem_access")
    if not isinstance(raw, dict):
        # Compatibility for direct/test hosts. Production ToolService always
        # supplies a Core-issued scope before a model-triggered execution.
        return {"level": "1", "root": None, "unrestricted": True, "allow_subprocess": True}
    level = str(raw.get("level") or "3").strip()
    if level not in {"1", "2", "3"}:
        level = "3"
    root_value = str(raw.get("root") or "").strip()
    if level == "1":
        root = None
    elif root_value:
        token = _guard_bypass.set(True)
        try:
            root = Path(root_value).expanduser().resolve(strict=False)
        finally:
            _guard_bypass.reset(token)
    else:
        workspace = str(context.get("workspace") or "").strip()
        token = _guard_bypass.set(True)
        try:
            root = Path(workspace or os.getcwd()).expanduser().resolve(strict=False)
        finally:
            _guard_bypass.reset(token)
    internal_roots: list[Path] = []
    for value in raw.get("internalRoots") or raw.get("internal_roots") or []:
        if not isinstance(value, str) or not value.strip():
            continue
        token = _guard_bypass.set(True)
        try:
            internal_roots.append(Path(value).expanduser().resolve(strict=False))
        finally:
            _guard_bypass.reset(token)
    return {
        "level": level,
        "root": root,
        "internal_roots": tuple(internal_roots),
        "unrestricted": level == "1",
        "allow_subprocess": bool(raw.get("allowSubprocess") or raw.get("allow_subprocess")),
    }


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(str(root)), os.path.normcase(str(candidate))]) == os.path.normcase(str(root))
    except ValueError:
        return False


def _guarded_candidate(raw: Any) -> Any:
    scope = _active_filesystem_scope.get()
    if scope is None or scope.get("unrestricted") or _guard_bypass.get() or isinstance(raw, int):
        return raw
    root = scope.get("root")
    if not isinstance(root, Path):
        raise PermissionError("Filesystem Access boundary is unavailable for this tool call.")
    token = _guard_bypass.set(True)
    try:
        supplied = Path(os.fspath(raw)).expanduser()
        lexical = supplied if supplied.is_absolute() else Path(os.getcwd()) / supplied
        candidate = lexical.resolve(strict=False)
    finally:
        _guard_bypass.reset(token)
    allowed_roots = (root, *tuple(scope.get("internal_roots") or ()))
    if not any(isinstance(allowed_root, Path) and _inside(allowed_root, candidate) for allowed_root in allowed_roots):
        raise PermissionError(f"Filesystem Access Level {scope['level']} denied path: {candidate}")
    return os.fspath(raw)


def _guarded_open(file: Any, *args: Any, **kwargs: Any):
    _guarded_candidate(file)
    return _original_open(file, *args, **kwargs)


def _guarded_io_open(file: Any, *args: Any, **kwargs: Any):
    _guarded_candidate(file)
    return _original_io_open(file, *args, **kwargs)


def _guarded_os_open(file: Any, *args: Any, **kwargs: Any):
    _guarded_candidate(file)
    return _original_os_open(file, *args, **kwargs)


def _one_path(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(path_value: Any, *args: Any, **kwargs: Any):
        _guarded_candidate(path_value)
        return original(path_value, *args, **kwargs)
    return wrapped


def _optional_path(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(path_value: Any = '.', *args: Any, **kwargs: Any):
        _guarded_candidate(path_value)
        return original(path_value, *args, **kwargs)
    return wrapped


def _two_paths(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(source: Any, destination: Any, *args: Any, **kwargs: Any):
        _guarded_candidate(source)
        _guarded_candidate(destination)
        return original(source, destination, *args, **kwargs)
    return wrapped


def _restricted_scope() -> dict[str, Any] | None:
    scope = _active_filesystem_scope.get()
    if scope is None or scope.get('unrestricted') or _guard_bypass.get():
        return None
    return scope


def _guarded_link_operation(kind: str, original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(source: Any, destination: Any, *args: Any, **kwargs: Any):
        scope = _restricted_scope()
        if scope is not None:
            raise PermissionError(f"{kind} creation is blocked by Filesystem Access Level {scope.get('level', '3')} to prevent link-based boundary escapes.")
        return original(source, destination, *args, **kwargs)
    return wrapped


def _guarded_fchdir(fd: int) -> None:
    scope = _restricted_scope()
    if scope is not None:
        raise PermissionError(f"Descriptor-based chdir is blocked by Filesystem Access Level {scope.get('level', '3')}.")
    if _original_fchdir is None:
        raise AttributeError('os.fchdir is unavailable on this platform')
    return _original_fchdir(fd)


def _guarded_process_primitive(kind: str, original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(*args: Any, **kwargs: Any):
        if not _subprocess_allowed():
            scope = _active_filesystem_scope.get() or {}
            raise PermissionError(f"{kind} is blocked by Filesystem Access Level {scope.get('level', '3')} for this tool.")
        return original(*args, **kwargs)
    return wrapped


def _subprocess_allowed() -> bool:
    scope = _active_filesystem_scope.get()
    return scope is None or scope.get("unrestricted") or scope.get("allow_subprocess") is True


def _guarded_popen(*args: Any, **kwargs: Any):
    if not _subprocess_allowed():
        scope = _active_filesystem_scope.get() or {}
        raise PermissionError(f"Child-process execution is blocked by Filesystem Access Level {scope.get('level', '3')} for this tool.")
    return _original_popen(*args, **kwargs)


def _guarded_run(*args: Any, **kwargs: Any):
    if not _subprocess_allowed():
        scope = _active_filesystem_scope.get() or {}
        raise PermissionError(f"Child-process execution is blocked by Filesystem Access Level {scope.get('level', '3')} for this tool.")
    return _original_run(*args, **kwargs)


def _guarded_call(*args: Any, **kwargs: Any):
    if not _subprocess_allowed():
        scope = _active_filesystem_scope.get() or {}
        raise PermissionError(f"Child-process execution is blocked by Filesystem Access Level {scope.get('level', '3')} for this tool.")
    return _original_call(*args, **kwargs)


def _guarded_check_call(*args: Any, **kwargs: Any):
    if not _subprocess_allowed():
        scope = _active_filesystem_scope.get() or {}
        raise PermissionError(f"Child-process execution is blocked by Filesystem Access Level {scope.get('level', '3')} for this tool.")
    return _original_check_call(*args, **kwargs)


def _guarded_check_output(*args: Any, **kwargs: Any):
    if not _subprocess_allowed():
        scope = _active_filesystem_scope.get() or {}
        raise PermissionError(f"Child-process execution is blocked by Filesystem Access Level {scope.get('level', '3')} for this tool.")
    return _original_check_output(*args, **kwargs)


def _guarded_os_system(command: str) -> int:
    if not _subprocess_allowed():
        scope = _active_filesystem_scope.get() or {}
        raise PermissionError(f"Child-process execution is blocked by Filesystem Access Level {scope.get('level', '3')} for this tool.")
    return _original_os_system(command)


def _guarded_os_popen(command: str, *args: Any, **kwargs: Any):
    if not _subprocess_allowed():
        scope = _active_filesystem_scope.get() or {}
        raise PermissionError(f"Child-process execution is blocked by Filesystem Access Level {scope.get('level', '3')} for this tool.")
    return _original_os_popen(command, *args, **kwargs)


def _install_filesystem_guard() -> None:
    builtins.open = _guarded_open
    io.open = _guarded_io_open
    os.open = _guarded_os_open
    os.stat = _one_path(_original_stat)
    os.lstat = _one_path(_original_lstat)
    os.listdir = _optional_path(_original_listdir)
    os.scandir = _optional_path(_original_scandir)
    os.readlink = _one_path(_original_readlink)
    os.access = _one_path(_original_access)
    os.chdir = _one_path(_original_chdir)
    os.remove = _one_path(_original_remove)
    os.unlink = _one_path(_original_unlink)
    os.rmdir = _one_path(_original_rmdir)
    os.mkdir = _one_path(_original_mkdir)
    os.rename = _two_paths(_original_rename)
    os.replace = _two_paths(_original_replace)
    os.chmod = _one_path(_original_chmod)
    os.truncate = _one_path(_original_truncate)
    os.utime = _one_path(_original_utime)
    os.symlink = _guarded_link_operation('Symbolic-link', _original_symlink)
    os.link = _guarded_link_operation('Hard-link', _original_link)
    if _original_fchdir is not None:
        os.fchdir = _guarded_fchdir
    for name, original in _original_exec_functions.items():
        setattr(os, name, _guarded_process_primitive(f'os.{name}', original))
    for name, original in _original_spawn_functions.items():
        setattr(os, name, _guarded_process_primitive(f'os.{name}', original))
    subprocess.Popen = _guarded_popen
    subprocess.run = _guarded_run
    subprocess.call = _guarded_call
    subprocess.check_call = _guarded_check_call
    subprocess.check_output = _guarded_check_output
    os.system = _guarded_os_system
    os.popen = _guarded_os_popen


@contextlib.contextmanager
def _filesystem_scope(context: dict[str, Any]):
    token = _active_filesystem_scope.set(_scope_from_context(context))
    try:
        yield
    finally:
        _active_filesystem_scope.reset(token)


@contextlib.contextmanager
def _working_directory(context: dict[str, Any]):
    workspace = context.get("workspace")
    if not workspace:
        yield
        return
    previous = os.getcwd()
    _original_chdir(str(workspace))
    try:
        yield
    finally:
        _original_chdir(previous)


def _execute(name: str, arguments: Any, context: Any) -> Any:
    entry = registry.get(str(name or ""))
    if entry is None:
        raise KeyError(f"Unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise TypeError("Tool arguments must be a JSON object")
    context_dict = context if isinstance(context, dict) else {}
    with _working_directory(context_dict):
        with _filesystem_scope(context_dict):
            return _call_handler(entry, arguments, context_dict)


def _response(request_id: Any, success: bool, *, result: Any = None, error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": request_id, "success": success}
    if success:
        payload["result"] = result
    else:
        payload["error"] = error or "Python tool failed"
    return payload


def _serve(tool_file: Path) -> None:
    description = _provider_description(tool_file)
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        request_id: Any = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            action = request.get("action")
            if action == "describe":
                payload = _response(request_id, True, result=description)
            elif action == "execute":
                result = _execute(request.get("tool"), request.get("arguments") or {}, request.get("context") or {})
                payload = _response(request_id, True, result=result)
            elif action == "shutdown":
                print(json.dumps(_response(request_id, True, result={"shutdown": True}), ensure_ascii=False), flush=True)
                return
            else:
                raise ValueError(f"Unknown action: {action}")
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            payload = _response(request_id, False, error=f"{type(exc).__name__}: {exc}")
        print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("tool_file")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--describe", action="store_true")
    mode.add_argument("--serve", action="store_true")
    args = parser.parse_args()

    tool_file = Path(args.tool_file).expanduser().resolve()
    if tool_file.suffix.lower() != ".py" or not tool_file.is_file():
        raise FileNotFoundError(f"Select an existing .py tool file: {tool_file}")
    _install_bundled_python_dependencies()
    _install_filesystem_guard()
    _load_tool_file(tool_file)
    if not registry.entries():
        raise RuntimeError("The selected Python file did not register any tools")

    if args.describe:
        print(json.dumps(_provider_description(tool_file), ensure_ascii=False), flush=True)
        return 0
    _serve(tool_file)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"success": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
        raise SystemExit(2)
