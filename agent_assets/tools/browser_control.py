# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar Browser Control with strict online browsing, spatial control, live Three.js diagnostics, and transactional modeling.

This is the full Browser Control provider. It preserves the existing browser and
Three.backend/renderer/modeling features and adds constrained spatial inspection and semantic
grid control for canvas/custom-rendered interfaces. The tool remains registered
as ``browser_control`` because Darkstar uses that name as the browser security
boundary.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from tools.registry import registry

PROVIDER_ID = "browser-control-spatial-threejs-modeler"
PROVIDER_NAME = "Browser Control + Spatial Control + Three.js Debug + Modeler"

STANDARD_ACTIONS = [
    "open",
    "status",
    "snapshot",
    "screenshot",
    "click",
    "move",
    "mouse_down",
    "mouse_up",
    "drag",
    "type",
    "fill",
    "key",
    "key_down",
    "key_up",
    "wheel",
    "wait",
    "reload",
    "back",
    "forward",
    "console",
    "dialog",
    "evaluate",
    "release_all",
    "reset",
]

SPATIAL_ACTIONS = [
    "interactive_map",
    "get_element_coordinates",
    "scroll_into_view",
    "hit_test",
    "inspect_at_point",
    "wait_for_stable",
    "annotated_screenshot",
    "grid_inspect",
    "grid_overlay",
    "grid_click",
    "grid_drag",
]

DEBUG_ACTIONS = [
    "threejs_source_audit",
    "threejs_open_debug",
    "threejs_debug_status",
    "threejs_audit",
    "threejs_profile",
    "threejs_object",
    "threejs_cleanup_debug",
    "threejs_model",
]

ACTIONS = STANDARD_ACTIONS + SPATIAL_ACTIONS + DEBUG_ACTIONS
TIMER_ACTIONS = {
    "open",
    "screenshot",
    "click",
    "drag",
    "type",
    "fill",
    "key",
    "wheel",
    "wait",
    "reload",
    "back",
    "forward",
    "dialog",
    "evaluate",
    "threejs_open_debug",
    "wait_for_stable",
    "annotated_screenshot",
    "grid_click",
    "grid_drag",
}

MAX_TIMER_MS = 10_000
MAX_HTML_BYTES = 16 * 1024 * 1024
MAX_SOURCE_ISSUES = 60
DEBUG_FILE_MARKER = "DARKSTAR THREE DEBUG COPY"

DESCRIPTION = (
    "Control Darkstar's isolated internal browser with native Chromium input in local OFFLINE mode or STRICT ONLINE mode, with deterministic spatial control for canvas/custom-rendered interfaces. "
    "For online browsing use open with url='https://…'; for workspace-local HTML use open with path='page.html'. Provide exactly one. "
    "Prefer interactive_map and stable refs for ordinary controls. interactive_map returns exact CSS-pixel boxes, centers, occlusion state, viewport size, devicePixelRatio, and a short-lived layout id. "
    "Use get_element_coordinates or scroll_into_view for an exact current ref position, and hit_test/inspect_at_point to identify what receives input at a CSS-pixel point. "
    "For canvas/board/grid interfaces, call grid_inspect first. It creates a grid id from a live element ref or an automatically detected square surface, returns its exact current bounds and labels, and refuses chess actions when orientation is uncertain. "
    "Then use grid_overlay for a labeled screenshot, grid_click for one cell, or grid_drag for a semantic move such as E2 to E4. Darkstar resolves cell coordinates from the live grid immediately before input; do not estimate board coordinates from screenshots. "
    "Use annotated_screenshot to label visible interactive elements with their stable refs. Use wait_for_stable before measuring highly animated layouts. "
    "For difficult local Three.js work use threejs_source_audit, threejs_open_debug, threejs_audit, threejs_profile, threejs_object, and threejs_model. "
    "Arbitrary evaluate is for workspace-local pages only and is rejected by the secure online host. Online pages remain in Darkstar's separate ephemeral browser compartment. "
    "Three.js r184 is preloaded as window.THREE before local page scripts."
)

SCHEMA = {
    "name": "browser_control",
    "description": DESCRIPTION,
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ACTIONS,
                "description": (
                    "Browser, spatial, or Three.js diagnostic operation. For arbitrary sites prefer interactive_map -> ref action. "
                    "For canvas/board surfaces use grid_inspect -> grid_overlay -> grid_click/grid_drag. Never guess grid pixels when a semantic grid is available. "
                    "For Three.js debugging use threejs_source_audit -> threejs_open_debug -> threejs_audit."
                ),
            },
            "path": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1024,
                "description": "Workspace-relative HTML path for local open, threejs_source_audit, or threejs_open_debug. For open, provide path or url, never both.",
            },
            "url": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4096,
                "pattern": "^https://",
                "description": "HTTPS address for action='open' in STRICT ONLINE mode. Provide url or path, never both.",
            },
            "ref": {
                "type": "string",
                "pattern": "^e[0-9]+$",
                "description": "Stable element reference returned by snapshot or interactive_map.",
            },
            "end_ref": {
                "type": "string",
                "pattern": "^e[0-9]+$",
                "description": "Destination element reference for drag.",
            },
            "x": {"type": "number", "minimum": 0, "description": "Viewport X coordinate in CSS pixels."},
            "y": {"type": "number", "minimum": 0, "description": "Viewport Y coordinate in CSS pixels."},
            "end_x": {"type": "number", "minimum": 0, "description": "Destination viewport X coordinate for drag."},
            "end_y": {"type": "number", "minimum": 0, "description": "Destination viewport Y coordinate for drag."},
            "offset_x": {"type": "number", "description": "X offset from a referenced element's center."},
            "offset_y": {"type": "number", "description": "Y offset from a referenced element's center."},
            "text": {
                "type": "string",
                "maxLength": 64_000,
                "description": "Text for type or fill. fill replaces the editable value; type inserts at the caret.",
            },
            "key": {
                "type": "string",
                "minLength": 1,
                "maxLength": 40,
                "description": "Key name such as Enter, Escape, ArrowLeft, Space, F6, a, or 7.",
            },
            "modifiers": {
                "type": "array",
                "items": {"type": "string", "enum": ["ctrl", "alt", "shift", "meta"]},
                "uniqueItems": True,
                "maxItems": 4,
                "description": "Keyboard or pointer modifiers.",
            },
            "button": {
                "type": "string",
                "enum": ["left", "middle", "right", "back", "forward"],
                "description": "Mouse button. Defaults to left.",
            },
            "click_count": {"type": "integer", "minimum": 1, "maximum": 3, "description": "Click count."},
            "delta_x": {"type": "number", "description": "Horizontal wheel delta."},
            "delta_y": {"type": "number", "description": "Vertical wheel delta; positive scrolls down."},
            "steps": {"type": "integer", "minimum": 2, "maximum": 60, "description": "Pointer steps in a drag."},
            "duration_ms": {
                "type": "integer",
                "minimum": 0,
                "maximum": 5000,
                "description": "Drag duration, or profile duration for threejs_profile. Profile default is 2000 ms.",
            },
            "timer_ms": {
                "type": "integer",
                "minimum": 0,
                "maximum": MAX_TIMER_MS,
                "description": "Optional browser-side wait. Preferred over wait_ms.",
            },
            "wait_ms": {
                "type": "integer",
                "minimum": 0,
                "maximum": MAX_TIMER_MS,
                "description": "Backward-compatible alias for timer_ms. Do not provide both.",
            },
            "snapshot_mode": {
                "type": "string",
                "enum": ["all", "interactive"],
                "description": "Snapshot detail mode.",
            },
            "max_elements": {
                "type": "integer",
                "minimum": 1,
                "maximum": 300,
                "description": "Maximum snapshot elements.",
            },
            "snapshot_after": {
                "type": "boolean",
                "description": "Return an interactive snapshot after a state-changing browser action.",
            },
            "accept": {"type": "boolean", "description": "For dialog: accept when true, dismiss when false."},
            "prompt_text": {"type": "string", "maxLength": 4000, "description": "Prompt response for dialog."},
            "script": {
                "type": "string",
                "minLength": 1,
                "maxLength": 64_000,
                "description": "JavaScript statement body for evaluate on workspace-local pages only. Secure online pages reject arbitrary evaluation. Use return to provide a result.",
            },
            "layout_id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 160,
                "description": "Optional short-lived layout id returned by interactive_map. Re-measure after navigation, resize, scroll, or major DOM changes.",
            },
            "stable_ms": {
                "type": "integer",
                "minimum": 50,
                "maximum": 1500,
                "description": "For wait_for_stable: required quiet period with no meaningful layout mutation. Defaults to about 220 ms.",
            },
            "annotation_mode": {
                "type": "string",
                "enum": ["interactive", "grid", "all"],
                "description": "Overlay content for annotated_screenshot. interactive labels refs; grid labels the selected grid; all shows both.",
            },
            "grid_id": {
                "type": "string",
                "pattern": "^g[0-9]+$",
                "description": "Stable grid reference returned by grid_inspect. Re-inspect after navigation or when the surface is replaced.",
            },
            "grid_ref": {
                "type": "string",
                "pattern": "^e[0-9]+$",
                "description": "Element ref to use as a grid surface. Prefer a canvas, board, SVG, or custom board container returned by interactive_map.",
            },
            "grid_target": {
                "type": "string",
                "minLength": 1,
                "maxLength": 160,
                "description": "Optional semantic hint for grid_inspect auto-detection, for example 'chess board'.",
            },
            "grid_rows": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "description": "Logical grid row count. Chess defaults to 8.",
            },
            "grid_columns": {
                "type": "integer",
                "minimum": 1,
                "maximum": 64,
                "description": "Logical grid column count. Chess defaults to 8.",
            },
            "grid_label_mode": {
                "type": "string",
                "enum": ["chess", "spreadsheet", "row-column", "numeric"],
                "description": "Cell naming scheme. chess uses A1-H8 semantics; spreadsheet uses top-left A1; row-column uses R1C1; numeric uses 1..N.",
            },
            "grid_orientation": {
                "type": "string",
                "enum": ["auto", "white-bottom", "black-bottom", "top-left"],
                "description": "Grid orientation. For chess, auto is preferred; if Darkstar cannot prove orientation it returns unknown and refuses grid input until explicitly supplied.",
            },
            "cell": {
                "type": "string",
                "minLength": 1,
                "maxLength": 32,
                "description": "Target cell for grid_click, for example E4, A12, R3C5, or 17 depending on grid_label_mode.",
            },
            "from_cell": {
                "type": "string",
                "minLength": 1,
                "maxLength": 32,
                "description": "Source cell for grid_drag, for example E2.",
            },
            "to_cell": {
                "type": "string",
                "minLength": 1,
                "maxLength": 32,
                "description": "Destination cell for grid_drag, for example E4.",
            },
            "verify": {
                "type": "boolean",
                "description": "For grid_click/grid_drag, verify that the grid surface visibly changed after input. Defaults to true. A visible change proves the surface reacted, not that arbitrary site-specific business logic accepted the intended semantic operation.",
            },
            "detail": {
                "type": "string",
                "enum": ["summary", "standard", "deep"],
                "description": "Three.js audit depth. standard is recommended; deep scans more geometry data and may take longer.",
            },
            "compile_shaders": {
                "type": "boolean",
                "description": "For threejs_audit, ask the renderer to precompile the active scene and capture compilation failures. Defaults to false.",
            },
            "object_limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 40,
                "description": "Maximum detailed objects or matches in Three.js reports. Defaults to 24; capped to keep model context bounded.",
            },
            "query": {
                "type": "string",
                "minLength": 1,
                "maxLength": 200,
                "description": "Case-insensitive object name, UUID, or type query for threejs_object.",
            },
            "model_action": {
                "type": "string",
                "enum": ["help", "init", "apply", "status", "inspect", "undo", "redo", "view", "restore_view", "export_recipe", "commit_recipe", "cleanup"],
                "description": "Required when action is threejs_model. Call help once for the complete operation reference. Start live work with init. apply executes every supplied operation atomically; a failure rolls the whole batch back. commit_recipe safely inserts or replaces one marked model recipe in an existing HTML file.",
            },
            "operations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 64,
                "items": {"type": "object", "required": ["op"], "additionalProperties": True},
                "description": "Ordered modeling operations for apply or commit_recipe. Use stable ids. Example: [{\"op\":\"create\",\"id\":\"hull\",\"primitive\":\"box\",\"size\":[4,1,6]},{\"op\":\"transform\",\"target\":\"hull\",\"position\":[0,0.5,0]}]. Call model_action=help for every field and example.",
            },
            "target": {
                "type": "string",
                "minLength": 1,
                "maxLength": 160,
                "description": "Model object id, object name, or UUID for inspect/view. Omit to use the complete Darkstar model root.",
            },
            "model_id": {
                "type": "string",
                "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$",
                "description": "Stable identifier for a committed model block. Defaults to model.",
            },
            "view": {
                "type": "string",
                "enum": ["front", "back", "left", "right", "top", "bottom", "isometric"],
                "description": "Technical camera view for threejs_model model_action=view.",
            },
            "overlays": {
                "type": "array",
                "uniqueItems": True,
                "maxItems": 6,
                "items": {"type": "string", "enum": ["wireframe", "bounds", "edges", "axes", "pivots", "grid"]},
                "description": "Temporary technical overlays for a modeling view. Restore with model_action=restore_view.",
            },
            "deep": {
                "type": "boolean",
                "description": "For model inspection, scan more vertices/triangles and include deeper topology diagnostics.",
            },
            "expected_sha256": {
                "type": "string",
                "pattern": "^[A-Fa-f0-9]{64}$",
                "description": "Optional optimistic-concurrency hash for commit_recipe. The existing HTML must still have this SHA-256 or no write occurs.",
            },
            "include_info": {
                "type": "boolean",
                "description": "For source audit, include informational findings in addition to warnings/errors. Defaults to false.",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _validated_timer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer between 0 and {MAX_TIMER_MS}")
    if not 0 <= value <= MAX_TIMER_MS:
        raise ValueError(f"{field_name} must be between 0 and {MAX_TIMER_MS} milliseconds")
    return value


def _validated_online_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("url must be a non-empty HTTPS address")
    url = value.strip()
    if len(url) > 4096:
        raise ValueError("url must not exceed 4096 characters")
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("STRICT ONLINE mode accepts only absolute https:// URLs")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Online URLs must not contain embedded credentials")
    return url


def _workspace_root(kwargs: dict[str, Any]) -> Path:
    candidates: list[Any] = []
    for mapping in (kwargs, kwargs.get("context"), kwargs.get("execution_context"), kwargs.get("executionContext")):
        if isinstance(mapping, dict):
            for key in (
                "workspace",
                "workspace_root",
                "workspaceRoot",
                "working_directory",
                "workingDirectory",
                "cwd",
                "root",
            ):
                candidates.append(mapping.get(key))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            root = Path(candidate).expanduser().resolve(strict=False)
            if root.exists() and root.is_dir():
                return root
    root = Path.cwd().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("The current project workspace is unavailable.")
    return root


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(str(root)), os.path.normcase(str(candidate))]) == os.path.normcase(str(root))
    except ValueError:
        return False


def _resolve_html(raw_path: Any, kwargs: dict[str, Any], *, must_exist: bool = True) -> tuple[Path, Path, str]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("path is required")
    root = _workspace_root(kwargs)
    supplied = Path(raw_path.strip()).expanduser()
    lexical = supplied if supplied.is_absolute() else root / supplied
    lexical = Path(os.path.abspath(os.path.normpath(str(lexical))))
    parent = lexical.parent.resolve(strict=False)
    candidate = parent / lexical.name
    if not _is_within(root, candidate):
        raise ValueError("path must stay inside the current project workspace")
    if candidate.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("path must identify an .html or .htm file")
    if must_exist:
        if not candidate.exists():
            raise ValueError(f"HTML file does not exist: {raw_path}")
        if candidate.is_symlink():
            raise ValueError("Symbolic-link HTML files are not accepted")
        if not candidate.is_file():
            raise ValueError("path is not a regular file")
        if candidate.stat().st_size > MAX_HTML_BYTES:
            raise ValueError(f"HTML file exceeds the {MAX_HTML_BYTES // (1024 * 1024)} MiB debug limit")
    return root, candidate, candidate.relative_to(root).as_posix()


def _read_html(path: Path) -> str:
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError("HTML file appears to be binary")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"HTML file is not valid UTF-8 at byte {exc.start}") from exc


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _excerpt(text: str, offset: int, limit: int = 180) -> str:
    start = text.rfind("\n", 0, max(0, offset)) + 1
    end = text.find("\n", max(0, offset))
    if end < 0:
        end = len(text)
    return re.sub(r"\s+", " ", text[start:end]).strip()[:limit]


def _source_issue(issues: list[dict[str, Any]], severity: str, code: str, message: str, *, line: int | None = None,
                  evidence: str | None = None, fix: str | None = None) -> None:
    if len(issues) >= MAX_SOURCE_ISSUES:
        return
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if line is not None:
        item["line"] = line
    if evidence:
        item["evidence"] = evidence
    if fix:
        item["fix"] = fix
    issues.append(item)


