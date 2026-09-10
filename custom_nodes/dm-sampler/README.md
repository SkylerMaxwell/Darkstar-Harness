# DM Sampler

`[ Custom ] DM Sampler` is Darkstar's diffusion-model sampling-policy node.

Its UI follows the practical control surface of a basic ComfyUI-style KSampler while preserving Darkstar's orchestration and privilege boundaries:

- one optional `DIFFUSION_MODEL` input named **Diffusion Model**;
- one `DM_SAMPLER` output named **DM Sampler**;
- the Diffusion Model input is intended for **Diffusion Backend GGUF**;
- the DM Sampler output connects to Orchestrator's **DM Sampler** input;
- the node does not launch native diffusion processes itself;
- prompts, requested image geometry, generated media, cancellation, and native runtime lifecycle are owned by the model-invoked **Generate Image** path in privileged Core.

The canonical image-generation triangle is:

`Diffusion Backend GGUF -> DM Sampler -> Orchestrator`

with **Tools** also connected to Orchestrator. When the Tools node contains the bundled `generate_image` provider, Orchestrator passes the connected DM configuration into Core's ToolService. The tool is exposed to the language model only when that configuration is valid. **Steps** is a 0-150 slider where **0 = Auto**; Auto requires the language model to choose a 1-150 step count on every `generate_image` call, while a non-zero slider value forces that exact count for every generation. **Guidance / CFG** also supports **0 = Auto**; Auto requires the language model to choose a CFG value for each `generate_image` call, while a non-zero slider value forces that exact CFG. **Sampler** supports **Auto** as well; Auto requires the language model to choose a sampler, while any manually selected sampler is enforced for every generation. **Compute Device** is independent of model sampling and offers **Auto**, **CPU**, plus each individual GPU reported by stable-diffusion.cpp. Auto chooses the highest-ranked available GPU (preferring discrete devices and, where NVIDIA telemetry is available, greater VRAM); an explicit GPU or CPU selection is enforced by privileged Core at native launch. Core's DiffusionRuntime launches the pinned stable-diffusion.cpp runtime, streams transient denoising previews to the renderer, and returns only the finished image as the durable multimodal artifact. If Orchestrator's Dynamic VRAM policy is enabled, Core temporarily unloads the active llama.cpp model before diffusion starts and restores it before the next agent round; DM Sampler remains configuration-only and never owns LM memory transitions.

## Persisted sampling policy

- Seed (`-1` means random)
- Steps
- Guidance / CFG
- Sampler algorithm
- Scheduler
- Attention implementation (`Auto`, `Standard (GGML)`, `Flash Attention (Diffusion)`, or `Flash Attention (All supported modules)`)
- Denoise strength
- Compute Device (`Auto`, `CPU`, or an individual detected GPU)
- Generation Prefix (prepended to every positive generation prompt)

The node emits a versioned normalized object and, when connected, carries the normalized diffusion-model descriptor selected by Diffusion Backend GGUF. `Auto` sampler values are selected by the language model through the Generate Image tool, while `Auto` scheduler values defer to the diffusion runtime/model default. Attention is user-owned policy: `Auto` leaves stable-diffusion.cpp at its native default, `Standard (GGML)` explicitly selects the non-Flash path by emitting no Flash flag, `Flash Attention (Diffusion)` requires and emits `--diffusion-fa`, and `Flash Attention (All supported modules)` requires and emits `--fa`. Core probes `sd-cli --help` before launch and rejects a selected Flash mode when the installed runtime does not expose the corresponding flag.

`xFormers` is intentionally not presented as a selectable mode. It is a PyTorch/xFormers implementation and is not provided by Darkstar's native stable-diffusion.cpp/GGML diffusion runtime. Exposing it here would either be a no-op or require a separate Python Diffusers execution backend, which would violate this node's current native-runtime contract.

## Preview and context ownership

Live diffusion previews are presentation-only progress state. They are replaced in-place while the tool runs and are removed from the persisted agent timeline when the tool reaches a terminal state. The completed PNG follows Darkstar's normal `context-image` path: it is always presented to the user and is available to a following model round when the active language model has a compatible multimodal projector.

## LM Sampler display rename

This custom-node package also installs the requested **LM Sampler** display title for Darkstar's existing `localSampler` node at custom-node load time. The underlying node id, ports, parameters, execution implementation, and serialized type remain unchanged, and legacy `L_Sampler`, `L Sampler`, and `Local Sampler` titles normalize to **LM Sampler**. This keeps the rename presentation-only and avoids modifying the production renderer monolith.
