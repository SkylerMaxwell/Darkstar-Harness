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
2. The decoded bundled workflow `workflows/darkstar-workflow.dswf` for shipped graph state.
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

Privileged operations must cross the trusted preload/IPC boundary. Preserve context isolation, sender validation, CSP, isolated online-browser boundaries, and project/application scoping.

Do not weaken a security boundary to make a feature easier to implement.

## 8. IPC has one canonical registry and parity must remain exact

All first-party IPC channels belong in the canonical protocol/channel registry inside `backend/Darkstar_Core.js` (logical `backend/protocol/channels.js`).

New or changed IPC must preserve exact parity among channel declaration, preload exposure, trusted main-process registration, argument validation, and tests. Preload must consume the canonical channel registry rather than maintaining a duplicate table. Do not invent ad-hoc channel strings in unrelated modules.

Ordinary request/response IPC failure normalization belongs to the canonical IPC error/registration helper. Endpoint-specific success/failure payload shapes remain part of each endpoint contract and must be preserved rather than flattened into one generic response shape.

## 9. Persistence has one canonical binary/atomic-write architecture

Workflow and chat persistence must use the existing shared binary-envelope and atomic-file primitives. Do not create a second header/hash/compression/temp-file/rename mechanism.

Wire-format changes require explicit versioning/migration behavior and regression coverage. Never silently reinterpret persisted data under a new schema.

Runtime/transient generation state must not masquerade as durable conversation history.

## 10. Tool calls are atomic historical objects

A tool call may exist transiently while generation is live, but it enters historical conversation state only as a completed assistant tool-call + matching tool-result pair.

An interrupted, malformed, cancelled, or otherwise incomplete tool call is historically nonexistent. Do not manufacture synthetic interrupted tool results merely to balance protocol structure.

Completed tool calls are immutable historical state. Stop, Continue, Retry/Edit, context handling, model changes, compaction, restore, or later reasoning must never delete or reclassify an earlier completed tool.

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

The local Autoregressive Sampler context control is model-relative. `contextPercent` is the user-owned setting and must be one of exactly `10, 20, ... 100`; `contextSize` is a derived runtime allocation calculated from the selected GGUF model's authoritative `contextLength`. The renderer must not expose an arbitrary numeric context-size editor. A model change must preserve the selected percentile and recompute the absolute token allocation for the new model, while stale/legacy absolute values migrate to the nearest ten-percent step and may never produce a value above the selected model capability. The privileged runtime must retain its independent final clamp as defense in depth.

## 13. Configuration changes must respect model/server lifecycle ownership

Control, Server, Context, and Sampler settings must use the established deferred runtime-dirty/unload policy rather than directly manipulating model state from UI controls.

Where a whole node is designated runtime-sensitive, future parameters added to that node must inherit the policy automatically; do not enumerate only today's controls unless the contract intentionally applies to one specific field.

## 14. Workspace, project, browser, and Application Interface scope must remain isolated

Project/tab/workspace ownership must remain explicit. Filesystem operations must stay within workspace containment rather than exposing arbitrary renderer paths.

Connected Application targets are project-scoped. Chromium, Windows UI Automation, and memory capabilities are capability layers on one target, not user-selected competing interfaces. Discovery must avoid duplicate application entries.

Secure Browser and online/untrusted content must remain isolated from the privileged main renderer/runtime boundary.

When browser/Application Interface adapters perform genuinely identical low-level mechanics, share those mechanics through one canonical primitive instead of cloning them. Adapter-specific semantics—verification policy, timing, modifier state, error contracts, capability differences, and security behavior—must remain in the owning adapter. Stable accessibility-reference matching likewise belongs to the shared reference-tracking primitive, with provider-specific identity rules supplied by the Chromium/UIA owners.

## 15. Preserve renderer load order and DOM ownership

Renderer logical modules execute in a dependency-sensitive order. When changing renderer initialization, verify that dependencies exist before use and that no module relies on accidental global initialization timing.

Do not duplicate DOM/event ownership for the same control. Static and dynamic actionable controls must retain one clear owning module and regression coverage.

Generation activity is owned by the registered generation session, not by answer-text emptiness. While the active tab owns a live generation, its assistant surface must retain the generation spinner through model/server preparation, prompt tokenization, reasoning, tool work, continuation, and streamed answer text; tab rerenders and delayed paints must restore/preserve it. Remove the spinner only when that generation retires, stops, or fails.

## 16. File/path moves must update every consumer, not only runtime imports

When moving or consolidating paths, search and update all relevant consumers: Core/Renderer logical identifiers, shell HTML asset URLs, package/build inputs, launcher/build scripts, workflow/provider paths, audits, source verification, tests, runtime-generated path assumptions, and documentation/indexes.

