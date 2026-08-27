# SPDX-License-Identifier: Apache-2.0
"""Darkstar Tool: capture a workspace HTML page in the isolated side browser."""

from tools.registry import registry

MAX_WAIT_MS = 10_000

SCHEMA = {
    "name": "screenshot_html",
    "description": (
        "Open a workspace-local .html or .htm file in Darkstar's network-isolated side browser, "
        "capture the current browser viewport as PNG, and attach it to the next multimodal model turn. "
        "Use this for visual QA after creating or editing local HTML/CSS/JavaScript."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1024,
                "pattern": r".*\.[Hh][Tt][Mm][Ll]?$",
                "description": "Workspace-relative .html or .htm file to render.",
            },
            "wait_ms": {
                "type": "integer",
                "minimum": 0,
                "maximum": MAX_WAIT_MS,
                "description": "Optional extra render-settling delay in milliseconds. Defaults to 0.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


def handler(args, **_context):
    path = str(args.get("path") or "").strip()
    if not path:
        raise ValueError("path is required.")
    if not path.lower().endswith((".html", ".htm")):
        raise ValueError("screenshot_html accepts only .html or .htm files.")
    wait_ms = args.get("wait_ms", 0)
    if isinstance(wait_ms, bool) or not isinstance(wait_ms, int) or not 0 <= wait_ms <= MAX_WAIT_MS:
        raise ValueError(f"wait_ms must be an integer between 0 and {MAX_WAIT_MS}.")
    return {
        "__darkstarAction": "screenshot_html",
        "path": path,
        "wait_ms": wait_ms,
    }


registry.register(
    name=SCHEMA["name"],
    toolset="browser",
    schema=SCHEMA,
    handler=handler,
    description=SCHEMA["description"],
)
