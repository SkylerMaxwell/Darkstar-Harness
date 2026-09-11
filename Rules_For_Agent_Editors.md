# Rules for Agent Editors

**Applies to:** every source, test, documentation, workflow, asset, configuration, packaging, persistence, security, and user-visible behavior change in Darkstar.

These are mandatory engineering invariants for both AI coding agents and human editors. A change that violates any rule below is incomplete and must not be presented as finished.

## 1. All harness features must be model invariant

Darkstar features must work independently of any specific model family, chat template, reasoning syntax, tool-call syntax, or vendor convention. Do not design production behavior around Qwen, DeepSeek, Llama, or another particular model.

Model-specific parsing belongs behind the normalized llama.cpp/runtime boundary. Darkstar generation, Stop, Continue, Retry/Edit, Auto-compact, context accounting, tool execution, persistence, and UI behavior must consume model-neutral state and events.

A model may lack an optional capability such as tool calling, but Darkstar's own feature semantics must not change because a different compatible model or chat template was selected.

## 2. Implement every change in the correct architectural owner

The correct implementation is the one that fits Darkstar's existing architecture, not the one that is easiest to patch locally.

Production JavaScript is physically split along Darkstar's real Electron privilege boundary: `backend/Darkstar_Core.js` owns main/preload/backend/runtime/IPC/development-command code, while `backend/Darkstar_Renderer.js` owns sandboxed renderer code. Their indexed logical modules remain strict architectural boundaries. Extend the logical section that already owns the behavior or introduce a clean indexed owning abstraction when no appropriate owner exists.

Do not create additional first-party production `.js` files merely to avoid working inside the owning Core or Renderer monolith. Do not duplicate lifecycle, persistence, security, state, cancellation, tool, rendering, protocol, workspace, or model-management logic in unrelated sections.

`Index_for_Agents.txt` is the canonical navigation map for both production monoliths. Keep it synchronized whenever category structure, logical modules, or indexed line ranges change.

## 3. Spaghetti code, band-aids, and shallow compatibility patches are prohibited

Do not stack narrow conditionals, one-model exceptions, duplicated state, hidden fallbacks, compatibility shims, or special-case recovery branches on top of a wrong invariant.

Fix the underlying state model, ownership boundary, or lifecycle contract. When obsolete machinery conflicts with the correct architecture, remove it completely rather than wrapping another exception around it.

Do not preserve a retired source layout by making production or development tooling pretend that layout still exists. Audits and tests must understand the real Core/Renderer logical-source architecture directly; do not globally monkey-patch filesystem APIs, synthesize retired production files, or add compatibility projection steps merely to satisfy stale tooling.

A bug class should become structurally impossible whenever practical; merely hiding the observed symptom is not an acceptable fix.

## 4. Every fix must be locked by regression coverage

Every bug fix must add or strengthen automated regression coverage that reproduces the failure and proves the intended invariant.

Prefer behavioral tests over source-string assertions whenever the behavior can be exercised. Tests should cover the architectural boundary that failed, including relevant lifecycle ordering and persistence behavior, rather than only the visible symptom.

The development-only regression suite lives in `backend/Dev/Darkstar_Tests.js`. Production code must never import, embed, or package the test monolith.

A fix without regression protection is incomplete.

## 5. Maintain one source of truth; do not maintain duplicate architecture inventories

The retired `Production_Table.md` / `Development_Table.md` inventory documents must not be recreated. They became a duplicated, manually synchronized description of implementation facts and are no longer part of Darkstar's source contract.

Use these sources in this order when investigating a mismatch:

1. Executed production source and schemas in `backend/Darkstar_Core.js`, `backend/Darkstar_Renderer.js`, and non-JS runtime assets.
2. The decoded bundled workflow seed `backend/assets/default-workflow.dswf` for shipped graph state. Runtime/user workflow files are owned by the managed Workflows store (`%LOCALAPPDATA%\Darkstar\Workflows` on normal Windows launches) and must never be redirected back into the source/application tree.
3. Regression tests in `backend/Dev/Darkstar_Tests.js` for intentionally locked contracts.
4. `Rules_For_Agent_Editors.md` for engineering invariants.
5. `Index_for_Agents.txt` for source navigation and ownership.
6. `README.md` for end-user orientation.

