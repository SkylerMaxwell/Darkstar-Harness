# SPDX-License-Identifier: GPL-3.0-only
"""Darkstar tool: inspect only Node, Electron, and Three.js compatibility facts."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.registry import registry

PROVIDER_ID = "threejs-inspection"
PROVIDER_NAME = "ThreeJS Inspection"

_MAX_JSON_BYTES = 1_000_000
_MAX_TEXT_BYTES = 12_000_000
_PROBE_TIMEOUT_SECONDS = 4.0

SCHEMA = {
    "name": "inspect_threejs_environment",
    "description": (
        "Return a compact, read-only compatibility report for Node.js, Electron, and Three.js in the "
        "current Darkstar installation and active project. Use it before writing or debugging Three.js "
        "software to learn the exact available revisions, Node/Electron/Chromium runtime versions, module "
        "format, package availability, browser preload mode, offline loading behavior, and whether common "
        "Three.js addons are bundled. It performs no network requests, modifies no files, and omits paths, "
        "machine identity, credentials, and unrelated system details."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


def _read_text(path: Path, max_bytes: int = _MAX_TEXT_BYTES) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError):
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    text = _read_text(path, _MAX_JSON_BYTES)
    if text is None:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _safe_root(value: Any) -> Path | None:
    if not value:
        return None
    try:
        candidate = Path(str(value)).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate if candidate.is_dir() else None


def _workspace_root(context: dict[str, Any]) -> Path:
    return _safe_root(context.get("workspace")) or Path.cwd().resolve(strict=False)


def _host_root(context: dict[str, Any], workspace: Path) -> Path | None:
    skills_root = _safe_root(context.get("skills_root"))
    if skills_root and skills_root.name == "skills" and skills_root.parent.name == "agent_assets":
        candidate = skills_root.parent.parent
        if (candidate / "backend" / "shell" / "package.json").is_file():
            return candidate

    candidates: list[Path] = []
    tool_path = Path(__file__).resolve(strict=False)
    candidates.extend(tool_path.parents[:5])
    candidates.extend([workspace, *workspace.parents[:3]])
    for candidate in candidates:
        if (
            (candidate / "backend" / "shell" / "package.json").is_file()
            and (candidate / "backend" / "browser" / "offline-browser-service.js").is_file()
            and (candidate / "agent_assets").is_dir()
        ):
            return candidate
    return None


def _dependency(package: dict[str, Any] | None, name: str) -> dict[str, str] | None:
    if not package:
        return None
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        values = package.get(section)
        if isinstance(values, dict) and name in values:
            return {"section": section, "specifier": str(values[name])}
    return None


def _lockfile(root: Path) -> str | None:
    for filename, manager in (
        ("package-lock.json", "npm"),
        ("npm-shrinkwrap.json", "npm"),
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("bun.lock", "bun"),
        ("bun.lockb", "bun"),
    ):
        if (root / filename).is_file():
            return manager
    return None


def _package_manager(package: dict[str, Any] | None, root: Path) -> str | None:
    declared = str((package or {}).get("packageManager") or "").strip()
    if declared:
        return declared
    locked = _lockfile(root)
    if locked:
        return locked
    return "npm" if ((root / "package.json").is_file() or (root / "backend" / "shell" / "package.json").is_file()) else None


def _flatten_export_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_flatten_export_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_flatten_export_keys(child))
    return keys


def _installed_package(root: Path, package_name: str) -> dict[str, Any] | None:
    parts = package_name.split("/")
    package_path = root / "node_modules"
    for part in parts:
        package_path /= part
    package = _read_json(package_path / "package.json")
    if not package:
        return None

    exports = package.get("exports")
    export_keys = _flatten_export_keys(exports)
    return {
        "version": str(package.get("version") or "") or None,
        "package_type": str(package.get("type") or "commonjs"),
        "main": str(package.get("main") or "") or None,
        "module": str(package.get("module") or "") or None,
        "supports_import_condition": "import" in export_keys,
        "supports_require_condition": "require" in export_keys,
        "supports_addons_alias": "./addons/*" in export_keys,
        "supports_examples_jsm_alias": "./examples/jsm/*" in export_keys,
    }


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT_SECONDS,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _node_probe(root: Path) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        return {"available": False}

    script = r"""
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
(async () => {
  const output = {
    version: process.version,
    major: Number(process.versions.node.split('.')[0]),
    platform: process.platform,
    architecture: process.arch,
    module_abi: process.versions.modules || null,
    napi: process.versions.napi || null,
    v8: process.versions.v8 || null,
    three: { importable: false }
  };
  try {
    const resolved = require.resolve('three', { paths: [process.cwd()] });
    const imported = await import(pathToFileURL(resolved).href);
    const three = imported && imported.default && imported.default.REVISION ? imported.default : imported;
    output.three = {
      importable: true,
      revision: String(three.REVISION || ''),
      webgl_renderer_exported: typeof three.WebGLRenderer === 'function',
      webgpu_renderer_exported: typeof three.WebGPURenderer === 'function'
    };
  } catch (error) {
    output.three = {
      importable: false,
      error_code: String(error && (error.code || error.name) || 'IMPORT_FAILED')
    };
  }
  process.stdout.write(JSON.stringify(output));
})().catch(() => process.stdout.write(JSON.stringify({ probe_failed: true })));
"""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "NO_COLOR": "1",
    }
    completed = _run([node, "-e", script], cwd=root, env=env)
    if not completed or completed.returncode != 0:
        return {"available": True, "probe_failed": True}
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"available": True, "probe_failed": True}
    return {"available": True, **parsed} if isinstance(parsed, dict) else {"available": True, "probe_failed": True}


def _electron_runtime_probe(root: Path) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        return {"available": False}

    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "NO_COLOR": "1",
    }
    locator = _run(
        [node, "-e", "try{const p=require('electron');if(typeof p==='string')process.stdout.write(p)}catch(_){}"],
        cwd=root,
        env=env,
    )
    if not locator or locator.returncode != 0 or not locator.stdout.strip():
        return {"available": False}

    binary = Path(locator.stdout.strip())
    try:
        if not binary.is_file():
            return {"available": False}
    except OSError:
        return {"available": False}

    electron_env = dict(env)
    electron_env["ELECTRON_RUN_AS_NODE"] = "1"
    probe = _run(
        [str(binary), "-e", "process.stdout.write(JSON.stringify(process.versions))"],
        cwd=root,
        env=electron_env,
    )
    if not probe or probe.returncode != 0:
        return {"available": True, "probe_failed": True}
    try:
        versions = json.loads(probe.stdout)
    except json.JSONDecodeError:
        return {"available": True, "probe_failed": True}
    if not isinstance(versions, dict):
        return {"available": True, "probe_failed": True}
    return {
        "available": True,
        "electron": str(versions.get("electron") or "") or None,
        "chromium": str(versions.get("chrome") or "") or None,
        "embedded_node": str(versions.get("node") or "") or None,
        "v8": str(versions.get("v8") or "") or None,
        "module_abi": str(versions.get("modules") or "") or None,
        "napi": str(versions.get("napi") or "") or None,
    }


def _project_summary(root: Path) -> dict[str, Any]:
    package = _read_json(root / "package.json") or _read_json(root / "backend" / "shell" / "package.json")
    node = _node_probe(root)
    installed_three = _installed_package(root, "three")
    installed_types = _installed_package(root, "@types/three")
    installed_electron = _installed_package(root, "electron")

    return {
        "package_json": package is not None,
        "module_system": "esm" if str((package or {}).get("type") or "").lower() == "module" else "commonjs",
        "node_engine": str(((package or {}).get("engines") or {}).get("node") or "") or None,
        "package_manager": _package_manager(package, root),
        "three": {
            "declared": _dependency(package, "three"),
            "installed": installed_three,
            "node_import": node.get("three") if isinstance(node.get("three"), dict) else {"importable": False},
        },
        "types_three": {
            "declared": _dependency(package, "@types/three"),
            "installed_version": (installed_types or {}).get("version"),
        },
        "electron": {
            "declared": _dependency(package, "electron"),
            "installed_version": (installed_electron or {}).get("version"),
        },
    }


def _extract_revision_from_spec(specifier: str | None) -> str | None:
    if not specifier:
        return None
    match = re.search(r"(?:^|[^0-9])0\.(\d+)\.(?:\d+|x)(?:[^0-9]|$)", specifier)
    return match.group(1) if match else None


def _browser_runtime(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {"available": False}

    vendor_root = root / "vendor" / "three"
    revision_dirs: list[tuple[int, Path]] = []
    try:
        if vendor_root.is_dir():
            for candidate in vendor_root.iterdir():
                match = re.fullmatch(r"r(\d+)", candidate.name)
                if match and candidate.is_dir() and not candidate.is_symlink():
                    revision_dirs.append((int(match.group(1)), candidate))
    except OSError:
        revision_dirs = []

    if not revision_dirs:
        return {"available": False}

    revision_number, runtime_root = max(revision_dirs, key=lambda item: item[0])
    global_path = runtime_root / "three.global.js"
    global_source = _read_text(global_path) or ""
    service_source = _read_text(root / "backend" / "browser" / "offline-browser-service.js", 4_000_000) or ""

    assets = {
        "global_bundle": global_path.is_file(),
        "esm_bundle": (runtime_root / "three.module.min.js").is_file(),
        "core_bundle": (runtime_root / "three.core.js").is_file(),
        "preload": (runtime_root / "three.preload.js").is_file(),
    }
    def is_exported(name: str) -> bool:
        return bool(re.search(r"(?:^|[,\{])" + re.escape(name) + r":", global_source))

    exports = {
        "WebGLRenderer": is_exported("WebGLRenderer"),
        "WebGPURenderer": is_exported("WebGPURenderer"),
        "OrbitControls": is_exported("OrbitControls"),
        "GLTFLoader": is_exported("GLTFLoader"),
        "EffectComposer": is_exported("EffectComposer"),
    }
    addons_bundled = any((runtime_root / name).exists() for name in ("addons", "examples", "jsm"))

    return {
        "available": all((assets["global_bundle"], assets["preload"])),
        "revision": str(revision_number),
        "exposure": "window.THREE",
        "mode": "document-start" if "mode: 'document-start'" in service_source else "preload",
        "offline": "NETWORK_PROTOCOLS" in service_source and "callback({ cancel: true })" in service_source,
        "common_cdn_urls_redirect_to_packaged_runtime": (
            "_threeRedirect" in service_source
            and "unpkg" in service_source
            and "jsdelivr" in service_source
        ),
        "configured_as_browser_preload": "preload: this.threePreloadPath" in service_source,
        "assets": assets,
        "exports": exports,
        "addons_directory_bundled": addons_bundled,
    }


def _alignment(host_project: dict[str, Any] | None, browser: dict[str, Any]) -> dict[str, Any]:
    sources: dict[str, str] = {}
    browser_revision = str(browser.get("revision") or "")
    if browser_revision:
        sources["browser_runtime"] = browser_revision

    if host_project:
        declared = ((host_project.get("three") or {}).get("declared") or {}).get("specifier")
        declared_revision = _extract_revision_from_spec(str(declared or ""))
        if declared_revision:
            sources["declared_package"] = declared_revision

        installed = ((host_project.get("three") or {}).get("installed") or {}).get("version")
        installed_revision = _extract_revision_from_spec(str(installed or ""))
        if installed_revision:
            sources["installed_package"] = installed_revision

        node_import = (host_project.get("three") or {}).get("node_import") or {}
        imported_revision = str(node_import.get("revision") or "")
        if imported_revision:
            sources["node_import"] = imported_revision

    unique = sorted(set(sources.values()), key=lambda value: int(value) if value.isdigit() else value)
    if not unique:
        status = "unknown"
    elif len(sources) == 1:
        status = "single_source"
    elif len(unique) == 1:
        status = "aligned"
    else:
        status = "mismatch"
    return {"status": status, "revisions": sources}


def _compatibility_rules(
    host_project: dict[str, Any] | None,
    workspace_project: dict[str, Any],
    browser: dict[str, Any],
    alignment: dict[str, Any],
) -> list[str]:
    rules: list[str] = []
    if browser.get("available"):
        rules.append(
            f"Browser preview code can use window.THREE revision {browser.get('revision')}; remote CDN access is not required."
        )
        if not browser.get("addons_directory_bundled"):
            rules.append(
                "OrbitControls, GLTFLoader, EffectComposer, and other Three.js addons are not bundled by default; package or vendor each addon explicitly."
            )
    workspace_import = (workspace_project.get("three") or {}).get("node_import") or {}
    if workspace_import.get("importable"):
        rules.append(
            f"Node code in the active project can import three revision {workspace_import.get('revision') or 'unknown'}."
        )
    else:
        rules.append("Node code must not assume the three package is installed or importable in the active project.")
    if alignment.get("status") == "mismatch":
        rules.append("Three.js revisions differ across the packaged browser runtime and Node package; avoid sharing revision-specific APIs until they are aligned.")
    elif alignment.get("status") == "aligned" and host_project:
        rules.append("The detected packaged browser and Node Three.js revisions are aligned.")
    return rules[:4]


def handler(_arguments: dict[str, Any], **context: Any) -> str:
    workspace_root = _workspace_root(context)
    host_root = _host_root(context, workspace_root)

    node_runtime = _node_probe(workspace_root)
    workspace_project = _project_summary(workspace_root)
    host_project = _project_summary(host_root) if host_root else None
    browser = _browser_runtime(host_root)
    electron_runtime = _electron_runtime_probe(host_root or workspace_root)
    alignment = _alignment(host_project, browser)

    result = {
        "success": True,
        "node_runtime": {
            key: node_runtime.get(key)
            for key in ("available", "version", "major", "platform", "architecture", "module_abi", "napi", "v8")
            if key in node_runtime
        },
        "electron_runtime": electron_runtime,
        "darkstar_host": {
            "detected": host_root is not None,
            "project": host_project,
            "browser_three_runtime": browser,
            "three_revision_alignment": alignment,
        },
        "active_project": workspace_project,
        "compatibility_rules": _compatibility_rules(host_project, workspace_project, browser, alignment),
    }
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


registry.register(
    name=SCHEMA["name"],
    toolset="compatibility",
    schema=SCHEMA,
    handler=handler,
)
