# Darkstar Harness

Darkstar is a local-first orchestration environment for model execution on privately controlled compute infrastructure.

The standard distribution provides integrated Tools, Skills, workflows, extensible custom nodes, and local diffusion image generation without dependency on hosted AI infrastructure.

Darkstar currently supports three execution backends:

- CUDA
- Vulkan
- CPU

## System Requirements

Darkstar currently targets **Windows environments**. macOS and Linux support is planned for future releases.

Deployment requires:

- Windows 10 or Windows 11
- A compatible GGUF model
- Sufficient system RAM and/or GPU VRAM for the selected workload
- Network access during initial runtime provisioning when required components are not already present

### Compute Backends

Three execution backends are currently supported:

- **CUDA** requires a compatible NVIDIA GPU and current NVIDIA drivers.
- **Vulkan** requires a Vulkan-capable GPU and appropriate graphics drivers.
- **CPU** executes without a supported GPU.

Memory requirements are determined by model scale, quantization, context allocation, and the selected execution backend.

## Deployment

### 1. Acquire Darkstar

Download or clone the Darkstar Harness repository to the target system.

### 2. Provision a Model

Place a `.gguf` model inside:

```text
models/<your_model_name_here>
```

Alternatively, in the **Invoke Language Model (GGUF)** node, click the **⋯** button immediately to the right of the **Model** dropdown to select a local `.gguf` model without copying it into Darkstar's `models/` directory. The browser is rendered by Darkstar and does not invoke the operating system's native file picker.

For multimodal capability, place a compatible projector in the same directory as the model. When a model is selected, Darkstar detects compatible same-directory projectors and automatically selects the best match. The **Projector** dropdown provides **None** to explicitly disable projector loading; click the adjacent **⋯** button to select another local projector through Darkstar's own filesystem browser.

Common projector filenames include:

```text
mmproj*.gguf
*.mmproj
*.mproj
```

### 3. Launch Darkstar

Run the Windows batch launcher:

```text
Launch_Darkstar.bat
```

`Launch_Darkstar.bat` is the primary source-checkout entrypoint. It performs presence-only checks for the pinned Python, Electron, llama.cpp, and stable-diffusion.cpp runtime entrypoints, invokes the existing PowerShell bootstrap helper only when a required component is absent, then starts the `backend/shell` Electron application directly. No separate launcher executable is required.

The application now opens the main Darkstar workspace directly. Theme persistence remains program-wide: **Space** is the first-launch default, and later launches restore the saved **Light, Quantum, Terminal, Arctic, or Space** selection before the main window is shown.

## Initial Operation

Following initialization:

1. Select the execution backend: **CUDA**, **Vulkan**, or **CPU**.
2. Select a GGUF model from the dropdown, or click the **⋯** button beside **Model** to select one elsewhere on the local filesystem.
3. Accept the automatically selected compatible projector, choose **None**, or click the **⋯** button beside **Projector** to select another local projector.
4. Configure model parameters as required.
5. Submit an instruction through the chat interface.
6. Begin generation.

The bundled immutable `backend/assets/default-workflow.dswf` snapshot is the canonical default workflow seed. On Windows, writable workflow files live under `%LOCALAPPDATA%\Darkstar\Workflows`; Darkstar creates that directory automatically and seeds `darkstar-workflow.dswf` from the bundled snapshot when the file is missing. On a fresh install with no workflow autosave, Darkstar restores an exact clone of that snapshot—including node parameters, graph connections, legacy layout metadata, Loader assets, and workflow security. An existing user autosave always takes precedence during startup. An older application-side `./workflows` directory is treated only as a legacy import source: `.dswf` files are copied into the managed Workflows store without deleting the old directory, and an existing AppData file is never overwritten by a same-named legacy file.

## Models

Darkstar executes GGUF models compatible with `llama.cpp`.