If documentation disagrees with correct source/tests, fix the documentation. Do not alter correct runtime behavior merely to match stale prose.

## 6. Preserve the Core/Renderer monolith execution boundary

`backend/Darkstar_Core.js` and `backend/Darkstar_Renderer.js` are separate physical production files because they execute on opposite sides of Electron's privilege boundary. Core owns main process, sandboxed preload, backend/runtime, IPC, persistence, privileged services, and development commands. Renderer owns the sandboxed UI application and renderer-side custom-node code.

Each monolith's private logical module scopes and dependency direction remain architectural boundaries. Cross-file interaction must occur through the established preload/IPC bridge; do not create shared privileged globals, direct backend imports from Renderer, or renderer execution inside Core.

The sandboxed preload is especially strict: its bootstrap must rely only on APIs Electron actually guarantees in sandboxed preload. It must not assume unrestricted Node built-ins or CommonJS globals before the preload bridge has safely initialized. Internal logical-module resolution used by preload must remain pathless/Node-independent at bootstrap so preload can consume canonical Core modules without duplicating their contracts.

Production packaging must contain both production monoliths but exclude `backend/Dev/**`. Tests and audits consume the Core/Renderer logical-source inventories directly; they must not create a temporary legacy `backend/Darkstar.js` projection.

## 7. Preserve Electron security and privilege boundaries

Renderer code remains unprivileged and sandboxed. Do not enable renderer Node integration or move privileged filesystem/process/runtime operations into the renderer.

Program-wide UI theme persistence is Core-owned so the main renderer consumes one canonical selection. `Space` is the default when no theme has ever been persisted. The renderer must never consult localStorage as a theme authority; any stale pre-store theme key is discarded so it cannot override the Core-selected launch theme.

Privileged operations must cross the trusted preload/IPC boundary. Preserve context isolation, sender validation, CSP, isolated online-browser boundaries, and project/application scoping.

Do not weaken a security boundary to make a feature easier to implement.

Model-action authorization is Core-owned. The Renderer may display and edit the workflow-owned permission level only through the canonical preload/IPC bridge; it must never decide whether a tool may execute. The workflow is the sole durable source of the normalized `modelActionPermissionLevel`; loading or restoring a workflow must apply that level through Core, and no separate application preference may compete with it. Workflow data must never serialize pending attention requests, one-shot grants, per-tool approval state, or privileged execution modes. Tool definitions may declare permission risk through the supported schema metadata, but only Core may assign privileged/self-gated execution modes, and Core-owned actions must enforce non-downgradable minimum risk. Unknown undeclared tools fail closed at the external-impact class. Permission review occurs synchronously at the tool-execution boundary: Allow resumes the same in-flight invocation without exposing approval state or synthetic retry instructions to model context; Reject prevents that invocation from executing and yields exactly `The user has rejected this command.` as its tool error.

Filesystem Access is a separate Core-owned security boundary and is workflow-owned durable state under normalized `filesystemAccessLevel`. Level `1` is intentionally unrestricted by Darkstar's filesystem policy and is limited only by the OS account and the tool's other safety contracts; Level `2` is the default for new workflows and is bounded to the canonical current OS user-profile directory; Level `3` is bounded to the active workspace directory. Renderer may display/edit this value only through preload/IPC and must never enforce paths itself. Core must compute the live scope at execution time, canonicalize existing paths and parent symlinks before allowing access, revalidate delayed privileged actions such as workspace changes at Allow time, and pass only Core-issued scope metadata to bundled Python providers. File-backed internal transports may receive only narrow per-call Core-issued internal roots and must never widen the user-selected boundary. Tools must have a Core-resolved filesystem contract (`none`, `scoped`, or `unrestricted`); unknown/custom host-process providers and any tool whose filesystem behavior cannot be verifiably confined fail closed at Levels `2` and `3`. A `cwd`, sanitized environment, command blocklist, provider-declared metadata, or ordinary child process is never sufficient evidence of filesystem sandboxing.

