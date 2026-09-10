# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: present a previously produced tool image in the assistant response."""
from __future__ import annotations

import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath

_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry

SCHEMA = {
    "name": "show_image",
    "description": (
        "Display one image cleanly in your assistant response. Use the exact image_id returned by a previous "
        "image-producing tool call in this same response, especially after generate_image. This is presentation-only: "
        "it does not inspect, modify, regenerate, or load an image from a filesystem path."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "image_id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 512,
                "description": "Exact image_id returned by a previous image-producing tool call in this response.",
            },
        },
        "required": ["image_id"],
        "additionalProperties": False,
    },
}


def handler(args, **_context):
    image_id = str(args.get("image_id") or "").strip()
    if not image_id:
        raise ValueError("image_id is required.")
    return {"__darkstarAction": "show_image", "image_id": image_id}


registry.register(
    name=SCHEMA["name"],
    toolset="media",
    schema=SCHEMA,
    handler=handler,
    description=SCHEMA["description"],
    permission={"risk": "read"},
    filesystem="none",
)
