# llama.cpp runtime source

Darkstar Harness source checkouts do not track native llama.cpp/CUDA binaries. `backend/scripts/bootstrap-llamacpp.ps1` materializes one pinned Windows x64 **CPU + Vulkan + CUDA** bundle on first startup/build whenever any required backend is absent.

The authoritative pin is `RUNTIME_LICENSE_POLICY.json`:

- llama.cpp build: `b10520`
- upstream commit: `cd644c39545aac3dca63261f99a9bfc35956cb25`
- CUDA runtime: `12.4`
- CPU asset: `llama-b10520-bin-win-cpu-x64.zip`
  - SHA-256: `e91930be901cd7efd6fda1ed5343aea0aa77a5aac73a1a80e90e3b169677e874`
- Vulkan asset: `llama-b10520-bin-win-vulkan-x64.zip`
  - SHA-256: `53d0ed54e6993c25f0a69f7924617ece72d3983e9c22475a5a7a288f2fb75eb6`
- CUDA asset: `llama-b10520-bin-win-cuda-12.4-x64.zip`
  - SHA-256: `ea9c64786333f8052056fb3735d3edb95d4b9a5e4c816390d81c45ec8e59780f`
- CUDA runtime asset: `cudart-llama-bin-win-cuda-12.4-x64.zip`
  - SHA-256: `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6`

The helper does not query a latest-release endpoint. It downloads only source-controlled URLs, verifies every pinned SHA-256, and extracts into isolated staging directories. The final layout is:

- `backend/bin/backends/cpu/`
- `backend/bin/backends/vulkan/`
- `backend/bin/backends/cuda/`

CPU validation requires the server, common llama/ggml libraries, and a CPU backend. Vulkan additionally requires `ggml-vulkan.dll`. CUDA additionally requires `ggml-cuda.dll` plus the pinned CUDA 12.4 `cudart`/cuBLAS DLLs. The exact llama.cpp MIT `LICENSE` at the pinned commit and archived NVIDIA CUDA 12.4 EULA are SHA-256 verified and installed under `backend/bin/licenses/`. Only after all three backends validate is the prior backend bundle atomically replaced. Verified downloads are cached under `.darkstar-runtime/llama-cache/b10520-all-backends/`.
## Windows server layout

Pinned b10520 Windows releases use a split server layout: `llama-server.exe` is a small launcher and `llama-server-impl.dll` contains the server implementation. Bootstrap validation therefore checks the required companion DLL set and never infers validity from the executable's byte size.

