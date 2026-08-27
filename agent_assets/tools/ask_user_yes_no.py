# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: ask the user one short Yes/No question."""
from __future__ import annotations

import sys as _darkstar_sys
from pathlib import Path as _DarkstarPath

_DARKSTAR_TOOL_DIRECTORY = str(_DarkstarPath(__file__).resolve().parent)
if _DARKSTAR_TOOL_DIRECTORY not in _darkstar_sys.path:
    _darkstar_sys.path.insert(0, _DARKSTAR_TOOL_DIRECTORY)

from tools.registry import registry
from _darkstar_tool_common import ToolInputError, request_yes_no

PROVIDER_ID = "ask-user-yes-no"
PROVIDER_NAME = "Ask User Yes/No"
MAX_QUESTION_CHARS = 240

SCHEMA = {
    "name": "ask_user_yes_no",
    "description": (
        "Ask the user one short Yes/No question and wait for their answer. "
        "The question MUST be exactly one sentence, directly answerable with Yes or No, "
        "and end with a question mark."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "minLength": 3,
                "maxLength": MAX_QUESTION_CHARS,
                "description": (
                    "One short sentence that can be answered Yes or No. "
                    "It must end with a question mark."
                ),
            },
        },
        "required": ["question"],
        "additionalProperties": False,
    },
}


def _normalize_question(value: object) -> str:
    if not isinstance(value, str):
        raise ToolInputError("question must be a string.")
    question = value.strip()
    if not question:
        raise ToolInputError("question must not be empty.")
    if len(question) > MAX_QUESTION_CHARS:
        raise ToolInputError(f"question must be at most {MAX_QUESTION_CHARS} characters.")
    if "\n" in question or "\r" in question:
        raise ToolInputError("question must be exactly one sentence on one line.")
    if not question.endswith("?") or question.count("?") != 1:
        raise ToolInputError("question must be one sentence ending with a single question mark.")
    return question


def handler(args, **_context):
    return request_yes_no(_normalize_question(args.get("question")))


registry.register(
    name=SCHEMA["name"],
    toolset="interaction",
    schema=SCHEMA,
    handler=handler,
    description=SCHEMA["description"],
    permission={"risk": "read"},
)
