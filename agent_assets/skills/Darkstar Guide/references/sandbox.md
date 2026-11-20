# Sandbox tabs

A **Sandbox** tab is an Agent chat with one difference: its agent, the **Sandbox Agent**, works only inside its own Windows sandbox, so it cannot harm your computer. Choose **Sandbox** when you open a new tab with **+**.

## What the agent can and cannot do

- **It works in its sandbox.** Its terminal (the Windows command prompt (cmd), with Python), its files and its own browser all run inside the sandbox, the same kind every swarm agent uses. It cannot read or change your files, your other programs or the system, even if a command goes wrong.
- **It starts empty.** Its working folder starts with nothing in it: none of your project is copied in. It is a plain folder with no version history. Give it what it needs in the chat (text or images): long text you paste becomes a chip, and Darkstar puts that text in the agent's own folder so it can read it.
- **It hands you files with send_file.** That is the only way its work reaches you: the file appears at the end of its reply as a card you can save. It can only send files from its own sandbox. You can also look through its folder in the File Explorer.
- **It is temporary.** Closing the tab deletes the sandbox and everything in it. Save anything you want to keep from its send_file cards first.
- **Not available:** MCP servers, skills, Global Memory and Infinite Context (they would reach outside the sandbox). It does have Tasks: it can plan a complex request as a task list, and E shows the plan. It can still ask you Yes/No questions, use the clipboard tool, and end the chat as a last resort, like any agent you talk to.

## Using it

It looks and works like an Agent chat: **Q** is the chat and **W** is the Action Engine, which shows the agent's own sandboxed browser. Stop, Continue, Retry and Edit work as usual, the status bar's pause button holds and resumes its reply, and Infinite Context keeps earlier replies' reasoning and tool calls out of the model's context. A message you send to it takes over the model at once even while another tab is generating, exactly as in an Agent chat.