Language models, diffusion models, and projectors selected from custom filesystem locations are remembered in Darkstar's protected local user data and remain available in their relevant dropdowns after restart. Their histories and last-used browser locations are purpose-specific: a GGUF chosen for Invoke Language Model never appears in Diffusion Backend GGUF history, and a diffusion selection never enters language-model history. When a Diffusion Backend GGUF is selected, Darkstar inspects supported model-weight files in that same directory and automatically fills a required standalone LLM text encoder or VAE when exactly one structurally compatible candidate exists; ambiguous directories remain user-selectable instead of being guessed. Darkstar automatically removes remembered entries when the underlying file is deleted or no longer valid.

Runtime characteristics are primarily determined by:

- Parameter count
- Quantization
- Available RAM
- Available VRAM
- Context allocation
- GPU offloading

## Capability Extensions

Darkstar's **Loader** node owns optional Tools and Skills that extend model capabilities beyond direct generation.

Tools provide controlled access to additional operations such as filesystem interaction, supported local execution, webpage interaction, and other configured capabilities, while Skills provide reusable instruction sets that modify or specialize model behavior.

Tool and Skill file loading uses Darkstar's own filesystem browser; Loader supports multi-selection for both asset types and only renders a collection section when that collection has entries. The chat image attachment button uses the same browser in single-image mode. Model, Projector, Tool, Skill, and Image browsers each remember their own last-used directory independently in Darkstar's local user-data preferences, so navigating one picker never changes where another picker opens.

### Model Action Permissions

The **Authorization** shield in the Settings sidebar controls a five-level model-action permission policy. The levels range from reviewing every tool action to unrestricted execution, with intermediate levels that progressively limit prompts to state-changing, connected, or workspace-boundary actions. The selected level is stored with the workflow and is restored when that workflow is loaded; Core remains the sole authority that enforces the policy.

The **Filesystem Access** control in the Settings sidebar independently sets the maximum filesystem scope available to model-invoked tools. **Level 1 · Full Filesystem** removes Darkstar's filesystem boundary, so tools may reach any path the current OS account can access. **Level 2 · User Profile** confines filesystem-capable tools to the current user's profile directory (the OS profile directory reported by the platform). **Level 3 · Working Directory** confines them to the active project working directory. New workflows default to **Level 2 · User Profile**. The selected level is workflow-owned and restored with the workflow. Core issues and enforces the scope at each tool call; path resolution follows symlinks/canonical paths before authorization so traversal and link escapes cannot broaden the boundary.

Filesystem Access is a containment policy, not an approval policy: Authorization still decides whether an otherwise-permitted action needs user approval. At Levels 2 and 3, tools that require an unrestricted host process and cannot be verifiably contained to the selected filesystem boundary fail closed instead of running with a misleading `cwd`-only restriction. This includes host shell/process tools, arbitrary model-authored `run_python`, and custom Python/JavaScript providers that execute without an OS-level filesystem sandbox. Level 1 permits those tools subject to their existing tool-specific safety checks and OS-account permissions.

The **Internet Access** control in the same Settings sidebar security section is a direct pressed-state sidebar toggle, matching the interaction pattern of **Traces**, and is a workflow-owned browser network switch. It defaults to **On** for compatibility with existing workflows. When switched **Off**, Core immediately tears down any isolated online-browser host, returns live browser tabs to their local/offline surface, and rejects subsequent public internet navigation from both the model's browser tool and the browser UI. Local HTML and bundled offline browser assets, including the bundled Three.js runtime, remain available. Loading another workflow restores that workflow's Internet Access setting through the same Core-owned policy boundary.

The **Browser Workspace** keeps its existing minimum resize width as a deliberate stop. Continuing to drag inward a further 160 CSS pixels beyond that stop collapses the Browser Workspace, preventing incidental pressure against the minimum edge from closing it. While collapsed, a narrow invisible resize affordance remains at the right edge of the window; dragging it outward reopens the browser only when the pointer reaches the legal minimum-width edge, so the first visible browser edge and the pointer occupy the same CSS-pixel coordinate instead of introducing a post-reopen offset. Ordinary resizing derives width directly from the pointer's absolute viewport coordinate, keeping the browser edge mechanically attached to the mouse regardless of where inside the invisible hit target the drag began or what display scaling is active. Collapse/reopen still uses the Browser Workspace's eased slide animation.

