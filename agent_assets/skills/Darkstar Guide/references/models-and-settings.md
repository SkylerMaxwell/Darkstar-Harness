# Models and Settings

Settings has five tabs, in this order: **Language Model**, **Inference**, **Text Generation**, **Tools & Skills** and **Conversation**. Changes apply to chats as you make them; settings that shape how the model is loaded (the Inference tab and the model itself) take effect by reloading the model the next time it is needed, without interrupting a chat that is mid-reply on the old setting. Your settings are saved as you change them.

## Language Model tab

- **Model:** a dropdown of the models Darkstar finds in its `models` folder, with a browse button for a `.gguf` file anywhere else. The first model found is selected automatically on a fresh profile.
- **Projector:** the multimodal projector file (a "mmproj" GGUF) that lets a vision model see images. Darkstar looks for a matching projector with the model; you can choose one, or none. A model that can see images but has no projector loaded cannot read pictures.
- **Speculative drafter:** an optional small GGUF used to draft tokens that the main model then checks, which can speed generation up.
- **MTP module:** an optional separate GGUF holding the model's multi-token prediction (MTP) head, for models whose MTP head is published as its own file. Files named the way llama.cpp names them (`mtp-` in the file name) beside the model are offered automatically, and the best match is selected by itself, as the projector is, unless you chose a module or None for that model; it is not selected while a speculative drafter is chosen, for a model with its own MTP head, or when it was made for another kind of model. **Browse** finds others. It speeds generation up the same way, using that head instead of one built into the model. A speculative drafter and an MTP module cannot be loaded together: choosing one sets the other to None.
- **Open File Location:** right-click any of these four fields, or a file in its list, to show that file in your system's file explorer.
- **Unload model:** frees the memory the loaded model uses. The same action is a button in the status bar.
- Darkstar reads a model into memory when it fits in the memory free at load time, leaving a reserve for the rest of the computer (the larger of 2 GB and 15% of your memory). A larger model is read from its file on disk as it is needed instead (memory-mapped), so loading it does not stall the computer; it then runs slower than one that fits. The model is never locked in RAM. (A model whose N-gram table Darkstar keeps on disk always reads that table from the file.) While a model runs, llama.cpp works at below-normal priority, so the rest of the computer stays responsive.

## Inference tab

These control how llama.cpp loads and runs a local model. They are hidden or fixed where they make no sense for the chosen backend.

- **llama.cpp backend:** **CUDA** (NVIDIA GPU), **Vulkan** (cross-vendor GPU) or **CPU**. Default CUDA. Pick Vulkan for AMD or Intel graphics, CPU if there is no usable GPU. CPU forces zero GPU layers.
- **Darkstar version:** the version you have. **Check for updates** asks GitHub for the newest release; if it is newer, the update notice downloads its installer (hash-checked), then Darkstar closes and opens it, and the installer updates Darkstar in place, keeping your chats, projects and settings. The same check runs when Darkstar starts, before the trial notice. **Not now** keeps the version you have.
- **llama.cpp version:** the build that ships with Darkstar is used by default. **Get latest llama.cpp** downloads the newest numbered release from GitHub (hash-checked) next to the bundled one so you can select it; it never replaces the bundled build.
- **Context size:** a slider from 10% to 100% of the model's maximum context (default 100%), shown with the resulting token count. More context needs more memory.
- **Rope Frequency Base:** 0 leaves the model's own value. Change only if you know why.
- **KV cache location:** GPU (in video memory) or CPU (in system RAM); not shown on the CPU backend. CPU saves video memory at some cost in speed.
- **KV cache type:** how the context cache is stored; the default is `q4_0` (smaller, uses less memory). Larger types (`f16`, `bf16`, `f32`, `q8_0`) use more memory for slightly higher fidelity.
- **GPU layers** (CUDA and Vulkan): how many of the model's layers go to the GPU; **Auto** by default. Lower it if the model does not fit in video memory.
- **Multi-GPU loading** (CUDA, several GPUs): **Sequential** (layers pipelined across GPUs, the default) or **Parallel** (tensor split). A live panel shows GPU memory use.
- **Threads:** 0 means half the computer's performance cores (on a processor with only one kind of core, half of all cores), never more, so the computer stays responsive while a model runs.
- **Batch size:** default 512 (32 to 65,536); larger can speed up reading long prompts at the cost of memory.
- **Parallel Slots:** default 1 (1 to 128): how many requests the model server handles at once, for example several tabs generating together. llama.cpp divides the context between the slots, so each one gets a share.
- **MTP (multi-token prediction) and N-gram table:** these run automatically, tuned to the model and the computer, and have no settings to change.

