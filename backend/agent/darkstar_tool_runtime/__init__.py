# SPDX-License-Identifier: Apache-2.0
"""Internal Python runtime support for Darkstar tool providers.

These modules are application infrastructure. They do not register model-facing
functions and are intentionally stored outside the user-selectable tool catalog.
"""

from .tool_common import ToolInputError

__all__ = ["ToolInputError"]
