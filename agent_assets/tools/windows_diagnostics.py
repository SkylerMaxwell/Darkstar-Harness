# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: bounded Windows diagnostics using inbox ETW utilities only.

Requires no Python packages and no third-party downloads. On Windows it uses
``tasklist.exe``, ``logman.exe``, and ``tracerpt.exe`` from the operating system.
"""
from __future__ import annotations

import csv
import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from tools.registry import registry


PROVIDER_BY_CATEGORY = {
    "process": "Microsoft-Windows-Kernel-Process",
    "file": "Microsoft-Windows-Kernel-File",
    "registry": "Microsoft-Windows-Kernel-Registry",
    "network": "Microsoft-Windows-Kernel-Network",
}
DEFAULT_CATEGORIES = ("process", "file", "registry", "network")
MAX_DURATION_SECONDS = 10
MAX_RETURNED_EVENTS = 100
MAX_TRACE_MEGABYTES = 64
COMMAND_TIMEOUT_SECONDS = 30


class ToolInputError(ValueError):
    """Raised when a tool request is invalid or cannot be completed safely."""


def _json_result(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _is_windows() -> bool:
    return os.name == "nt" and platform.system().lower() == "windows"


def _is_elevated() -> bool:
    if not _is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _command_path(name: str) -> str | None:
    return shutil.which(name)


def _run(
    command: list[str],
    *,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if _is_windows() else 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolInputError(f"Windows diagnostic command timed out: {Path(command[0]).name}") from exc
    except OSError as exc:
        raise ToolInputError(f"Could not run {Path(command[0]).name}: {exc}") from exc

    if check and completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "command failed").strip()
        if len(message) > 1200:
            message = message[:1200] + "…"
        raise ToolInputError(f"{Path(command[0]).name} failed: {message}")
    return completed


def _required_commands() -> dict[str, str | None]:
    return {
        "tasklist": _command_path("tasklist.exe") or _command_path("tasklist"),
        "logman": _command_path("logman.exe") or _command_path("logman"),
        "tracerpt": _command_path("tracerpt.exe") or _command_path("tracerpt"),
    }


def _available_providers(logman: str) -> set[str]:
    result = _run([logman, "query", "providers"], timeout=20)
    if result.returncode != 0:
        return set()
    available: set[str] = set()
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"^(.*?)\s+\{[0-9A-Fa-f-]{36}\}\s*$", line)
        if match:
            available.add(match.group(1).strip())
    return available


def _processes(tasklist: str) -> list[dict[str, Any]]:
    result = _run([tasklist, "/FO", "CSV", "/NH"], timeout=15, check=True)
    rows: list[dict[str, Any]] = []
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) < 2:
            continue
        image = row[0].strip()
        pid_text = row[1].replace(",", "").strip()
        if not image or not pid_text.isdigit():
            continue
        rows.append({"name": image, "pid": int(pid_text)})
    return rows


def _resolve_target(tasklist: str, process_name: Any, pid_value: Any) -> dict[str, Any]:
    if process_name is not None and pid_value is not None:
        raise ToolInputError("Provide process_name or pid, not both.")

    rows = _processes(tasklist)
    if pid_value is not None:
        if isinstance(pid_value, bool) or not isinstance(pid_value, int) or pid_value <= 0:
            raise ToolInputError("pid must be a positive integer.")
        matches = [row for row in rows if row["pid"] == pid_value]
        if not matches:
            raise ToolInputError(f"No running process has PID {pid_value}.")
        return matches[0]

    if not isinstance(process_name, str) or not process_name.strip():
        raise ToolInputError("capture requires process_name or pid.")
    requested = process_name.strip()
    if len(requested) > 260 or any(char in requested for char in "\r\n\0"):
        raise ToolInputError("process_name is invalid.")
    lowered = requested.casefold()
    matches = [row for row in rows if row["name"].casefold() == lowered]
    if not matches and not lowered.endswith(".exe"):
        matches = [row for row in rows if row["name"].casefold() == lowered + ".exe"]
    if not matches:
        raise ToolInputError(f"No running process named {requested!r} was found.")
    if len(matches) > 1:
        pids = [row["pid"] for row in matches[:12]]
        raise ToolInputError(
            f"Multiple {matches[0]['name']} processes are running with PIDs {pids}. Call again with one pid."
        )
    return matches[0]


def _validate_categories(value: Any) -> list[str]:
    if value is None:
        return list(DEFAULT_CATEGORIES)
    if not isinstance(value, list) or not value:
        raise ToolInputError("categories must be a non-empty array.")
    categories: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in PROVIDER_BY_CATEGORY:
            allowed = ", ".join(PROVIDER_BY_CATEGORY)
            raise ToolInputError(f"Each category must be one of: {allowed}.")
        if item not in categories:
            categories.append(item)
    return categories


def _validate_capture_args(args: dict[str, Any]) -> tuple[int, list[str], int, bool]:
    duration = args.get("duration_seconds", 5)
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise ToolInputError("duration_seconds must be a whole number.")
    if not 1 <= duration <= MAX_DURATION_SECONDS:
        raise ToolInputError(f"duration_seconds must be between 1 and {MAX_DURATION_SECONDS}.")

    max_events = args.get("max_events", 40)
    if isinstance(max_events, bool) or not isinstance(max_events, int):
        raise ToolInputError("max_events must be a whole number.")
    if not 1 <= max_events <= MAX_RETURNED_EVENTS:
        raise ToolInputError(f"max_events must be between 1 and {MAX_RETURNED_EVENTS}.")

    failures_only = args.get("failures_only", False)
    if not isinstance(failures_only, bool):
        raise ToolInputError("failures_only must be true or false.")

    return duration, _validate_categories(args.get("categories")), max_events, failures_only


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean_text(value: Any, *, limit: int = 800) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _flatten_event(element: ET.Element) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)
    for node in element.iter():
        tag = _local_name(node.tag)
        for attr_name, attr_value in node.attrib.items():
            key = f"{tag}.{_local_name(attr_name)}"
            cleaned = _clean_text(attr_value)
            if cleaned:
                values[key].append(cleaned)
        text = _clean_text(node.text)
        if text:
            key = tag
            data_name = node.attrib.get("Name") or node.attrib.get("name")
            if data_name:
                key = str(data_name)
            values[key].append(text)
    return values


def _first(values: dict[str, list[str]], names: Iterable[str]) -> str | None:
    wanted = {name.casefold() for name in names}
    for key, entries in values.items():
        if key.casefold() in wanted and entries:
            return entries[0]
    return None


def _integer_candidates(values: dict[str, list[str]], names: Iterable[str]) -> set[int]:
    wanted = {name.casefold() for name in names}
    found: set[int] = set()
    for key, entries in values.items():
        key_folded = key.casefold()
        if key_folded not in wanted and not any(key_folded.endswith("." + name) for name in wanted):
            continue
        for entry in entries:
            match = re.fullmatch(r"(?:0x([0-9a-fA-F]+)|([0-9]+))", entry.strip())
            if match:
                found.add(int(match.group(1), 16) if match.group(1) else int(match.group(2)))
    return found


def _event_pid(values: dict[str, list[str]]) -> set[int]:
    return _integer_candidates(
        values,
        (
            "ProcessID",
            "ProcessId",
            "PID",
            "Execution.ProcessID",
            "Execution.ProcessId",
            "EventHeader.ProcessId",
        ),
    )


def _provider(values: dict[str, list[str]]) -> str:
    return _first(values, ("Provider.Name", "ProviderName", "Provider")) or "unknown"


def _event_name(values: dict[str, list[str]]) -> str:
    return (
        _first(values, ("Task", "TaskName", "Opcode", "OpcodeName", "EventName"))
        or ("Event " + (_first(values, ("EventID", "EventId", "ID")) or "unknown"))
    )


def _path_or_endpoint(values: dict[str, list[str]]) -> str | None:
    direct = _first(
        values,
        (
            "FileName",
            "FilePath",
            "Path",
            "OpenPath",
            "KeyName",
            "RelativeName",
            "ObjectName",
            "daddr",
            "DestinationAddress",
            "RemoteAddress",
        ),
    )
    if direct:
        return direct
    for key, entries in values.items():
        folded = key.casefold()
        if any(token in folded for token in ("path", "filename", "keyname", "address")) and entries:
            return entries[0]
    return None


_FAILURE_WORDS = (
    "access denied",
    "not found",
    "name not found",
    "path not found",
    "failed",
    "failure",
    "denied",
    "timeout",
    "timed out",
    "refused",
    "sharing violation",
    "invalid parameter",
)
_SUCCESS_VALUES = {"0", "0x0", "success", "the operation completed successfully"}


def _failure_reason(values: dict[str, list[str]]) -> str | None:
    for key, entries in values.items():
        key_folded = key.casefold()
        if any(token in key_folded for token in ("status", "result", "error", "hresult", "ntstatus")):
            for entry in entries:
                value = entry.strip().casefold()
                if value and value not in _SUCCESS_VALUES:
                    if value.startswith("0x"):
                        try:
                            if int(value, 16) == 0:
                                continue
                        except ValueError:
                            pass
                    elif value.isdigit() and int(value) == 0:
                        continue
                    return f"{key}={entry}"
    combined = " ".join(entry for entries in values.values() for entry in entries).casefold()
    for word in _FAILURE_WORDS:
        if word in combined:
            return word
    return None


def _event_summary(values: dict[str, list[str]], failure: str | None) -> dict[str, Any]:
    timestamp = _first(values, ("TimeCreated.SystemTime", "TimeStamp", "Timestamp", "Clock-Time"))
    event_id = _first(values, ("EventID", "EventId", "ID"))
    detail = _first(values, ("Message", "Detail", "FormattedMessage", "UserData"))
    summary: dict[str, Any] = {
        "provider": _provider(values),
        "event": _event_name(values),
    }
    if event_id:
        summary["event_id"] = event_id
    if timestamp:
        summary["timestamp"] = timestamp
    path = _path_or_endpoint(values)
    if path:
        summary["path_or_endpoint"] = _clean_text(path, limit=500)
    if failure:
        summary["failure"] = _clean_text(failure, limit=240)
    if detail:
        summary["detail"] = _clean_text(detail, limit=500)
    return summary


def _parse_xml_events(xml_path: Path, target_pid: int) -> tuple[list[dict[str, Any]], int]:
    matched: list[dict[str, Any]] = []
    total_events = 0
    try:
        iterator = ET.iterparse(xml_path, events=("end",))
        for _event, element in iterator:
            if _local_name(element.tag).casefold() != "event":
                continue
            total_events += 1
            values = _flatten_event(element)
            pids = _event_pid(values)
            if target_pid in pids:
                failure = _failure_reason(values)
                matched.append(_event_summary(values, failure))
            element.clear()
    except (ET.ParseError, OSError) as exc:
        raise ToolInputError(f"Could not parse the ETW trace output: {exc}") from exc
    return matched, total_events


def _top_counts(events: list[dict[str, Any]], key: str, limit: int = 10) -> list[dict[str, Any]]:
    counts = Counter(str(event.get(key)) for event in events if event.get(key))
    return [{key: value, "count": count} for value, count in counts.most_common(limit)]


def _diagnostic_status() -> dict[str, Any]:
    commands = _required_commands()
    response: dict[str, Any] = {
        "success": True,
        "action": "status",
        "platform": platform.system(),
        "available": False,
        "requires_download": False,
        "uses": "Windows inbox ETW commands (logman, tracerpt, tasklist)",
    }
    if not _is_windows():
        response["reason"] = "windows_only"
        response["message"] = "Windows diagnostics are available only on Windows."
        return response

    missing = [name for name, path in commands.items() if not path]
    response["elevated"] = _is_elevated()
    response["commands"] = {name: bool(path) for name, path in commands.items()}
    if missing:
        response["reason"] = "missing_inbox_command"
        response["missing"] = missing
        response["message"] = "One or more required Windows inbox commands are unavailable."
        return response

    available = _available_providers(commands["logman"] or "logman")
    categories = {
        category: provider in available
        for category, provider in PROVIDER_BY_CATEGORY.items()
    }
    response["providers"] = categories
    response["available"] = any(categories.values())
    if not response["available"]:
        response["reason"] = "providers_unavailable"
        response["message"] = "The required ETW providers were not found on this Windows installation."
    else:
        response["message"] = (
            "Ready. Kernel ETW categories may require Darkstar to run as administrator; "
            "capture reports permission failures clearly."
        )
    return response


def _capture(args: dict[str, Any]) -> str:
    if not _is_windows():
        return _json_result(
            success=False,
            action="capture",
            available=False,
            reason="windows_only",
            message="windows_diagnostics can capture only on Windows.",
        )

    commands = _required_commands()
    missing = [name for name, path in commands.items() if not path]
    if missing:
        raise ToolInputError(f"Required Windows inbox commands are unavailable: {', '.join(missing)}.")
    tasklist = commands["tasklist"] or "tasklist"
    logman = commands["logman"] or "logman"
    tracerpt = commands["tracerpt"] or "tracerpt"

    duration, categories, max_events, failures_only = _validate_capture_args(args)
    target = _resolve_target(tasklist, args.get("process_name"), args.get("pid"))

    available_providers = _available_providers(logman)
    enabled: list[tuple[str, str]] = []
    unavailable_categories: list[str] = []
    for category in categories:
        provider = PROVIDER_BY_CATEGORY[category]
        if provider in available_providers:
            enabled.append((category, provider))
        else:
            unavailable_categories.append(category)
    if not enabled:
        raise ToolInputError("None of the requested ETW providers is available on this Windows installation.")

    session_name = "DarkstarDiag_" + uuid.uuid4().hex
    created = False
    started = False
    command_errors: list[str] = []
    active_enabled: list[tuple[str, str]] = []

    with tempfile.TemporaryDirectory(prefix="darkstar-etw-") as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        etl_path = temp_dir / "trace.etl"
        xml_path = temp_dir / "trace.xml"

        first_category, first_provider = enabled[0]
        create_command = [
            logman,
            "create",
            "trace",
            session_name,
            "-o",
            str(etl_path),
            "-ow",
            "-nb",
            "8",
            "64",
            "-bs",
            "64",
            "-max",
            str(MAX_TRACE_MEGABYTES),
            "-p",
            first_provider,
            "0xffffffffffffffff",
            "0xff",
        ]

        try:
            create_result = _run(create_command)
            if create_result.returncode != 0:
                message = (create_result.stderr or create_result.stdout or "unknown error").strip()
                permission_hint = " Run Darkstar as administrator." if not _is_elevated() else ""
                raise ToolInputError(f"Could not create the ETW session: {message}.{permission_hint}")
            created = True
            active_enabled.append((first_category, first_provider))

            for category, provider in enabled[1:]:
                update_result = _run(
                    [
                        logman,
                        "update",
                        "trace",
                        session_name,
                        "-p",
                        provider,
                        "0xffffffffffffffff",
                        "0xff",
                    ]
                )
                if update_result.returncode != 0:
                    command_errors.append(
                        f"Provider {provider} could not be enabled: "
                        + _clean_text(update_result.stderr or update_result.stdout, limit=500)
                    )
                else:
                    active_enabled.append((category, provider))

            start_result = _run([logman, "start", session_name])
            if start_result.returncode != 0:
                message = (start_result.stderr or start_result.stdout or "unknown error").strip()
                permission_hint = " Run Darkstar as administrator." if not _is_elevated() else ""
                raise ToolInputError(f"Could not start the ETW session: {message}.{permission_hint}")
            started = True
            time.sleep(duration)
        finally:
            if started:
                try:
                    stop_result = _run([logman, "stop", session_name])
                    if stop_result.returncode != 0:
                        command_errors.append(
                            "The ETW session did not stop cleanly: "
                            + _clean_text(stop_result.stderr or stop_result.stdout, limit=500)
                        )
                except ToolInputError as exc:
                    command_errors.append(f"The ETW session could not be stopped cleanly: {exc}")
            if created:
                try:
                    delete_result = _run([logman, "delete", session_name])
                    if delete_result.returncode != 0:
                        command_errors.append(
                            "The temporary ETW collector could not be deleted: "
                            + _clean_text(delete_result.stderr or delete_result.stdout, limit=500)
                        )
                except ToolInputError as exc:
                    command_errors.append(f"The temporary ETW collector could not be deleted: {exc}")

        trace_candidates = [etl_path, *sorted(temp_dir.glob("trace*.etl"))]
        actual_etl = next((candidate for candidate in trace_candidates if candidate.is_file() and candidate.stat().st_size > 0), None)
        if actual_etl is None:
            raise ToolInputError("The ETW capture produced no trace file.")
        if actual_etl.stat().st_size > MAX_TRACE_MEGABYTES * 1024 * 1024:
            raise ToolInputError("The ETW trace exceeded its safety size limit.")

        trace_result = _run(
            [tracerpt, str(actual_etl), "-o", str(xml_path), "-of", "XML", "-lr", "-y"],
            timeout=60,
        )
        if trace_result.returncode != 0 or not xml_path.exists():
            message = (trace_result.stderr or trace_result.stdout or "unknown error").strip()
            raise ToolInputError(f"tracerpt could not decode the ETW trace: {message}")

        matched_events, total_trace_events = _parse_xml_events(xml_path, target["pid"])

    failure_events = [event for event in matched_events if event.get("failure")]
    if failures_only:
        candidates = failure_events
    else:
        candidates = failure_events + [event for event in matched_events if not event.get("failure")]
    selected = candidates[:max_events]

    return _json_result(
        success=True,
        action="capture",
        target=target,
        duration_seconds=duration,
        elevated=_is_elevated(),
        requested_categories=categories,
        captured_categories=[category for category, _provider in active_enabled],
        unavailable_categories=unavailable_categories,
        total_trace_events=total_trace_events,
        target_event_count=len(matched_events),
        target_failure_count=len(failure_events),
        failures_only=failures_only,
        truncated=len(candidates) > max_events,
        top_providers=_top_counts(matched_events, "provider"),
        top_events=_top_counts(matched_events, "event"),
        top_failures=_top_counts(failure_events, "failure"),
        events=selected,
        warnings=command_errors,
        limitations=[
            "ETW providers record system-wide activity and this tool filters decoded events to the requested PID afterward.",
            "Some Windows builds omit friendly paths, status values, or event descriptions for individual kernel events.",
            "Kernel ETW providers may require administrator privileges.",
        ],
    )


SCHEMA = {
    "name": "windows_diagnostics",
    "description": (
        "Inspect or briefly trace one running Windows process using only Windows' built-in ETW commands; "
        "no download or Python package is required. Use action=status to check readiness. Use action=capture "
        "with exactly one process_name or pid to collect a bounded 1-10 second process/file/Registry/network trace. "
        "The tool owns and removes its temporary session and files, never changes persistent logging settings, and "
        "returns a compact PID-filtered diagnostic summary. Some kernel providers require administrator privileges."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "capture"],
                "description": "status checks readiness; capture records a short trace for one running process.",
            },
            "process_name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 260,
                "description": "Exact running executable name, such as BlackSun.exe. Use pid when several instances exist.",
            },
            "pid": {
                "type": "integer",
                "minimum": 1,
                "description": "Exact running process ID. Do not supply process_name with pid.",
            },
            "duration_seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_DURATION_SECONDS,
                "default": 5,
                "description": "Capture duration in whole seconds.",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": list(PROVIDER_BY_CATEGORY)},
                "minItems": 1,
                "maxItems": len(PROVIDER_BY_CATEGORY),
                "uniqueItems": True,
                "default": list(DEFAULT_CATEGORIES),
                "description": "ETW activity categories to request.",
            },
            "failures_only": {
                "type": "boolean",
                "default": False,
                "description": "Return only events with a recognizable non-success status or failure phrase.",
            },
            "max_events": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_RETURNED_EVENTS,
                "default": 40,
                "description": "Maximum individual events returned to the model.",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def handler(args: dict[str, Any], **_context: Any) -> str:
    if not isinstance(args, dict):
        raise ToolInputError("Arguments must be an object.")
    action = args.get("action")
    if action == "status":
        unexpected = set(args) - {"action"}
        if unexpected:
            raise ToolInputError("status accepts only action.")
        return _json_result(**_diagnostic_status())
    if action == "capture":
        return _capture(args)
    raise ToolInputError("action must be status or capture.")


registry.register(
    name=SCHEMA["name"],
    toolset="system",
    schema=SCHEMA,
    handler=handler,
)
