# [ Custom ] Set Diffusion Backend (GGUF)

This custom node selects and analyzes a standalone GGUF diffusion model without adding graph sockets.

## Diffusion model selection

The primary **Diffusion GGUF** field intentionally uses the same Darkstar GGUF selection surface as **Invoke Language Model (GGUF)**:

- the same GGUF dropdown presentation, backed by diffusion-specific history;
- the adjacent **⋯** Darkstar local-filesystem browser in diffusion mode;
- diffusion-specific remembered-model behavior for locally selected GGUFs.

There is no manual diffusion-path textbox and no GGUF drag/drop target.

## Text encoder and VAE companions

After a diffusion GGUF is analyzed, the node derives the external text-encoder/VAE roles required by the detected diffusion family and adds only the relevant companion controls. Examples include CLIP-L, CLIP-G, T5/UMT5 XXL, LLM text encoders, CLIP Vision, and VAE/autoencoder fields.

These controls are deliberately presented as ordinary model fields immediately beneath **Diffusion GGUF**. There is no separate "Pipeline companions" panel and no disclosure toggle: required/relevant fields appear automatically when analysis says the selected pipeline uses them, and the entire companion block is absent when no external encoder/VAE role applies.

Companion discovery is deliberately conservative:

- automatic preflight scans **only the directory containing the selected diffusion GGUF**;
- GGUF and Safetensors/SFT candidates are inspected from header/tensor descriptors only; tensor payloads are never loaded;
- a field is auto-populated when exactly one candidate is a structurally definite match for that role; for required standalone **LLM text encoder** and **VAE** roles, exactly one structurally proven same-directory candidate may also be auto-bound when the file header proves the component type but omits parent diffusion-family identity;
- T5-XXL and UMT5-XXL are distinguished structurally (Wan requires UMT5), and broad LLM-family matches such as generic Mistral/Qwen are kept at **Possible** unless the header proves stronger pipeline identity;
- ambiguous directories with multiple plausible candidates are never auto-selected;
- legacy opaque weight formats (`.ckpt`, `.pt`, `.pth`, `.bin`) can be chosen manually but are never auto-selected from filename guesses;
- manual selection is available through each field's **⋯** browser and can navigate outside the diffuser directory.

VAE matching is intentionally stricter than filename matching. Some diffuser families use autoencoders with nearly identical tensor geometry but different latent semantics, so the node reports those as **Possible** unless the header provides enough evidence to prove the family match. This avoids silently binding a plausible-looking but semantically wrong VAE.

The custom companion browser is implemented by this custom node and does not extend or alter Darkstar's global model-file browser.

## Diagnostic sections

The analysis summary remains visible at a glance, while the verbose **Resolved pipeline paths**, **Model analysis**, and **GGUF metadata** sections are collapsed by default. They remain user-expandable for diagnostics and inspection.

## What it persists

The workflow stores only resolved filesystem paths:

- `diffusionModelPath`
- `highNoiseDiffusionModelPath`
- `uncondDiffusionModelPath`
- `clipLPath`
- `clipGPath`
- `t5xxlPath`
- `llmPath`
- `llmVisionPath`
- `clipVisionPath`
- `vaePath`
- `embeddingsConnectorsPath`
- `audioVaePath`

GGUF inspection, same-directory candidate catalogs, compatibility evidence, and automatic/manual selection provenance remain volatile under `node.runtime`, so they do not inflate `.dswf` workflow files. A restored workflow re-analyzes its selected diffusion GGUF.

## Analyzer behavior

The analyzer reads GGUF header metadata and tensor descriptors only. It supports GGUF v2/v3, little-endian GGUF and v3 big-endian files, current GGML tensor type identifiers, sparse-metadata diffusion GGUFs, and unknown architectures.

Architecture identification is layered:

1. declared GGUF metadata and filename identity;
2. recognizable diffusion tensor signatures;
3. generic GGUF fallback when no family can be identified confidently.

Safetensors companion inspection reads only the bounded JSON header containing tensor names, dtypes, shapes, and optional metadata.

## Compatibility references

No third-party runtime dependency is vendored. The implementation follows the active upstream conventions used by:

- GGUF/GGML format and tensor identifiers: https://github.com/ggml-org/ggml
- current diffusion component/path conventions and weight-based model configuration: https://github.com/leejet/stable-diffusion.cpp

The node treats stable-diffusion.cpp's actual runtime validation as authoritative; the custom-node preflight is intentionally conservative and never upgrades an ambiguous candidate to an automatic selection.