def _literal_asset_references(source: str) -> list[tuple[str, int, str]]:
    patterns = [
        re.compile(r"\b(?:load|setPath|setResourcePath)\s*\(\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL),
        re.compile(r"\b(?:fetch|new\s+Worker|new\s+Audio)\s*\(\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL),
    ]
    found: list[tuple[str, int, str]] = []
    for pattern in patterns:
        for match in pattern.finditer(source):
            value = html.unescape(match.group(2)).strip()
            found.append((value, match.start(2), match.group(0)[:80]))
    for match in re.finditer(r"\b(?:src|href)\s*=\s*(['\"])(.*?)\1", source, re.IGNORECASE | re.DOTALL):
        value = html.unescape(match.group(2)).strip()
        found.append((value, match.start(2), match.group(0)[:80]))
    return found


def _resolve_local_reference(html_path: Path, reference: str) -> Path | None:
    value = reference.strip()
    if not value or value.startswith(("#", "data:", "blob:", "javascript:", "mailto:")):
        return None
    split = urlsplit(value)
    if split.scheme:
        if split.scheme.lower() == "file":
            return Path(unquote(split.path)).resolve(strict=False)
        return None
    clean = unquote(split.path)
    if not clean:
        return None
    return (html_path.parent / clean).resolve(strict=False)


def _source_audit(raw_path: Any, kwargs: dict[str, Any], include_info: bool = False) -> dict[str, Any]:
    root, path, display = _resolve_html(raw_path, kwargs)
    source = _read_html(path)
    lower = source.lower()
    issues: list[dict[str, Any]] = []

    def matches(pattern: str, flags: int = re.IGNORECASE) -> list[re.Match[str]]:
        return list(re.finditer(pattern, source, flags))

    remote_refs = []
    missing_assets = []
    checked_assets = 0
    seen_refs: set[str] = set()
    for ref, offset, _evidence in _literal_asset_references(source):
        if ref in seen_refs:
            continue
        seen_refs.add(ref)
        split = urlsplit(ref)
        if split.scheme.lower() in {"http", "https", "ws", "wss", "ftp"} or ref.startswith("//"):
            remote_refs.append(ref)
            _source_issue(
                issues,
                "error",
                "OFFLINE_REMOTE_RESOURCE",
                "The offline browser will block this remote resource.",
                line=_line_number(source, offset),
                evidence=ref[:180],
                fix="Store the asset inside the workspace and use a relative path.",
            )
            continue
        local = _resolve_local_reference(path, ref)
        if local is None:
            continue
        checked_assets += 1
        if not _is_within(root, local):
            _source_issue(
                issues,
                "error",
                "ASSET_OUTSIDE_WORKSPACE",
                "A referenced local asset resolves outside the active workspace.",
                line=_line_number(source, offset),
                evidence=ref[:180],
                fix="Move the asset into the workspace and update the relative path.",
            )
        elif not local.exists():
            missing_assets.append(ref)
            _source_issue(
                issues,
                "error",
                "MISSING_ASSET",
                "A statically referenced local asset does not exist.",
                line=_line_number(source, offset),
                evidence=ref[:180],
                fix="Correct the path or create the missing asset.",
            )

    three_script_matches = matches(r"<script\b[^>]*\bsrc\s*=\s*(['\"])[^'\"]*three(?:\.min|\.module|\.core)?(?:\.js)?[^'\"]*\1")
    if three_script_matches:
        for match in three_script_matches[:8]:
            _source_issue(
                issues,
                "error",
                "DUPLICATE_THREE_CORE",
                "Do not load another Three.js core build; Darkstar already preloads r184 as window.THREE.",
                line=_line_number(source, match.start()),
                evidence=_excerpt(source, match.start()),
                fix="Remove the Three.js core script/import and use the preloaded window.THREE runtime.",
            )

    for match in matches(r"\bimport\s+(?:[^;]*?\s+from\s+)?['\"]three(?:/[^'\"]*)?['\"]"):
        _source_issue(
            issues,
            "error",
            "BARE_THREE_IMPORT",
            "A bare Three.js import will not resolve in the offline file-based preview without a bundler or import map.",
            line=_line_number(source, match.start()),
            evidence=_excerpt(source, match.start()),
            fix="Use preloaded window.THREE for core, and bundle or provide local addon modules explicitly.",
        )

    deprecated_patterns = [
        (r"\bTHREE\.(?:Geometry|Face3|Projector|JSONLoader|ImageUtils)\b", "REMOVED_THREE_API", "This Three.js API was removed long before r184.", "Replace it with BufferGeometry or the current loader/API equivalent."),
        (r"\b(?:renderer|\w+)\.outputEncoding\b|\bTHREE\.sRGBEncoding\b|\btexture\.encoding\b", "OLD_COLOR_API", "Legacy encoding properties are incompatible with current Three.js color management.", "Use renderer.outputColorSpace and texture.colorSpace with THREE.SRGBColorSpace where appropriate."),
        (r"\.addAttribute\s*\(", "OLD_GEOMETRY_ATTRIBUTE_API", "BufferGeometry.addAttribute is obsolete.", "Use geometry.setAttribute(name, attribute)."),
        (r"\.getInverse\s*\(", "OLD_MATRIX_INVERSE_API", "Matrix4.getInverse is obsolete.", "Use matrix.copy(source).invert() or source.clone().invert()."),
        (r"\bTHREE\.(?:OrbitControls|GLTFLoader|FBXLoader|OBJLoader|EffectComposer|RenderPass|ShaderPass|FontLoader|TextGeometry)\b", "ADDON_AS_CORE_GLOBAL", "This addon is not a Three.js core global in a normal r184 build.", "Bundle the addon locally or expose it explicitly; do not assume it exists on window.THREE."),
    ]
    for pattern, code, message, fix in deprecated_patterns:
        for match in matches(pattern)[:12]:
            _source_issue(issues, "error", code, message, line=_line_number(source, match.start()), evidence=_excerpt(source, match.start()), fix=fix)

    for match in matches(r"\bwindow\.onload\s*=\s*[A-Za-z_$][\w$]*\s*\(\s*\)"):
        _source_issue(
            issues,
            "error",
            "IMMEDIATE_ONLOAD_CALL",
            "window.onload is assigned the result of a function call instead of the function.",
            line=_line_number(source, match.start()),
            evidence=_excerpt(source, match.start()),
            fix="Use window.onload = init; or addEventListener('load', init).",
        )

    renderer_count = len(matches(r"new\s+THREE\.WebGLRenderer\s*\("))
    raf_count = len(matches(r"\brequestAnimationFrame\s*\("))
    animation_loop_count = len(matches(r"\.setAnimationLoop\s*\("))
    render_call_count = len(matches(r"\.render\s*\("))
    resize_listener = bool(re.search(r"(?:addEventListener\s*\(\s*['\"]resize|onresize\s*=)", source, re.IGNORECASE))
    set_size = bool(re.search(r"\.setSize\s*\(", source))
    perspective_camera = bool(re.search(r"new\s+THREE\.PerspectiveCamera\s*\(", source))
    updates_aspect = bool(re.search(r"\.aspect\s*=|updateProjectionMatrix\s*\(", source))

    if renderer_count == 0:
        _source_issue(issues, "warning", "NO_RENDERER_CONSTRUCTION_FOUND", "No literal new THREE.WebGLRenderer(...) call was found.", fix="Confirm that a renderer is created or that it is supplied by another local module.")
    elif renderer_count > 1:
        _source_issue(issues, "warning", "MULTIPLE_RENDERERS", f"Found {renderer_count} WebGLRenderer constructions; accidental duplicate renderers waste GPU memory.", fix="Use one renderer unless multiple independent canvases are intentional.")

    if render_call_count == 0:
        _source_issue(issues, "warning", "NO_RENDER_CALL_FOUND", "No obvious renderer.render(...) call was found.", fix="Render the active scene and camera from an animation loop or after state changes.")
    if raf_count > 1 and animation_loop_count > 0:
        _source_issue(issues, "warning", "MIXED_ANIMATION_LOOPS", "Both requestAnimationFrame and setAnimationLoop appear multiple times; duplicate loops can accelerate game logic and rendering.", fix="Use one authoritative animation loop.")
    if set_size and not resize_listener:
        _source_issue(issues, "warning", "NO_RESIZE_HANDLER", "The renderer is sized, but no window resize handler was found.", fix="On resize, update renderer size, camera aspect, and camera projection matrix.")
    if perspective_camera and resize_listener and not updates_aspect:
        _source_issue(issues, "warning", "CAMERA_ASPECT_NOT_UPDATED", "A PerspectiveCamera and resize handler exist, but no aspect/projection update was found.", fix="Set camera.aspect = width / height and call camera.updateProjectionMatrix().")

    loader_calls = matches(r"\b(?:GLTFLoader|TextureLoader|CubeTextureLoader|AudioLoader|FileLoader|ObjectLoader)\b[\s\S]{0,180}?\.load\s*\(")
    if loader_calls and not re.search(r"\.load\s*\([^;]{0,1000}?(?:=>|function)[^;]{0,1000}?(?:console\.error|onError|catch)", source, re.IGNORECASE | re.DOTALL):
        _source_issue(issues, "warning", "LOADER_ERRORS_NOT_HANDLED", "Asset loading is present, but no obvious loader error handling was found.", fix="Provide the loader onError callback and report the failing URL.")

    if re.search(r"\beval\s*\(|\bnew\s+Function\s*\(", source):
        match = re.search(r"\beval\s*\(|\bnew\s+Function\s*\(", source)
        _source_issue(issues, "warning", "DYNAMIC_CODE_EXECUTION", "Dynamic JavaScript evaluation makes debugging and security harder.", line=_line_number(source, match.start()) if match else None, fix="Use ordinary functions or data-driven dispatch instead.")

    if include_info:
        if not remote_refs:
            _source_issue(issues, "info", "OFFLINE_REFERENCES_OK", "No statically visible remote resource URLs were found.")
        if renderer_count == 1:
            _source_issue(issues, "info", "SINGLE_RENDERER", "Exactly one literal WebGLRenderer construction was found.")
        if raf_count + animation_loop_count == 1:
            _source_issue(issues, "info", "SINGLE_ANIMATION_LOOP", "Exactly one obvious animation-loop entry point was found.")

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda item: (severity_rank.get(item["severity"], 9), item.get("line", 10**9), item["code"]))
    counts = {level: sum(1 for item in issues if item["severity"] == level) for level in ("error", "warning", "info")}
    score = max(0, 100 - counts["error"] * 18 - counts["warning"] * 6)
    return {
        "success": counts["error"] == 0,
        "action": "threejs_source_audit",
        "path": display,
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "bytes": len(source.encode("utf-8")),
        "lines": source.count("\n") + 1,
        "three_revision_expected": "184",
        "health_score": score,
        "counts": counts,
        "facts": {
            "webgl_renderer_constructions": renderer_count,
            "render_calls": render_call_count,
            "request_animation_frame_calls": raf_count,
            "set_animation_loop_calls": animation_loop_count,
            "local_asset_references_checked": checked_assets,
            "missing_local_assets": len(missing_assets),
            "remote_references": len(remote_refs),
        },
        "issues": issues[:MAX_SOURCE_ISSUES],
        "next_step": "Fix source-level errors, then call threejs_open_debug on this path and run threejs_audit.",
    }


# This bootstrap runs before the project's first script.  Keep it self-contained
# and avoid any dependency on application globals other than preloaded THREE.
_DEBUG_BOOTSTRAP = r"""(()=>{if(globalThis.__DARKSTAR_THREE_DEBUG__?.version>=2)return;const T=globalThis.THREE;const cap=(a,v,max=120)=>{a.push(v);if(a.length>max)a.splice(0,a.length-max)};const d={version:2,installedAt:Date.now(),threeRevision:String(T?.REVISION||''),renderers:[],scenes:[],cameras:[],mixers:[],console:[],lastRenderer:null,lastScene:null,lastCamera:null,renderCount:0,renderErrors:[],frameTimes:[],rafCalls:0,animationLoops:0,loading:{started:[],ended:[],errors:[],pending:[]},resources:[],errors:[],contextEvents:[]};globalThis.__DARKSTAR_THREE_DEBUG__=d;for(const level of ['warn','error']){const original=console[level]?.bind(console);if(!original)continue;console[level]=(...values)=>{try{cap(d.console,{time:Date.now(),level,message:values.map(v=>{try{return typeof v==='string'?v:JSON.stringify(v)}catch(_){return String(v)}}).join(' ').slice(0,1600)},100)}catch(_){}return original(...values)}}const add=(a,v)=>{if(v&&!a.includes(v))a.push(v)};const err=(kind,e)=>cap(d.errors,{time:Date.now(),kind,message:String(e?.message||e||''),stack:String(e?.stack||'').slice(0,1200)});addEventListener('error',e=>{if(e.target&&e.target!==globalThis)cap(d.resources,{time:Date.now(),kind:'resource-error',tag:String(e.target.tagName||''),url:String(e.target.src||e.target.href||'').slice(0,500)});else err('error',e.error||e.message)},true);addEventListener('unhandledrejection',e=>err('unhandledrejection',e.reason));addEventListener('webglcontextlost',e=>cap(d.contextEvents,{time:Date.now(),type:'lost',canvas:{width:e.target?.width||0,height:e.target?.height||0}}),true);addEventListener('webglcontextrestored',e=>cap(d.contextEvents,{time:Date.now(),type:'restored'}),true);const oraf=globalThis.requestAnimationFrame?.bind(globalThis);if(oraf){let last=0;globalThis.requestAnimationFrame=(cb)=>{d.rafCalls++;return oraf((t)=>{if(last){cap(d.frameTimes,t-last,600)}last=t;try{return cb(t)}catch(e){err('raf-callback',e);throw e}})}}const wrapCtor=(name,onCreate)=>{const C=T?.[name];if(typeof C!=='function'||C.__darkstarWrapped)return;let P;P=new Proxy(C,{construct(target,args,newTarget){const instance=Reflect.construct(target,args,newTarget===P?target:newTarget);try{onCreate(instance,args)}catch(e){err('instrument-'+name,e)}return instance}});try{Object.defineProperty(P,'__darkstarWrapped',{value:true});Object.defineProperty(P,'name',{value:C.name})}catch(_){}T[name]=P};const instrumentRenderer=(r)=>{add(d.renderers,r);d.lastRenderer=r;const originalRender=r.render;if(typeof originalRender==='function'&&!originalRender.__darkstarWrapped){const wrapped=function(scene,camera){d.lastRenderer=this;d.lastScene=scene||d.lastScene;d.lastCamera=camera||d.lastCamera;add(d.scenes,scene);add(d.cameras,camera);d.renderCount++;const started=performance.now();try{return originalRender.call(this,scene,camera)}catch(e){cap(d.renderErrors,{time:Date.now(),message:String(e?.message||e),stack:String(e?.stack||'').slice(0,1200)});throw e}finally{this.__darkstarLastRenderMs=performance.now()-started;this.__darkstarLastScene=scene;this.__darkstarLastCamera=camera}};wrapped.__darkstarWrapped=true;r.render=wrapped}const originalLoop=r.setAnimationLoop;if(typeof originalLoop==='function'&&!originalLoop.__darkstarWrapped){const wrapped=function(cb){this.__darkstarAnimationLoop=cb||null;d.animationLoops=d.renderers.filter(x=>x.__darkstarAnimationLoop).length;return originalLoop.call(this,cb)};wrapped.__darkstarWrapped=true;r.setAnimationLoop=wrapped}};wrapCtor('WebGLRenderer',instrumentRenderer);wrapCtor('WebGPURenderer',instrumentRenderer);wrapCtor('Scene',s=>add(d.scenes,s));for(const n of ['PerspectiveCamera','OrthographicCamera','ArrayCamera','CubeCamera'])wrapCtor(n,c=>add(d.cameras,c));wrapCtor('AnimationMixer',m=>add(d.mixers,m));const lm=T?.DefaultLoadingManager;if(lm&&!lm.__darkstarWrapped){for(const [name,bucket] of [['itemStart','started'],['itemEnd','ended'],['itemError','errors']]){const original=lm[name];if(typeof original!=='function')continue;lm[name]=function(url){const value=String(url||'').slice(0,800);cap(d.loading[bucket],{time:Date.now(),url:value});if(name==='itemStart'&&!d.loading.pending.includes(value))d.loading.pending.push(value);if(name!=='itemStart')d.loading.pending=d.loading.pending.filter(x=>x!==value);return original.apply(this,arguments)}}lm.__darkstarWrapped=true}d.ready=true})()"""


def _instrumented_copy_path(original: Path) -> Path:
    return original.with_name(f".{original.stem}.darkstar-three-debug{original.suffix.lower()}")


def _inject_debug_bootstrap(source: str, original_display: str) -> str:
    marker = f"<!-- {DEBUG_FILE_MARKER}: {html.escape(original_display, quote=True)} -->"
    doctype = re.match(r"\s*<!doctype\s+html[^>]*>", source, re.IGNORECASE)
    if doctype:
        source = source[:doctype.end()] + marker + source[doctype.end():]
    else:
        source = marker + source
    script = f"<script>{_DEBUG_BOOTSTRAP}</script>"
    head = re.search(r"<head\b[^>]*>", source, re.IGNORECASE)
    if head:
        return source[:head.end()] + script + source[head.end():]
    html_tag = re.search(r"<html\b[^>]*>", source, re.IGNORECASE)
    if html_tag:
        return source[:html_tag.end()] + "<head>" + script + "</head>" + source[html_tag.end():]
    return script + source


def _open_debug(raw_path: Any, kwargs: dict[str, Any], timer_ms: int | None) -> dict[str, Any]:
    root, original, display = _resolve_html(raw_path, kwargs)
    source = _read_html(original)
    generated = _instrumented_copy_path(original)
    if generated.exists():
        existing = _read_html(generated)
        if DEBUG_FILE_MARKER not in existing[:1000]:
            raise ValueError(f"Refusing to overwrite non-debug file: {generated.relative_to(root).as_posix()}")
    instrumented = _inject_debug_bootstrap(source, display)
    temporary = generated.with_name(generated.name + f".tmp-{os.getpid()}")
    try:
        temporary.write_bytes(instrumented.encode("utf-8"))
        os.replace(temporary, generated)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    request: dict[str, Any] = {
        "__darkstarAction": "browser_control",
        "action": "open",
        "path": generated.relative_to(root).as_posix(),
        "snapshot_mode": "all",
        "max_elements": 160,
    }
    if timer_ms is not None:
        request["wait_ms"] = timer_ms
    return request


def _cleanup_debug(raw_path: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    root = _workspace_root(kwargs)
    removed: list[str] = []
    if raw_path:
        _root, original, _display = _resolve_html(raw_path, kwargs)
        candidates = [_instrumented_copy_path(original)]
    else:
        candidates = []
        visited = 0
        excluded = {".git", "node_modules", ".venv", "venv", "dist", "build", "coverage"}
        for directory, names, files in os.walk(root):
            names[:] = [name for name in names if name not in excluded and not Path(directory, name).is_symlink()]
            visited += len(names) + len(files)
            if visited > 50_000:
                break
            for name in files:
                if name.endswith((".darkstar-three-debug.html", ".darkstar-three-debug.htm")) and name.startswith("."):
                    candidates.append(Path(directory, name))
    for candidate in candidates:
        if not _is_within(root, candidate) or not candidate.exists() or candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            raw_prefix = candidate.open("rb").read(4096)
            prefix = raw_prefix.decode("utf-8-sig", errors="strict")
        except (OSError, UnicodeError):
            continue
        if DEBUG_FILE_MARKER not in prefix:
            continue
        candidate.unlink()
        removed.append(candidate.relative_to(root).as_posix())
    return {"success": True, "action": "threejs_cleanup_debug", "removed": removed, "removed_count": len(removed)}


_DEBUG_STATUS_SCRIPT = r"""
const T=globalThis.THREE;const d=globalThis.__DARKSTAR_THREE_DEBUG__;const own=[];for(const k of Object.getOwnPropertyNames(globalThis)){let v;try{v=globalThis[k]}catch(_){continue}if(v?.isScene||v?.isCamera||(v?.domElement&&v?.info&&typeof v.render==='function'))own.push({name:k,type:v.type||v.constructor?.name||typeof v})}return {page:{title:document.title,url:location.href,readyState:document.readyState,viewport:[innerWidth,innerHeight],devicePixelRatio},three:{available:!!T,revision:String(T?.REVISION||''),webglRenderer:typeof T?.WebGLRenderer==='function'},instrumentation:{installed:!!d,version:d?.version||null,ready:d?.ready===true,renderers:d?.renderers?.length||0,scenes:d?.scenes?.length||0,cameras:d?.cameras?.length||0,mixers:d?.mixers?.length||0,renderCount:d?.renderCount||0,rafCalls:d?.rafCalls||0,animationLoops:d?.animationLoops||0,loadingPending:d?.loading?.pending||[],runtimeErrors:(d?.errors||[]).slice(-10),renderErrors:(d?.renderErrors||[]).slice(-10),contextEvents:(d?.contextEvents||[]).slice(-10),console:(d?.console||[]).slice(-20)},discoverableGlobals:own.slice(0,40),guidance:!d?'Reopen the original HTML with action threejs_open_debug before a deep audit.':null}
"""


# The live audit deliberately returns a prioritized, bounded report rather than
# dumping entire Three.js objects into model context.
_LIVE_AUDIT_TEMPLATE = r"""
const OPT=__OPTIONS__;
const T=globalThis.THREE,d=globalThis.__DARKSTAR_THREE_DEBUG__;
const finite=n=>typeof n==='number'&&Number.isFinite(n),round=(n,p=3)=>finite(n)?Number(n.toFixed(p)):n;
const clean=(v,n=300)=>String(v??'').replace(/\s+/g,' ').trim().slice(0,n);
const arr=v=>Array.isArray(v)?v:[];
const issues=[];const add=(severity,code,message,evidence,fix)=>{if(issues.length>=80)return;const x={severity,code,message};if(evidence!==undefined&&evidence!==null&&evidence!=='')x.evidence=evidence;if(fix)x.fix=fix;issues.push(x)};
const unique=a=>Array.from(new Set(a.filter(Boolean)));
const renderers=[],scenes=[],cameras=[],mixers=[];
const push=(a,v)=>{if(v&&!a.includes(v))a.push(v)};
for(const v of arr(d?.renderers))push(renderers,v);for(const v of arr(d?.scenes))push(scenes,v);for(const v of arr(d?.cameras))push(cameras,v);for(const v of arr(d?.mixers))push(mixers,v);
const visited=new WeakSet();let scanned=0;
const scan=(v,depth=0)=>{if(!v||(typeof v!=='object'&&typeof v!=='function')||visited.has(v)||scanned>1800||depth>2)return;visited.add(v);scanned++;try{if(v.isScene)push(scenes,v);if(v.isCamera)push(cameras,v);if(v.domElement&&v.info&&typeof v.render==='function')push(renderers,v);if(v._root&&Array.isArray(v._actions))push(mixers,v)}catch(_){}if(depth>=2)return;let keys=[];try{keys=Object.keys(v).slice(0,80)}catch(_){return}for(const k of keys){if(['window','self','top','parent','frames','document','THREE'].includes(k))continue;let child;try{child=v[k]}catch(_){continue}if(child instanceof Node)continue;scan(child,depth+1)}};
for(const k of Object.getOwnPropertyNames(globalThis).slice(0,700)){let v;try{v=globalThis[k]}catch(_){continue}scan(v,0)}
if(d?.lastRenderer)push(renderers,d.lastRenderer);if(d?.lastScene)push(scenes,d.lastScene);if(d?.lastCamera)push(cameras,d.lastCamera);
const activeRenderer=d?.lastRenderer||renderers[0]||null,activeScene=d?.lastScene||scenes[0]||null,activeCamera=d?.lastCamera||cameras[0]||null;
const canvases=Array.from(document.querySelectorAll('canvas')).map((c,i)=>{const r=c.getBoundingClientRect(),s=getComputedStyle(c),top=document.elementFromPoint(Math.max(0,Math.min(innerWidth-1,r.left+r.width/2)),Math.max(0,Math.min(innerHeight-1,r.top+r.height/2)));return {index:i,id:c.id||'',class:clean(c.className,100),buffer:[c.width,c.height],css:[round(r.width,1),round(r.height,1)],position:[round(r.left,1),round(r.top,1)],display:s.display,visibility:s.visibility,opacity:s.opacity,connected:c.isConnected,contextLost:!!c.getContext('webgl2')?.isContextLost?.()||!!c.getContext('webgl')?.isContextLost?.(),topElement:top?clean(top.tagName.toLowerCase()+(top.id?'#'+top.id:''),100):null}});
if(!T)add('critical','THREE_MISSING','window.THREE is unavailable.','The packaged runtime did not initialize.','Inspect the Browser Control console and preload configuration.');
else if(String(T.REVISION)!=='184')add('warning','THREE_REVISION_MISMATCH','The page is not using the packaged Three.js revision 184.',String(T.REVISION),'Remove duplicate Three.js core scripts or imports.');
if(!d)add('warning','DEBUG_HOOKS_MISSING','Live constructor/render hooks are not installed.','Scene variables declared with top-level const may be undiscoverable.','Reopen the original file with threejs_open_debug, then rerun this audit.');
if(!canvases.length)add('critical','NO_CANVAS','The page contains no canvas element.',null,'Create a renderer and attach renderer.domElement to the document.');
for(const c of canvases){if(c.css[0]<1||c.css[1]<1)add('critical','ZERO_SIZE_CANVAS','A canvas has zero CSS size.',c,'Give the canvas or its container nonzero width and height.');if(c.buffer[0]<1||c.buffer[1]<1)add('critical','ZERO_BUFFER_CANVAS','A canvas has a zero drawing-buffer dimension.',c,'Call renderer.setSize with nonzero dimensions.');if(c.display==='none'||c.visibility==='hidden'||Number(c.opacity)===0)add('critical','HIDDEN_CANVAS','A render canvas is hidden by CSS.',c,'Remove display:none, visibility:hidden, or zero opacity.');if(c.contextLost)add('critical','WEBGL_CONTEXT_LOST','A canvas reports a lost WebGL context.',c,'Release GPU resources, reduce memory pressure, and recreate the renderer if needed.');if(c.topElement&&c.topElement!=='canvas'&&!c.topElement.startsWith('canvas#'))add('warning','CANVAS_OBSCURED','Another element is above the center of the canvas.',c.topElement,'Inspect overlays and z-index; hide unintended full-screen blockers.');}
if(!renderers.length)add('critical','NO_RENDERER_FOUND','No live Three.js renderer could be discovered.',null,d?'Ensure the renderer has rendered at least one frame.':'Use threejs_open_debug so renderer construction is instrumented.');
if(renderers.length>1)add('warning','MULTIPLE_RENDERERS',`Discovered ${renderers.length} renderers.`,null,'Dispose unintended renderers and keep one animation loop unless multiple canvases are intentional.');if((d?.animationLoops||0)>1)add('warning','MULTIPLE_ANIMATION_LOOPS',`Instrumentation observed ${d.animationLoops} active renderer animation loops.`,null,'Keep one authoritative loop unless independent renderers are intentional.');
if(!scenes.length)add('critical','NO_SCENE_FOUND','No Three.js Scene could be discovered.',null,'Use threejs_open_debug or expose the scene through window.__DARKSTAR_GAME_DEBUG__.');
if(!cameras.length)add('critical','NO_CAMERA_FOUND','No Three.js camera could be discovered.',null,'Create and render with an active camera.');
const rendererReports=[];
for(const [i,r] of renderers.slice(0,4).entries()){let size=null,buffer=null,context=null;try{const v=new T.Vector2();r.getSize(v);size=[round(v.x,1),round(v.y,1)];const b=new T.Vector2();r.getDrawingBufferSize(b);buffer=[round(b.x,1),round(b.y,1)]}catch(_){}try{const gl=r.getContext?.();const attrs=gl?.getContextAttributes?.();context={version:(typeof WebGL2RenderingContext!=='undefined'&&gl instanceof WebGL2RenderingContext)?2:1,attributes:attrs||null,maxTextureSize:gl?.getParameter?.(gl.MAX_TEXTURE_SIZE)||null,maxCubeMapSize:gl?.getParameter?.(gl.MAX_CUBE_MAP_TEXTURE_SIZE)||null,maxVertexAttribs:gl?.getParameter?.(gl.MAX_VERTEX_ATTRIBS)||null,maxSamples:gl?.MAX_SAMPLES?gl.getParameter(gl.MAX_SAMPLES):null}}catch(_){}const info=r.info||{};rendererReports.push({index:i,type:r.constructor?.name||'Renderer',size,buffer,pixelRatio:round(r.getPixelRatio?.(),3),outputColorSpace:String(r.outputColorSpace||''),toneMapping:r.toneMapping,exposure:round(r.toneMappingExposure,3),shadowMap:{enabled:!!r.shadowMap?.enabled,type:r.shadowMap?.type},xr:!!r.xr?.enabled,localClipping:!!r.localClippingEnabled,lastRenderMs:round(r.__darkstarLastRenderMs,3),info:{autoReset:info.autoReset,memory:{geometries:info.memory?.geometries||0,textures:info.memory?.textures||0},render:{calls:info.render?.calls||0,triangles:info.render?.triangles||0,points:info.render?.points||0,lines:info.render?.lines||0,frame:info.render?.frame||0},programs:Array.isArray(info.programs)?info.programs.length:null},capabilities:{isWebGL2:!!r.capabilities?.isWebGL2,maxTextures:r.capabilities?.maxTextures,maxVertexTextures:r.capabilities?.maxVertexTextures,maxTextureSize:r.capabilities?.maxTextureSize,precision:r.capabilities?.precision},context});if(size&&(size[0]<1||size[1]<1))add('critical','RENDERER_ZERO_SIZE','A renderer reports zero size.',rendererReports.at(-1),'Call renderer.setSize after the container has dimensions.');if((r.getPixelRatio?.()||1)>2.25)add('warning','HIGH_PIXEL_RATIO','Renderer pixel ratio exceeds 2.25 and can severely increase fill cost.',{pixelRatio:r.getPixelRatio?.()},'Clamp pixel ratio, for example Math.min(devicePixelRatio, 2).');if((info.render?.calls||0)>600)add('warning','HIGH_DRAW_CALLS','The latest frame exceeds 600 draw calls.',{calls:info.render.calls},'Merge static geometry, use instancing, reduce materials, and cull unseen objects.');if((info.render?.triangles||0)>3000000)add('warning','HIGH_TRIANGLE_COUNT','The latest frame exceeds three million triangles.',{triangles:info.render.triangles},'Reduce model density, add LODs, or cull distant objects.');if((info.render?.calls||0)===0&&(d?.renderCount||0)>0)add('warning','ZERO_DRAW_CALLS','The renderer ran, but the latest frame has zero draw calls.',rendererReports.at(-1),'Verify scene visibility, camera framing, layers, and materials.');}
if(OPT.compileShaders&&activeRenderer&&activeScene&&activeCamera){try{const compile=activeRenderer.compileAsync?activeRenderer.compileAsync(activeScene,activeCamera):Promise.resolve(activeRenderer.compile?.(activeScene,activeCamera));await Promise.race([compile,new Promise((_,reject)=>setTimeout(()=>reject(new Error('compile timeout')),3500))])}catch(e){add('error','SHADER_COMPILE_FAILED','Scene shader precompilation failed.',clean(e?.message||e,500),'Inspect custom shaders, defines, attributes, and Browser Control console diagnostics.')}}
const typeCounts={},objects=[],geometries=new Set(),materials=new Set(),textures=new Set(),lights=[],meshes=[],sprites=[],lines=[],points=[],skinned=[],instanced=[];
const mapNames=['map','alphaMap','aoMap','bumpMap','displacementMap','emissiveMap','envMap','lightMap','metalnessMap','normalMap','roughnessMap','specularMap','gradientMap','matcap'];
const addMaterial=m=>{if(!m)return;for(const x of (Array.isArray(m)?m:[m])){if(!x)continue;materials.add(x);for(const n of mapNames)if(x[n]?.isTexture)textures.add(x[n]);if(x.uniforms)for(const u of Object.values(x.uniforms))if(u?.value?.isTexture)textures.add(u.value)}};
const finiteVector=(v,n)=>{if(!v)return true;for(const k of n)if(!finite(v[k]))return false;return true};
for(const [si,s] of scenes.slice(0,6).entries()){try{s.updateMatrixWorld?.(true)}catch(e){add('error','MATRIX_UPDATE_FAILED','Scene matrix update threw an exception.',clean(e?.message||e,400),'Fix invalid transforms or custom Object3D overrides.')}s.traverse?.(o=>{typeCounts[o.type||o.constructor?.name||'Object3D']=(typeCounts[o.type||o.constructor?.name||'Object3D']||0)+1;if(o.isMesh)meshes.push(o);if(o.isLight)lights.push(o);if(o.isSprite)sprites.push(o);if(o.isLine)lines.push(o);if(o.isPoints)points.push(o);if(o.isSkinnedMesh)skinned.push(o);if(o.isInstancedMesh)instanced.push(o);if(o.geometry?.isBufferGeometry)geometries.add(o.geometry);addMaterial(o.material);if(!finiteVector(o.position,['x','y','z'])||!finiteVector(o.scale,['x','y','z'])||!finiteVector(o.quaternion,['x','y','z','w']))add('critical','NONFINITE_TRANSFORM','An object has NaN or Infinity in its transform.',{name:o.name||'',uuid:o.uuid,type:o.type,position:o.position?.toArray?.(),scale:o.scale?.toArray?.(),quaternion:o.quaternion?.toArray?.()},'Trace the calculation producing the invalid transform and guard divisions/normalization.');if(Math.abs(o.scale?.x||0)<1e-8||Math.abs(o.scale?.y||0)<1e-8||Math.abs(o.scale?.z||0)<1e-8)add('warning','ZERO_SCALE','An object has an effectively zero scale and cannot render normally.',{name:o.name||'',uuid:o.uuid,type:o.type,scale:o.scale?.toArray?.()},'Set nonzero scale or hide the object intentionally.');if(objects.length<OPT.objectLimit)objects.push({scene:si,name:o.name||'',uuid:o.uuid,type:o.type,visible:o.visible,renderOrder:o.renderOrder,layers:o.layers?.mask,position:o.position?.toArray?.().map(x=>round(x)),rotation:o.rotation?[round(o.rotation.x),round(o.rotation.y),round(o.rotation.z),o.rotation.order]:null,scale:o.scale?.toArray?.().map(x=>round(x)),children:o.children?.length||0,geometry:o.geometry?.uuid||null,material:Array.isArray(o.material)?o.material.map(m=>m?.uuid):o.material?.uuid||null,castShadow:!!o.castShadow,receiveShadow:!!o.receiveShadow})})}
const geometryReports=[];let totalVertices=0,totalIndices=0,invalidGeometryValues=0;
const deep=OPT.detail==='deep',scanCap=deep?250000:30000;
for(const [i,g] of Array.from(geometries).slice(0,OPT.objectLimit).entries()){const attrs={};for(const [name,a] of Object.entries(g.attributes||{})){attrs[name]={count:a.count,itemSize:a.itemSize,normalized:!!a.normalized,arrayType:a.array?.constructor?.name||'',bytes:a.array?.byteLength||0};if(name==='position')totalVertices+=a.count||0;const data=a.array||[];const step=Math.max(1,Math.ceil(data.length/scanCap));for(let j=0;j<data.length;j+=step){if(!finite(Number(data[j]))){invalidGeometryValues++;add('critical','NONFINITE_GEOMETRY_ATTRIBUTE','A geometry attribute contains NaN or Infinity.',{geometry:g.uuid,attribute:name,index:j,value:String(data[j])},'Fix geometry generation and validate all numeric inputs.');break}}}if(!g.attributes?.position)add('error','GEOMETRY_MISSING_POSITION','A render geometry has no position attribute.',{uuid:g.uuid,name:g.name||''},'Set a valid BufferAttribute named position.');if((g.attributes?.position?.count||0)===0)add('warning','EMPTY_GEOMETRY','A geometry has zero vertices.',{uuid:g.uuid,name:g.name||''},'Populate or remove the geometry.');const index=g.index;if(index){totalIndices+=index.count||0;let max=-1;const data=index.array||[];const step=Math.max(1,Math.ceil(data.length/scanCap));for(let j=0;j<data.length;j+=step)max=Math.max(max,Number(data[j])||0);if(max>=(g.attributes?.position?.count||0))add('critical','INDEX_OUT_OF_RANGE','A geometry index may reference a missing vertex.',{uuid:g.uuid,maxSampledIndex:max,positionCount:g.attributes?.position?.count||0},'Regenerate the index or position attribute with matching counts.')}let bounds=null;try{if(!g.boundingBox)g.computeBoundingBox?.();if(!g.boundingSphere)g.computeBoundingSphere?.();bounds={box:g.boundingBox?{min:g.boundingBox.min.toArray().map(x=>round(x)),max:g.boundingBox.max.toArray().map(x=>round(x))}:null,sphere:g.boundingSphere?{center:g.boundingSphere.center.toArray().map(x=>round(x)),radius:round(g.boundingSphere.radius)}:null}}catch(e){add('error','BOUNDING_VOLUME_FAILED','Computing geometry bounds failed.',{uuid:g.uuid,error:clean(e?.message||e,300)},'Remove nonfinite attributes and ensure valid position data.')}geometryReports.push({index:i,uuid:g.uuid,name:g.name||'',attributes:attrs,indexCount:index?.count||0,drawRange:g.drawRange,bounds})}
const materialReports=[];let pbrCount=0,transparentDepthWrites=0;
for(const [i,m] of Array.from(materials).slice(0,OPT.objectLimit).entries()){if(m.isMeshStandardMaterial||m.isMeshPhysicalMaterial||m.isMeshLambertMaterial||m.isMeshPhongMaterial||m.isToonMaterial)pbrCount++;if(m.transparent&&m.depthWrite)transparentDepthWrites++;const maps={};for(const n of mapNames)if(m[n]?.isTexture)maps[n]=m[n].uuid;materialReports.push({index:i,uuid:m.uuid,name:m.name||'',type:m.type,visible:m.visible,transparent:!!m.transparent,opacity:round(m.opacity),depthTest:!!m.depthTest,depthWrite:!!m.depthWrite,side:m.side,wireframe:!!m.wireframe,color:m.color?.getHexString?.(),emissive:m.emissive?.getHexString?.(),maps,uniformCount:m.uniforms?Object.keys(m.uniforms).length:0})}
if(pbrCount&&!lights.length&&!activeScene?.environment){add('warning','LIT_MATERIALS_WITHOUT_LIGHTS',`${pbrCount} light-dependent materials were found, but no lights or scene environment were discovered.`,null,'Add an AmbientLight/DirectionalLight or an environment map, or use an unlit material.');}
if(transparentDepthWrites)add('warning','TRANSPARENT_DEPTH_WRITE',`${transparentDepthWrites} transparent materials still write depth and may cause ordering artifacts.`,null,'Set depthWrite=false when appropriate for blended transparent surfaces.');
const textureReports=[];let estimatedTextureBytes=0,unreadyTextures=0;
for(const [i,t] of Array.from(textures).slice(0,OPT.objectLimit).entries()){const img=t.image||t.source?.data;const width=Number(img?.videoWidth||img?.naturalWidth||img?.width||0),height=Number(img?.videoHeight||img?.naturalHeight||img?.height||0);const ready=!!(width&&height);if(!ready){unreadyTextures++;add('warning','TEXTURE_NOT_READY','A referenced texture has no loaded dimensions.',{uuid:t.uuid,name:t.name||'',source:clean(img?.src||t.source?.data?.src||'',300)},'Check the asset path and loader error callback.')}if(width>8192||height>8192)add('warning','OVERSIZED_TEXTURE','A texture exceeds 8192 pixels on one axis.',{uuid:t.uuid,width,height},'Downscale or use tiled/streamed assets.');estimatedTextureBytes+=width*height*4;textureReports.push({index:i,uuid:t.uuid,name:t.name||'',size:[width,height],ready,colorSpace:String(t.colorSpace||''),flipY:t.flipY,generateMipmaps:t.generateMipmaps,minFilter:t.minFilter,magFilter:t.magFilter,wrapS:t.wrapS,wrapT:t.wrapT,source:clean(img?.currentSrc||img?.src||'',300)})}
if(estimatedTextureBytes>512*1024*1024)add('warning','HIGH_TEXTURE_MEMORY_ESTIMATE','Uncompressed texture estimate exceeds 512 MiB.',{estimatedBytes:estimatedTextureBytes},'Downscale textures, reuse maps, and consider KTX2 compression.');const lightReports=unique(lights).slice(0,OPT.objectLimit).map(l=>({name:l.name||'',uuid:l.uuid,type:l.type,color:l.color?.getHexString?.(),intensity:round(l.intensity),castShadow:!!l.castShadow,shadowMapSize:l.shadow?.mapSize?[l.shadow.mapSize.x,l.shadow.mapSize.y]:null}));for(const l of unique(lights))if(!finite(l.intensity)||l.intensity<0)add('error','INVALID_LIGHT_INTENSITY','A light has a negative or nonfinite intensity.',{name:l.name||'',type:l.type,intensity:l.intensity},'Use a finite nonnegative light intensity.');
const cameraReports=[];
for(const [i,c] of cameras.slice(0,OPT.objectLimit).entries()){const report={index:i,name:c.name||'',uuid:c.uuid,type:c.type,near:round(c.near),far:round(c.far),zoom:round(c.zoom),aspect:round(c.aspect),position:c.position?.toArray?.().map(x=>round(x)),layers:c.layers?.mask};cameraReports.push(report);if(!finite(c.near)||!finite(c.far)||c.near<=0||c.far<=c.near)add('critical','INVALID_CAMERA_CLIP','A camera has invalid near/far clipping planes.',report,'Use finite values with 0 < near < far.');const canvas=activeRenderer?.domElement;if(c.isPerspectiveCamera&&canvas){const rect=canvas.getBoundingClientRect(),expected=rect.height?rect.width/rect.height:0;if(expected&&Math.abs((c.aspect||0)-expected)/expected>.03)add('warning','CAMERA_ASPECT_MISMATCH','Perspective camera aspect does not match the canvas.',{cameraAspect:round(c.aspect),canvasAspect:round(expected)},'On resize, set camera.aspect = width / height and call updateProjectionMatrix().')}}
let frustumSummary=null;if(activeScene&&activeCamera&&T?.Frustum&&T?.Matrix4){try{activeScene.updateMatrixWorld(true);activeCamera.updateMatrixWorld(true);const matrix=new T.Matrix4().multiplyMatrices(activeCamera.projectionMatrix,activeCamera.matrixWorldInverse);const frustum=new T.Frustum().setFromProjectionMatrix(matrix);let renderable=0,outside=0;const outsideSamples=[];activeScene.traverse(o=>{if(!(o.isMesh||o.isLine||o.isPoints||o.isSprite)||o.visible===false)return;renderable++;try{if(!frustum.intersectsObject(o)){outside++;if(outsideSamples.length<12)outsideSamples.push({name:o.name||'',uuid:o.uuid,type:o.type})}}catch(_){}});frustumSummary={renderable,outside,outsideSamples};if(renderable>0&&outside===renderable)add('critical','ALL_OBJECTS_OUTSIDE_FRUSTUM','Every discovered renderable object is outside the active camera frustum.',frustumSummary,'Reposition/orient the camera or objects and verify near/far planes.');else if(renderable>0&&outside/renderable>.9)add('warning','MOST_OBJECTS_OUTSIDE_FRUSTUM','More than 90% of renderable objects are outside the camera frustum.',frustumSummary,'Verify camera framing and object world transforms.')}catch(e){add('warning','FRUSTUM_CHECK_FAILED','Camera-frustum analysis failed.',clean(e?.message||e,300),'Verify camera and world matrices.')}}
const resources=performance.getEntriesByType?.('resource')?.slice(-100).map(r=>({name:clean(r.name,300),type:r.initiatorType,duration:round(r.duration),transferSize:r.transferSize||0,decodedBodySize:r.decodedBodySize||0}))||[];const failedResources=arr(d?.resources).slice(-30);const loading={pending:arr(d?.loading?.pending).slice(0,30),errors:arr(d?.loading?.errors).slice(-30),resourceErrors:failedResources};if(loading.pending.length)add('warning','ASSETS_STILL_LOADING',`${loading.pending.length} assets remain pending.`,loading.pending.slice(0,12),'Wait for explicit readiness or fix stalled asset paths.');if(loading.errors.length||failedResources.length)add('error','ASSET_LOAD_FAILURES','The debug hook observed asset-loading failures.',{loadingErrors:loading.errors.slice(-10),resourceErrors:failedResources.slice(-10)},'Correct the reported URL/path and retain loader error callbacks.');
const runtimeErrors=arr(d?.errors).slice(-20),renderErrors=arr(d?.renderErrors).slice(-20),contextEvents=arr(d?.contextEvents).slice(-20),consoleMessages=arr(d?.console).slice(-30);if(consoleMessages.some(x=>x.level==='error'))add('error','CONSOLE_ERRORS','The page emitted console errors.',consoleMessages.filter(x=>x.level==='error').slice(-8),'Fix the first console error, then rerun the audit.');else if(consoleMessages.some(x=>x.level==='warn'))add('warning','CONSOLE_WARNINGS','The page emitted console warnings.',consoleMessages.filter(x=>x.level==='warn').slice(-8),'Review warnings for deprecated APIs, shader issues, and invalid values.');if(runtimeErrors.length)add('error','RUNTIME_EXCEPTIONS','Runtime exceptions were captured by the debug hook.',runtimeErrors.slice(-8),'Fix the first exception before addressing downstream symptoms.');if(renderErrors.length)add('critical','RENDER_EXCEPTIONS','renderer.render threw an exception.',renderErrors.slice(-8),'Fix the first render exception and rerun the audit.');if(contextEvents.some(x=>x.type==='lost'))add('critical','CONTEXT_LOSS_RECORDED','A WebGL context-loss event was recorded.',contextEvents,'Dispose resources and reduce GPU memory pressure.');
const debugState=globalThis.__DARKSTAR_GAME_DEBUG__;let gameDebug=null;if(debugState!==undefined){try{const text=JSON.stringify(debugState);gameDebug=text.length<=5000?JSON.parse(text):{truncated:true,preview:text.slice(0,5000)}}catch(_){gameDebug={unserializable:true,type:typeof debugState}}}
const severityWeight={critical:28,error:16,warning:5,info:0};let health=100;for(const x of issues)health-=severityWeight[x.severity]||0;health=Math.max(0,Math.min(100,health));const rank={critical:0,error:1,warning:2,info:3};issues.sort((a,b)=>(rank[a.severity]??9)-(rank[b.severity]??9)||a.code.localeCompare(b.code));const status=issues.some(x=>x.severity==='critical')?'broken':issues.some(x=>x.severity==='error')?'failing':issues.some(x=>x.severity==='warning')?'needs_attention':'healthy';
const report={success:!issues.some(x=>x.severity==='critical'||x.severity==='error'),action:'threejs_audit',status,healthScore:health,page:{title:document.title,url:location.href,readyState:document.readyState,viewport:[innerWidth,innerHeight],devicePixelRatio},three:{available:!!T,revision:String(T?.REVISION||''),instrumented:!!d,debugVersion:d?.version||null},summary:{renderers:renderers.length,scenes:scenes.length,cameras:cameras.length,objects:Object.values(typeCounts).reduce((a,b)=>a+b,0),meshes:unique(meshes).length,lights:unique(lights).length,materials:materials.size,geometries:geometries.size,textures:textures.size,vertices:totalVertices,indices:totalIndices,estimatedTextureBytes,skinnedMeshes:unique(skinned).length,instancedMeshes:unique(instanced).length,sprites:unique(sprites).length,lines:unique(lines).length,points:unique(points).length,renderCount:d?.renderCount||0,rafCalls:d?.rafCalls||0,animationLoops:d?.animationLoops||0},issues:issues.slice(0,80),renderers:rendererReports,canvases,cameras:cameraReports,lights:lightReports,frustum:frustumSummary,objects:OPT.detail==='summary'?objects.slice(0,8):objects,geometries:OPT.detail==='deep'?geometryReports:geometryReports.slice(0,12),materials:OPT.detail==='deep'?materialReports:materialReports.slice(0,12),textures:OPT.detail==='deep'?textureReports:textureReports.slice(0,12),loading,resources:OPT.detail==='deep'?resources:resources.slice(-25),runtime:{errors:runtimeErrors,renderErrors,contextEvents,console:consoleMessages},gameDebug,nextActions:issues.slice(0,8).map(x=>x.fix).filter(Boolean)};const trimKeys=['objects','geometries','materials','textures','resources'];let trimmed=false;while(JSON.stringify(report).length>22000){let changed=false;for(const key of trimKeys){if(Array.isArray(report[key])&&report[key].length>4){report[key].pop();changed=true;trimmed=true;break}}if(!changed&&report.issues.length>20){report.issues.pop();changed=true;trimmed=true}if(!changed)break}if(trimmed)report.outputTruncated=true;report.outputCharacters=JSON.stringify(report).length;return report
"""


_PROFILE_TEMPLATE = r"""
const DURATION=__DURATION__,T=globalThis.THREE,d=globalThis.__DARKSTAR_THREE_DEBUG__;const renderers=[];const push=(v)=>{if(v&&!renderers.includes(v))renderers.push(v)};for(const r of (d?.renderers||[]))push(r);if(d?.lastRenderer)push(d.lastRenderer);for(const k of Object.getOwnPropertyNames(globalThis).slice(0,700)){let v;try{v=globalThis[k]}catch(_){continue}if(v?.domElement&&v?.info&&typeof v.render==='function')push(v)}const r=d?.lastRenderer||renderers[0]||null;if(!r)return {success:false,action:'threejs_profile',error:'No renderer found. Reopen the page with threejs_open_debug and render at least one frame.'};const startMem={geometries:r.info?.memory?.geometries||0,textures:r.info?.memory?.textures||0,programs:Array.isArray(r.info?.programs)?r.info.programs.length:null,heap:performance.memory?.usedJSHeapSize||null};const frames=[],samples=[],longTasks=[];let observer=null;try{observer=new PerformanceObserver(list=>{for(const e of list.getEntries())longTasks.push({start:Number(e.startTime.toFixed(2)),duration:Number(e.duration.toFixed(2))})});observer.observe({entryTypes:['longtask']})}catch(_){}const started=performance.now();let last=started;await new Promise(resolve=>{const tick=t=>{const dt=t-last;last=t;if(dt>0&&dt<1000)frames.push(dt);const info=r.info||{};samples.push({time:Number((t-started).toFixed(1)),calls:info.render?.calls||0,triangles:info.render?.triangles||0,points:info.render?.points||0,lines:info.render?.lines||0,geometries:info.memory?.geometries||0,textures:info.memory?.textures||0});if(t-started>=DURATION)resolve();else requestAnimationFrame(tick)};requestAnimationFrame(tick)});try{observer?.disconnect()}catch(_){}const sorted=frames.slice().sort((a,b)=>a-b),pct=p=>sorted.length?sorted[Math.min(sorted.length-1,Math.floor((sorted.length-1)*p))]:null,avg=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null,max=(key)=>samples.reduce((m,x)=>Math.max(m,Number(x[key])||0),0),endMem={geometries:r.info?.memory?.geometries||0,textures:r.info?.memory?.textures||0,programs:Array.isArray(r.info?.programs)?r.info.programs.length:null,heap:performance.memory?.usedJSHeapSize||null};const mean=avg(frames),fps=mean?1000/mean:0;const issues=[];if(!frames.length)issues.push({severity:'critical',code:'NO_FRAMES',message:'No animation frames were observed during the sample.'});if(fps&&fps<30)issues.push({severity:'error',code:'LOW_FPS',message:`Average FPS was ${fps.toFixed(1)}.`});else if(fps&&fps<50)issues.push({severity:'warning',code:'FPS_BELOW_50',message:`Average FPS was ${fps.toFixed(1)}.`});if((pct(.95)||0)>33.3)issues.push({severity:'warning',code:'FRAME_TIME_P95_HIGH',message:`95th-percentile frame time was ${pct(.95).toFixed(2)} ms.`});if(endMem.geometries>startMem.geometries||endMem.textures>startMem.textures)issues.push({severity:'warning',code:'GPU_RESOURCE_GROWTH',message:'Renderer geometry/texture counts increased during a short steady-state sample.',evidence:{start:startMem,end:endMem},fix:'Check whether resources are created every frame and dispose replaced resources.'});if(startMem.heap&&endMem.heap&&endMem.heap-startMem.heap>8*1024*1024)issues.push({severity:'warning',code:'HEAP_GROWTH',message:'JavaScript heap grew by more than 8 MiB during the sample.',evidence:{bytes:endMem.heap-startMem.heap},fix:'Inspect per-frame allocations, arrays, event listeners, and object creation.'});const jank={over16_7:frames.filter(x=>x>16.7).length,over33_3:frames.filter(x=>x>33.3).length,over50:frames.filter(x=>x>50).length,over100:frames.filter(x=>x>100).length};return {success:!issues.some(x=>x.severity==='critical'||x.severity==='error'),action:'threejs_profile',durationMs:DURATION,frames:frames.length,fps:{average:Number((fps||0).toFixed(2)),frameTimeAverage:mean&&Number(mean.toFixed(3)),median:pct(.5)&&Number(pct(.5).toFixed(3)),p95:pct(.95)&&Number(pct(.95).toFixed(3)),p99:pct(.99)&&Number(pct(.99).toFixed(3)),worst:sorted.length&&Number(sorted.at(-1).toFixed(3))},jank,longTasks:longTasks.slice(0,30),rendererPeaks:{calls:max('calls'),triangles:max('triangles'),points:max('points'),lines:max('lines'),geometries:max('geometries'),textures:max('textures')},memory:{start:startMem,end:endMem,heapDelta:startMem.heap&&endMem.heap?endMem.heap-startMem.heap:null},issues,sampleTail:samples.slice(-10),guidance:issues.length?'Fix the listed bottlenecks, then repeat the same-duration profile for comparison.':'The short sample found no major frame-time or resource-growth warning.'}
"""


_OBJECT_TEMPLATE = r"""
const Q=__QUERY__.toLowerCase(),LIMIT=__LIMIT__,T=globalThis.THREE,d=globalThis.__DARKSTAR_THREE_DEBUG__;const scenes=[];const push=v=>{if(v?.isScene&&!scenes.includes(v))scenes.push(v)};for(const s of (d?.scenes||[]))push(s);if(d?.lastScene)push(d.lastScene);for(const k of Object.getOwnPropertyNames(globalThis).slice(0,700)){let v;try{v=globalThis[k]}catch(_){continue}push(v)}if(!scenes.length)return {success:false,action:'threejs_object',error:'No scene found. Reopen with threejs_open_debug and render at least one frame.'};const matches=[];for(const [si,s] of scenes.entries()){s.updateMatrixWorld?.(true);s.traverse?.(o=>{if(matches.length>=LIMIT)return;const hay=[o.name,o.uuid,o.type,o.constructor?.name].map(x=>String(x||'').toLowerCase());if(!hay.some(x=>x.includes(Q)))return;let bounds=null;try{if(T?.Box3&&(o.isMesh||o.isLine||o.isPoints||o.isSprite)){const b=new T.Box3().setFromObject(o);bounds={min:b.min.toArray(),max:b.max.toArray(),empty:b.isEmpty()}}}catch(e){bounds={error:String(e?.message||e)}}const parentChain=[];let p=o.parent;while(p&&parentChain.length<12){parentChain.push({name:p.name||'',uuid:p.uuid,type:p.type,visible:p.visible});p=p.parent}const mats=(Array.isArray(o.material)?o.material:[o.material]).filter(Boolean).map(m=>({uuid:m.uuid,name:m.name||'',type:m.type,visible:m.visible,opacity:m.opacity,transparent:m.transparent,depthTest:m.depthTest,depthWrite:m.depthWrite,color:m.color?.getHexString?.()}));const g=o.geometry;matches.push({scene:si,name:o.name||'',uuid:o.uuid,type:o.type,visible:o.visible,visibleInHierarchy:o.visible&&parentChain.every(x=>x.visible),frustumCulled:o.frustumCulled,renderOrder:o.renderOrder,layers:o.layers?.mask,local:{position:o.position?.toArray?.(),quaternion:o.quaternion?.toArray?.(),rotation:o.rotation?[o.rotation.x,o.rotation.y,o.rotation.z,o.rotation.order]:null,scale:o.scale?.toArray?.()},world:{position:o.getWorldPosition&&T?.Vector3?o.getWorldPosition(new T.Vector3()).toArray():null,quaternion:o.getWorldQuaternion&&T?.Quaternion?o.getWorldQuaternion(new T.Quaternion()).toArray():null,scale:o.getWorldScale&&T?.Vector3?o.getWorldScale(new T.Vector3()).toArray():null},bounds,geometry:g?{uuid:g.uuid,name:g.name||'',type:g.type,attributes:Object.fromEntries(Object.entries(g.attributes||{}).map(([k,a])=>[k,{count:a.count,itemSize:a.itemSize,arrayType:a.array?.constructor?.name}])),indexCount:g.index?.count||0,drawRange:g.drawRange}:null,materials:mats,parentChain,children:(o.children||[]).slice(0,30).map(c=>({name:c.name||'',uuid:c.uuid,type:c.type,visible:c.visible})),userData:(()=>{try{const t=JSON.stringify(o.userData||{});return t.length<3000?JSON.parse(t):{truncated:true,preview:t.slice(0,3000)}}catch(_){return {unserializable:true}}})()})})}return {success:true,action:'threejs_object',query:Q,sceneCount:scenes.length,matchCount:matches.length,truncated:matches.length>=LIMIT,matches,guidance:matches.length?'Use UUID for an exact follow-up query when names are duplicated.':'No object matched name, UUID, or type. Verify the object was added to a discovered scene.'}
"""


MODEL_OPERATION_NAMES = {
    "create", "transform", "set_dimensions", "duplicate", "array", "mirror",
    "delete", "group", "parent", "align", "material", "repair", "pivot",
    "rename", "visibility", "generate_uv", "lod", "collision", "boolean",
}
MODEL_RECIPE_BEGIN = "DARKSTAR_MODEL_BEGIN"
MODEL_RECIPE_END = "DARKSTAR_MODEL_END"
MAX_MODEL_RECIPE_BYTES = 256 * 1024

# Installed once into the live preview.  All later modeling calls are tiny commands
# against this stateful, transactional runtime.
_MODELER_INSTALL_SCRIPT = r"""
const T=globalThis.THREE;
if(!T)return {success:false,action:'threejs_model',error:'Three.js is unavailable. Open the project with threejs_open_debug first.'};
if(globalThis.__DARKSTAR_THREE_MODELER__?.version===1)return globalThis.__DARKSTAR_THREE_MODELER__.status();
const finite=n=>typeof n==='number'&&Number.isFinite(n),num=(v,d=0)=>finite(Number(v))?Number(v):d,clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
const vec3=(v,d=[0,0,0])=>Array.isArray(v)&&v.length>=3?new T.Vector3(num(v[0]),num(v[1]),num(v[2])):new T.Vector3(...d);
const deg=v=>num(v)*Math.PI/180,plain=v=>JSON.parse(JSON.stringify(v));
const disposeMaterial=m=>{if(!m)return;for(const k of Object.keys(m)){const x=m[k];if(x?.isTexture)x.dispose?.()}m.dispose?.()};
const disposeObject=o=>o?.traverse?.(x=>{x.geometry?.dispose?.();if(Array.isArray(x.material))x.material.forEach(disposeMaterial);else disposeMaterial(x.material)});
const deepClone=o=>{const c=o.clone(true);const src=[],dst=[];o.traverse(x=>src.push(x));c.traverse(x=>dst.push(x));for(let i=0;i<Math.min(src.length,dst.length);i++){if(src[i].geometry)dst[i].geometry=src[i].geometry.clone();if(src[i].material)dst[i].material=Array.isArray(src[i].material)?src[i].material.map(m=>m.clone()):src[i].material.clone()}return c};
const findScene=()=>{const d=globalThis.__DARKSTAR_THREE_DEBUG__;if(d?.lastScene?.isScene)return d.lastScene;for(const s of d?.scenes||[])if(s?.isScene)return s;for(const k of Object.getOwnPropertyNames(globalThis).slice(0,900)){let v;try{v=globalThis[k]}catch(_){continue}if(v?.isScene)return v}return null};
const state={version:1,createdAt:Date.now(),scene:null,root:null,undoStack:[],redoStack:[],recipe:[],viewState:null,helpers:null,maxHistory:24};
state.ensure=()=>{state.scene=state.scene?.isScene?state.scene:findScene();if(!state.scene)throw new Error('No live Three.js scene was found. Use threejs_open_debug and ensure at least one frame renders.');let root=state.scene.getObjectByName('__DARKSTAR_MODEL_ROOT__');if(!root){root=new T.Group();root.name='__DARKSTAR_MODEL_ROOT__';root.userData.darkstarModelRoot=true;state.scene.add(root)}state.root=root;return root};
state.idOf=o=>String(o?.userData?.darkstarModelId||o?.name||o?.uuid||'');state.relabelClone=(o,id)=>{let n=0;o.traverse?.(x=>{x.userData=x.userData||{};if(x===o){x.userData.darkstarModelId=id;x.name=id}else{delete x.userData.darkstarModelId;if(x.name)x.name=`${id}_${++n}_${x.name}`}});return o};
state.find=(id,required=true)=>{state.ensure();if(!id)return state.root;let hit=null;state.root.traverse(o=>{if(hit)return;const q=String(id);if(o.userData?.darkstarModelId===q||o.name===q||o.uuid===q)hit=o});if(!hit&&required)throw new Error(`Model object not found: ${id}`);return hit};
state.uniqueId=id=>{const q=String(id||'').trim();if(!q||q.length>96||!/^[A-Za-z][A-Za-z0-9_.-]*$/.test(q))throw new Error('Object id must start with a letter and contain only letters, numbers, dot, underscore, or hyphen.');if(state.find(q,false))throw new Error(`Object id already exists: ${q}`);return q};
state.snapshot=()=>({root:deepClone(state.ensure()),recipe:plain(state.recipe)});
state.restore=s=>{const old=state.ensure();const parent=old.parent||state.scene;const index=parent.children.indexOf(old);parent.remove(old);disposeObject(old);state.root=s.root;state.root.name='__DARKSTAR_MODEL_ROOT__';if(index>=0)parent.children.splice(index,0,state.root),state.root.parent=parent;else parent.add(state.root);state.recipe=plain(s.recipe)};
state.pushUndo=()=>{state.undoStack.push(state.snapshot());if(state.undoStack.length>state.maxHistory){const old=state.undoStack.shift();disposeObject(old.root)}for(const s of state.redoStack)disposeObject(s.root);state.redoStack=[]};
state.material=spec=>{spec=spec||{};const preset=String(spec.preset||'matte').toLowerCase(),color=spec.color??'#b7bec9',common={color,side:spec.side==='double'?T.DoubleSide:spec.side==='back'?T.BackSide:T.FrontSide};let m;if(preset==='unlit')m=new T.MeshBasicMaterial(common);else if(preset==='wireframe')m=new T.MeshBasicMaterial({...common,wireframe:true});else if(preset==='glass'&&T.MeshPhysicalMaterial)m=new T.MeshPhysicalMaterial({...common,metalness:0,roughness:num(spec.roughness,.08),transmission:1,thickness:num(spec.thickness,.15),transparent:true,opacity:num(spec.opacity,.38)});else{const defaults={painted_metal:[.65,.34],bare_metal:[.98,.18],rubber:[0,.9],plastic:[.03,.42],matte:[0,.68],emissive:[0,.45]};const [metalness,roughness]=defaults[preset]||defaults.matte;m=new T.MeshStandardMaterial({...common,metalness:num(spec.metalness,metalness),roughness:num(spec.roughness,roughness)})}if(spec.opacity!==undefined){m.opacity=clamp(num(spec.opacity,1),0,1);m.transparent=m.opacity<1||spec.transparent===true}if(spec.wireframe!==undefined)m.wireframe=!!spec.wireframe;if(spec.emissive&&m.emissive){m.emissive.set(spec.emissive);m.emissiveIntensity=num(spec.emissive_intensity,1)}if(preset==='emissive'&&m.emissive){m.emissive.set(spec.emissive||color);m.emissiveIntensity=num(spec.emissive_intensity,1.5)}m.name=String(spec.name||preset);return m};
state.geometry=op=>{const p=String(op.primitive||'box').toLowerCase(),seg=(v,d,min=3,max=256)=>clamp(Math.round(num(v,d)),min,max);if(p==='box'){const s=op.size||[1,1,1];return new T.BoxGeometry(num(s[0],1),num(s[1],1),num(s[2],1),seg(op.width_segments,1,1,64),seg(op.height_segments,1,1,64),seg(op.depth_segments,1,1,64))}if(p==='sphere')return new T.SphereGeometry(num(op.radius,1),seg(op.width_segments,32),seg(op.height_segments,16,2));if(p==='cylinder')return new T.CylinderGeometry(num(op.radius_top,op.radius??1),num(op.radius_bottom,op.radius??1),num(op.height,1),seg(op.radial_segments,32),seg(op.height_segments,1,1,64),!!op.open_ended);if(p==='cone')return new T.ConeGeometry(num(op.radius,1),num(op.height,2),seg(op.radial_segments,32),seg(op.height_segments,1,1,64),!!op.open_ended);if(p==='plane'){const s=op.size||[1,1];return new T.PlaneGeometry(num(s[0],1),num(s[1],1),seg(op.width_segments,1,1,128),seg(op.height_segments,1,1,128))}if(p==='circle')return new T.CircleGeometry(num(op.radius,1),seg(op.segments,32));if(p==='ring')return new T.RingGeometry(num(op.inner_radius,.5),num(op.outer_radius,1),seg(op.segments,32));if(p==='torus')return new T.TorusGeometry(num(op.radius,1),num(op.tube,.25),seg(op.radial_segments,16),seg(op.tubular_segments,64));if(p==='capsule'){if(!T.CapsuleGeometry)throw new Error('CapsuleGeometry is unavailable in this Three.js runtime.');return new T.CapsuleGeometry(num(op.radius,.5),num(op.height,1),seg(op.cap_segments,8,1,64),seg(op.radial_segments,16))}if(p==='lathe'){if(!Array.isArray(op.points)||op.points.length<2)throw new Error('lathe requires points: [[radius,y], ...].');return new T.LatheGeometry(op.points.map(x=>new T.Vector2(num(x[0]),num(x[1]))),seg(op.segments,24))}if(p==='extrude'){if(!Array.isArray(op.points)||op.points.length<3)throw new Error('extrude requires at least three 2D points.');const shape=new T.Shape();shape.moveTo(num(op.points[0][0]),num(op.points[0][1]));for(const q of op.points.slice(1))shape.lineTo(num(q[0]),num(q[1]));shape.closePath();return new T.ExtrudeGeometry(shape,{depth:num(op.depth,1),steps:seg(op.steps,1,1,64),bevelEnabled:!!op.bevel_enabled,bevelThickness:num(op.bevel_thickness,.1),bevelSize:num(op.bevel_size,.08),bevelSegments:seg(op.bevel_segments,2,1,16)})}if(p==='tube'){if(!Array.isArray(op.points)||op.points.length<2)throw new Error('tube requires at least two 3D points.');const curve=new T.CatmullRomCurve3(op.points.map(q=>vec3(q)));return new T.TubeGeometry(curve,seg(op.tubular_segments,64,2,512),num(op.radius,.1),seg(op.radial_segments,12),!!op.closed)}throw new Error(`Unsupported primitive: ${p}`)};
state.applyTransform=(o,op)=>{const mode=String(op.mode||'set');if(op.position){const v=vec3(op.position);mode==='add'?o.position.add(v):o.position.copy(v)}if(op.rotation_deg){const r=op.rotation_deg;const e=new T.Euler(deg(r[0]),deg(r[1]),deg(r[2]),String(op.rotation_order||'XYZ'));if(mode==='add'){o.rotation.x+=e.x;o.rotation.y+=e.y;o.rotation.z+=e.z}else o.rotation.copy(e)}if(op.scale!==undefined){const s=Array.isArray(op.scale)?vec3(op.scale,[1,1,1]):new T.Vector3(num(op.scale,1),num(op.scale,1),num(op.scale,1));mode==='multiply'?o.scale.multiply(s):o.scale.copy(s)}o.updateMatrix();o.updateMatrixWorld(true)};
state.anchor=(box,axis,kind)=>kind==='min'?box.min[axis]:kind==='max'?box.max[axis]:(box.min[axis]+box.max[axis])/2;
state.geometryReport=(g,deep=false)=>{if(!g?.isBufferGeometry)return null;const pos=g.getAttribute('position'),idx=g.index,tri=Math.floor((idx?.count||pos?.count||0)/3),limit=deep?Math.min(tri,250000):Math.min(tri,25000);let invalidPosition=0,invalidIndex=0,degenerate=0,surfaceArea=0,volume=0;const a=new T.Vector3(),b=new T.Vector3(),c=new T.Vector3(),ab=new T.Vector3(),ac=new T.Vector3();if(pos){for(let i=0;i<Math.min(pos.count,deep?500000:100000);i++)if(!finite(pos.getX(i))||!finite(pos.getY(i))||!finite(pos.getZ(i)))invalidPosition++;for(let f=0;f<limit;f++){const ia=idx?idx.getX(f*3):f*3,ib=idx?idx.getX(f*3+1):f*3+1,ic=idx?idx.getX(f*3+2):f*3+2;if(ia>=pos.count||ib>=pos.count||ic>=pos.count||ia<0||ib<0||ic<0){invalidIndex++;continue}a.fromBufferAttribute(pos,ia);b.fromBufferAttribute(pos,ib);c.fromBufferAttribute(pos,ic);ab.subVectors(b,a);ac.subVectors(c,a);const area=ab.cross(ac).length()/2;if(area<=1e-12)degenerate++;surfaceArea+=area;volume+=a.dot(new T.Vector3().crossVectors(b,c))/6}}g.computeBoundingBox?.();g.computeBoundingSphere?.();const uv=g.getAttribute('uv'),normal=g.getAttribute('normal');let uvOut=0,badNormals=0;if(uv)for(let i=0;i<Math.min(uv.count,deep?250000:50000);i++){const u=uv.getX(i),v=uv.getY(i);if(!finite(u)||!finite(v)||u<0||u>1||v<0||v>1)uvOut++}if(normal)for(let i=0;i<Math.min(normal.count,deep?250000:50000);i++){const l=Math.hypot(normal.getX(i),normal.getY(i),normal.getZ(i));if(!finite(l)||Math.abs(l-1)>.08)badNormals++}let duplicateVertices=0;if(pos&&pos.count<=100000){const seen=new Set();for(let i=0;i<pos.count;i++){const k=`${Math.round(pos.getX(i)*1e6)},${Math.round(pos.getY(i)*1e6)},${Math.round(pos.getZ(i)*1e6)}`;if(seen.has(k))duplicateVertices++;else seen.add(k)}}return {type:g.type,vertices:pos?.count||0,indexed:!!idx,indices:idx?.count||0,triangles:tri,scannedTriangles:limit,attributes:Object.fromEntries(Object.entries(g.attributes||{}).map(([k,v])=>[k,{count:v.count,itemSize:v.itemSize,arrayType:v.array?.constructor?.name}])),groups:g.groups?.length||0,invalidPositionValues:invalidPosition,invalidIndices:invalidIndex,degenerateTriangles:degenerate,duplicatePositionVertices:duplicateVertices,normalIssues:normal?badNormals:null,uvOutOfRange:uv?uvOut:null,surfaceArea:Number(surfaceArea.toFixed(6)),signedVolume:Number(volume.toFixed(6)),bounds:g.boundingBox?{min:g.boundingBox.min.toArray(),max:g.boundingBox.max.toArray()}:null,boundingSphere:g.boundingSphere?{center:g.boundingSphere.center.toArray(),radius:g.boundingSphere.radius}:null,truncated:limit<tri}};
state.measure=o=>{o.updateMatrixWorld?.(true);const box=new T.Box3().setFromObject(o),size=new T.Vector3(),center=new T.Vector3();box.getSize(size);box.getCenter(center);let vertices=0,triangles=0,meshes=0,surfaceArea=0,volume=0;o.traverse?.(x=>{if(!x.isMesh||!x.geometry)return;meshes++;const r=state.geometryReport(x.geometry,false);vertices+=r.vertices;triangles+=r.triangles;surfaceArea+=r.surfaceArea;volume+=r.signedVolume*Math.abs(x.getWorldScale(new T.Vector3()).x*x.getWorldScale(new T.Vector3()).y*x.getWorldScale(new T.Vector3()).z)});return {id:state.idOf(o),type:o.type,name:o.name||'',worldBounds:{min:box.min.toArray(),max:box.max.toArray(),center:center.toArray(),dimensions:size.toArray(),empty:box.isEmpty()},meshes,vertices,triangles,approxSurfaceArea:Number(surfaceArea.toFixed(6)),approxSignedVolume:Number(volume.toFixed(6))}};
state.inspect=(id,deep=false)=>{const o=state.find(id);const objects=[];o.traverse?.(x=>{if(objects.length>=80)return;objects.push({id:state.idOf(x),name:x.name||'',uuid:x.uuid,type:x.type,visible:x.visible,parent:x.parent?state.idOf(x.parent):null,children:x.children?.length||0,position:x.position?.toArray?.(),rotationDeg:x.rotation?[x.rotation.x*180/Math.PI,x.rotation.y*180/Math.PI,x.rotation.z*180/Math.PI]:null,scale:x.scale?.toArray?.(),geometry:x.geometry?state.geometryReport(x.geometry,deep):null,material:Array.isArray(x.material)?x.material.map(m=>({type:m.type,name:m.name||'',color:m.color?.getHexString?.(),metalness:m.metalness,roughness:m.roughness,opacity:m.opacity,transparent:m.transparent,wireframe:m.wireframe})):x.material?{type:x.material.type,name:x.material.name||'',color:x.material.color?.getHexString?.(),metalness:x.material.metalness,roughness:x.material.roughness,opacity:x.material.opacity,transparent:x.material.transparent,wireframe:x.material.wireframe}:null})});const measurement=state.measure(o),issues=[];for(const x of objects){const g=x.geometry;if(!g)continue;if(g.invalidPositionValues)issues.push({severity:'error',id:x.id,code:'NONFINITE_VERTICES',count:g.invalidPositionValues});if(g.invalidIndices)issues.push({severity:'error',id:x.id,code:'INVALID_INDICES',count:g.invalidIndices});if(g.degenerateTriangles)issues.push({severity:'warning',id:x.id,code:'DEGENERATE_TRIANGLES',count:g.degenerateTriangles});if(g.normalIssues)issues.push({severity:'warning',id:x.id,code:'BAD_NORMALS',count:g.normalIssues});if(g.uvOutOfRange)issues.push({severity:'warning',id:x.id,code:'UV_OUT_OF_RANGE',count:g.uvOutOfRange})}return {success:!issues.some(x=>x.severity==='error'),action:'threejs_model',modelAction:'inspect',measurement,issues,objects,truncated:objects.length>=80}};
state.weld=g=>{if(Object.keys(g.morphAttributes||{}).length)throw new Error('weld_vertices does not support morph-target geometry.');const pos=g.getAttribute('position');if(!pos)return;const attrs=g.attributes,keys=Object.keys(attrs),count=pos.count,map=new Int32Array(count),seen=new Map(),values=Object.fromEntries(keys.map(k=>[k,[]]));let next=0;for(let i=0;i<count;i++){const parts=[];for(const k of keys){const a=attrs[k];for(let j=0;j<a.itemSize;j++)parts.push(Math.round(a.array[i*a.itemSize+j]*1e6))}const key=parts.join(',');let ni=seen.get(key);if(ni===undefined){ni=next++;seen.set(key,ni);for(const k of keys){const a=attrs[k];for(let j=0;j<a.itemSize;j++)values[k].push(a.array[i*a.itemSize+j])}}map[i]=ni}const oldIndex=g.index;const source=oldIndex?Array.from(oldIndex.array):Array.from({length:count},(_,i)=>i);for(const k of keys){const a=attrs[k],Ctor=a.array.constructor;g.setAttribute(k,new T.BufferAttribute(new Ctor(values[k]),a.itemSize,a.normalized))}const IndexCtor=next>65535?Uint32Array:Uint16Array;g.setIndex(new T.BufferAttribute(new IndexCtor(source.map(i=>map[i])),1));return count-next};
state.removeDegenerate=g=>{const pos=g.getAttribute('position');if(!pos)return 0;const source=g.index?Array.from(g.index.array):Array.from({length:pos.count},(_,i)=>i),out=[],a=new T.Vector3(),b=new T.Vector3(),c=new T.Vector3(),ab=new T.Vector3(),ac=new T.Vector3();let removed=0;for(let i=0;i+2<source.length;i+=3){const ia=source[i],ib=source[i+1],ic=source[i+2];if(ia===ib||ib===ic||ia===ic){removed++;continue}a.fromBufferAttribute(pos,ia);b.fromBufferAttribute(pos,ib);c.fromBufferAttribute(pos,ic);if(ab.subVectors(b,a).cross(ac.subVectors(c,a)).lengthSq()<=1e-20){removed++;continue}out.push(ia,ib,ic)}const C=pos.count>65535?Uint32Array:Uint16Array;g.setIndex(new T.BufferAttribute(new C(out),1));if(removed)g.clearGroups();return removed};
state.repair=(o,fixes)=>{const results=[];const list=Array.isArray(fixes)&&fixes.length?fixes:['recompute_normals','recompute_bounds'];o.traverse?.(x=>{if(!x.geometry?.isBufferGeometry)return;const g=x.geometry,r={id:state.idOf(x),fixes:[]};for(const fix of list){if(fix==='remove_degenerate_triangles')r.fixes.push({fix,removed:state.removeDegenerate(g)});else if(fix==='weld_vertices')r.fixes.push({fix,removed:state.weld(g)});else if(fix==='recompute_normals'){g.deleteAttribute('normal');g.computeVertexNormals();r.fixes.push({fix})}else if(fix==='normalize_normals'){g.normalizeNormals?.();r.fixes.push({fix})}else if(fix==='recompute_bounds'){g.computeBoundingBox();g.computeBoundingSphere();r.fixes.push({fix})}else if(fix==='center_geometry'){g.center();r.fixes.push({fix})}else if(fix==='flip_winding'){const pos=g.getAttribute('position'),src=g.index?Array.from(g.index.array):Array.from({length:pos.count},(_,i)=>i);for(let i=0;i+2<src.length;i+=3){const t=src[i+1];src[i+1]=src[i+2];src[i+2]=t}const C=pos.count>65535?Uint32Array:Uint16Array;g.setIndex(new T.BufferAttribute(new C(src),1));g.deleteAttribute('normal');g.computeVertexNormals();r.fixes.push({fix})}else if(fix==='bake_transform'){x.updateMatrix();g.applyMatrix4(x.matrix);x.position.set(0,0,0);x.rotation.set(0,0,0);x.scale.set(1,1,1);x.updateMatrix();r.fixes.push({fix})}else throw new Error(`Unsupported repair: ${fix}`)}g.computeBoundingBox();g.computeBoundingSphere();results.push(r)});return results};
state.generateUV=(o,projection='box',scale=1)=>{const results=[];o.traverse?.(x=>{if(!x.isMesh||!x.geometry?.isBufferGeometry)return;let g=x.geometry;if(Object.keys(g.morphAttributes||{}).length)throw new Error('UV generation does not support morph-target geometry.');if(projection==='box'&&g.index){g=g.toNonIndexed();x.geometry=g}const p=g.getAttribute('position');if(!p)return;g.computeBoundingBox();const b=g.boundingBox,size=b.getSize(new T.Vector3()),center=b.getCenter(new T.Vector3()),uv=new Float32Array(p.count*2);const safe=(v)=>Math.abs(v)<1e-12?1:v;for(let i=0;i<p.count;i++){const px=p.getX(i),py=p.getY(i),pz=p.getZ(i);let u=0,v=0;if(projection==='planar_xy'){u=(px-b.min.x)/safe(size.x);v=(py-b.min.y)/safe(size.y)}else if(projection==='planar_yz'){u=(pz-b.min.z)/safe(size.z);v=(py-b.min.y)/safe(size.y)}else if(projection==='planar_xz'||projection==='planar'){u=(px-b.min.x)/safe(size.x);v=(pz-b.min.z)/safe(size.z)}else if(projection==='cylindrical'){u=Math.atan2(pz-center.z,px-center.x)/(Math.PI*2)+.5;v=(py-b.min.y)/safe(size.y)}else if(projection==='spherical'){const q=new T.Vector3(px-center.x,py-center.y,pz-center.z).normalize();u=Math.atan2(q.z,q.x)/(Math.PI*2)+.5;v=Math.asin(clamp(q.y,-1,1))/Math.PI+.5}else if(projection==='box'){const t=Math.floor(i/3)*3,a=new T.Vector3().fromBufferAttribute(p,t),bb=new T.Vector3().fromBufferAttribute(p,t+1),c=new T.Vector3().fromBufferAttribute(p,t+2),n=bb.sub(a).cross(c.sub(a));const ax=Math.abs(n.x),ay=Math.abs(n.y),az=Math.abs(n.z);if(ax>=ay&&ax>=az){u=(pz-b.min.z)/safe(size.z);v=(py-b.min.y)/safe(size.y)}else if(ay>=az){u=(px-b.min.x)/safe(size.x);v=(pz-b.min.z)/safe(size.z)}else{u=(px-b.min.x)/safe(size.x);v=(py-b.min.y)/safe(size.y)}}else throw new Error(`Unsupported UV projection: ${projection}`);uv[i*2]=u*num(scale,1);uv[i*2+1]=v*num(scale,1)}g.setAttribute('uv',new T.BufferAttribute(uv,2));g.attributes.uv.needsUpdate=true;results.push({id:state.idOf(x),vertices:p.count,projection})});return results};
state.simplify=(g,ratio)=>{ratio=clamp(num(ratio,.5),.03,1);if(ratio>=.999)return g.clone();if(Object.keys(g.morphAttributes||{}).length||g.getAttribute('skinIndex'))throw new Error('LOD simplification does not support skinned or morph-target geometry.');const pos=g.getAttribute('position');if(!pos)return g.clone();g.computeBoundingBox();const b=g.boundingBox,size=b.getSize(new T.Vector3()),target=Math.max(4,Math.floor(pos.count*ratio)),res=Math.max(1,Math.round(Math.cbrt(target))),cell=new T.Vector3(size.x/res||1,size.y/res||1,size.z/res||1),attrs=g.attributes,keys=Object.keys(attrs),clusters=new Map(),map=new Int32Array(pos.count);for(let i=0;i<pos.count;i++){const key=`${Math.floor((pos.getX(i)-b.min.x)/cell.x)},${Math.floor((pos.getY(i)-b.min.y)/cell.y)},${Math.floor((pos.getZ(i)-b.min.z)/cell.z)}`;let c=clusters.get(key);if(!c){c={index:clusters.size,count:0,sums:Object.fromEntries(keys.map(k=>[k,new Array(attrs[k].itemSize).fill(0)]))};clusters.set(key,c)}c.count++;for(const k of keys){const a=attrs[k];for(let j=0;j<a.itemSize;j++)c.sums[k][j]+=a.array[i*a.itemSize+j]}map[i]=c.index}const ng=new T.BufferGeometry();for(const k of keys){if(k==='normal'||k==='tangent')continue;const a=attrs[k],out=[];for(const c of clusters.values())for(let j=0;j<a.itemSize;j++)out.push(c.sums[k][j]/c.count);ng.setAttribute(k,new T.BufferAttribute(new a.array.constructor(out),a.itemSize,a.normalized))}const src=g.index?Array.from(g.index.array):Array.from({length:pos.count},(_,i)=>i),ind=[];for(let i=0;i+2<src.length;i+=3){const a=map[src[i]],bb=map[src[i+1]],c=map[src[i+2]];if(a!==bb&&bb!==c&&a!==c)ind.push(a,bb,c)}const C=clusters.size>65535?Uint32Array:Uint16Array;ng.setIndex(new T.BufferAttribute(new C(ind),1));ng.computeVertexNormals();ng.computeBoundingBox();ng.computeBoundingSphere();return ng};
const CSG_EPS=1e-5;
class CSGVertex{constructor(pos,normal,uv){this.pos=pos;this.normal=normal;this.uv=uv}clone(){return new CSGVertex(this.pos.clone(),this.normal.clone(),this.uv?.clone?.()||null)}flip(){this.normal.multiplyScalar(-1)}interpolate(other,t){return new CSGVertex(this.pos.clone().lerp(other.pos,t),this.normal.clone().lerp(other.normal,t).normalize(),this.uv&&other.uv?this.uv.clone().lerp(other.uv,t):null)}}
class CSGPlane{constructor(normal,w){this.normal=normal;this.w=w}clone(){return new CSGPlane(this.normal.clone(),this.w)}flip(){this.normal.multiplyScalar(-1);this.w*=-1}static fromPoints(a,b,c){const n=new T.Vector3().subVectors(b,a).cross(new T.Vector3().subVectors(c,a));if(n.lengthSq()<1e-20)return null;n.normalize();return new CSGPlane(n,n.dot(a))}splitPolygon(poly,cf,cb,f,b){const types=[],FRONT=1,BACK=2,COPLANAR=0,SPANNING=3;let type=0;for(const v of poly.vertices){const t=this.normal.dot(v.pos)-this.w,ty=t<-CSG_EPS?BACK:t>CSG_EPS?FRONT:COPLANAR;type|=ty;types.push(ty)}if(type===COPLANAR)(this.normal.dot(poly.plane.normal)>0?cf:cb).push(poly);else if(type===FRONT)f.push(poly);else if(type===BACK)b.push(poly);else{const fv=[],bv=[];for(let i=0;i<poly.vertices.length;i++){const j=(i+1)%poly.vertices.length,ti=types[i],tj=types[j],vi=poly.vertices[i],vj=poly.vertices[j];if(ti!==BACK)fv.push(vi);if(ti!==FRONT)bv.push(ti!==BACK?vi.clone():vi);if((ti|tj)===SPANNING){const direction=new T.Vector3().subVectors(vj.pos,vi.pos),den=this.normal.dot(direction);if(Math.abs(den)>1e-12){const t=(this.w-this.normal.dot(vi.pos))/den,v=vi.interpolate(vj,t);fv.push(v);bv.push(v.clone())}}}if(fv.length>=3)f.push(new CSGPolygon(fv,poly.shared));if(bv.length>=3)b.push(new CSGPolygon(bv,poly.shared))}}}
class CSGPolygon{constructor(vertices,shared=0){this.vertices=vertices;this.shared=shared;this.plane=CSGPlane.fromPoints(vertices[0].pos,vertices[1].pos,vertices[2].pos)}clone(){return new CSGPolygon(this.vertices.map(v=>v.clone()),this.shared)}flip(){this.vertices.reverse().forEach(v=>v.flip());this.plane?.flip()}}
class CSGNode{constructor(polys=[]){this.plane=null;this.front=null;this.back=null;this.polygons=[];if(polys.length)this.build(polys)}clone(){const n=new CSGNode();n.plane=this.plane?.clone()||null;n.front=this.front?.clone()||null;n.back=this.back?.clone()||null;n.polygons=this.polygons.map(p=>p.clone());return n}invert(){for(const p of this.polygons)p.flip();this.plane?.flip();this.front?.invert();this.back?.invert();const t=this.front;this.front=this.back;this.back=t}clipPolygons(polys){if(!this.plane)return polys.slice();let f=[],b=[];for(const p of polys)this.plane.splitPolygon(p,f,b,f,b);if(this.front)f=this.front.clipPolygons(f);if(this.back)b=this.back.clipPolygons(b);else b=[];return f.concat(b)}clipTo(node){this.polygons=node.clipPolygons(this.polygons);this.front?.clipTo(node);this.back?.clipTo(node)}allPolygons(){return this.polygons.concat(this.front?this.front.allPolygons():[],this.back?this.back.allPolygons():[])}build(polys){if(!polys.length)return;if(!this.plane)this.plane=polys.find(p=>p.plane)?.plane?.clone()||null;if(!this.plane)return;const f=[],b=[];for(const p of polys)this.plane.splitPolygon(p,this.polygons,this.polygons,f,b);if(f.length){if(!this.front)this.front=new CSGNode();this.front.build(f)}if(b.length){if(!this.back)this.back=new CSGNode();this.back.build(b)}}}
state.meshToCSG=mesh=>{if(!mesh?.isMesh||!mesh.geometry?.isBufferGeometry)throw new Error('Boolean operands must be Mesh objects with BufferGeometry.');mesh.updateMatrixWorld(true);const g=mesh.geometry,pos=g.getAttribute('position'),normal=g.getAttribute('normal'),uv=g.getAttribute('uv'),idx=g.index,normalMatrix=new T.Matrix3().getNormalMatrix(mesh.matrixWorld),polys=[];if(!pos)throw new Error('Boolean operand has no position attribute.');const tri=Math.floor((idx?.count||pos.count)/3);if(tri>12000)throw new Error('Boolean operand exceeds 12,000 triangles. Generate an LOD or simplify it first.');for(let f=0;f<tri;f++){const vs=[];for(let k=0;k<3;k++){const i=idx?idx.getX(f*3+k):f*3+k,p=new T.Vector3().fromBufferAttribute(pos,i).applyMatrix4(mesh.matrixWorld),n=normal?new T.Vector3().fromBufferAttribute(normal,i).applyMatrix3(normalMatrix).normalize():new T.Vector3(),u=uv?new T.Vector2().fromBufferAttribute(uv,i):null;vs.push(new CSGVertex(p,n,u))}const poly=new CSGPolygon(vs);if(poly.plane)polys.push(poly)}return polys};
state.csgOp=(a,b,mode)=>{let A=new CSGNode(state.meshToCSG(a)),B=new CSGNode(state.meshToCSG(b));if(mode==='union'){A.clipTo(B);B.clipTo(A);B.invert();B.clipTo(A);B.invert();A.build(B.allPolygons());return A.allPolygons()}if(mode==='subtract'){A.invert();A.clipTo(B);B.clipTo(A);B.invert();B.clipTo(A);B.invert();A.build(B.allPolygons());A.invert();return A.allPolygons()}if(mode==='intersect'){A.invert();B.clipTo(A);B.invert();A.clipTo(B);B.clipTo(A);A.build(B.allPolygons());A.invert();return A.allPolygons()}throw new Error('Boolean mode must be union, subtract, or intersect.')};
state.csgGeometry=polys=>{const positions=[],normals=[],uvs=[];for(const p of polys){for(let i=2;i<p.vertices.length;i++){for(const v of [p.vertices[0],p.vertices[i-1],p.vertices[i]]){positions.push(v.pos.x,v.pos.y,v.pos.z);normals.push(v.normal.x,v.normal.y,v.normal.z);if(v.uv)uvs.push(v.uv.x,v.uv.y)}}}if(!positions.length)throw new Error('Boolean operation produced empty geometry.');const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(positions,3));g.setAttribute('normal',new T.Float32BufferAttribute(normals,3));if(uvs.length===positions.length/3*2)g.setAttribute('uv',new T.Float32BufferAttribute(uvs,2));g.computeBoundingBox();g.computeBoundingSphere();return g};
state.applyOp=op=>{const kind=String(op.op||'').toLowerCase();if(kind==='create'){const id=state.uniqueId(op.id),g=state.geometry(op),m=state.material(op.material||op),o=new T.Mesh(g,m);o.name=String(op.name||id);o.userData.darkstarModelId=id;state.applyTransform(o,op);state.ensure().add(o);return {op:kind,id}}if(kind==='transform'){const o=state.find(op.target);state.applyTransform(o,op);return {op:kind,id:state.idOf(o)}}if(kind==='set_dimensions'){const o=state.find(op.target),wanted=vec3(op.dimensions,[1,1,1]),box=new T.Box3().setFromObject(o),cur=new T.Vector3();box.getSize(cur);if(cur.x<=0||cur.y<=0||cur.z<=0)throw new Error('Cannot set dimensions on an empty or flat object.');let s=new T.Vector3(wanted.x/cur.x,wanted.y/cur.y,wanted.z/cur.z);if(op.preserve_aspect){const f=Math.min(s.x,s.y,s.z);s.set(f,f,f)}o.scale.multiply(s);o.updateMatrixWorld(true);return {op:kind,id:state.idOf(o),dimensions:state.measure(o).worldBounds.dimensions}}if(kind==='duplicate'){const src=state.find(op.target),id=state.uniqueId(op.id),c=deepClone(src);state.relabelClone(c,id);c.name=String(op.name||id);state.applyTransform(c,{position:op.offset||op.position||[0,0,0],mode:'add'});(src.parent||state.ensure()).add(c);return {op:kind,id}}if(kind==='array'){const src=state.find(op.target),count=clamp(Math.round(num(op.count,2)),2,100),offset=vec3(op.offset,[1,0,0]),prefix=String(op.id_prefix||`${state.idOf(src)}_copy`),ids=[];for(let i=1;i<count;i++){const id=state.uniqueId(`${prefix}${i}`),c=deepClone(src);state.relabelClone(c,id);c.position.addScaledVector(offset,i);(src.parent||state.ensure()).add(c);ids.push(id)}return {op:kind,ids}}if(kind==='mirror'){const src=state.find(op.target),axis=String(op.axis||'x'),o=op.duplicate===false?src:deepClone(src);if(o!==src){const id=state.uniqueId(op.id);state.relabelClone(o,id);(src.parent||state.ensure()).add(o)}o.scale[axis]*=-1;o.updateMatrixWorld(true);return {op:kind,id:state.idOf(o)}}if(kind==='delete'){const ids=op.targets||[op.target],removed=[];for(const id of ids){const o=state.find(id);if(o===state.root)throw new Error('The model root cannot be deleted.');o.parent?.remove(o);disposeObject(o);removed.push(id)}return {op:kind,removed}}if(kind==='group'){const id=state.uniqueId(op.id),g=new T.Group();g.name=String(op.name||id);g.userData.darkstarModelId=id;state.ensure().add(g);for(const q of op.targets||[])g.attach(state.find(q));return {op:kind,id,children:g.children.map(state.idOf)}}if(kind==='parent'){const o=state.find(op.target),p=state.find(op.parent);if(o===p||o===state.root)throw new Error('Invalid parent operation.');p.attach(o);return {op:kind,id:state.idOf(o),parent:state.idOf(p)}}if(kind==='align'){const o=state.find(op.target),r=state.find(op.relative_to),bo=new T.Box3().setFromObject(o),br=new T.Box3().setFromObject(r),axes=op.axes||['x','y','z'],self=String(op.self_anchor||'center'),other=String(op.other_anchor||'center'),off=vec3(op.offset),delta=new T.Vector3();for(const a of axes)delta[a]=state.anchor(br,a,other)-state.anchor(bo,a,self)+off[a];const wp=o.getWorldPosition(new T.Vector3()).add(delta);if(o.parent)o.parent.worldToLocal(wp);o.position.copy(wp);o.updateMatrixWorld(true);return {op:kind,id:state.idOf(o),position:o.position.toArray()}}if(kind==='material'){const ids=op.targets||[op.target],changed=[];for(const id of ids){const o=state.find(id);o.traverse?.(x=>{if(!x.isMesh)return;x.material=state.material(op);changed.push(state.idOf(x))})}return {op:kind,changed}}if(kind==='repair'){const ids=op.targets||[op.target],results=[];for(const id of ids)results.push(...state.repair(state.find(id),op.fixes));return {op:kind,results}}if(kind==='pivot'){const o=state.find(op.target);if(!o.isMesh||!o.geometry)throw new Error('pivot currently requires a Mesh target.');o.geometry.computeBoundingBox();const b=o.geometry.boundingBox,p=new T.Vector3();if(op.mode==='base')p.set((b.min.x+b.max.x)/2,b.min.y,(b.min.z+b.max.z)/2);else p.copy(b.getCenter(new T.Vector3()));o.geometry.translate(-p.x,-p.y,-p.z);const delta=p.clone().multiply(o.scale).applyQuaternion(o.quaternion);o.position.add(delta);o.geometry.computeBoundingBox();o.geometry.computeBoundingSphere();return {op:kind,id:state.idOf(o),pivot:op.mode==='base'?'base':'center'}}if(kind==='rename'){const o=state.find(op.target);o.name=String(op.name||'').slice(0,160);return {op:kind,id:state.idOf(o),name:o.name}}if(kind==='visibility'){const ids=op.targets||[op.target],visible=op.visible!==false;for(const id of ids)state.find(id).visible=visible;return {op:kind,targets:ids,visible}}if(kind==='generate_uv'){const ids=op.targets||[op.target],results=[];for(const id of ids)results.push(...state.generateUV(state.find(id),String(op.projection||'box'),num(op.uv_scale,1)));return {op:kind,results}}if(kind==='boolean'){const a=state.find(op.target),b=state.find(op.tool),id=state.uniqueId(op.id),polys=state.csgOp(a,b,String(op.mode||'subtract')),g=state.csgGeometry(polys),m=Array.isArray(a.material)?a.material[0].clone():a.material?.clone?.()||state.material(op),o=new T.Mesh(g,m);o.name=String(op.name||id);o.userData.darkstarModelId=id;state.ensure().add(o);if(op.keep_originals!==true){a.parent?.remove(a);b.parent?.remove(b)}return {op:kind,id,mode:String(op.mode||'subtract'),triangles:Math.floor(g.getAttribute('position').count/3)}}if(kind==='lod'){const src=state.find(op.target),id=state.uniqueId(op.id),levels=Array.isArray(op.levels)&&op.levels.length?op.levels:[{distance:0,ratio:1},{distance:40,ratio:.5},{distance:100,ratio:.2}],lod=new T.LOD();lod.name=String(op.name||id);lod.userData.darkstarModelId=id;for(const level of levels.slice(0,8).sort((x,y)=>num(x.distance)-num(y.distance))){const c=state.relabelClone(deepClone(src),`${id}_level${lod.levels.length}`),ratio=clamp(num(level.ratio,1),.03,1);c.traverse?.(x=>{if(x.isMesh&&x.geometry){if(ratio<.999&&Array.isArray(x.material)&&x.material.length>1)throw new Error('LOD simplification does not support meshes with multiple materials.');x.geometry=state.simplify(x.geometry,ratio)}});lod.addLevel(c,Math.max(0,num(level.distance,0)))}(src.parent||state.ensure()).add(lod);if(op.keep_original!==true)src.parent?.remove(src);return {op:kind,id,levels:lod.levels.map(x=>({distance:x.distance}))}}if(kind==='collision'){const src=state.find(op.target),id=state.uniqueId(op.id),type=String(op.collision_type||'box'),box=new T.Box3().setFromObject(src),size=box.getSize(new T.Vector3()),center=box.getCenter(new T.Vector3()),mat=new T.MeshBasicMaterial({color:op.color||0x00ff88,wireframe:true,transparent:true,opacity:num(op.opacity,.45),depthWrite:false}),group=new T.Group();group.name=String(op.name||id);group.userData.darkstarModelId=id;group.userData.darkstarCollision=true;const addBox=(b)=>{const s=b.getSize(new T.Vector3()),c=b.getCenter(new T.Vector3()),mesh=new T.Mesh(new T.BoxGeometry(s.x,s.y,s.z),mat.clone());mesh.position.copy(c);group.add(mesh)};if(type==='box')addBox(box);else if(type==='sphere'){const sphere=box.getBoundingSphere(new T.Sphere()),mesh=new T.Mesh(new T.SphereGeometry(sphere.radius,20,12),mat.clone());mesh.position.copy(sphere.center);group.add(mesh)}else if(type==='capsule'){if(!T.CapsuleGeometry)throw new Error('CapsuleGeometry is unavailable.');const radius=Math.max(.001,Math.min(size.x,size.z)/2),height=Math.max(.001,size.y-2*radius),mesh=new T.Mesh(new T.CapsuleGeometry(radius,height,8,16),mat.clone());mesh.position.copy(center);group.add(mesh)}else if(type==='compound_boxes'){const candidates=[];src.traverse?.(x=>{if(x.isMesh)candidates.push(x)});for(const x of candidates.slice(0,clamp(Math.round(num(op.max_shapes,12)),1,32)))addBox(new T.Box3().setFromObject(x))}else throw new Error('collision_type must be box, sphere, capsule, or compound_boxes.');state.ensure().add(group);return {op:kind,id,type,shapes:group.children.length,dimensions:size.toArray()}}throw new Error(`Unsupported modeling operation: ${kind}`)};
state.renderOnce=()=>{const d=globalThis.__DARKSTAR_THREE_DEBUG__,r=d?.lastRenderer,c=d?.lastCamera,s=d?.lastScene||state.scene;try{if(r&&c&&s)r.render(s,c)}catch(_){}};
state.apply=ops=>{if(!Array.isArray(ops)||!ops.length)throw new Error('operations must contain at least one operation.');if(ops.length>64)throw new Error('A modeling batch may contain at most 64 operations.');state.ensure();state.pushUndo();const before=state.recipe.length,results=[];try{for(const op of ops)results.push(state.applyOp(op));state.recipe.push(...plain(ops));state.renderOnce();return {success:true,action:'threejs_model',modelAction:'apply',operationCount:ops.length,results,recipeLength:state.recipe.length,status:state.status()}}catch(e){const snap=state.undoStack.pop();if(snap)state.restore(snap);state.recipe.splice(before);return {success:false,action:'threejs_model',modelAction:'apply',error:String(e?.message||e),failedOperation:ops[results.length]||null,rolledBack:true}}};
state.status=()=>{let root=null;try{root=state.ensure()}catch(e){return {success:false,action:'threejs_model',modelAction:'status',initialized:true,error:String(e?.message||e)}}let objects=0,meshes=0,triangles=0;root.traverse(o=>{objects++;if(o.isMesh){meshes++;const p=o.geometry?.getAttribute?.('position'),i=o.geometry?.index;triangles+=Math.floor((i?.count||p?.count||0)/3)}});return {success:true,action:'threejs_model',modelAction:'status',version:state.version,scene:{name:state.scene.name||'',uuid:state.scene.uuid},root:{uuid:root.uuid,children:root.children.length},objects,meshes,triangles,recipeLength:state.recipe.length,undoDepth:state.undoStack.length,redoDepth:state.redoStack.length,viewActive:!!state.viewState}};
state.undo=()=>{if(!state.undoStack.length)return {success:false,action:'threejs_model',modelAction:'undo',error:'Nothing to undo.'};state.redoStack.push(state.snapshot());state.restore(state.undoStack.pop());state.renderOnce();return state.status()};
state.redo=()=>{if(!state.redoStack.length)return {success:false,action:'threejs_model',modelAction:'redo',error:'Nothing to redo.'};state.undoStack.push(state.snapshot());state.restore(state.redoStack.pop());state.renderOnce();return state.status()};
state.clearHelpers=()=>{if(state.helpers){state.helpers.parent?.remove(state.helpers);disposeObject(state.helpers);state.helpers=null}};
state.restoreView=()=>{if(!state.viewState)return {success:false,action:'threejs_model',modelAction:'restore_view',error:'No technical view is active.'};const v=state.viewState,c=v.camera;c.position.fromArray(v.position);c.quaternion.fromArray(v.quaternion);c.up.fromArray(v.up);if(v.zoom!==undefined)c.zoom=v.zoom;if(v.left!==undefined){c.left=v.left;c.right=v.right;c.top=v.top;c.bottom=v.bottom}c.updateProjectionMatrix?.();for(const [m,w] of v.wireframes)m.wireframe=w;state.clearHelpers();state.viewState=null;state.renderOnce();return {success:true,action:'threejs_model',modelAction:'restore_view'}};
state.view=(id,view,overlays)=>{if(state.viewState)state.restoreView();const target=state.find(id),d=globalThis.__DARKSTAR_THREE_DEBUG__,camera=d?.lastCamera;if(!camera)throw new Error('No active camera was captured. Render at least one frame first.');const box=new T.Box3().setFromObject(target),center=box.getCenter(new T.Vector3()),size=box.getSize(new T.Vector3()),span=Math.max(size.x,size.y,size.z,.01),dirs={front:[0,0,1],back:[0,0,-1],left:[-1,0,0],right:[1,0,0],top:[0,1,0],bottom:[0,-1,0],isometric:[1,1,1]},dir=vec3(dirs[view]||dirs.isometric).normalize(),distance=span*2.4;state.viewState={camera,position:camera.position.toArray(),quaternion:camera.quaternion.toArray(),up:camera.up.toArray(),zoom:camera.zoom,left:camera.left,right:camera.right,top:camera.top,bottom:camera.bottom,wireframes:[]};camera.position.copy(center).addScaledVector(dir,distance);camera.up.set(0,1,0);if(view==='top'||view==='bottom')camera.up.set(0,0,view==='top'?-1:1);camera.lookAt(center);if(camera.isPerspectiveCamera){camera.near=Math.max(.001,distance-span*2);camera.far=Math.max(camera.near+10,distance+span*3)}else if(camera.isOrthographicCamera){const aspect=innerWidth/Math.max(1,innerHeight);camera.left=-span*aspect*.75;camera.right=span*aspect*.75;camera.top=span*.75;camera.bottom=-span*.75;camera.zoom=1}camera.updateProjectionMatrix?.();const helper=new T.Group();helper.name='__DARKSTAR_MODEL_HELPERS__';const set=new Set(overlays||[]);if(set.has('wireframe'))target.traverse(o=>{for(const m of (Array.isArray(o.material)?o.material:[o.material]).filter(Boolean)){state.viewState.wireframes.push([m,m.wireframe]);m.wireframe=true}});if(set.has('bounds'))helper.add(new T.Box3Helper(box,0xffff00));if(set.has('axes')){const h=new T.AxesHelper(span*.65);h.position.copy(center);helper.add(h)}if(set.has('grid')){const h=new T.GridHelper(span*2,20);h.position.set(center.x,box.min.y,center.z);helper.add(h)}if(set.has('pivots'))target.traverse(o=>{if(o===target||o.isMesh){const h=new T.AxesHelper(span*.12);h.position.copy(o.getWorldPosition(new T.Vector3()));helper.add(h)}});if(set.has('edges'))target.traverse(o=>{if(!o.isMesh||!o.geometry)return;const e=new T.LineSegments(new T.EdgesGeometry(o.geometry),new T.LineBasicMaterial({color:0xffffff}));e.matrix.copy(o.matrixWorld);e.matrixAutoUpdate=false;helper.add(e)});state.scene.add(helper);state.helpers=helper;state.renderOnce();return {success:true,action:'threejs_model',modelAction:'view',view,target:state.idOf(target),center:center.toArray(),dimensions:size.toArray(),overlays:Array.from(set),guidance:'Call screenshot next, then restore_view when finished.'}};
state.cleanup=()=>{if(state.viewState)state.restoreView();const root=state.ensure();root.parent?.remove(root);disposeObject(root);state.root=null;state.recipe=[];for(const s of [...state.undoStack,...state.redoStack])disposeObject(s.root);state.undoStack=[];state.redoStack=[];return {success:true,action:'threejs_model',modelAction:'cleanup'}};
state.command=cmd=>{const a=cmd.modelAction;if(a==='status')return state.status();if(a==='apply')return state.apply(cmd.operations);if(a==='inspect')return state.inspect(cmd.target,!!cmd.deep);if(a==='undo')return state.undo();if(a==='redo')return state.redo();if(a==='view')return state.view(cmd.target,cmd.view,cmd.overlays);if(a==='restore_view')return state.restoreView();if(a==='export_recipe')return {success:true,action:'threejs_model',modelAction:'export_recipe',recipe:plain(state.recipe),operationCount:state.recipe.length,modelRoot:state.measure(state.ensure())};if(a==='cleanup')return state.cleanup();throw new Error(`Unsupported model action: ${a}`)};
globalThis.__DARKSTAR_THREE_MODELER__=state;
return state.status();
"""



def _model_help() -> dict[str, Any]:
    return {
        "success": True,
        "action": "threejs_model",
        "model_action": "help",
        "workflow": [
            "Open the HTML with threejs_open_debug and allow one rendered frame.",
            "Call threejs_model/init once.",
            "Call threejs_model/apply with one or more operations; batches are atomic.",
            "Use inspect and technical view + screenshot to verify shape and topology.",
            "Use undo/redo while refining.",
            "Call export_recipe, then commit_recipe with that recipe and the original HTML path.",
            "Open the original HTML and run threejs_audit after committing.",
        ],
        "operations": {
            "create": {
                "required": ["op=create", "id", "primitive"],
                "primitives": ["box", "sphere", "cylinder", "cone", "plane", "circle", "ring", "torus", "capsule", "lathe", "extrude", "tube"],
                "common": ["size", "radius", "height", "position", "rotation_deg", "scale", "preset", "color"],
                "example": {"op": "create", "id": "hull", "primitive": "box", "size": [4, 1, 6], "position": [0, 0.5, 0], "preset": "painted_metal", "color": "#526b45"},
            },
            "transform": {"required": ["target"], "fields": ["position", "rotation_deg", "scale", "mode=set|add|multiply"], "example": {"op": "transform", "target": "turret", "rotation_deg": [0, 30, 0]}},
            "set_dimensions": {"required": ["target", "dimensions"], "optional": ["preserve_aspect"], "example": {"op": "set_dimensions", "target": "tank", "dimensions": [4, 2.5, 7], "preserve_aspect": True}},
            "duplicate": {"required": ["target", "id"], "optional": ["offset", "name"]},
            "array": {"required": ["target", "count", "offset"], "optional": ["id_prefix"], "limit": 100},
            "mirror": {"required": ["target", "axis=x|y|z"], "optional": ["duplicate", "id"]},
            "delete": {"required": ["target or targets"]},
            "group": {"required": ["id", "targets"], "notes": "Preserves world transforms."},
            "parent": {"required": ["target", "parent"], "notes": "Preserves world transform."},
            "align": {"required": ["target", "relative_to"], "optional": ["axes", "self_anchor=min|center|max", "other_anchor=min|center|max", "offset"]},
            "material": {"required": ["target or targets"], "presets": ["matte", "painted_metal", "bare_metal", "rubber", "plastic", "glass", "emissive", "unlit", "wireframe"], "optional": ["color", "metalness", "roughness", "opacity", "emissive", "emissive_intensity", "side"]},
            "repair": {"required": ["target or targets"], "fixes": ["remove_degenerate_triangles", "weld_vertices", "recompute_normals", "normalize_normals", "recompute_bounds", "center_geometry", "flip_winding", "bake_transform"]},
            "pivot": {"required": ["target"], "modes": ["center", "base"], "notes": "Currently supports Mesh targets."},
            "rename": {"required": ["target", "name"]},
            "visibility": {"required": ["target or targets", "visible"]},
            "generate_uv": {"required": ["target or targets"], "projections": ["box", "planar", "planar_xy", "planar_xz", "planar_yz", "cylindrical", "spherical"], "optional": ["uv_scale"]},
            "boolean": {"required": ["target", "tool", "id"], "modes": ["union", "subtract", "intersect"], "optional": ["keep_originals"], "limits": "Static BufferGeometry meshes only; maximum 12,000 triangles per operand."},
            "lod": {"required": ["target", "id"], "optional": ["levels=[{distance,ratio}]", "keep_original"], "notes": "Creates THREE.LOD with deterministic vertex-cluster simplification."},
            "collision": {"required": ["target", "id"], "types": ["box", "sphere", "capsule", "compound_boxes"], "optional": ["collision_type", "max_shapes", "color", "opacity"]},
        },
        "technical_views": {"views": ["front", "back", "left", "right", "top", "bottom", "isometric"], "overlays": ["wireframe", "bounds", "edges", "axes", "pivots", "grid"]},
        "limits": {"operations_per_batch": 64, "undo_snapshots": 24, "modeling_scope": "Objects inside __DARKSTAR_MODEL_ROOT__ only"},
    }


def _model_command_script(args: dict[str, Any]) -> str:
    model_action = str(args.get("model_action") or "").strip().lower()
    allowed = {"init", "apply", "status", "inspect", "undo", "redo", "view", "restore_view", "export_recipe", "cleanup"}
    if model_action not in allowed:
        raise ValueError("model_action must be one of: " + ", ".join(sorted(allowed | {"commit_recipe"})))
    if model_action == "init":
        return _MODELER_INSTALL_SCRIPT
    command: dict[str, Any] = {"modelAction": model_action}
    if model_action == "apply":
        command["operations"] = _validate_model_operations(args.get("operations"))
    if model_action in {"inspect", "view"} and args.get("target"):
        command["target"] = str(args["target"])
    if model_action == "inspect":
        command["deep"] = args.get("deep") is True
    if model_action == "view":
        view = str(args.get("view") or "isometric")
        if view not in {"front", "back", "left", "right", "top", "bottom", "isometric"}:
            raise ValueError("view must be front, back, left, right, top, bottom, or isometric")
        command["view"] = view
        command["overlays"] = list(args.get("overlays") or [])
    payload = json.dumps(command, ensure_ascii=False, separators=(",", ":"))
    return (
        "const M=globalThis.__DARKSTAR_THREE_MODELER__;"
        "if(!M)return {success:false,action:'threejs_model',error:'Modeler is not initialized. Call action=threejs_model with model_action=init first.'};"
        f"return M.command({payload})"
    )


def _validate_model_operations(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("operations must be a non-empty array")
    if len(raw) > 64:
        raise ValueError("operations may contain at most 64 entries")
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"operations[{index}] must be an object")
        op = str(item.get("op") or "").strip().lower()
        if op not in MODEL_OPERATION_NAMES:
            raise ValueError(f"operations[{index}].op is unsupported: {op or '<missing>'}")
        encoded = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 32 * 1024:
            raise ValueError(f"operations[{index}] is too large")
        cleaned.append(_json_safe(item))
    total = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(total) > MAX_MODEL_RECIPE_BYTES:
        raise ValueError("The complete modeling recipe is too large")
    return cleaned


def _model_marker(model_id: str) -> tuple[str, str]:
    return (f"<!-- {MODEL_RECIPE_BEGIN}:{model_id} -->", f"<!-- {MODEL_RECIPE_END}:{model_id} -->")


def _committed_model_script(model_id: str, operations: list[dict[str, Any]]) -> str:
    recipe = json.dumps(operations, ensure_ascii=False, separators=(",", ":"))
    # The model is attached on the first renderer.render(scene, camera), so this
    # works even when the page keeps `scene` in a top-level const rather than on window.
    runtime = _MODELER_INSTALL_SCRIPT
    return f"""<script data-darkstar-model={json.dumps(model_id)}>
(()=>{{
'use strict';
const MODEL_ID={json.dumps(model_id)};
const RECIPE={recipe};
let applied=false;
const applyToScene=(scene)=>{{
  if(applied||!scene?.isScene||!globalThis.THREE)return;
  applied=true;
  try{{
    const d=globalThis.__DARKSTAR_THREE_DEBUG__||(globalThis.__DARKSTAR_THREE_DEBUG__={{scenes:[],lastScene:null}});
    d.lastScene=scene;if(!d.scenes)d.scenes=[];if(!d.scenes.includes(scene))d.scenes.push(scene);
    const install=function(){{{runtime}}};
    install();
    const result=globalThis.__DARKSTAR_THREE_MODELER__.apply(RECIPE);
    globalThis.__DARKSTAR_COMMITTED_MODELS__=globalThis.__DARKSTAR_COMMITTED_MODELS__||{{}};
    globalThis.__DARKSTAR_COMMITTED_MODELS__[MODEL_ID]=result;
    if(!result.success)console.error('Darkstar model recipe failed',MODEL_ID,result);
  }}catch(error){{console.error('Darkstar model commit failed',MODEL_ID,error);}}
}};
for(const key of Object.getOwnPropertyNames(globalThis).slice(0,900)){{let value;try{{value=globalThis[key]}}catch(_){{continue}}if(value?.isScene){{applyToScene(value);break;}}}}
const R=globalThis.THREE?.WebGLRenderer?.prototype;
if(!applied&&R&&typeof R.render==='function'){{
  const original=R.render;
  const wrapped=function(scene,camera){{applyToScene(scene);return original.call(this,scene,camera)}};
  wrapped.__darkstarModelCommit=true;wrapped.__darkstarOriginal=original;R.render=wrapped;
}}
}})();
</script>"""


def _commit_model_recipe(args: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    operations = _validate_model_operations(args.get("operations"))
    model_id = str(args.get("model_id") or "model").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", model_id):
        raise ValueError("model_id must start with a letter and contain only letters, numbers, underscore, or hyphen")
    root, path, display = _resolve_html(args.get("path"), kwargs)
    source = _read_html(path)
    expected = args.get("expected_sha256")
    before_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if expected and str(expected).lower() != before_hash:
        raise ValueError(f"SHA-256 conflict for {display}: expected {expected}, found {before_hash}")
    begin, end = _model_marker(model_id)
    block = begin + "\n" + _committed_model_script(model_id, operations) + "\n" + end
    pattern = re.compile(re.escape(begin) + r"[\s\S]*?" + re.escape(end))
    if pattern.search(source):
        updated = pattern.sub(lambda _match: block, source, count=1)
        mode = "replaced"
    else:
        head = re.search(r"<head\b[^>]*>", source, re.IGNORECASE)
        if head:
            updated = source[:head.end()] + "\n" + block + source[head.end():]
        else:
            first_script = re.search(r"<script\b", source, re.IGNORECASE)
            at = first_script.start() if first_script else 0
            updated = source[:at] + block + "\n" + source[at:]
        mode = "inserted"
    encoded = updated.encode("utf-8")
    if len(encoded) > MAX_HTML_BYTES:
        raise ValueError("Committed HTML would exceed the browser tool's maximum HTML size")
    temporary = path.with_name(path.name + f".tmp-model-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    after_hash = hashlib.sha256(encoded).hexdigest()
    return {
        "success": True,
        "action": "threejs_model",
        "model_action": "commit_recipe",
        "path": display,
        "model_id": model_id,
        "mode": mode,
        "operation_count": len(operations),
        "sha256_before": before_hash,
        "sha256_after": after_hash,
        "bytes": len(encoded),
        "guidance": "Open the original HTML with Browser Control and run threejs_audit to verify the committed model.",
    }

def _replace_token(template: str, token: str, value: Any) -> str:
    return template.replace(token, json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _audit_script(args: dict[str, Any]) -> str:
    detail = str(args.get("detail") or "standard")
    if detail not in {"summary", "standard", "deep"}:
        raise ValueError("detail must be summary, standard, or deep")
    object_limit = args.get("object_limit", 24)
    if isinstance(object_limit, bool) or not isinstance(object_limit, int) or not 1 <= object_limit <= 40:
        raise ValueError("object_limit must be an integer from 1 to 40")
    options = {"detail": detail, "objectLimit": object_limit, "compileShaders": args.get("compile_shaders") is True}
    return _replace_token(_LIVE_AUDIT_TEMPLATE, "__OPTIONS__", options)


def _profile_script(args: dict[str, Any]) -> str:
    duration = args.get("duration_ms", 2000)
    if isinstance(duration, bool) or not isinstance(duration, int) or not 250 <= duration <= 5000:
        raise ValueError("threejs_profile duration_ms must be an integer from 250 to 5000")
    return _replace_token(_PROFILE_TEMPLATE, "__DURATION__", duration)


def _object_script(args: dict[str, Any]) -> str:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required for threejs_object")
    limit = args.get("object_limit", 20)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 40:
        raise ValueError("object_limit must be an integer from 1 to 40")
    script = _replace_token(_OBJECT_TEMPLATE, "__QUERY__", query)
    return _replace_token(script, "__LIMIT__", limit)


def _evaluate_request(script: str, *, snapshot_after: bool = False) -> dict[str, Any]:
    if len(script) > 64_000:
        raise ValueError(f"Generated Three.js diagnostic script is too large ({len(script)} characters)")
    return {
        "__darkstarAction": "browser_control",
        "action": "evaluate",
        "script": script,
        "snapshot_after": snapshot_after,
    }


def handler(args: dict[str, Any], **kwargs: Any) -> Any:
    action = str(args.get("action") or "").strip().lower()
    if action not in ACTIONS:
        raise ValueError("action must be one of: " + ", ".join(ACTIONS))

    raw_path = args.get("path")
    raw_url = args.get("url")
    has_path = isinstance(raw_path, str) and bool(raw_path.strip())
    has_url = isinstance(raw_url, str) and bool(raw_url.strip())
    if action == "open":
        if has_path == has_url:
            raise ValueError("action='open' requires exactly one of path or url")
        if has_url:
            _validated_online_url(raw_url)
    elif raw_url is not None:
        raise ValueError("url is supported only for action='open'")

    if action in {"get_element_coordinates", "scroll_into_view"} and not args.get("ref"):
        raise ValueError(f"ref is required for action='{action}'")
    if action in {"hit_test", "inspect_at_point"} and (args.get("x") is None or args.get("y") is None):
        raise ValueError(f"x and y are required for action='{action}'")
    if action == "grid_overlay" and not args.get("grid_id"):
        raise ValueError("grid_id is required for grid_overlay; call grid_inspect first")
    if action == "grid_click" and (not args.get("grid_id") or not args.get("cell")):
        raise ValueError("grid_id and cell are required for grid_click")
    if action == "grid_drag" and (not args.get("grid_id") or not args.get("from_cell") or not args.get("to_cell")):
        raise ValueError("grid_id, from_cell, and to_cell are required for grid_drag")

    has_timer = args.get("timer_ms") is not None
    has_legacy_wait = args.get("wait_ms") is not None
    if has_timer and has_legacy_wait:
        raise ValueError("Provide timer_ms or wait_ms, not both")
    timer_ms = None
    if has_timer:
        timer_ms = _validated_timer(args["timer_ms"], "timer_ms")
    elif has_legacy_wait:
        timer_ms = _validated_timer(args["wait_ms"], "wait_ms")

    if action == "threejs_source_audit":
        return _source_audit(args.get("path"), kwargs, include_info=args.get("include_info") is True)
    if action == "threejs_open_debug":
        return _open_debug(args.get("path"), kwargs, timer_ms)
    if action == "threejs_cleanup_debug":
        return _cleanup_debug(args.get("path"), kwargs)
    if action == "threejs_debug_status":
        return _evaluate_request(_DEBUG_STATUS_SCRIPT)
    if action == "threejs_audit":
        return _evaluate_request(_audit_script(args))
    if action == "threejs_profile":
        return _evaluate_request(_profile_script(args))
    if action == "threejs_object":
        return _evaluate_request(_object_script(args))
    if action == "threejs_model":
        model_action = str(args.get("model_action") or "").strip().lower()
        if model_action == "help":
            return _model_help()
        if model_action == "commit_recipe":
            return _commit_model_recipe(args, kwargs)
        return _evaluate_request(_model_command_script(args))

    if timer_ms is not None and action not in TIMER_ACTIONS:
        supported = ", ".join(sorted(TIMER_ACTIONS))
        raise ValueError(f"timer_ms is not supported for action '{action}'. Use action='wait' or one of: {supported}")

    request: dict[str, Any] = {"__darkstarAction": "browser_control", "action": action}
    debug_only = {"detail", "compile_shaders", "object_limit", "query", "include_info", "model_action", "operations", "target", "model_id", "view", "overlays", "deep", "expected_sha256"}
    for key, value in args.items():
        if key in {"action", "timer_ms", "wait_ms"} or key in debug_only or value is None:
            continue
        request[key] = _json_safe(value)
    if timer_ms is not None:
        request["wait_ms"] = timer_ms
    return request


registry.register(
    name=SCHEMA["name"],
    toolset="browser",
    schema=SCHEMA,
    handler=handler,
    description=DESCRIPTION,
)
