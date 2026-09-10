# Runtime license files

This directory is intentionally part of the Darkstar Harness release layout.

The first-run native bootstrap installs a pinned llama.cpp CPU/Vulkan/CUDA bundle and a pinned stable-diffusion.cpp CPU/Vulkan bundle. Before building a release runtime:

1. The pinned `bootstrap-llamacpp.ps1` downloads the exact upstream `LICENSE` from the pinned llama.cpp commit, verifies its SHA-256, and installs it as `llama.cpp-LICENSE`.
2. For the pinned CUDA 12.4 runtime, the bootstrap downloads the official archived NVIDIA CUDA Toolkit **Release 12.4** EULA as `NVIDIA-CUDA-12.4-EULA.pdf`, verifies its SHA-256 from `backend/runtime-component-policy.json`, and preserves it beside the runtime. If the CUDA release changes, update the policy, bootstrap pin, and notice together; do not reuse the 12.4 EULA for another CUDA release.
3. The same bootstrap installs the exact pinned stable-diffusion.cpp CPU/Vulkan release archives and preserves their bundled MIT notices as `stable-diffusion.cpp-LICENSE` and `stable-diffusion.cpp-ggml-LICENSE`.
4. If any generated backend directory contains an additional `.exe` or `.dll` not already classified by policy, review its redistribution terms and add an explicit `manualDeclarations` entry to `backend/runtime-component-policy.json`, including every required notice file and `"redistributionReviewed": true`.

`npm --prefix backend/shell run runtime-license-audit` checks these rules. The offline release build runs the same audit in strict mode and refuses to package an incomplete or unclassified native runtime.

Do not add placeholder license text just to satisfy the gate. Preserve the actual notice/license material for the exact binaries being redistributed.
