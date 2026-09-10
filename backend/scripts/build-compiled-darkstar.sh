#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$ROOT/binary}"
STAGE="$ROOT/.darkstar-build/compiled-core"
rm -rf "$STAGE" "$OUT"
mkdir -p "$STAGE/embedded" "$OUT"
cp "$ROOT/launcher/compiled/main_windows.go" "$STAGE/main_windows.go"
printf 'module darkstar-compiled-launcher\n\ngo 1.22\n' > "$STAGE/go.mod"
gzip -9 -c "$ROOT/backend/Darkstar_Core.js" > "$STAGE/embedded/Darkstar_Core.js.gz"
gzip -9 -c "$ROOT/backend/Darkstar_Renderer.js" > "$STAGE/embedded/Darkstar_Renderer.js.gz"
(
  cd "$STAGE"
  CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath -ldflags='-s -w -H=windowsgui' -o "$OUT/Darkstar.exe" .
)
cp -a "$ROOT/backend" "$ROOT/agent_assets" "$ROOT/custom_nodes" "$ROOT/workflows" "$OUT/"
rm -f "$OUT/backend/Darkstar_Core.js" "$OUT/backend/Darkstar_Renderer.js"
rm -rf "$OUT/backend/Dev"
rm -f "$OUT/backend/scripts/build-compiled-darkstar.ps1" "$OUT/backend/scripts/build-compiled-darkstar.sh"
cp "$ROOT/README.md" "$ROOT/LICENSE.md" "$OUT/"
cat > "$OUT/Launch_Darkstar.bat" <<'BAT'
@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "DARKSTAR_ROOT=%~dp0"
start "" "%DARKSTAR_ROOT%Darkstar.exe" %*
if errorlevel 1 (
  echo [Darkstar] ERROR: Could not start Darkstar.exe.
  pause >nul
  exit /b 1
)
exit /b 0
BAT
CORE_HASH="$(sha256sum "$ROOT/backend/Darkstar_Core.js" | awk '{print $1}')"
RENDERER_HASH="$(sha256sum "$ROOT/backend/Darkstar_Renderer.js" | awk '{print $1}')"
EXE_HASH="$(sha256sum "$OUT/Darkstar.exe" | awk '{print $1}')"
cat > "$OUT/COMPILED_CORE_MANIFEST.json" <<JSON
{
  "schemaVersion": 1,
  "architecture": "windows-x64",
  "executable": "Darkstar.exe",
  "executableSha256": "$EXE_HASH",
  "embeddedMonoliths": {
    "backend/Darkstar_Core.js": "$CORE_HASH",
    "backend/Darkstar_Renderer.js": "$RENDERER_HASH"
  }
}
JSON
printf 'Built %s\nDarkstar.exe SHA-256: %s\n' "$OUT" "$EXE_HASH"
