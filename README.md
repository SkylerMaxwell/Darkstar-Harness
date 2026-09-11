# Darkstar Harness

Darkstar Harness is a local-first AI orchestration environment for running models on your own hardware.

It supports GGUF language models, workflows, Tools, Skills, custom nodes, and local image generation.

## Features

* Local GGUF model execution
* CUDA, Vulkan, and CPU backends
* Multimodal model support
* Local image generation
* Visual workflow system
* Extensible Tools, Skills, and custom nodes
* Multiple interface themes
* Designed for privately controlled local compute

Darkstar currently targets Windows 10 and Windows 11.

## Install & Run

Download or clone the repository.

Place a compatible `.gguf` model in the `models` folder, or select one from another location through Darkstar.

Launch Darkstar with:

```text
Launch_Darkstar.bat
```

Required runtime components are provisioned automatically when needed.

For portable builds, use:

```text
Build_Portable_EXE.bat
```

Hardware requirements depend on the model, quantization, context size, and selected execution backend.

## License

Darkstar Harness is licensed under the **Apache License 2.0**.

See `LICENSE.md` for the full license terms.

Third-party components remain subject to their respective licenses.
