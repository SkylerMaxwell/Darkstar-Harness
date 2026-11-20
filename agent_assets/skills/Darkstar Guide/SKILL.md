---
name: darkstar-guide
description: Complete user guide to Darkstar, the Windows desktop app that runs language models on the user's own computer. Use it whenever the user asks how to do something in Darkstar, what a button, setting, hotkey or slash command means, why Darkstar behaves a certain way, or what it can and cannot do. Covers installing, the 31-day trial and license editions, local GGUF models, every Settings tab, chats, Agent tabs, tools, skills, MCP servers, Internet Access and the Action Engine, Sandbox tabs, Notebook tabs, Ghostwriter tabs, Task Force tabs, Swarm tabs, voice input, images, shortcuts, where data is stored, privacy, and troubleshooting.
---

# Darkstar guide

Darkstar is a Windows 11 desktop app for running language models on the user's own computer. It runs GGUF models locally through llama.cpp (CUDA, Vulkan or CPU), and can act as an agent: it can use tools, skills, MCP servers, and an embedded browser. A Task Force tab gives the user a Lieutenant that leads a single task force of up to 8 agents, and a Swarm tab runs a whole hierarchy of agents.

This guide is for answering the user's questions about Darkstar. Load a reference file only when the question needs it, with `skill_view` and the `file_path` shown below.

## Which file answers what

| The user asks about | Load |
| --- | --- |
| Installing, requirements, first launch, models folder, trial, license keys, updating, uninstalling, where files are kept, privacy, what Darkstar sends over the network | `references/getting-started.md` |
| The window: tabs, sidebar, projects, chat box, sending, scheduling, attachments, slash commands, status bar, spaces, hotkeys, themes, sound, Markup Tool | `references/interface.md` |
| Choosing and loading a model, context size, GPU and memory options, sampling, reasoning, vision, speculative decoding, voice input | `references/models-and-settings.md` |
| Agent tabs, tools, Python and terminal tools, skills, MCP servers, files from the model, questions from the model, project folders | `references/agents-tools-skills-mcp.md` |
| Internet Access, Search Web, the Action Engine browser, browser control, privacy of web use | `references/web-and-internet.md` |
| Sandbox tabs: one agent that works only inside its own disposable sandbox and hands you files with send_file | `references/sandbox.md` |
| Notebook tabs: cells written in plain words that an agent codes and runs in a Python kernel, Code and Markdown cells, running, the kernel | `references/notebook.md` |
| Ghostwriter tabs: writing papers and other manuscripts with a model that continues the text, Generate, Retry and takes, the Brief (Memory, Author's Note, Length, References), context, export | `references/ghostwriter.md` |
| Task Force tabs: the Lieutenant, its roadmap, its up to 8 agents, their context, views and files | `references/task-force.md` |
| Swarm tabs: the command hierarchy, sandboxes, version control, chatrooms, the Table of Organization, objectives, freezing | `references/swarm.md` |
| Something is wrong: a model will not load, it is slow or out of memory, tools are missing, a server fails, the trial or license, a blank or odd screen | `references/troubleshooting.md` |

A question can span files; load each one it needs. For a question about one setting, `references/models-and-settings.md` has the exact label, default and meaning.

## The few facts to know without loading anything

- **Settings** opens from the gear in the status bar, or from the DARKSTAR title. Its tabs are Language Model, Inference, Text Generation, Tools & Skills and Conversation. Internet, Sound, Theme, Clear and Traces are actions beside the tabs.
- **A tab is an Agent chat, a Sandbox, a Task Force, a Swarm, a Notebook or a Ghostwriter.** The + button opens a new tab at once, which asks which of the first four it is and offers Notebook and Ghostwriter below them, turning the tab into that page at once; right-clicking + opens a menu of all six.
- **Skills and MCP servers are for Agent tabs only.** Task Force and Swarm tabs do not get them.
- **MCP servers are off by default.** The switch is Settings, Conversation, MCP Servers. While it is off, nothing MCP-related is started or contacted.
- **Internet Access** is the single network switch for the Action Engine, Search Web and Browser Control. Turned off, those tools disappear from the model's functions and web pages close.
- **Everything stays on the computer** unless the user chooses an internet-facing MCP server, web browsing or search, or enters a Professional or Enterprise license key (the only thing Darkstar checks on its own; only the key is sent).
- **Agent chats have built-in helpers** besides the tools the user adds: `clipboard` (copy and paste lines between files and the conversation), `file_history` (undo for files the agent changed, until Darkstar closes) `tasks` (a plan and task list for a complex request, shown with **E**, while Tasks is on) and, while Global Memory is on, `global_memory` (search every conversation). **Infinite Context** (on by default) keeps earlier reasoning and tool calls out of the model's context and, while Global Memory is on, sets the earliest turns aside whenever the context is above 90%, so a chat never runs out of room. There is no draft tool.
- **Closing Darkstar ends everything it started**: the model server, tool processes, and the programs those started.
- **The trial** is 31 days from first launch. After it, use requires a Professional or Enterprise license.

## How to answer

1. Answer the question that was asked, in plain language, with the exact name of the control or place (for example Settings, Conversation, Name Conversations). Give steps in the order the user will meet them.
2. Use only what this guide and its reference files say. If something is not covered, say you are not sure instead of guessing, and never invent a setting, a hotkey or a menu. Suggest the closest thing the guide does describe.
3. Do not read the user's settings from memory: you cannot see which options they have set. Say where to look, and what each choice does.
4. For a problem, ask for the visible message or behaviour only if the guide's troubleshooting list does not already point to a likely cause, then give the first step to try and what result to expect.
5. Describe what Darkstar does for the user, not how it is built. This guide deliberately says nothing about Darkstar's source code or internal design; do not speculate about it. If asked, say that is not something this guide covers.
6. Be honest about limits. Darkstar cannot make a model do what the model cannot (for example, a model without tool calling cannot use tools), and local speed and memory depend on the computer.
7. Safety first where it matters: Agent chats run tools with the user's own Windows rights and MCP servers run on the computer or receive what the model sends them, so say so when advising on tools, Python, terminal commands or servers, and recommend adding only what the user trusts.