When approval is required, Darkstar shows the concrete action while that exact tool invocation remains suspended inside Core. **Allow** resumes and executes the same invocation transparently; no approval state, retry instruction, or synthetic conversation message is exposed to the model. **Reject** terminates that invocation without executing it and returns exactly `The user has rejected this command.` as the tool error. A later tool call may request permission again normally.

The default Loader tool collection also includes **Ask User Yes/No**. This tool lets the model ask one short, single-sentence question that must be directly answerable with **Yes** or **No**. The tool invocation remains suspended until the user answers; the answer is returned to the model as the tool result. This interaction is distinct from Authorization approval and is always presented to the user. On Windows, when Darkstar is not the active window, the question also appears as a native desktop notification; clicking the notification returns focus to Darkstar.

The default Loader tool collection also includes **Generate Image**. The provider becomes model-visible only when **Diffusion Backend GGUF -> DM Sampler -> Orchestrator** supplies a valid diffusion configuration. The Python tool itself cannot launch the native engine; it requests a capability-bound Core action. Orchestrator's **Image count (0 = Model)** setting ranges from 0 to 50: at `0`, the model must choose `image_count` from 1 to 50 for each tool call; at 1-50, the fixed setting overrides model control and the count is hidden from the model-facing schema. Multiple images are generated strictly as sequential single-image native runs rather than a diffusion batch. Generate Image also becomes the inpainting tool whenever the user arms an image edit: Core supplies the pristine source and an authoritative mask to stable-diffusion.cpp, chooses a padded high-resolution edit crop, and hard-composites the generated patch back over the pristine source so pixels outside the user-approved region cannot change. The model describes only the desired replacement; mask, crop, source image, width, and height remain user/Core-owned rather than model-controlled. During generation, Darkstar renders transient step previews under the animated diffusion overlay. On completion, each validated PNG enters the durable tool-image timeline as a collapsed diagnostic image patch and, when the active language model has a compatible multimodal projector, is supplied to the following model round as image context. Each image-producing tool result also gives the model a stable `image_id`. The bundled **Show Image** tool accepts one of those exact IDs from the current agent interaction and promotes that already-produced image into the assistant's visible response as a normal clean image appended after the assistant text as the final response element, without a filename caption and without copying the image bytes into a second message payload.

On a normal Windows launch, Darkstar-managed projects live under `%LOCALAPPDATA%\Darkstar\Darkstar-Projects`, not beside the application checkout. The portable EXE keeps its explicit portability contract and uses `<portable data root>\Darkstar-Projects`. On the first launch after upgrading, an existing legacy `<data root>\projects` directory is migrated wholesale before project discovery; if the move crosses filesystem volumes, Darkstar copies the tree into the canonical location and retains the original as a `projects.migrated-backup` sibling rather than deleting user data. Each project owns its durable conversations under a reserved `.darkstar/chat-session.dscs` file inside that project root. Core merges those project sessions at startup, so moving or reinstalling Darkstar cannot separate a project's filesystem from its chat history. The `.darkstar` metadata directory is hidden from the Workspace File Explorer and is blocked from scoped model filesystem access at Filesystem Access Levels 2 and 3; Level 1 retains its existing unrestricted-filesystem semantics. External project roots are remembered in AppData only as a protected lightweight root registry—chat content itself is not stored there. On first launch after the chat-session migration, the legacy `%APPDATA%\Darkstar\chat-session.dscs` snapshot is partitioned into the corresponding project roots and the original global file is retained as `chat-session.dscs.migrated-backup` (or a timestamped sibling if a prior backup already exists). **Autosave Chats: Off** now means only that new chat changes stop being persisted; it never clears previously saved conversations, and saved conversations are still restored at startup.