Attention presentation and composer/queue dispatch gating are owned by the request's execution tab. A pending Allow/Reject or Yes/No decision may block only the tab whose `tabId` owns that in-flight invocation; it must never surface its decision card, error text, fresh-send block, scheduled-message block, or queued-generation block in a sibling tab, including another tab in the same project/workspace. Switching back to the owning tab must restore its pending attention surface without changing or resolving the Core request.

Model-initiated user questions are a distinct attention contract, not a permission decision. The bundled `ask_user_yes_no` tool must accept only one short single-line question ending in one question mark, must instruct the model that the sentence is directly answerable with Yes or No, and must remain self-gated so the Authorization level cannot auto-answer it. Core must keep the same invocation suspended until the user chooses Yes or No and return that answer as the ordinary tool result; No must never be translated into `USER_REJECTED_COMMAND`. Renderer presentation may relabel the generic attention buttons for this decision mode but may not own the decision semantics. On Windows, Core may emit the model's bounded question through the native Notification API only when Darkstar is unfocused or minimized; notification clicks may restore/focus Darkstar but must not answer the question.

## 8. IPC has one canonical registry and parity must remain exact

All first-party IPC channels belong in the canonical protocol/channel registry inside `backend/Darkstar_Core.js` (logical `backend/protocol/channels.js`).

New or changed IPC must preserve exact parity among channel declaration, preload exposure, trusted main-process registration, argument validation, and tests. Preload must consume the canonical channel registry rather than maintaining a duplicate table. Do not invent ad-hoc channel strings in unrelated modules.

Ordinary request/response IPC failure normalization belongs to the canonical IPC error/registration helper. Endpoint-specific success/failure payload shapes remain part of each endpoint contract and must be preserved rather than flattened into one generic response shape.

## 9. Persistence has one canonical binary/atomic-write architecture

Workflow and chat persistence must use the existing shared binary-envelope and atomic-file primitives. Do not create a second header/hash/compression/temp-file/rename mechanism.

Wire-format changes require explicit versioning/migration behavior and regression coverage. Never silently reinterpret persisted data under a new schema.

Runtime/transient generation state must not masquerade as durable conversation history.
Project chat persistence is project-owned. On normal Windows launches, Core-owned managed project directories live under `%LOCALAPPDATA%\Darkstar\Darkstar-Projects`; explicit portable-data launches use `<portable data root>\Darkstar-Projects`. The legacy lowercase `<data root>\projects` location exists only as a migration source and must never become the target for newly managed projects. Durable chat content belongs under the project's reserved `.darkstar/` metadata directory, not in a renderer-origin preference store or one global application session blob. Core owns both the canonical managed-projects root and the authoritative per-project root used for persistence; renderer-supplied workspace paths must never redirect writes. Managed-root migrations must move the whole project tree before discovery and retain a recovery copy when a cross-volume move requires copying. The reserved metadata directory must stay hidden from ordinary Workspace File Explorer operations and inaccessible to scoped filesystem tools. External project roots may be remembered globally only as lightweight pointers needed to rediscover their project-owned session files.

A missing/disabled autosave preference, renderer-origin change, load/decrypt/parse failure, or filesystem reconciliation failure must never delete durable chat state or synthesize an empty replacement over it. Autosave controls future writes only. Destructive deletion of saved chat state must require an explicit destructive action. Legacy migrations must be lossless, atomically write the new project-owned representation, verify/reload successfully where practical, and retain the original legacy session as a recovery backup rather than deleting it.

## 10. Tool calls are atomic historical objects

A tool call may exist transiently while generation is live, but it enters historical conversation state only as a completed assistant tool-call + matching tool-result pair.

An interrupted, malformed, cancelled, or otherwise incomplete tool call is historically nonexistent. Do not manufacture synthetic interrupted tool results merely to balance protocol structure.

Completed tool calls are immutable historical state. Stop, Continue, Retry/Edit, context handling, model changes, compaction, restore, or later reasoning must never delete or reclassify an earlier completed tool.

`/adversary` must review the same visible multimodal evidence available to the original agent without receiving hidden reasoning or raw tool protocol. Tool-produced image context should be projected into ordinary user-role image context for the adversary request; do not expose the persisted `toolContext` container itself.

