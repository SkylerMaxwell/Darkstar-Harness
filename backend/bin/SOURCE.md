# llama.cpp runtime source

Darkstar Harness source checkouts do not track native llama.cpp/CUDA binaries. `backend/scripts/bootstrap-llamacpp.ps1` materializes one pinned Windows x64 **CPU + Vulkan + CUDA** bundle on first startup/build whenever any required backend is absent.

The authoritative pin is `backend/runtime-component-policy.json`:

- llama.cpp build: `b10645`
- upstream commit: `c5fc7e34885ba31217e330809437afa993d27745`
- CUDA runtime: `12.4`
- CPU asset: `llama-b10645-bin-win-cpu-x64.zip`
  - SHA-256: `d3a82793b79701cff48323ebf18d3f0a4384d54aacd502e13cc3c30fa09653b2`
- Vulkan asset: `llama-b10645-bin-win-vulkan-x64.zip`
  - SHA-256: `2dbb1b161252d0caf704a20a00a111fdc53b1f77812787e3ab87c3ef726b9666`
- CUDA asset: `llama-b10645-bin-win-cuda-12.4-x64.zip`
  - SHA-256: `c172f30312a8830795fba4b08f4ac027777f62505d61653b07b896c43898c86a`
- CUDA runtime asset: `cudart-llama-bin-win-cuda-12.4-x64.zip`
  - SHA-256: `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6`

The helper does not query a latest-release endpoint. It downloads only source-controlled URLs, verifies every pinned SHA-256, and extracts into isolated staging directories. The final layout is:

- `backend/bin/backends/cpu/`
- `backend/bin/backends/vulkan/`
- `backend/bin/backends/cuda/`

CPU validation requires the server, common llama/ggml libraries, and a CPU backend. Vulkan additionally requires `ggml-vulkan.dll`. CUDA additionally requires `ggml-cuda.dll` plus the pinned CUDA 12.4 `cudart`/cuBLAS DLLs. The exact llama.cpp MIT `LICENSE` at the pinned commit and archived NVIDIA CUDA 12.4 EULA are SHA-256 verified and installed under `backend/bin/licenses/`. Only after all three backends validate is the prior backend bundle atomically replaced. Verified downloads are cached under `.darkstar-runtime/llama-cache/b10645-all-backends/`.
## Windows server layout

Pinned b10645 Windows releases use a split server layout: `llama-server.exe` is a small launcher and `llama-server-impl.dll` contains the server implementation. Bootstrap validation therefore checks the required companion DLL set and never infers validity from the executable's byte size.

