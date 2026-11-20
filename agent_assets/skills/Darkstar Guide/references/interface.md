# The Darkstar window

## Layout

- **Title bar:** the DARKSTAR title (click it to open Settings) and the window buttons.
- **Tab bar:** one tab per conversation, a **+** button for a new tab, and a close button on each tab. Closing a tab deletes everything it kept on disk (its folder, its sandboxes, its sent files and pasted text only it used), like deleting a project and without asking. The project's own files and attached folders are never touched. Clicking **+** opens a new tab at once, which first asks what it is: an **Agent** chat, a **Sandbox** (one agent in its own sandbox), a **Task Force** or a **Swarm** (see the sandbox, task force and swarm references). Agent is chosen to start with, and your first message makes the choice final. Below those four sit **Notebook** and **Ghostwriter**: choosing one turns the New Tab into that page at once. Right-clicking **+** opens a drop-down menu under it with all six kinds of tab, also a **Notebook** and a **Ghostwriter** (see the notebook and ghostwriter references): click one, or use the **Up** and **Down** arrow keys and **Enter**; **Esc** or a click elsewhere closes the menu. A Notebook tab has no message box, because you write in its cells, and neither has a Ghostwriter tab, because you write in its manuscript.
- **Sidebar (SCHEMA):** two parts.
  - **File Explorer** shows the project's folders and each Agent tab's own folder. **Add Directory** attaches another folder you can then point the model at.
  - **Projects:** every tab belongs to a project. **New Project** adds one; projects can be renamed, and deleting one asks for confirmation. If a project has no working folder yet, Darkstar shows "Choose a workspace directory before chatting with the model" with a **Choose Directory** button.
- **Chat area** with the message list; a **Jump to latest** control appears when you have scrolled up. An empty chat shows a welcome screen.
- **Message box** at the bottom, then the **status bar**.
- The trial notice and the file dialogs open as their own small windows.

## Messages

Each message has actions:
- **Edit message**, **Retry from this message** (generate again from that point), **Delete message**, **Copy response**, and **Continue response** (carry on an interrupted answer from where it stopped; what was already generated and any completed tool call are kept).
- Reasoning ("thinking") and tool calls are shown as collapsible traces. What the model writes before a tool call (for example "Now I'll check the position") stays in the reply's trace too, between the steps it leads into, so expanding the trace shows the whole run in order. **Traces** (beside the Settings tabs) expands or collapses all of them. **Clear** empties the active chat's context.
- Images in a chat can be opened in the **Markup Tool** by clicking them (see below).

## The message box

- Type and press Enter to send. Use **Up/Down** to recall earlier messages you sent.
- **Upload image** (the image button) attaches pictures; you can also paste or drop images. An image you add before typing anything is attached **large** above the text; hover it for a pencil button (opens the Markup Tool) and **×**; once you have typed, it becomes a small chip where your cursor is. Hold **Ctrl+V** to paste an image large even when there is text. Drag a chip (the cursor shows four arrows) to move it anywhere in your message; click it to edit it. Long pasted text and dropped files become small chips you can open or remove. Whether the model can actually see images depends on it being a multimodal model with its projector loaded (see models-and-settings).
- While the model is answering, the single action button changes meaning:
  - empty box: **Stop** generation;
  - text in the box: **Send** inserts your message into the reply in progress (an "intervention");
  - text in the box while **holding Ctrl**: **Schedule**, which queues the message to be sent after the current reply finishes.
  Scheduled messages are listed behind the **Scheduled messages** button with a count; each can be edited or removed before it is sent.
- **Voice input:** hold the voice hotkey (default **Ctrl+O**) to dictate, release to transcribe into the box. Set it in Settings, Conversation (see models-and-settings).
- **Slash commands:** switched off. Typing `/` shows no menu and a message starting with `/` is sent as ordinary text. The command code remains in the app and can be re-enabled.

## Status bar

From left to right: the **Settings** gear; the **spaces** (see below); a button to **unload the model from memory**; the generation speed in tokens per second; the **context counter** (tokens used of the context size); and the boxed **#** that shows the raw context. In an Agent chat, a Sandbox, a Task Force or a Swarm tab there is also a pause/resume button: it holds the reply (or the whole task force or swarm) and play carries on from where it stopped.

## Spaces and keys

Press these with no text box focused and no modifier key:

| Key | Goes to |
| --- | --- |
| **Q** | the chat (in a Task Force tab, the Lieutenant; in a Swarm tab, the Central Orchestration Element) |
| **W** | the Action Engine browser |
| **E** | the Roadmap (Task Force tabs), the Tree of Objectives (Swarm tabs), or the plan of an Agent or Sandbox chat (Tasks; empty until its model makes one) |
| **R** | the chatrooms (Task Force and Swarm tabs) |
| **Tab** | the Table of Organization (Task Force and Swarm tabs); Tab never moves keyboard focus anywhere else in Darkstar |
| **P** | the raw context |
| **O** | toggles Settings open or closed |
| **Esc** | back to the chat |

Every message you send reaches the model with the time you sent it (the weekday and your local time), so agents can plan against the clock. You don't see the label in the chat.

A row of small icons in the status bar shows the spaces of the current tab (an Agent chat or a Sandbox has W and E; a Ghostwriter tab is a single page and has none, so these keys do nothing there apart from P and O). A small switcher at the bottom right appears for a couple of seconds when you change space; click an icon to jump.

Other keys: **hold F6** to see how the visible text is split into tokens. Browser zoom (Ctrl with plus, minus or 0) is switched off. Developer tools are disabled in every window. **Ctrl+W** and **Ctrl+R** do nothing: they never close or reload Darkstar; use the window's close button.

## Raw context

Press **P** (or the **#** button beside the context counter) to see exactly what the model is receiving for the chat or swarm agent you are viewing: the chat template, system message, tool definitions and special tokens, followed by what the model is generating. It is observation only. The last finished request is kept, so it is still there after the model is unloaded or Darkstar restarts. **Q** or **Esc** returns.

## Settings bar actions

Beside the Settings tabs: **Internet** (the Internet Access switch), **Sound** (mute the interface sounds), **Theme** (switches between the three themes: Space, Light and Terminal), **Clear** and **Traces** as above.

## Markup Tool

Click an image in a chat (or one in the message box) to open the Markup Tool over the chat. It has layers, selections, painting, text, filters and transforms. Right-click the canvas for the options of the active tool. **Enter** or the tick applies: the flattened result is put into the message box as a new image. **Esc** or the cross discards your changes to that image. Edits live in memory for that tab and go when the tab closes.

## Generation in the background

Generation keeps full speed when Darkstar is minimised, behind other windows, unfocused or the screen is locked.

## Message formatting

Chat messages render full Markdown: headings, nested lists, task lists, tables with alignment, blockquotes, callouts (`> [!NOTE]`), footnotes, collapsible `<details>`, `==highlight==`, `~~strike~~`, sub/superscript, and LaTeX math (`$...$`, `$$...$$`, `\(...\)`, `\[...\]`, matrices, aligned equations) via the engine's native MathML. Remote images are not loaded.