Continue applies to assistant reasoning/content, never to resuming a partial tool invocation. If a tool is interrupted, discard only that incomplete tool artifact and preserve valid assistant state before it. Tool-preparation state therefore represents only the current live call and must not contain resumable seed/partial-call reconstruction state.

## 11. Generation lifecycle and cancellation must have canonical owners

Start, Stop, forced-stop conditions, interruption persistence, Retry/Edit regeneration, Continue, compaction, queue dispatch, and model unload must use the established generation/session lifecycle owners.

Do not create parallel cancellation semantics. A feature that needs to stop generation must reach the same authoritative cancellation lifecycle rather than approximating Stop with an unrelated abort path.

UI state such as Continue visibility, composer blocking, and generation-active state should be derived from canonical runtime/history state instead of sticky independent booleans whenever possible.

Destructive conversation mutations (Clear, Delete, Edit/regenerate, Retry truncation, tab/project removal) must never rewrite or remove history while an older generation owner can still finalize into that history. Cancel queued work assembled against superseded history, request cancellation from the canonical owner, await owner retirement when a live session exists, then commit the mutation against stable message identity rather than stale array coordinates.

## 12. Context accounting must use authoritative runtime state

Do not infer an authoritative context-window conclusion before the active model/runtime has established the real context length.

Live generation occupancy and reconstructed idle-conversation occupancy may be different measurements, but they must be explicitly distinguished and evaluated against the same authoritative loaded context length when relevant.

Context-safety behavior must remain a rough safety contract, not a fake exact final-token detector.

Purpose-specific local asset history must remain namespaced by semantic owner. Invoke Language Model GGUF history, Diffusion Backend GGUF history, projector history, and their last-used filesystem-browser locations must not share persistence keys or populate one another's dropdowns. Reusing the common filesystem-browser UI is allowed; reusing unrelated history/inventory state is not. Diffusion companion discovery may inspect supported weight files only in the selected diffuser's directory for automatic binding; it may auto-bind a required LLM text encoder or VAE only when exactly one structurally compatible candidate exists. Ambiguous candidates must remain unselected rather than being guessed.

The local LlamaCPP Server context control is model-relative. `contextPercent` is the user-owned setting and must be one of exactly `10, 20, ... 100`; `contextSize` is a derived runtime allocation calculated from the selected GGUF model's authoritative `contextLength`. The renderer must not expose an arbitrary numeric context-size editor. A model change must preserve the selected percentile and recompute the absolute token allocation for the new model, while stale/legacy absolute values migrate to the nearest ten-percent step and may never produce a value above the selected model capability. The privileged runtime must retain its independent final clamp as defense in depth.

## 13. Configuration changes must respect model/server lifecycle ownership

