# Darkstar Harness

Darkstar is a local-first orchestration environment for model execution.

The standard distribution provides integrated Tools, Skills, workflows, and extensible custom nodes without dependency on hosted AI infrastructure.

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

Alternatively, in the **Load Model (GGUF)** node, click the **⋯** button immediately to the right of the **Model** dropdown to select a local `.gguf` model without copying it into Darkstar's `models/` directory. The browser is rendered by Darkstar and does not invoke the operating system's native file picker.

For multimodal capability, place a compatible projector in the same directory as the model. When a model is selected, Darkstar detects compatible same-directory projectors and automatically selects the best match. The **Projector** dropdown provides **No Projector** to explicitly disable projector loading; click the adjacent **⋯** button to select another local projector through Darkstar's own filesystem browser.

Common projector filenames include:

```text
mmproj*.gguf
*.mmproj
*.mproj
```

### 3. Launch Darkstar

Run the root entrypoint:

```text
Launch_Darkstar.bat
```

`Launch_Darkstar.bat` first requires a **64-bit Python 3.11** interpreter for Darkstar's Python-backed tools, then checks the pinned Electron and llama.cpp runtimes. If Python 3.11 x64 is absent, Darkstar opens the pinned official **Python 3.11.9** Windows installer and waits while the user completes or cancels the installer UI; Darkstar does not perform a silent Python installation or choose installer options on the user's behalf. When Electron/llama.cpp provisioning is required, Darkstar intentionally opens a visible setup terminal and shows download, verification, and extraction progress. As soon as provisioning completes, that setup terminal closes automatically and the application continues through the hidden launcher. Once the prerequisites and runtimes are ready, normal launches hand off to the hidden launcher for the full application session.

## Initial Operation

Following initialization:

1. Select the execution backend: **CUDA**, **Vulkan**, or **CPU**.
2. Select a GGUF model from the dropdown, or click the **⋯** button beside **Model** to select one elsewhere on the local filesystem.
3. Accept the automatically selected compatible projector, choose **No Projector**, or click the **⋯** button beside **Projector** to select another local projector.
4. Configure model parameters as required.
5. Submit an instruction through the chat interface.
6. Begin generation.

The bundled `workflows/darkstar-workflow.dswf` snapshot is the canonical default workflow. On a fresh install with no workflow autosave, Darkstar restores an exact clone of that snapshot—including node parameters, positions, connections, Tools, and workflow security. **Reset Graph** restores the same canonical snapshot; an existing user autosave always takes precedence during startup.

## Models

Darkstar executes GGUF models compatible with `llama.cpp`.

Models and projectors selected from custom filesystem locations are remembered in Darkstar's protected local user data and remain available in their dropdowns after restart. Darkstar monitors those remembered files alongside the managed `models/` inventory and automatically removes history entries when the underlying file is deleted or no longer valid.

Runtime characteristics are primarily determined by:

- Parameter count
- Quantization
- Available RAM
- Available VRAM
- Context allocation
- GPU offloading

## Capability Extensions

Darkstar supports optional Tools and Skills that extend model capabilities beyond direct generation.

Tools provide controlled access to additional operations such as filesystem interaction, supported local execution, webpage interaction, and other configured capabilities.

Skills provide reusable instruction sets that modify or specialize model behavior.

Tool and Skill file loading uses Darkstar's own filesystem browser; both collection nodes support multi-selection. The chat image attachment button uses the same browser in single-image mode. Model, Projector, Tool, Skill, and Image browsers each remember their own last-used directory independently in Darkstar's local user-data preferences, so navigating one picker never changes where another picker opens.

### Model Action Permissions

The **Authorization** shield in the Nodes sidebar controls a five-level model-action permission policy. The levels range from reviewing every tool action to unrestricted execution, with intermediate levels that progressively limit prompts to state-changing, connected, or workspace-boundary actions. The selected level is stored with the workflow and is restored when that workflow is loaded; Core remains the sole authority that enforces the policy.

The **Filesystem Access** control in the Nodes sidebar independently sets the maximum filesystem scope available to model-invoked tools. **Level 1 · Full Filesystem** removes Darkstar's filesystem boundary, so tools may reach any path the current OS account can access. **Level 2 · User Profile** confines filesystem-capable tools to the current user's profile directory (the OS profile directory reported by the platform). **Level 3 · Working Directory** confines them to the active project working directory. New workflows default to **Level 2 · User Profile**. The selected level is workflow-owned and restored with the workflow. Core issues and enforces the scope at each tool call; path resolution follows symlinks/canonical paths before authorization so traversal and link escapes cannot broaden the boundary.

Filesystem Access is a containment policy, not an approval policy: Authorization still decides whether an otherwise-permitted action needs user approval. At Levels 2 and 3, tools that require an unrestricted host process and cannot be verifiably contained to the selected filesystem boundary fail closed instead of running with a misleading `cwd`-only restriction. This includes host shell/process tools, arbitrary model-authored `run_python`, and custom Python/JavaScript providers that execute without an OS-level filesystem sandbox. Level 1 permits those tools subject to their existing tool-specific safety checks and OS-account permissions.

When approval is required, Darkstar shows the concrete action while that exact tool invocation remains suspended inside Core. **Allow** resumes and executes the same invocation transparently; no approval state, retry instruction, or synthetic conversation message is exposed to the model. **Reject** terminates that invocation without executing it and returns exactly `The user has rejected this command.` as the tool error. A later tool call may request permission again normally.

The default Tools collection also includes **Ask User Yes/No**. This tool lets the model ask one short, single-sentence question that must be directly answerable with **Yes** or **No**. The tool invocation remains suspended until the user answers; the answer is returned to the model as the tool result. This interaction is distinct from Authorization approval and is always presented to the user. On Windows, when Darkstar is not the active window, the question also appears as a native desktop notification; clicking the notification returns focus to Darkstar.

## Orchestration

Darkstar uses a visual workflow environment to define relationships between models, context, Tools, Skills, and generation controls.

The standard distribution includes `workflows/darkstar-workflow.dswf` as the single canonical default for general-purpose local model execution. Renderer fallback graph construction exists only as an emergency recovery path if that bundled snapshot is missing or corrupt.

The orchestration graph may be modified, replaced, or extended through compatible custom nodes.

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

Darkstar Harness is open-source software released under the **Apache License 2.0**. The complete first-party source code is included with the project. See `LICENSE` for the terms.

Third-party components retain their upstream licenses and required notices alongside those components.

## Contribution

Repository contribution requirements are defined in `CONTRIBUTING.md`. Contributions accepted into Darkstar Harness are distributed under Apache-2.0.

## Contact

For inquiries, contact **smsterling@protonmail.com**.
