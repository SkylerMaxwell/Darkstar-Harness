# Agent chats: tools, skills and MCP servers

An **Agent chat** (a normal tab) is one model that can act: call tools, read skills, use MCP servers and browse. The model must support tool calling for any of this to work; a model without it will simply answer in text.

While it works, the agent is asked to say in a sentence or two what it is about to do before each tool call. That line stays at the bottom of its reply, above the working dots, until it writes again, so you can follow what it is doing; every line also stays in the reply's Processing steps. An agent's own chat in a Task Force or Swarm tab shows its latest line the same way. Everything below is for Agent tabs. Swarm tabs have their own rules (see the swarm reference); they get no skills and no MCP servers.

## Where an agent works

- Each Agent tab gets its own folder inside its project, named after the tab. Relative paths in tool calls, and default file searches, start there. The folder follows the tab when you rename it or move it to another project. Closing the tab deletes the folder and everything in it, without asking, so the user should copy anything they want to keep first; the project's own files and attached folders are never touched.
- To reach another project file or a folder you attached with **Add Directory** in the File Explorer, the model uses an explicit path.
- A new project needs a working directory; Darkstar asks for it when you first chat.

## Tools

Tools are Python files the model can call. Open **Settings, Tools & Skills** to choose them. On a fresh profile every bundled tool is connected for you. **Add Tool Files…** (or dropping `.py` files on the tab) adds more; the row's remove button takes one out. A tool whose file was deleted is dropped automatically.

Bundled tools:
- **file_operations:** create a file, read lines from a file, and edit an existing file with checked, line-level replacements. It stays inside the project workspace and attached folders.
- **windows_cmd:** runs a Windows command (cmd) in the workspace, with a timeout (120 seconds by default, at most 600) and an output limit. Commands that delete or overwrite files must be explicitly marked as such, system-destroying commands are blocked, and it does not start nested shells such as PowerShell, WSL or bash.

**Important:** in Agent chats, tools run **with your own Windows rights**. `windows_cmd` can do anything you can. Only connect tools you trust, and watch what an agent is doing in sensitive folders. Swarm elements, by contrast, run inside a restricted sandbox.

Built into Darkstar (not listed under Tools & Skills, nothing to select):
- **browser_control:** drives the Action Engine browser (needs Internet Access on). **search_web:** web search (needs Internet Access on and Web Crawler on). **show_image:** shows an existing image in the chat.
- **list_dir** and **file_search:** look through folders and files.
- **read_context:** lets the agent search and read its own conversation so far. It opens in the Action Engine's code view as context.md.
- **global_memory** (Agent chats only, while **Global Memory** is on in Settings, Conversation): searches and reads every conversation in every project, including earlier replies' reasoning and tool calls that Infinite Context keeps out of the model's context, and the turns of the current conversation that Infinite Context set aside, marked (outside your context). Nothing is stored for it: each use reads the conversations as they are at that moment, so anything closed, deleted or retried away is gone from it at once. It is never shown in the Action Engine, and a swarm never has it.
- **clipboard** (agents only, not swarm commanders): copies lines from a file or from the agent's own conversation and pastes them into a file (before a line, over a range of lines, or at the end), so the model does not have to retype them. Every copy and paste shows in the Action Engine's code view with its lines highlighted. It holds one copy, in memory only, cleared when the chat closes, the agent ends its cycle or Darkstar closes. Pasting stays inside the agent's own working folders (in a swarm, inside its sandbox). Darkstar has no draft or scratch-editor tool.
- **file_history** (Agent chats only): undo for files. Darkstar keeps earlier versions of every file the agent's tools change; the agent can list them, show or compare one with the file now, and restore it (a restore can be undone too). A restore shows in the code view with the restored lines highlighted. Text files up to 4 MiB; terminal commands are not recorded; kept in memory until Darkstar closes or the project is deleted.
- **send_file:** hands you a file. It appears at the end of the answer as a card with its name, type and size; click it to save the file where you like. The card holds a copy taken when it was sent. Files sent in a conversation are deleted with it (closing the tab, clearing, deleting the project).
- **ask_user_yes_no:** asks you one short Yes/No question and waits for your answer in a **Confirmation needed** card with **Allow** and **Reject**.
- **end_chat** (the agent you talk to: an Agent chat, a Sandbox Agent, a Task Force's Lieutenant, a Swarm's Central Orchestration Element): ends the chat for good, as a last resort, when you keep pressing for something it has declined because it would cause serious harm, or keep being severely abusive after it asked you to stop. It warns you first, and does not end a chat over disagreement, criticism or a single rude message, or when you may be in distress. Its last reply closes the chat: nothing can be sent, retried, edited or continued in it again (also after a restart), scheduled messages are dropped, and in a Task Force or Swarm every agent stops. You can still read, copy and delete it.