Runtime-owning LlamaCPP Server settings and strategic Orchestrator settings must use the established deferred runtime-dirty/unload policy rather than directly manipulating model state from arbitrary UI controls. **LlamaCPP Server is the sole owner of Context size** because context allocation configures llama.cpp startup/runtime memory. Context-size edits are runtime-affecting and must defer unload/restart. **LM Sampler** (stable node type `localSampler`; legacy display title `L_Sampler`) owns Reasoning Effort, request-time language-model sampling, Stop strings, prompt-cache reuse, and Ignore EOS; those request-time edits must not unload or restart the loaded model. Its required Language Model input comes from LlamaCPP Server, and its single LM Sampler output embeds the selected model descriptor and connects to Orchestrator. The bundled **DM Sampler custom node** owns diffusion sampling policy, has one optional `DIFFUSION_MODEL` input from Diffusion Backend GGUF, and has exactly one `DM_SAMPLER` output to Orchestrator. DM Sampler must never launch the native runtime itself. Its persisted **Compute Device** policy must remain `Auto`, `CPU`, or one exact GPU device identifier discovered through the privileged diffusion runtime. GPU enumeration must use the native stable-diffusion.cpp device inventory exposed through preload/IPC rather than renderer-side process access; explicit device selection must reach stable-diffusion.cpp through `--backend`, and `--auto-fit` must not override a resolved CPU/GPU choice. **Generate Image** is a bundled Tools provider: Orchestrator forwards the connected DM configuration into Core ToolService, ToolService exposes `generate_image` only when that configuration is valid, and only privileged Core DiffusionRuntime may launch/cancel stable-diffusion.cpp. Orchestrator also owns the persisted **Image count (0 = Model)** override from 0 to 50: `0` must expose a required model-selected `image_count` of 1-50, while a nonzero override must hide model count control and force the exact configured value. Counts above one must execute as sequential single-image DiffusionRuntime generations, never as a native batch, and each completed image must receive a distinct durable `context-image` identity. Live preview frames are transient renderer progress and must not be persisted into chat history; only completed validated images may enter the durable `context-image` path. Diagnostic `context-image` patches must default to the same collapsed disclosure state as other traces. **Show Image** is the dedicated response-presentation capability: it may accept only an exact stable `image_id` already registered by an image-producing tool in the current agent interaction, must not accept arbitrary filesystem paths or model-supplied base64, and must resolve to the existing durable image timeline payload rather than creating a duplicate `context-image` or second copy of the image bytes. Its model-neutral `presentedImageIds` state must survive every sampler/graph/finalization boundary, and the resolved image must render after assistant text as the final answer element. When a user-authored image edit is armed, the existing Generate Image capability becomes masked inpainting: model-visible schema must hide source/mask/crop/width/height authority, Core must validate the pristine PNG and approved region, derive its own black/white mask, invoke native `--init-img` + `--mask` (and configured denoise strength where supported), and hard-composite the generated patch over the pristine source before any final image is published so native mask leakage can never alter protected pixels. For canonical local GGUF workflows, **Orchestrator owns chat-history/system-prompt assembly plus strategic controls for conversation naming, Auto-compact, model idle unload, Dynamic VRAM, Image count, delegated-agent enablement, and Maximum sub-agent depth**. Maximum sub-agent depth defaults to 8 for legacy compatibility, accepts `0` as Unlimited, must be copied into every child request unchanged, and must remain the sole Core nesting-depth ceiling; do not introduce a second hidden constant cap. Dynamic VRAM is an Orchestrator-owned cross-runtime policy: before diffusion execution, Core must measure currently available system RAM and compare it against a conservative resident-memory estimate for the loaded language model (including projector overhead where present), its KV cache, and every configured diffusion pipeline file including text encoders and VAEs. When that estimate is reliable and free RAM is strictly greater than the combined requirement, Darkstar should establish a CPU/no-mmap RAM parking runtime for the same model/KV capacity before releasing the GPU-resident model; after diffusion, restore the original model/projector/runtime configuration while the RAM copy is still warm, then destroy the parking runtime. If RAM is insufficient, the estimate is unreliable, the original LM is already CPU-only, or RAM parking cannot be established, the existing full unload/restore path remains the mandatory fallback. Both strategies must preserve the owning agent stream/controller, invalidate physical KV/cache residency for the primary runtime, reject competing LM work while the lease is active, and restore unconditionally before the agent resumes. App shutdown may release the lease without restoring because no subsequent inference will occur. It is the composition boundary for LM Sampler + optional DM Sampler + Skills/Tools; no direct Language Model/`gguf` socket belongs on canonical Orchestrator. The legacy Context and Control node types remain model-independent compatibility surfaces for API/custom workflows that explicitly use them, but canonical local workflows must not require separate Context or Control graph sockets.

Where a whole node is designated runtime-sensitive, future parameters added to that node must inherit the policy automatically; explicit request-only exemptions must be declared by the owning node definition rather than duplicated in unrelated dirty-state code.

## 14. Workspace, project, browser, and Application Interface scope must remain isolated

Project/tab/workspace ownership must remain explicit. Filesystem operations must stay within workspace containment rather than exposing arbitrary renderer paths. Unsent composer state is tab-owned: text and the pending image attachment must survive tab/project switches and chat-session persistence, and programmatic submit/clear operations must update the owning tab draft rather than leaving stale text to reappear later. Tab order is durable UI state encoded by the canonical persisted tab array, not a second ordering store. Reordering within one project may never change conversation ownership or active-tab identity. Moving a tab across projects must preserve its globally stable tab identity and complete tab-owned state, rebind only future workspace/KV/security scope to the destination project, leave every source project with at least one tab, preserve the current project instead of navigating to the destination or auto-opening the moved tab, preserve the destination project's existing active-tab selection, and must be refused while that tab owns running or queued model work so an in-flight request can never change project/workspace scope underneath execution.