## Text Generation tab

- **System prompt:** an optional instruction placed at the start of every request.
- **Reasoning Effort:** **Auto** (the model's default) or the levels the loaded model supports (some models offer only On and Off; others offer effort levels).
- **Sampling** (defaults in brackets): **Temperature** (0.6), **Top K** (20), **Top P** (0.95), **Min P** (0.15; from 0.05, in steps of 0.05), **Repeat penalty** (1, meaning none). Lower temperature gives steadier answers, higher more varied ones.
- **DRY** repetition control, from 1 to 5 (1, off, by default): 1 turns it off, and each level after it penalises repeated phrases harder and looks further back in the text.

## Tools & Skills tab

Choose what Agent chats can use: tools, skills and MCP servers. See the agents reference for what each is and how to add it. Dropping `.py` tool files or `SKILL.md` files onto the tab adds them.

## Conversation tab

- **Name Conversations** (on by default): the loaded model names a new tab before its first answer.
- **Model idle unload** (off by default): unload the model after 10 minutes with no active or queued generation.
- **Global Memory** (on by default): gives Agent chats a tool that searches every conversation in every project, including earlier replies' reasoning and tool calls. Nothing is stored for it: it always reflects the conversations as they are now, so anything you close, delete or retry away is gone from it immediately. Agent chats only: a swarm never has it.
- **Infinite Context** (on by default) does two things. First, the model is sent only your messages and its final replies. Earlier replies' reasoning and tool calls stay visible in the chat but leave the model's context, which keeps long agent conversations small. The system prompt is always kept, and only replies the model actually finished are pruned: a reply being continued is sent whole, and so is a reply that never finished (stopped, interrupted with an instant message, or failed while the model was still reasoning), so the model still sees the work it had done. In a Task Force tab it also prunes each agent's earlier runs to their orders and reports. The raw context (**P**) shows exactly what is sent. The agent can still look up pruned reasoning and tool calls with `global_memory` while Global Memory is on; that tool's description tells it so, once, so it knows why earlier replies show no steps.
  Second, while Global Memory is on, whenever an Agent chat's context goes above 90%, during a reply or when it ends, the earliest 75% of the turns before the current one are set aside and the chat carries on with the rest. When no earlier turn is left (one long task in a single reply), the earliest 75% of that reply's own steps are set aside instead; your message and the latest step always stay. Set-aside turns stay in the chat and in Global Memory, where the model can read them again; set-aside steps stay in the reply in the chat. A request the model server refuses as too long is handled the same way and sent again; if what does not fit is the latest step's own result (a file read or command output larger than the whole context), that step is set aside too and the model is told to ask for less of it at a time. The context counter shows no figure until the next answer measures it. Turn Infinite Context off to send everything: every reply whole and the whole conversation (turning Global Memory off stops only the setting aside).
- **Tasks** (on by default): lets Agent and Sandbox chats plan a complex request as a task list, shown with **E** (see the agents reference). Turned off, the model has no planning tool.
- **Web Crawler** (on by default): offers the model the `search_web` tool. **Allow JS in Search** (off by default, shown only while Web Crawler is on) lets the pages it reads run JavaScript, including the script files they link; stylesheets, images and the scripts' own network requests stay blocked. **Max Results** (default 6) is how many pages it reads per search. Turning Web Crawler off removes the tool entirely, whatever Internet Access says.
- **MCP Servers** (off by default): the master switch for MCP. See the agents reference.
- **Microphone:** which microphone to dictate with (default microphone). **Transcription backend:** where the speech model runs (Default follows the main model's backend, or CPU, CUDA or Vulkan). **Voice transcription hotkey:** default Ctrl+O; hold it to dictate, release to transcribe into the message box. The speech-to-text runtime and its model come with the installer.

## Using a vision model

Load a multimodal model, make sure a **Projector** is selected for it, then attach or paste images in the message box. Images the model or tools show appear in the chat; click one to open the Markup Tool.

## Reasoning and "thinking"

Reasoning models show their thinking as a collapsible trace. **Reasoning Effort** sets how much it thinks, where the model supports it.

## Memory and speed, in short

Bigger models, longer context, more parallel slots and higher-precision caches all use more memory. If a model does not fit: lower the context size, move the KV cache to the CPU, keep the default `q4_0` cache type, lower GPU layers, or choose a smaller or more heavily quantized model. For speed: keep as many layers on the GPU as fit, and avoid the CPU backend if a GPU is available.