## Tasks: planning a complex request

While **Tasks** is on (Settings, Conversation; on by default), an Agent or Sandbox chat's model can plan a complex request before it starts. The model decides when a request needs a plan; it is told to plan any software development, benchmarking or other task that is more than simple, and to answer simple questions directly. The plan holds:

- an enhanced prompt (your request restated completely) and its requirements;
- pinned materials: your request word for word with its images and every message you send while it works, always pinned by Darkstar itself, then earlier messages of yours the model picked out, files by path and notes;
- a task list, each task possibly waiting on others.

The model marks each task in progress as it starts it and completed when it is done, and adds or drops tasks as the work goes. When Infinite Context sets earlier turns aside, the model reads the plan and its pinned materials back, or your request and messages when there is no plan, so nothing you gave it is lost. Press **E** to see the plan: the brief beside the task list. E is there from the start: before the model plans, it shows your request word for word with its images, and any messages you sent while it worked. The plan is saved with the chat, cleared with it and deleted with the tab. It belongs to one request: when the reply finishes, the plan is cleared, so a new request is planned from scratch. A reply that was stopped, cut short by an instant message or failed keeps its plan, so **Continue response**, or the instant message that cut it short, carries on with the same tasks; any other new message you send starts without it. **Retry** or **Edit** on the message the plan was made for (or an earlier one), or deleting that message, clears the plan, so the new answer plans afresh.

## Skills

A skill is a folder with a `SKILL.md` file: instructions the model can load on demand. The model sees only each skill's name and a short description; when a task matches, it opens the full instructions with `skill_view` and can open the skill's other files if the instructions point to them. Skills are text for the model to read, not programs.

- **Add SKILL.md Files…** (or drop a `.md` file) connects a skill; its file dialog opens in the bundled skills folder. Fresh profiles connect every bundled skill, this guide included.
- Skills apply to Agent chats only.
- A skill's frontmatter needs a `name` and a one-line `description`.

## MCP servers

MCP (Model Context Protocol) servers give the model extra tools, such as a database, GitHub or a notes app.

**Turn it on first.** MCP is **off by default**: Settings, Conversation, **MCP Servers**. While off, Darkstar never starts or contacts an MCP server, the MCP options in Tools & Skills are greyed out, and a request behaves as if MCP did not exist. Turning it off also stops any running server. **Internet Access** is a second, separate gate for servers on the internet.

Then add one under **Settings, Tools & Skills, MCP servers, Add MCP Server…**:
- **Local command:** the command that starts the server (for example `npx`, `uvx`, `python`, or a full path), its arguments one per line and environment variables as `NAME=value` lines. There is no working-folder setting: the server starts in the folder of the Agent chat that uses it, so each chat's server sees only that chat's folder.
- **Remote address:** the server's Streamable HTTP address (`https://…`; plain `http://` only for this computer or your local network) and any headers, such as `Authorization: Bearer …`.
- **Fill in from JSON:** paste a server's configuration as most READMEs give it (`{ "mcpServers": { "name": { "command": …, "args": […], "env": {…} } } }`), one server at a time.
- Each server has an on/off switch, and its row shows the tool count or why it is not working. A server that is on but failing stops sending with its name and the reason; switch it off to carry on without it.

Good to know:
- Values of environment variables and headers (often credentials) are stored encrypted with your Windows account, never with your other settings. They show as `••••••••` when editing; leave them to keep them. If you change a server's command, arguments, folder or address you must enter them again, so a saved value can only ever go to the server it was entered for. Removing a server deletes them.
- The model sees MCP tools named `server__tool` (for example `github__create_issue`). If two servers would get the same prefix, Darkstar asks you to rename one.
- Not supported: servers that only offer the older HTTP+SSE transport, and signing in through a browser (OAuth). Use a token header where the server offers one.
- A local server runs on your computer with your rights and a remote one receives what the model sends it, so add only servers you trust. Servers on the internet are skipped while Internet Access is off; local commands and local-network servers are unaffected. Closing Darkstar stops every local server it started.

## Cancelling and controlling an agent

Press **Stop** (an empty message box while it works) to stop. The **pause** button in the status bar holds the reply where it is, without losing anything, and play goes on from exactly there; while it is paused nothing new is sent to that tab, and the tab gives its model slot to your other tabs (a tool call already running finishes first). You can send a message while it works (it is inserted into the reply), or hold Ctrl to schedule it for after. **Continue response** resumes an interrupted answer. Completed tool calls are never lost or duplicated: a call exists in history only as a finished call with its result.
