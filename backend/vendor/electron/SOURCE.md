# Electron runtime source

Darkstar Harness pins **Electron 43.2.0 Windows x64**. The large unpacked runtime is intentionally not stored in Git.

- Version: 43.2.0
- Platform: win32
- Architecture: x64
- Official asset: `https://github.com/electron/electron/releases/download/v43.2.0/electron-v43.2.0-win32-x64.zip`
- Archive SHA-256: `eba5f5088af40ecb364fe258809c79a5234c6ece5a75c64722772eba01b02786`

`Launch_Darkstar.bat` automatically runs `backend/scripts/bootstrap-electron.ps1` when `backend/vendor/electron/win32-x64/` is absent or incomplete. The bootstrap downloads only the pinned official asset above, verifies the archive before extraction, caches the verified ZIP under `.darkstar-runtime/electron-cache/`, and installs it atomically.

The official archive supplies Electron's `LICENSE` and `LICENSES.chromium.html`; Darkstar Harness validates both as part of runtime-license auditing. Packaged Darkstar Harness releases bundle the verified Electron runtime and preserve those files.

For an offline machine, populate `backend/vendor/electron/win32-x64/` from an already verified Electron 43.2.0 Windows x64 distribution, or use the local `vendor-runtime` command described in the root `README.md`.
