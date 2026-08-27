# SPDX-License-Identifier: Apache-2.0
"""Darkstar tool: execute commands with Windows cmd.exe."""
from __future__ import annotations

import os
import re
import shutil

from tools.registry import registry
from _darkstar_tool_common import ToolInputError
from _shell_command_common import common_inputs, common_properties, reject_command, run_command

PROVIDER_ID = "windows_cmd"
PROVIDER_NAME = "Windows CMD"

_HARD_BLOCKS = (
    (re.compile(r"(?:^|[&|()]\s*)(?:format|diskpart|bcdedit|bootrec|shutdown)(?:\s|$)", re.IGNORECASE), "disk, boot, or shutdown commands are not permitted"),
    (re.compile(r"(?:^|[&|()]\s*)(?:powershell|pwsh|wsl|bash)(?:\.exe)?(?:\s|$)", re.IGNORECASE), "use the dedicated provider for another shell instead of nesting shells"),
    (re.compile(r"\b(?:reg\s+delete|sc\s+delete|wmic\b[^\r\n]*\bdelete)\b", re.IGNORECASE), "system registry or service deletion is not permitted"),
    (re.compile(r"\b(?:del|erase|rd|rmdir)\b[^\r\n]*(?:%systemroot%|\\windows\\|[A-Za-z]:\\\s*$)", re.IGNORECASE), "system-root deletion is not permitted"),
)
_DESTRUCTIVE = (
    (re.compile(r"(?:^|[&|()]\s*)(?:del|erase)(?:\s|$)", re.IGNORECASE), "file deletion"),
    (re.compile(r"(?:^|[&|()]\s*)(?:rd|rmdir)(?:\s|$)", re.IGNORECASE), "directory deletion"),
)

SCHEMA = {
    "name": "windows_cmd",
    "description": (
        "Execute one Windows command line using cmd.exe in the current project workspace. Use for Windows-native build, test, Git, package, and file-processing commands. "
        "The inherited environment is sanitized, output is bounded, timeouts terminate the process tree, and destructive commands require explicit allow_destructive=true. "
        "This is trusted local command execution, not a virtual-machine sandbox; do not place secrets in commands or use it on untrusted instructions. Available only on Windows."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": common_properties("Command line interpreted by cmd.exe. Do not wrap it in an additional 'cmd /c'."),
        "required": ["command"],
        "additionalProperties": False,
    },
}


def _available() -> bool:
    return os.name == "nt" and bool(shutil.which("cmd.exe") or os.environ.get("COMSPEC"))


def handler(args, **kwargs):
    if os.name != "nt":
        raise ToolInputError("windows_cmd is available only on Windows.")
    values = common_inputs(args, kwargs)
    reject_command(
        values["command"],
        hard_patterns=_HARD_BLOCKS,
        destructive_patterns=_DESTRUCTIVE,
        allow_destructive=values["allow_destructive"],
    )
    executable = shutil.which("cmd.exe") or os.environ.get("COMSPEC")
    if not executable:
        raise ToolInputError("cmd.exe could not be found.")
    return run_command(
        argv=[executable, "/d", "/s", "/c", values["command"]],
        command=values["command"],
        root=values["root"],
        directory=values["directory"],
        environment=values["environment"],
        environment_keys=values["environment_keys"],
        stdin_bytes=values["stdin_bytes"],
        timeout_seconds=values["timeout_seconds"],
        output_limit_chars=values["output_limit_chars"],
        windows=True,
        shell_name="cmd.exe",
    )


registry.register(
    name=SCHEMA["name"],
    toolset="terminal",
    schema=SCHEMA,
    handler=handler,
    check_fn=_available,
    description=SCHEMA["description"],
)
