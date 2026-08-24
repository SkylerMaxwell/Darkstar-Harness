# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: return the host computer's current local and UTC time."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from tools.registry import registry


SCHEMA = {
    "name": "get_current_time",
    "description": "Return the computer's current local time and UTC time. This tool takes no arguments.",
    "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


def handler(args: dict[str, Any], **_context: Any) -> str:
    if not isinstance(args, dict) or args:
        raise ValueError("get_current_time takes no arguments.")

    local_now = datetime.now().astimezone()
    utc_now = local_now.astimezone(timezone.utc)
    return json.dumps(
        {
            "success": True,
            "local_time": local_now.isoformat(timespec="seconds"),
            "utc_time": utc_now.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "timezone": local_now.tzname() or str(local_now.tzinfo),
            "unix_seconds": int(local_now.timestamp()),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


registry.register(
    name=SCHEMA["name"],
    toolset="system",
    schema=SCHEMA,
    handler=handler,
)