Chat composer drafts are owned by their chat tab: unsent text and an attached pending image survive tab/project switches and session restore instead of being cleared by navigation. Tool-produced image patches are collapsed by default in the chat timeline, matching the other trace/diagnostic patches, and omit source filenames from their visible presentation; users can still expand an individual image patch with its disclosure control. Images explicitly promoted with **Show Image** are rendered directly in the assistant response rather than as expanded diagnostic patches. Conversation images, tool-produced context images, queued attachments, and the composer image preview can be clicked (or opened with Enter/Space when focused) into the modal in-UI **Image editor**. The editor opens on a plain theme-owned canvas; the mouse wheel zooms around the exact image point under the cursor and holding the middle mouse button pans the zoomed canvas. **Select** lets the user drag a translucent-red rectangular edit region. **Brush** accepts arbitrary colors and sizes as a visual sketch and automatically derives the smallest in-image square that contains every stroke including its brush radius; if one square cannot contain all marks without leaving the source image, the editor fails closed and asks for separate edits instead of clipping the user's intent. **Use for inpainting** attaches a guide image plus a hidden pristine-source/edit contract to the active chat draft. Escape, the close control, or the backdrop closes the editor, and the native BrowserView is explicitly blocked while it is open so it cannot cover the image. `/adversary` receives the same visible image context available to the original agent, including tool-produced context images, while reasoning traces and raw tool protocol remain excluded.

Chat tabs use a compositor-driven pointer drag interaction rather than the operating system's native drag surface. Drag a tab left or right and neighboring tabs animate around the live insertion position; dropping persistently reorders conversations within the current project. Drag a tab onto another project in the project list to move the complete conversation there with an animated destination state without navigating away from the current project or auto-opening the moved tab. Cross-project moves preserve history, scheduled follow-ups, composer drafts, attached-image state, and the tab's stable identity while rebinding future model/tool work to the destination project's workspace; each project's existing active-tab selection remains stable unless its active tab itself is moved out. A tab with running or queued model work cannot cross project boundaries until that work retires; ordinary in-project reordering remains available. Moving the only tab out of a project leaves a fresh blank conversation behind automatically, and Escape cancels an active drag without changing state.

## Orchestration

Darkstar uses a typed workflow graph internally to define relationships between models, context, the unified Loader, and generation controls. The **Settings** view presents that graph as a tabbed property sheet instead of a movable node canvas: each workflow node becomes a horizontally navigable Settings tab, and the selected node is shown as one attached property panel with its section summary, semantic preference groups, aligned label/control rows, and bounded control widths. Tabs follow workflow execution dependencies, support mouse plus standard Left/Right/Home/End keyboard navigation, remain horizontally scrollable when custom sections expand the workflow, and keep the active panel reachable while long settings pages scroll. Graph sockets, wires, pan/zoom, and node dragging are intentionally hidden from normal presentation; saved node identities, parameters, typed connections, custom-node contracts, workflow persistence, and backend execution semantics remain unchanged.

Detected custom nodes can be inserted from **Add custom section** at the bottom of the workflow. Darkstar tags definitions registered by discovered custom-node plugins and shows only those definitions in that picker. When a newly inserted custom section has exactly one unambiguous compatible typed relationship, Darkstar creates that graph connection automatically; if more than one relationship is plausible, it does not guess or rewrite existing connections. Custom sections expose a header remove action that deletes the section and its graph links from the saved workflow; built-in sections do not expose that action.

