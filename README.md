<p align="center">
  <img src="backend/assets/icon.png" width="112" alt="Darkstar">
</p>

<h1 align="center">Darkstar</h1>

<p align="center"><b>Intelligence, contained.</b><br>Version 4.0.1</p>

---

Darkstar runs AI on your computer. One window. Your models, your files, your machine.

You don't set it up. You don't maintain it. We already did.

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

It is not the engine. The two files that *are* Darkstar are kept here as empty placeholders. They ship sealed, inside the installer.

```text
Darkstar/
├── agent_assets/
│   ├── agent_prompts/        what each agent is told
│   ├── skills/               what each agent can learn
│   └── tools/                what each agent can use
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

Download the installer from **Releases**. Windows 10 or 11, or x86-64 Linux.

Install. Launch. That's all.

## License

Source-available, not open source. Governed by the **Darkstar Software License v3.0** ([LICENSE.md](LICENSE.md)).
You may read it here and fork it on GitHub. No mirrors, no redistribution, no rebrands.

<p align="center"><sub>© 2026 S.M. Sterling</sub></p>