After a path migration, remove superseded files and empty directories rather than leaving compatibility residue unless a deliberate migration contract requires them.

## 17. Offline, privacy, and packaging guarantees are mandatory

The root `Darkstar.exe` is the supported polished Windows entrypoint and must remain a native GUI-subsystem launcher, not a generic BAT-to-EXE wrapper. It delegates to the root `Darkstar.bat` from the executable directory, hides the console by default with `CREATE_NO_WINDOW`, captures hidden-launch stdout/stderr in `backend/Dev/Diagnostics/launcher.log`, and exposes an explicit `--console` mode that allocates a real troubleshooting console. Because Go documents `cmd.exe`/batch files as using non-`CommandLineToArgvW` argument rules, the launcher must invoke the BAT through a controlled raw `SysProcAttr.CmdLine` with `cmd.Dir` set to the Darkstar root; do not revert to `exec.Command("cmd.exe", ...args)` quoting. Hidden BAT failures must skip the interactive `pause` and return their real exit code so the EXE can surface a Windows error dialog; direct `Darkstar.bat` launches must retain the existing visible failure pause. The launcher must embed the canonical Darkstar icon and keep its rebuildable first-party source under `launcher/windows/`.

Darkstar startup/build must not silently download, refresh, or install dependencies **except** for the two explicit source-checkout runtime bootstraps. When Electron is absent, `backend/scripts/bootstrap-electron.ps1` may fetch only its single version-pinned official Electron asset and must verify its SHA-256 before extraction. When any required `backend/bin/backends/{cpu,vulkan,cuda}/` runtime is absent, `backend/scripts/bootstrap-llamacpp.ps1` may fetch only the exact CPU, Vulkan, CUDA, CUDA-runtime, and legal-notice assets pinned in `RUNTIME_LICENSE_POLICY.json`; every download must pass its pinned SHA-256 before staged extraction/installation of the complete three-backend bundle. Neither helper may select mirrors, discover newer versions, or perform update checks. Packaged release runtime remains offline.

Do not introduce telemetry, remote fonts, hidden network bootstrap, machine-specific paths, credentials/secrets, model files, runtime profiles, diagnostics, caches, or user data into first-party source/package contents.

Generated runtime state must remain excluded from source control and production-source inventories.

Third-party native runtime licensing is a release invariant. `RUNTIME_LICENSE_POLICY.json` is the canonical classification policy for `backend/bin/`: release builds must classify every shipped `.exe`/`.dll`, preserve every required notice, reject unknown or ambiguously classified native binaries and CUDA-version mismatches, mirror runtime notices beside packaged executables, and emit the exact hashed `THIRD_PARTY_RUNTIME_MANIFEST.json`. Never weaken the gate merely to make a new runtime package build; review and declare the binary under its real upstream terms instead. Electron's own `LICENSE` and `LICENSES.chromium.html` must remain with every installed/packaged Electron distribution; the source checkout may omit the large runtime before its pinned bootstrap runs.

## 18. Build and diagnostics failures must be observable

Do not swallow startup, preload, renderer bootstrap, model/runtime, or packaging errors in ways that leave a silently crippled UI.

Where an execution boundary can fail before normal UI diagnostics exist, expose a bounded diagnostic through the owning process (for example main-process preload-error reporting) without weakening privacy or normal-release behavior.

## 19. Performance-sensitive state must have one owner and explicit invalidation

Do not repeatedly perform whole-repository, whole-process-table, whole-model-directory, or whole-stream reconstruction work inside polling/hot paths when the same result can be safely accumulated, indexed, watched, or cached once. Optimization must preserve observable behavior rather than merely reduce work or line count.

Caches are allowed only when their validity boundary is explicit. Prompt/token caches must be keyed by every prompt-affecting input and invalidated on model/server lifecycle changes. Application Interface target metadata may be reused only within its bounded freshness window and must be invalidated after target/action failures. Development source views are per-audit snapshots rather than mutable global filesystem overlays.

Model-directory monitoring should use native filesystem notifications when available, with debouncing and the existing stable-scan publication rule; unsupported/erroring native watches must retain the polling fallback. Process-family discovery should build one process graph per discovery pass instead of rescanning the complete process table for every window.

Streaming tool-call state must be incrementally accumulated by the canonical tool-call stream owner. Presentation-only derived values should be computed at emission/finalization boundaries rather than on every incoming fragment.

Generation TPS is authoritative llama.cpp telemetry, not a client-side stopwatch. Local llama.cpp requests must keep `timings_per_token: true`; transport `timings.predicted_per_second` unchanged to the renderer and use that native value for the displayed generation rate. Preserve the product gate of five consecutive exact generated-token timing samples before publishing a non-zero rate. Never derive TPS from renderer/IPC/SSE arrival timestamps, visible-text chunks, `usage` totals, or `predicted_ms`.

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
