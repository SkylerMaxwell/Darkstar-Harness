# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: execute commands with a non-login Linux shell."""
from __future__ import annotations

import os
import re
import shutil
import sys

from tools.registry import registry
from _darkstar_tool_common import ToolInputError
from _shell_command_common import common_inputs, common_properties, reject_command, run_command

PROVIDER_ID = "linux_terminal"
PROVIDER_NAME = "Linux Terminal"

_HARD_BLOCKS = (
    (re.compile(r"(?:^|[;&|()]\s*)(?:sudo|su|doas)(?:\s|$)", re.IGNORECASE), "privilege escalation is not permitted"),
    (re.compile(r"(?:^|[;&|()]\s*)(?:shutdown|reboot|poweroff|halt|init\s+[06])(?:\s|$)", re.IGNORECASE), "shutdown and reboot commands are not permitted"),
    (re.compile(r"(?:^|[;&|()]\s*)(?:mkfs(?:\.[A-Za-z0-9_-]+)?|fdisk|cfdisk|sfdisk|parted|wipefs)(?:\s|$)", re.IGNORECASE), "disk formatting and partitioning commands are not permitted"),
    (re.compile(r"\bdd\b[^\r\n]*\bof\s*=\s*/dev/", re.IGNORECASE), "raw writes to block devices are not permitted"),
    (re.compile(r"\brm\s+(?=[^\r\n]*-[^\r\n]*r)(?=[^\r\n]*-[^\r\n]*f)[^\r\n]*(?:^|\s)/(?:\s|$)", re.IGNORECASE), "recursive deletion of the filesystem root is not permitted"),
    (re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;\s*:", re.IGNORECASE), "fork bombs are not permitted"),
    (re.compile(r"(?:^|[;&|()]\s*)(?:cmd(?:\.exe)?|powershell(?:\.exe)?|pwsh(?:\.exe)?)(?:\s|$)", re.IGNORECASE), "use the dedicated Windows provider instead of nesting another platform shell"),
)
_DESTRUCTIVE = (
    (re.compile(r"(?:^|[;&|()]\s*)rm(?:\s|$)", re.IGNORECASE), "file deletion"),
    (re.compile(r"(?:^|[;&|()]\s*)(?:truncate|shred)(?:\s|$)", re.IGNORECASE), "file truncation or destruction"),
)

SCHEMA = {
    "name": "linux_terminal",
    "description": (
        "Execute one command line using a non-login Linux shell in the current project workspace. Use for Linux-native build, test, Git, package, and file-processing commands. "
        "The inherited environment is sanitized, output is bounded, timeouts terminate the process group, and destructive commands require explicit allow_destructive=true. "
        "This is trusted local command execution, not a container or virtual-machine sandbox; do not place secrets in commands or use it on untrusted instructions. Available only on Linux."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": common_properties("Command line interpreted by Bash when available, otherwise POSIX sh. Do not wrap it in an additional shell command."),
        "required": ["command"],
        "additionalProperties": False,
    },
}


def _shell() -> str | None:
    return shutil.which("bash") or shutil.which("sh")


def _available() -> bool:
    return sys.platform.startswith("linux") and bool(_shell())


def handler(args, **kwargs):
    if not sys.platform.startswith("linux"):
        raise ToolInputError("linux_terminal is available only on Linux.")
    values = common_inputs(args, kwargs)
    reject_command(
        values["command"],
        hard_patterns=_HARD_BLOCKS,
        destructive_patterns=_DESTRUCTIVE,
        allow_destructive=values["allow_destructive"],
    )
    executable = _shell()
    if not executable:
        raise ToolInputError("Neither bash nor sh could be found.")
    if os.path.basename(executable) == "bash":
        argv = [executable, "--noprofile", "--norc", "-c", values["command"]]
        shell_name = "bash"
    else:
        argv = [executable, "-c", values["command"]]
        shell_name = "sh"
    return run_command(
        argv=argv,
        command=values["command"],
        root=values["root"],
        directory=values["directory"],
        environment=values["environment"],
        environment_keys=values["environment_keys"],
        stdin_bytes=values["stdin_bytes"],
        timeout_seconds=values["timeout_seconds"],
        output_limit_chars=values["output_limit_chars"],
        windows=False,
        shell_name=shell_name,
    )


registry.register(
    name=SCHEMA["name"],
    toolset="terminal",
    schema=SCHEMA,
    handler=handler,
    check_fn=_available,
    description=SCHEMA["description"],
)
