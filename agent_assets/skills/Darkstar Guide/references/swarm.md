# Swarm tabs

A **Swarm** tab runs a whole organisation of agents on your behalf. Choose **Swarm** (instead of Agent) when you open a new tab with **+**. You talk to one agent only; it commands the rest.

## The hierarchy

- **Central Orchestration Element:** the only agent you talk to. It plans the work, commissions Hive Marshals and reports back to you. Tools it holds come from what Settings enable.
- **Hive Marshal:** runs one **objective**. It is commissioned with a **seat guideline**: about how many seats (Lieutenants and Agents) its hive should deploy over its life. It is guidance, not a limit: nothing in a swarm is capped, and a Marshal may go beyond its guideline when the work needs it. The smallest task force is 2 seats, one Lieutenant and one Agent; the marshal itself takes no seat.
- **Lieutenant:** leads one **assignment**, a task force, and decides how many agents it needs.
- **Agent:** does one **task**.
Planning goes Objective, then Assignment, then Task. The Central Orchestration Element's objectives are an ordered list that runs one after another; the parallel work happens below it, inside a Marshal's assignments and the task forces. Objectives are never deleted while a mission runs, only reworded, added to, or (before they start) reordered. Once every objective is accomplished and the Central Orchestration Element has given its final reply, the user's next request clears the mission: all objectives and every element under the Central Orchestration Element are deleted before it replies, and it plans the new request from scratch while keeping its conversation with the user. Until that request, the finished swarm can still be looked at, but its elements take no more orders. Each commander reviews what the level below submits, and reports travel upward: a final report to a Marshal or to the Central Orchestration Element must be assessed (completed, pending or failed, with evidence) before that commander does anything else.

A superior can pass tools and a reasoning level down, but never more than it holds. **Skills and MCP servers are not available in a swarm** at any rank.

## The five views

Press the key with no text box focused (or click the icons in the status bar):
- **Tab:** the **Table of Organization**, the org chart with every element, rooted at the Central Orchestration Element. Select an element for its details, zoom with the controls, fit to view. Permanently deleting an element is only possible here, by you (apart from the clean start after an accomplished mission). Like the Tree of Objectives and the chatrooms, it has no message box: press **Q** to write to the Central Orchestration Element.
- **Q:** the chat with the Central Orchestration Element.
- **W:** the Action Engine (and, while viewing an agent, that agent's own isolated browser).
- **E:** the **Tree of Objectives**, objectives drawn as one vertical column with their status.
- **R:** the **chatrooms**. The `# swarm` room is shared by the whole swarm; each task force also has a member-only room. You can watch and read pinned messages; instructions to individual elements still go through their own controls. Agents talk to each other with the `swarm_chat` tool. Messages in a room do not give anyone new authority. You can write in a room only while an objective is still pending and something is running; otherwise the message box is off and you write to the Central Orchestration Element with **Q**.
**Esc** returns from the room view.

## Controls

- **The swarm keeps working after the Central Orchestration Element replies.** A new message from you does not cancel it. There is no Stop button in the message box in a Swarm tab; while the Central Orchestration Element replies the action button inserts your message at once (hold **Ctrl** to schedule it after the reply).
- **Status bar, right side:** **Pause** halts the whole swarm. Pause is like pausing a virtual machine: nothing is lost, and **Resume** carries on. You can also freeze a single element. A pause never locks the message box; you can keep typing a draft.
- Closing a Swarm tab shuts down its swarm and removes its sandboxes. Closing Darkstar ends every program the swarm started.
- Agent identities, reports, transcripts and room messages are saved, but running work is **not** resumed after Darkstar restarts: interrupted work is marked stopped, not completed.
- A normal Agent chat in another tab takes priority for the local model: swarm model turns pause briefly while that chat generates, then continue. A paused Agent chat or Sandbox does not hold them back.

## Sandboxes

Every element of every rank, the Central Orchestration Element included, works in its **own Windows sandbox** (a restricted, low-integrity process of the kind Chrome and Edge use; not a virtual machine). Nothing to install, turn on or approve; it works the first time a swarm runs.
- Its tools and file operations run inside it, in its own folder. Expand a Swarm tab's folder in the File Explorer to browse every element's files (read-only).
- It cannot read or change your files or another agent's, cannot change Windows or your programs, and cannot touch your windows or clipboard. Memory, process count and processor time are limited.
- Its programs can use the network like any other program on your computer. Its browser follows Internet Access.

## Version control and delivery

The swarm works under version control, entirely on your computer, with no server. When it starts it records your working folder. Each agent works on its own branch in its own sandbox and submits changes; its Lieutenant reviews them, then its Hive Marshal, then the Central Orchestration Element, so a change climbs the chain only with every commander's approval, and any approved change can be reverted.

**Your working folder changes only when the Central Orchestration Element delivers the approved result and you approve it** (a **Confirmation needed** card). Only files the swarm tracks are written; if you edited a file since the swarm recorded it, delivery stops instead of overwriting your edit.

## Context and the end of an agent's life

An agent that fills 90% of its context stops for good (**Context-Accomplished**), after a warning at about 80%. Its uncommitted work is committed and submitted to its superior as a change request marked possibly unfinished, and its superiors can still read its files. A commander can also end a subordinate's cycle without deleting it.

## Tips

- Give the Central Orchestration Element a clear, bounded goal and the working folder it should deliver into; it decides the structure.
- Watch progress in the Tree of Objectives (E) and the Table of Organization (Tab) rather than reading every room.
- Swarms use the loaded local model heavily. Choose a model and context size that fit comfortably in memory, since many agents may be generating in turn.