For local GGUF workflows, **Invoke Language Model (GGUF)** selects the language model and feeds **LlamaCPP Server**. LlamaCPP Server owns llama.cpp runtime configuration, including **Context size**, backend/KV/GPU controls, and MTP settings. Its Language Model output feeds **LM Sampler** (stable node type `localSampler`; legacy title `L_Sampler`), which owns **Reasoning Effort**, request-time language-model sampling controls, **Stop strings**, **Reuse prompt cache**, and **Ignore EOS**. LM Sampler embeds the selected language-model descriptor in its single **LM Sampler** output, and that output connects to **Orchestrator**. For image generation, **Diffusion Backend GGUF** selects/analyzes the diffusion model and feeds the bundled **[ Custom ] DM Sampler**. DM Sampler owns diffusion sampling policy (seed, steps, CFG/guidance, sampler algorithm, scheduler, attention implementation, denoise strength, and compute device) and forwards its typed **DM Sampler** output to Orchestrator. With Loader's **Tools** output connected, the bundled **Generate Image** provider is exposed to the language model only when Orchestrator has a valid DM configuration; the Python provider requests a privileged action, Core's DiffusionRuntime owns stable-diffusion.cpp execution/cancellation and compute-device enforcement. DM Sampler's **Attention** selector offers **Auto**, **Standard (GGML)**, **Flash Attention (Diffusion)**, and **Flash Attention (All supported modules)**; Core maps the Flash modes to stable-diffusion.cpp's native `--diffusion-fa` / `--fa` flags only after capability probing, while xFormers remains unavailable because the native GGML runtime does not implement PyTorch/xFormers attention. DM Sampler's **Compute Device** selector offers **Auto**, **CPU**, and each GPU reported by the installed stable-diffusion.cpp runtime; Auto ranks available GPUs and chooses the strongest candidate without changing the persisted user selection. Transient denoising previews stream to the renderer while only the finished PNG becomes a durable context image. **Orchestrator** remains the local composition boundary for LM Sampler + optional DM Sampler + Loader-provided Skills/Tools and owns chat-context policy (**System prompt** and **Full chat context**) plus strategic controls (**Name Conversations**, **Auto-compact**, **Model idle unload**, **Dynamic VRAM**, **Image count (0 = Model)**, delegated-agent enablement, and **Maximum sub-agent depth (0 = Unlimited)**). The default maximum is 8 for backward compatibility; the configured value is inherited by every descendant and is the only nesting-depth ceiling enforced by Core. When Dynamic VRAM is enabled, Generate Image acquires an exclusive LM/diffusion lease. Darkstar first measures currently available system RAM and estimates the resident requirement of the active language model, its KV cache, and all configured diffusion pipeline components (including external text encoders and VAEs). If free RAM is strictly greater than that combined requirement, Darkstar parks the language model in a temporary CPU/no-mmap llama.cpp runtime, releases the GPU-resident copy for diffusion, restores the original GPU configuration afterward while the RAM copy is still warm, and then removes the parking runtime. If RAM is insufficient or the estimate/parking path is unavailable, Darkstar uses the original full unload/restore behavior unchanged. In either case the primary KV/cache residency is invalidated, competing model work is blocked for the lease, and restoration runs on success, diffusion failure, or user cancellation; application shutdown releases the lease without unnecessarily reloading the LM. The canonical local graph therefore needs no separate Context or Control nodes. Those node types remain available for API/custom workflows that explicitly use their sockets.

The standard distribution includes `backend/assets/default-workflow.dswf` as the immutable seed for the single canonical default general-purpose local workflow. The writable copy is created under the managed Workflows store (`%LOCALAPPDATA%\Darkstar\Workflows` on normal Windows launches, or `<portable-data-root>\Workflows` in portable mode). Renderer fallback graph construction exists only as an emergency recovery path if that bundled snapshot is missing or corrupt.

The underlying orchestration graph may still be replaced or extended through compatible custom nodes; the section interface is a presentation of that same persisted graph rather than a second workflow format.

## Development

Repository verification commands:

```text
npm --prefix backend/shell run quality
npm --prefix backend/shell run check
npm --prefix backend/shell test
npm --prefix backend/shell run verify
```

These commands are intended for development and contribution workflows. They are not required for standard operation.

## Licensing

Darkstar Harness first-party code and materials are licensed under the **Apache License 2.0**. See `LICENSE.md` for the complete terms.

Third-party components retain their upstream licenses and required notices alongside those components.

## Contribution

Repository contribution guidance is defined in `CONTRIBUTING.md`. Independent tools, plugins, custom nodes, skills, workflows, and integrations remain subject to the licenses chosen by their respective authors.

## Contact

For inquiries, contact **smsterling@protonmail.com**.