Connected Application targets are project-scoped. Chromium, Windows UI Automation, and memory capabilities are capability layers on one target, not user-selected competing interfaces. Discovery must avoid duplicate application entries.

Embedded browser online/untrusted content must remain separated from the privileged main renderer/runtime boundary.

Internet Access is a separate Core-owned, workflow-owned browser egress boundary under normalized `internetAccessEnabled`. Renderer may display/edit it only through preload/IPC. When disabled, every live hybrid browser must return to offline mode, any isolated online-browser host must be terminated, and all later online navigation/control attempts must fail closed in Core; local/offline browser content and bundled assets remain usable. Legacy workflows without the field preserve historical behavior by restoring Internet Access as enabled.

When browser/Application Interface adapters perform genuinely identical low-level mechanics, share those mechanics through one canonical primitive instead of cloning them. Adapter-specific semantics—verification policy, timing, modifier state, error contracts, capability differences, and security behavior—must remain in the owning adapter. Stable accessibility-reference matching likewise belongs to the shared reference-tracking primitive, with provider-specific identity rules supplied by the Chromium/UIA owners.

## 15. Preserve renderer load order and DOM ownership

Renderer logical modules execute in a dependency-sensitive order. When changing renderer initialization, verify that dependencies exist before use and that no module relies on accidental global initialization timing.

Do not duplicate DOM/event ownership for the same control. Static and dynamic actionable controls must retain one clear owning module and regression coverage.

Generation activity is owned by the registered generation session, not by answer-text emptiness. While the active tab owns a live generation, its assistant surface must retain the generation spinner through model/server preparation, prompt tokenization, reasoning, tool work, continuation, and streamed answer text; tab rerenders and delayed paints must restore/preserve it. Remove the spinner only when that generation retires, stops, or fails.

## 16. File/path moves must update every consumer, not only runtime imports

When moving or consolidating paths, search and update all relevant consumers: Core/Renderer logical identifiers, shell HTML asset URLs, package/build inputs, launcher/build scripts, workflow/provider paths, audits, source verification, tests, runtime-generated path assumptions, and documentation/indexes.

After a path migration, remove superseded files and empty directories rather than leaving compatibility residue unless a deliberate migration contract requires them.

## 17. Offline, privacy, and packaging guarantees are mandatory

Darkstar Harness first-party code and materials are licensed under the Apache License 2.0. The root `LICENSE.md` contains the first-party license terms. Keep first-party SPDX identifiers as `Apache-2.0`, and do not replace the project license or add incompatible first-party licensing terms unless the project owner explicitly directs a license change. Third-party components must retain their required upstream notices and license terms.

The root `Launch_Darkstar.bat` is the primary Windows source-checkout entrypoint. The BAT owns presence-only provisioning decisions for pinned Python/Electron/llama.cpp/stable-diffusion.cpp components and launches the `backend/shell` Electron application directly. **Normal startup must remain presence-only and single-Electron:** do not deep-validate already-present runtimes, do not enumerate every native DLL/license as a launch prerequisite, do not recursively invoke the BAT, and do not launch Electron in `ELECTRON_RUN_AS_NODE` mode as an intermediate process. Full version/hash/signature/runtime validation belongs inside bootstrap helpers and runs only when provisioning is actually needed. The obsolete VBS and native-EXE launcher handoffs must remain absent.


Darkstar startup/build must not silently download, refresh, or install dependencies **except** for the three explicit source-checkout bootstrap helpers. `backend/scripts/bootstrap-python.ps1` may use only the pinned official Python 3.11.9 x64 installer identified in `backend/runtime-component-policy.json`; it must require a 64-bit Python 3.11 interpreter, verify the installer SHA-256 and Python Software Foundation Authenticode signature before execution, and launch the official installer **interactively** without silent-install or feature-selection switches. A release archive should carry the installer under `backend/vendor/python/`; an incomplete source checkout may recover only that exact python.org asset. When Electron is absent, `backend/scripts/bootstrap-electron.ps1` may fetch only its single version-pinned official Electron asset and must verify its SHA-256 before extraction. When any required `backend/bin/backends/{cpu,vulkan,cuda}/` runtime is absent, `backend/scripts/bootstrap-llamacpp.ps1` may fetch only the exact CPU, Vulkan, CUDA, CUDA-runtime, and legal-notice assets pinned in `backend/runtime-component-policy.json`; every download must pass its pinned SHA-256 before staged extraction/installation of the complete three-backend bundle. None of these helpers may select mirrors, discover newer versions, or perform update checks. Packaged release runtime remains offline.

