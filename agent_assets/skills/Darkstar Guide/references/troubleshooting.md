# Troubleshooting

Work through the matching entry in order. Ask the user for the exact message they see only if none of these fits.

## Darkstar will not start

- **"Darkstar's program files have been changed or damaged"** (a message naming `backend\Darkstar_Core.js` or `backend\Darkstar_Renderer.js`): an installed copy checks its two program files at every start and refuses to run if either was edited or damaged. Run the Darkstar installer again over the existing install; it restores them and keeps your chats, projects and settings.
- **"Some of Darkstar's files are missing or damaged":** the same fix, run the installer again (an antivirus program may have quarantined a file; restore it or add an exception for the Darkstar folder first).
- **The installer will not run:** it will not proceed while Darkstar is open, so close Darkstar first. It also refuses Program Files and Windows folders and non-empty folders that are not a Darkstar install; choose the default or another folder you can write to.
- **Windows warns about an unknown publisher** when opening the installer: that is SmartScreen for an installer that is not code-signed by a publisher it knows. It is not a sign of damage.
- On launch, a **trial notice** may appear before the window; press **Continue Trial** (or **Continue** after the trial ends) to go on.

## A model will not load, or loads slowly

1. Check the backend (Settings, Inference, llama.cpp backend). **CUDA** needs an NVIDIA GPU. With AMD or Intel graphics choose **Vulkan**; with no usable GPU choose **CPU**.
2. Out of memory or a crash on load: lower **Context size**, set **KV cache location** to CPU, keep the **KV cache type** at `q4_0`, lower **GPU layers**, or choose a smaller or more heavily quantized model. Memory on the GPU is dedicated video memory only; an integrated GPU that shares system RAM does not provide extra.
3. After changing an Inference setting, the model reloads the next time it is used; the first message after a change takes longer.
4. A load error appears in the chat as a banner; starting another load clears the banners. If a specific llama.cpp build misbehaves, select the bundled version in **llama.cpp version** instead of a downloaded newer one.
5. For a very large model, close other programs that use video memory.
6. **"This llama.cpp build has no --api-key option"** or **"llama-server answered an unauthenticated request … instead of 401"**: the selected llama.cpp build cannot require Darkstar's server key, so Darkstar will not run it. Select the bundled version in **llama.cpp version**, or use **Get latest llama.cpp** for a current build.

## Answers are cut off, repeat, or lose the start of the conversation

- **Cut off:** the context filled up. Raise **Context size**.
- **Repeating itself:** raise **Repeat penalty** slightly above 1, or raise **DRY** above 1, and keep **Temperature** reasonable. Some models loop when the context is nearly full.
- **Does not remember its own earlier reasoning or tool output:** with **Infinite Context** on (Settings, Conversation; on by default), earlier replies' reasoning and tool calls are no longer sent, only your messages and its final replies. Turn on **Global Memory** so an Agent chat can look them up, or turn Infinite Context off.
- **Forgets the start of a very long conversation:** with **Infinite Context** on, the earliest turns were set aside when the context went above 90%. The model can still read them with Global Memory; ask it to look them up. Turn Infinite Context off to send the whole conversation, if it fits. The raw context (**P**) shows what the model receives.
- **Too short or too thoughtful:** adjust **Reasoning Effort** in Text Generation.
- **Stopped mid-answer:** use the **Continue response** button to carry on where it stopped.

## The model cannot see an image

It must be a multimodal model with a **Projector** selected (Settings, Language Model). Without the projector, picture input does not work.

## Tools, skills or the browser do not work

- The model must support **tool calling**. A model without it only answers in text.
- Check **Settings, Tools & Skills**: the tool must be listed. A tool whose file was deleted is removed automatically; re-add it with **Add Tool Files…**.
- Web tools missing: **Internet Access** must be on, and **Web Crawler** (Settings, Conversation) must be on for search.
- Skills and MCP servers exist only in Agent tabs, never in Swarm tabs.
- If tools worked and then stopped: a tool's Python code may be failing; the error appears in its trace in the chat.

## MCP servers

- Nothing appears or works: **Settings, Conversation, MCP Servers** is off by default; turn it on. While off, the MCP options in Tools & Skills are greyed out.
- Sending stops with a server's name and a reason: that server is switched on but cannot start or be reached. Fix it, or switch it off to chat without it.
- A local command is not found: the program (for example `npx` from Node.js, or `uvx`) must be installed on your computer and reachable by name, or give its full path. Darkstar does not install it.
- A server on the internet is skipped while **Internet Access** is off.
- After changing a server's command, arguments, folder or address, enter its environment variables or headers again; the saved ones only go to the exact server they were entered for.
- Two servers share a tool-name prefix: rename one.
- Only Streamable HTTP and local-command servers work, and a server that needs a browser sign-in (OAuth) is not supported; use a token header if the server offers one.

## The web browser is blank or searching fails

Check **Internet Access** (the Internet button beside the Settings tabs) and that the computer is online. Press **W** to watch what the browser is doing; the reset button in the browser clears every tab and all cookies.

## Voice input does nothing

Hold the hotkey (default **Ctrl+O**) while speaking and release to transcribe. Check **Microphone** and the hotkey in Settings, Conversation, and that Windows allows microphone access for desktop apps. If another program already uses Ctrl+O, choose another hotkey.

## Trial and license

- The trial is 31 days from first launch on this computer; the notice says how many days remain. After that, use requires a Professional or Enterprise license. Reinstalling Darkstar or deleting its data does not begin a new trial.
- **Key refused:** check all 20 characters. Darkstar must reach the license server to check a key; with no connection the key is not accepted, and you can try again later from the trial notice's *Enter license key* link. After a check, wait a few seconds before the next one.
- A licensed copy does not show the trial notice. It re-checks the key with the license server about weekly and keeps working offline in between.

## Swarm problems

- Elements do nothing: check the swarm is not **paused** (status bar) and that the model has memory for it.
- A tab will not send ("still paused"): it is paused. Press play in the status bar (or Stop, in an Agent chat or a Sandbox, to end the paused reply).
- Work seems to stop after a restart: running work is not resumed after Darkstar restarts; interrupted work is marked stopped.
- Delivery to your folder did not happen: it needs your approval in the **Confirmation needed** card, and it stops if you edited a tracked file after the swarm recorded it.
- An element stopped by itself: at 90% context an agent ends its cycle; its work is submitted to its superior.

## Where to look for more

Logs and diagnostics are under `%LOCALAPPDATA%\Darkstar\app` (folders `logs` and `diagnostics`). The raw context view (**P**) shows exactly what the model is being sent, which explains most surprising behaviour. The license terms are in `LICENSE.md`.
