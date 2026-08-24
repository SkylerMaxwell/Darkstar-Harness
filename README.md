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

For multimodal capability, place the compatible projector within the same model directory.

Common projector filenames include:

```text
mmproj*.gguf
*.mproj
```

### 3. Initialize Darkstar

Execute:

```text
Darkstar.exe
```

Darkstar will provision required application runtimes when they are not already present.

For development or diagnostic operation:

```text
Darkstar.exe --console
```

or:

```text
Darkstar.bat
```

## Initial Operation

Following initialization:

1. Select the execution backend: **CUDA**, **Vulkan**, or **CPU**.
2. Select a GGUF model.
3. Configure model parameters as required.
4. Submit an instruction through the chat interface.
5. Begin generation.

The default workflow provides the standard execution path and requires no additional orchestration configuration for conventional model interaction.

## Models

Darkstar executes GGUF models compatible with `llama.cpp`.

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

## Orchestration

Darkstar uses a visual workflow environment to define relationships between models, context, Tools, Skills, and generation controls.

The standard distribution includes a default workflow for general-purpose local model execution.

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

Darkstar Harness is distributed under the licensing terms included with the project.

Refer to:

- `LICENSE`
- `LICENSING.md`
- `THIRD_PARTY_NOTICES.md`

for applicable first-party and third-party licensing terms.

## Contribution

Repository contribution requirements are defined in:

```text
CONTRIBUTING.md
```

Additional contribution terms are defined in:

```text
CLA.md
```

## Contact

For inquiries, contact **smsterling@protonmail.com**.
