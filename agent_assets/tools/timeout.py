# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: pause the current agent run for a requested number of seconds."""
from __future__ import annotations

import sys as _darkstar_sys
import time
from pathlib import Path as _DarkstarPath

_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import ToolInputError, json_result

PROVIDER_ID = "timeout"
PROVIDER_NAME = "Timeout"
MAX_TIMEOUT_SECONDS = 3600

SCHEMA = {
    "name": "timeout",
    "description": (
        "Pause the current agent run for the requested timer duration, then return so the agent can continue. "
        "The required `seconds` value is always a whole number of seconds (s), never milliseconds or minutes. "
        "Example: seconds=30 waits for 30 seconds. Use this only when a real wall-clock delay is needed."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_TIMEOUT_SECONDS,
                "description": (
                    "REQUIRED timer duration in whole seconds (s). "
                    "Do not provide milliseconds or minutes. Example: 10 means wait 10 seconds."
                ),
            },
        },
        "required": ["seconds"],
        "additionalProperties": False,
    },
}


def _require_seconds(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInputError("seconds must be a whole number measured in seconds (s).")
    if value < 1 or value > MAX_TIMEOUT_SECONDS:
        raise ToolInputError(
            f"seconds must be between 1 and {MAX_TIMEOUT_SECONDS} seconds (s)."
        )
    return value


def handler(args, **_context):
    seconds = _require_seconds(args.get("seconds"))
    started_at = time.monotonic()
    time.sleep(seconds)
    elapsed = max(0.0, time.monotonic() - started_at)
    return json_result(
        success=True,
        requested_seconds=seconds,
        elapsed_seconds=round(elapsed, 3),
        unit="seconds (s)",
        message=f"Timeout completed after {seconds} second{'s' if seconds != 1 else ''}. Continue the agent run now.",
    )


registry.register(
    name=SCHEMA["name"],
    toolset="control",
    schema=SCHEMA,
    handler=handler,
    description=SCHEMA["description"],
)
