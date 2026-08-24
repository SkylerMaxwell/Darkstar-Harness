# Third-party notices

Darkstar Harness's GPL/commercial licensing choices apply only to First-Party Code over which the Darkstar Harness Licensor owns or controls sufficient licensing and relicensing rights. The following bundled or expected runtime components retain their upstream licenses. Their existing license files and required notices must be preserved in redistributions.

| Component | Version / scope | License | Notice location |
| --- | --- | --- | --- |
| Electron | 43.2.0 Windows x64 runtime; pinned official release asset is bootstrapped into source checkouts and bundled into packaged releases | MIT; Chromium and bundled components retain their own terms | The official archive supplies `backend/vendor/electron/win32-x64/LICENSE` and `backend/vendor/electron/win32-x64/LICENSES.chromium.html`; both are required when the runtime is present |
| three.js | 0.184.0 / r184 | MIT | `backend/vendor/three/r184/LICENSE`, `backend/vendor/three/r184/SOURCE.md` |
| openpyxl | 3.1.5 vendored Python package | MIT | `backend/agent/python_vendor/licenses/openpyxl-3.1.5-LICENSE.RST` |
| et_xmlfile | 2.0.0 vendored Python package | MIT; included Python-derived portions carry the PSF license described upstream | `backend/agent/python_vendor/licenses/et_xmlfile-2.0.0-LICENSE.RST`, `backend/agent/python_vendor/licenses/et_xmlfile-2.0.0-LICENSE.PYTHON` |
| Darkstar Harness Tool-use Skill Manual | packaged Skill, author metadata: OpenAI | MIT | `agent_assets/skills/Skill Manual/SKILL.md` |
| llama.cpp | b10520 Windows x64 CPU, Vulkan, and CUDA runtimes materialized under `backend/bin/backends/` | MIT for llama.cpp itself; bundled runtime dependencies may carry additional notices | Exact llama.cpp `LICENSE` copied to `backend/bin/licenses/llama.cpp-LICENSE` (mirrored to `licenses/runtime/` in packaged builds) |
| NVIDIA CUDA 12.4 runtime components (when bundled) | only Attachment-A redistributable runtime families actually shipped with the selected llama.cpp CUDA 12.4 build | NVIDIA CUDA Toolkit EULA, Release 12.4 | `backend/bin/licenses/NVIDIA-CUDA-12.4-EULA.pdf` (mirrored to `licenses/runtime/` in packaged builds); other NVIDIA/third-party notices remain separately applicable |

Electron's bootstrap is pinned by URL and SHA-256 in `RUNTIME_LICENSE_POLICY.json`. Its `LICENSES.chromium.html` is intentionally retained because the Electron distribution contains many third-party Chromium/runtime components whose individual terms are recorded there.

When CUDA runtime DLLs are bundled, they are redistributed only as third-party runtime components used by the separately licensed llama.cpp server. They do **not** become GPL-licensed or part of the Darkstar Harness Commercial License; NVIDIA's applicable terms continue to govern those files.

Native runtime licensing is enforced by `RUNTIME_LICENSE_POLICY.json` and `npm --prefix backend/shell run runtime-license-audit`. Every `.exe`/`.dll` under `backend/bin/` must classify as llama.cpp, a recognized CUDA runtime family, or an explicitly reviewed manual declaration with its required notices. The release build writes `THIRD_PARTY_RUNTIME_MANIFEST.json` containing the actual native-file hashes and notice hashes. The current policy is deliberately pinned to CUDA 12.4: the EULA must identify Release 12.4 and any native filename that reveals a different CUDA major version is rejected. Filename recognition is still a release-engineering guard, not a substitute for the exact NVIDIA terms.

Optional Python libraries imported by tools but not vendored in this repository are not part of the Darkstar Harness source distribution; users remain responsible for the terms of libraries they install separately.
