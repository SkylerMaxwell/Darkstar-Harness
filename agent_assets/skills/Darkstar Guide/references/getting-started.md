# Getting started, licensing and data

## What Darkstar is

A Windows 11 desktop app for running language models on your own computer. Local models are GGUF files run through llama.cpp with a CUDA (NVIDIA), Vulkan (any GPU) or CPU backend. Darkstar has chats, agent features (tools, skills, MCP servers and an embedded browser) and Swarm tabs. It makes no telemetry requests.

## Installing

- Run the Darkstar installer (`Darkstar-Setup-<version>.exe`). It is one file that carries everything Darkstar needs (its own Python with the tool packages, its own Electron, llama.cpp with CPU, Vulkan and CUDA builds, and the speech-to-text runtime), so it installs without an internet connection.
- It installs **per user, with no administrator prompt**, by default into `%LOCALAPPDATA%\Programs\Darkstar`. You can pick another folder, but it must be one you can write to; Program Files and Windows folders are refused. The installer checks free space first.
- Pages, in order: Welcome, license agreement (you must scroll to the end and tick acceptance), license key, models, location and options, then the install.
- **License key page:** leave the field empty and the button reads *Skip*, which continues with the default Community edition. Type or paste a 20-character key (dashes are added for you) and *Next* checks it with the Darkstar license server; only the key is sent. A wrong key is refused, and if the server cannot be reached the key is not accepted (you can skip and enter it later from the trial notice).
- **Models page (optional):** lists the models Darkstar publishes on Hugging Face, with the download size and the memory each needs. A row is green (*Likely fits*) when it needs no more than your memory minus 2 GB for Windows, red (*Too large*) otherwise. Memory counts installed RAM plus the dedicated memory of graphics cards that have their own; an integrated GPU that borrows system RAM adds nothing. Select any number, or press *Skip*. With no internet connection the list says so and checks again every 10 seconds.
- **Model downloads** run after Darkstar is installed, each into `<install folder>\models\<model name>\`. Every file is verified against the published checksum; a stopped or failed download leaves no partial file; a connection that drops is retried and resumes.
- Shortcuts: Start menu entries (Darkstar and Uninstall Darkstar) and, optionally, a desktop shortcut. Darkstar starts from `exec\Darkstar.exe` in the install folder.
- The installer refuses to run while Darkstar is open.

## Updating and uninstalling

- **Update:** run a newer installer over the existing install. It updates in place; the key page starts with your saved key so the edition is kept. Darkstar also checks for a newer version when it starts and offers it (see models-and-settings, Darkstar version); it never installs one unless you let the notice go ahead.
- **Uninstall:** Windows Settings, Installed apps, or *Uninstall Darkstar* in the Start menu. It removes what the installer installed. Your `models` folder and your data (`%LOCALAPPDATA%\Darkstar`: chats, projects, settings, swarm sandbox folders) are **kept** unless you tick *Also delete my chats, projects and settings*. A plain uninstall keeps the license key; the data option removes it.

## First launch

1. With no saved settings yet, Darkstar connects every bundled tool and skill (including this guide) and selects the first model it finds in the `models` folder. This happens only on the very first launch of a fresh profile. If a skill or tool of a later version is missing from Tools & Skills, add it with **Add Tool Files…** or **Add SKILL.md Files…** (the file dialog opens in the bundled folder).
2. A trial notice appears on the default edition (see below).
3. Pick a model in Settings, Language Model, then type in the message box.

To use a model that is somewhere else, choose it in Settings, Language Model with the browse button next to Model; the file can stay where it is.

## Editions, trial and licensing

- Darkstar is commercial software under the Darkstar Software License v3.0. Redistribution and rebranding are not permitted; the full terms are in `LICENSE.md` in the install folder.
- **Default (Community) edition:** includes a **31-day trial** that starts the first time Darkstar is launched. At launch a notice shows how many days remain (it says the trial is ending soon in the last days). It has **Continue Trial**, **Buy Now** and an **Enter license key** link. Once the 31 days are over the notice says the trial has ended and that use of Darkstar now requires a Professional or Enterprise license; its button then reads **Continue**.
- **Professional and Enterprise keys** are 20 letters or digits shown as `XXXX-XXXX-XXXX-XXXX-XXXX`. Enter one during installation, or in the trial notice with *Enter license key*, then *Activate*. The key is stored in your Windows user registry (`HKCU\Software\Darkstar\License`). A licensed edition does not show the trial notice.
- **The license check** is the one request Darkstar makes on its own, and only for Professional or Enterprise keys. It sends only the key. The answer is remembered and asked again after about a week, so a licensed copy keeps working offline in between.
- Licensing questions go to the Licensor named in `LICENSE.md`.

## Where things are kept

- **Program:** the install folder (default `%LOCALAPPDATA%\Programs\Darkstar`).
- **Models:** `<install folder>\models`, or wherever you point Darkstar.
- **Your data:** `%LOCALAPPDATA%\Darkstar`. It holds `app` (your settings, swarm state, logs and diagnostics), `projects` (one folder per project), `cache`, and `runtimes` (newer llama.cpp builds you installed, swarm sandboxes). Chats are saved automatically; there is no setting to turn that off.
- **MCP server values** are stored encrypted with your Windows account and never with your other settings or returned to the interface. The license key is in the registry as above.
- Setting the environment variable `DARKSTAR_PORTABLE_DATA_ROOT` moves the whole data folder to another place.

## Privacy and network use

- No telemetry, no analytics, no remote fonts, no automatic update checks.
- Network use happens only when you cause it: Search Web and the Action Engine (needs Internet Access on), an MCP server on the internet, model downloads in the installer, the optional *Get latest llama.cpp* button (downloads from GitHub, hash-checked), the update check (when Darkstar starts and from *Check for updates*: it asks GitHub for the newest release and, only when one is newer, downloads its installer, hash-checked), and the license check for Professional or Enterprise keys.
- With **Internet Access** off, the browser, Search Web and Browser Control are unavailable and open web pages are closed. With **MCP Servers** off, no MCP server is started or contacted.
- The local model server listens only on this computer and requires a random key that Darkstar creates at every launch and never writes down, so other programs and websites open in your browser cannot use your model or read what it is working on. Darkstar refuses to run a llama.cpp build that would not enforce the key.
- Local models never send your messages anywhere. Chats and files stay in the folders above.

## Closing Darkstar

Closing the window ends everything Darkstar started, immediately: the model server and any loaded model, speech and image runtimes, tool processes, and programs those started. Nothing keeps running or holding memory afterward, even if Darkstar crashes. Generation continues at full speed while the window is minimised, behind other windows, or when the screen is locked.
