<p align="center">
  <img src="backend/assets/icon.png" width="112" alt="Darkstar">
</p>

<h1 align="center">Darkstar</h1>

<p align="center"><b>Harness the Singularity</b><br>Version 4.0.1</p>

---

## Modes

| | |
|---|---|
| **Agent** | One model with a browser, a terminal and your files. It does the work. |
| **Sandbox** | The same agent, sealed in a disposable room of its own. |
| **Task Force** | A Lieutenant and up to eight agents, working a roadmap. |
| **Swarm** | A chain of command. Objectives at the top, workers below, one shared vault. |
| **Notebook** | Plain words in. Running code out. |
| **Ghostwriter** | You write. It continues. |

## Doctrine

- **Local.** Models run on your hardware through llama.cpp.
- **Silent.** No telemetry. No accounts. The only call it makes on its own checks a paid license key.
- **Contained.** Sandbox, Task Force and Swarm agents work inside operating-system sandboxes. Their work reaches your folders only when you approve it.
- **Invariant.** No feature depends on one model family.
- **Complete.** Python, Electron, llama.cpp, speech, sandbox. All of it ships inside the installer. It installs offline.

## This repository

This is the shape of Darkstar as it ships: its prompts, its tools, its skills, its interface shell.

The dual monolith engine core is kept empty in order to protect IP.

```text
Darkstar/
├── agent_assets/
│   ├── agent_prompts/        what each agent is told
│   ├── skills/               what each agent can learn
│   └── tools/                external tools
├── backend/
│   ├── Darkstar_Core.js      ∅  the system
│   ├── Darkstar_Renderer.js  ∅  the interface
│   ├── agent/                the tool runner
│   ├── notebook/             the kernel
│   ├── sandbox/helpers/      what runs inside the sandbox
│   ├── shell/                the window
│   └── assets/
└── LICENSE.md
```

## Get Darkstar

Install. Launch. That's all.

## License

While some of the source may be made available, Darkstar is NOT open source software. Darkstar is Governed by the **Darkstar Software License v3.0** ([LICENSE.md](LICENSE.md)).

For business inquiries: smsterling@protonmail.com

<p align="center"><sub>© 2026 S.M. Sterling</sub></p>