Do not introduce telemetry, remote fonts, hidden network bootstrap, machine-specific paths, credentials/secrets, model files, runtime profiles, diagnostics, caches, or user data into first-party source/package contents.

Generated runtime state must remain excluded from source control and production-source inventories.

Third-party native runtime licensing is a release invariant. `backend/runtime-component-policy.json` is the canonical classification policy for `backend/bin/`: release builds must classify every shipped `.exe`/`.dll`, preserve every required notice, reject unknown or ambiguously classified native binaries and CUDA-version mismatches, mirror runtime notices beside packaged executables, and emit the exact hashed `THIRD_PARTY_RUNTIME_MANIFEST.json`. Never weaken the gate merely to make a new runtime package build; review and declare the binary under its real upstream terms instead. Electron's own `LICENSE` and `LICENSES.chromium.html` must remain with every installed/packaged Electron distribution; the source checkout may omit the large runtime before its pinned bootstrap runs.

## 18. Build and diagnostics failures must be observable

Do not swallow startup, preload, renderer bootstrap, model/runtime, or packaging errors in ways that leave a silently crippled UI.

Where an execution boundary can fail before normal UI diagnostics exist, expose a bounded diagnostic through the owning process (for example main-process preload-error reporting) without weakening privacy or normal-release behavior.

## 19. Performance-sensitive state must have one owner and explicit invalidation

Do not repeatedly perform whole-repository, whole-process-table, whole-model-directory, or whole-stream reconstruction work inside polling/hot paths when the same result can be safely accumulated, indexed, watched, or cached once. Optimization must preserve observable behavior rather than merely reduce work or line count.

Caches are allowed only when their validity boundary is explicit. Prompt/token caches must be keyed by every prompt-affecting input and invalidated on model/server lifecycle changes. Application Interface target metadata may be reused only within its bounded freshness window and must be invalidated after target/action failures. Development source views are per-audit snapshots rather than mutable global filesystem overlays.

Model-directory monitoring should use native filesystem notifications when available, with debouncing and the existing stable-scan publication rule; unsupported/erroring native watches must retain the polling fallback. Process-family discovery should build one process graph per discovery pass instead of rescanning the complete process table for every window.

Streaming tool-call state must be incrementally accumulated by the canonical tool-call stream owner. Presentation-only derived values should be computed at emission/finalization boundaries rather than on every incoming fragment.

Generation TPS is authoritative llama.cpp telemetry, not a client-side stopwatch. Local llama.cpp requests must keep `timings_per_token: true`; transport `timings.predicted_per_second` unchanged to the renderer and use that native value for the displayed generation rate. Preserve the product gate of five consecutive exact generated-token timing samples before publishing a non-zero rate. Never derive TPS from renderer/IPC/SSE arrival timestamps, visible-text chunks, `usage` totals, or `predicted_ms`.

Normal renderer-driven autosaves must not perform workflow sanitization/filesystem probing, serialization, compression, whole-payload secure-storage encryption, file writes, or fsync work through synchronous Electron main-process paths. Keep payload-size-dependent preprocessing off the Electron browser/main thread; if OS secure storage is synchronous, use it only to wrap a small data key and protect the bulk payload asynchronously. Keep synchronous atomic persistence only for bounded shutdown/emergency durability, and sequence async commits so an older background save can never overwrite a newer synchronous checkpoint. Parameter-only Settings edits must use the lightweight node-patch autosave channel so one scalar control change never retransmits or structured-clones the complete workflow through Renderer→Core IPC; the persistence worker owns the mirrored workflow state and applies node replacements before encoding. Full-snapshot autosave remains reserved for structural workflow mutations, explicit fallback when no worker baseline exists, and shutdown durability.

