# Task Force tabs

A **Task Force** tab puts you one step down the chain of command: you talk directly to a **Lieutenant**, and the Lieutenant leads a single task force of up to **8 agents**. Choose **Task Force** (between Sandbox and Swarm) when you open a new tab with **+**. It sits between an Agent chat (one model) and a Swarm (a whole hierarchy).

## How it works

- **You command the Lieutenant.** It is the only agent you talk to. It does not do the work itself, and it has no objectives or hives.
- **It plans a roadmap.** The Lieutenant splits your request into tasks and says which tasks each one builds on. A task starts only when everything it builds on is finished and approved, so nobody is asked to comment, test or document code that does not exist yet; tasks that do not depend on each other run at the same time.
- **A standing team.** The Lieutenant staffs a few agents for the roles the roadmap needs (at most 8) and keeps them: each agent gets one task at a time and moves on to the next, usually the one that builds on its own work. An agent keeps its seat until the Lieutenant ends its cycle or you delete it.
- **Every task is judged.** When an agent finishes a task, the Lieutenant reviews its work and its report, then marks the task complete (which unlocks the tasks that build on it), sends it back with what is missing, or marks it failed and changes the plan.
- **The Lieutenant keeps going on its own.** When an agent finishes, writes to it or submits work, the Lieutenant gets a turn by itself (it shows in the chat as a "Task Force update") to review the work, judge the task, hand out the next ones and report back to you.
- **A finished request starts clean.** Once every task of the roadmap is complete and the Lieutenant has given its final reply, your next request clears it: the roadmap and every agent of the task force are deleted before the Lieutenant replies, and it plans the new request from scratch while keeping its conversation with you. Until that request, the finished task force can still be looked at, but its agents take no more orders.
- **Tools come from Settings.** The Lieutenant holds what Settings enable and passes each agent only what its task needs. **Skills, MCP servers and Global Memory are not available in a Task Force.**

## Context stays small, agents never run out

The Lieutenant and its agents keep the context savings of an Agent chat. With **Infinite Context** on (Settings, Conversation; on by default), your chat with the Lieutenant is pruned like an Agent chat, and each agent's earlier runs come back to it only as their orders and reports, without their tool calls, results or reasoning. Turn Infinite Context off to send everything.

Agents of a Task Force never reach an End of Cycle because their context filled up: when an agent's context passes 90%, its earliest runs are set aside so it can keep working, and the agent can still read and search them. Nothing is deleted: the full history of every agent stays readable in its chat and in the Table of Organization.

## The five views

Press the key with no text box focused (or click the icons in the status bar):
- **Tab:** the **Table of Organization**, with the Lieutenant at the top and its agents below. Select an agent for its details; right-click it to freeze, skip its turn, cancel its run or delete it. Click an agent to open its chat.
- **Q:** your chat with the Lieutenant.
- **W:** the Action Engine (and, while viewing an agent, that agent's own isolated browser).
- **E:** the **Roadmap**: every task as a node, joined to the tasks it builds on, with its state (locked, ready, in progress with the agent's name, awaiting the Lieutenant's verdict, complete or failed). Hover a task for its description, result and verdict.
- **R:** the task force's chatroom, **# task-force**, which every agent and the Lieutenant share. Write `agent-name:` at the start of a message to reach one agent. You can write there only while a task is still pending and something is running; otherwise the message box is off and you write to the Lieutenant with **Q**.

## Sandboxes and your files

Exactly as in a Swarm: the Lieutenant and every agent work in their own sandbox and on their own branch, and cannot read or change your files. Agents submit their work to the Lieutenant, which reviews it and approves it into the task force's main branch. **Your working folder changes only when the Lieutenant delivers the approved work and you approve it.** Expand the Task Force tab's folder in the File Explorer to browse its agents' files.

## Pausing and stopping

The pause button in the status bar pauses and resumes the whole task force, as in a Swarm. Closing the tab ends the task force and removes its sandboxes.
