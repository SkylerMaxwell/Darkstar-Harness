#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Generic host for trusted registry-based Python tool files.

The selected file is imported in a child Python process. During import this host
provides a minimal ``tools.registry`` module so files that call
``registry.register(...)`` can declare schemas and handlers without requiring an
external agent installation.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
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
    }
    kwargs = {key: value for key, value in kwargs.items() if value is not None}
    with contextlib.redirect_stdout(sys.stderr):
        result = entry.handler(arguments, **kwargs)
        if entry.is_async or inspect.isawaitable(result):
            result = asyncio.run(result)
    return result


@contextlib.contextmanager
def _working_directory(context: dict[str, Any]):
    workspace = context.get("workspace")
    if not workspace:
        yield
        return
    previous = os.getcwd()
    os.chdir(str(workspace))
    try:
        yield
    finally:
        os.chdir(previous)


def _execute(name: str, arguments: Any, context: Any) -> Any:
    entry = registry.get(str(name or ""))
    if entry is None:
        raise KeyError(f"Unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise TypeError("Tool arguments must be a JSON object")
    context_dict = context if isinstance(context, dict) else {}
    with _working_directory(context_dict):
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