Long-lived native helper processes must preserve the prior executable fallback, timeout/error, concurrency, security, and teardown semantics. Persistent Windows UIP PowerShell helpers are pooled so concurrent native operations remain independent, and every owning bridge/service must close them during shutdown. Do not serialize previously concurrent operations merely to reuse a process.

## 20. Continue must be a lossless recovery path

Native Continue is a first-class generation lifecycle, not a fresh-send approximation. Preserve every valid assistant reasoning/content token and every completed historical tool transaction. The sole intentional ablation is an incomplete final tool call: remove that generated tool tail and continue from the surviving assistant prefix rather than attempting to resume tool syntax.

A cancelled generation owner must retire before its successor starts, but a Continue action arriving during retirement must join that retirement rather than fail spuriously. A previously latched context warning must not preempt Continue or Auto-compact before the fully assembled request is evaluated. Prompt-cache reuse must remain enabled for explicitly isolated llama.cpp slots; prefer the slot that still owns the conversation cache identity. When physical cache ownership is unavailable, fall back to authoritative cold token accounting and reconstruction rather than assuming residency. Auxiliary model calls, model/server epoch changes, and prompt-affecting mutations must never be mistaken for resident conversation KV.

## 21. Documentation rules

Update `Rules_For_Agent_Editors.md` when an engineering invariant changes.

Update `Index_for_Agents.txt` whenever either production monolith's category/subcategory/module organization or line ranges change.

Update `README.md` when an end-user-facing startup, installation, feature, or usage statement changes.

Do **not** manually maintain exhaustive source inventories, line counts, test counts, feature ledgers, or implementation tables as a second source of truth. Such facts should be derived from source/tests/indexes when needed.

## Completion gate

Before considering any Darkstar change complete:

1. Confirm the change is model invariant where model/runtime behavior is involved.
2. Confirm the change lives in the correct architectural owner and introduces no duplicate source of truth.
3. Confirm no spaghetti, band-aid, obsolete compatibility, or dead-path residue remains.
4. Confirm completed historical tool calls and persisted state cannot be corrupted by the change.
5. Confirm Electron/main/preload/renderer privilege boundaries remain intact.
6. Confirm IPC/persistence/workspace/Application Interface scope contracts remain intact where touched.
7. Add or strengthen regression coverage for every bug fix.
8. Update `Index_for_Agents.txt`, `Rules_For_Agent_Editors.md`, and/or `README.md` only when their respective contracts actually changed.
9. Remove superseded files and empty directories created by the change.
10. Run `npm --prefix backend/shell run verify` from the repository root and resolve every failure before handoff; this includes the runtime-license audit.
11. For build/path/native changes, also exercise `npm --prefix backend/shell run build` far enough to verify the intended path/dependency behavior. Source startup/build may materialize only the explicitly pinned Electron and llama.cpp runtime bundles through their audited bootstrap helpers; no other dependency download is permitted.

A modification is not finished while a known architectural invariant, regression, security boundary, or documentation contract is knowingly false.

The Browser Workspace is browser-only; do not reintroduce an image editor, image-mode tab, image rail, or editor-local image store into that surface. Conversation and tool-produced images remain owned by canonical chat/context state and use the renderer-owned in-UI image editor. The editor must use the Browser foreground block-reason API while open so a native BrowserView cannot overlay it. Its viewport chrome stays minimal: a centered tool bar above a plain theme-owned canvas, no decorative checker pattern or persistent footer/caption, cursor-anchored wheel zoom, and middle-button panning that never steals left-button Select/Brush gestures. Image-edit authority is user-owned: rectangle selection must produce the exact approved region; brush mode must derive the minimum square that encloses every stroke including brush radius and must fail closed rather than clip marks when such a square cannot fit inside the source. The visible guide may be supplied to the model for understanding, but the pristine source image, authoritative region/mask, crop geometry, and final containment are never model-controlled. Core DiffusionRuntime must derive the mask itself, require stable-diffusion.cpp `--init-img` plus `--mask` support, and hard-composite the native result over the pristine source so every pixel outside the approved region remains byte-identical to the source. An armed edit must persist with the tab-owned image draft/session state and flow through the existing Generate Image capability rather than creating a second privileged diffusion tool.

