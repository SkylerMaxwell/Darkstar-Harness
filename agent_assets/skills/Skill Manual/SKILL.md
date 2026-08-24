---
name: darkstar-tool-usage
description: Detailed operating manual for choosing, sequencing, and safely using Darkstar's workspace, file, Python, browser screenshot, and Skill-access tools.
version: 1.0.0
author: OpenAI
license: MIT
platforms: [windows, macos, linux]
metadata:
  darkstar:
    category: agent-operations
    tags: [tools, filesystem, editing, python, browser, workflow]
---

# Darkstar tool-use manual

Use this Skill whenever a task requires inspecting, creating, editing, moving, copying, deleting, executing, or visually checking files in the active Darkstar project.

The available tool set depends on the current workflow. Never invent a tool that is not present in the current tool manifest. The standard Darkstar workflow exposes the tools documented below. `skills_list` and `skill_view` are present only when one or more Skills are connected.

## Core operating rules

1. **Treat the open project as the only writable workspace.**
   Filesystem tools confine paths to the project currently opened in Darkstar. Prefer workspace-relative paths such as `src/app.js`. An absolute path is valid only when it still resolves inside the active workspace.

2. **Inspect before mutating.**
   Before editing an existing file, read the relevant section. Copy the complete target line or line block and, when useful, the stable unchanged line immediately before and/or after it. Before moving, copying, or deleting, inspect the parent directory so the exact source and destination are known.

3. **Use the narrowest correct tool.**
   - Read by lines when line structure matters.
   - Read by characters when offsets, very long lines, or exact substrings matter.
   - Use `safe_edit_tool` for precise changes to an existing file. Supply an exact whole-line target; add exact adjacent `before`/`after` anchors when the target repeats. It never uses fuzzy matching or guesses an occurrence.
   - Use `replace_file` for a new file, a complete rewrite, or content too broad for exact replacements.
   - Use `run_python` for bounded computation or document generation, not as a substitute for ordinary file tools.

4. **Reject ambiguous edits.**
   A Safe Edit target must resolve to exactly one line-block location. If it appears more than once, add stable immediately adjacent `before` and/or `after` anchors. If the tool rejects the target or anchors, reread the nearby lines instead of guessing.

5. **Keep tool arguments strict JSON.**
   Use only declared fields. Do not include comments, trailing commas, unescaped control characters, or prose outside the JSON object. Ensure every string is fully closed.

6. **Recover from tool errors deliberately.**
   Read the error, correct the arguments or choose another tool, then continue. Do not repeat the same failing call unchanged.

7. **Verify important mutations.**
   After a write or edit, inspect the returned digest and, when correctness matters, reread the changed region. After producing HTML, use `screenshot_html` to inspect the rendered result.

8. **Avoid destructive operations unless required.**
   `delete` is permanent. Prefer moving a file to a backup name when the user's intent is uncertain. Never delete the project root.

9. **Do not treat helper files as callable tools.**
   `_darkstar_tool_common.py` is internal shared code and registers no tool.

## Recommended task sequence

For a typical coding or content-editing task:

1. Call `get_current_project_working_directory` only when the workspace location is unclear.
2. Use `list_dir` to understand the relevant folder.
3. Use `read_file_lines` or `read_file_chars` to inspect the target.
4. Plan the smallest safe mutation.
5. Call `safe_edit_tool` for existing-file edits or `replace_file` for creation/full rewrites. Copy exact whole lines into `target`; do not count line numbers or add a trailing newline.
6. Reread the changed section.
7. Run bounded validation with `run_python` when useful.
8. For HTML, call `screenshot_html` and inspect the attached image.
9. Report exactly what changed and any unresolved issue.

---

# Tool reference

## `get_current_project_working_directory`

### Purpose

Return the absolute path of the project folder currently opened in Darkstar. This is read-only and accepts no arguments.

### Use it when

- The active workspace is unknown.
- A user refers to “the current project,” “this folder,” or a path whose base is ambiguous.
- You need to explain where generated files were placed.

### Do not use it when

- A workspace-relative path is already known and no absolute path is needed.
- You merely want to inspect project contents; use `list_dir` instead.

### Arguments

```json
{}
```

### Important result fields

- `working_directory`: absolute project path.
- `source`: how Darkstar resolved the workspace, such as execution context or process working directory.

### Example

```json
{}
```

---

## `list_dir`

### Purpose

List the immediate children of one directory. It does not recurse.

### Arguments

- `path` — directory inside the project. Defaults to `.`.
- `include_hidden` — include names beginning with `.`. Defaults to `false`.
- `max_entries` — result bound from 1 to 10,000. Defaults to 1,000.

### Use it when

- Discovering project structure.
- Confirming whether a file or folder exists.
- Inspecting a destination before copy, move, or delete.
- Finding exact capitalization and names.

### Result behavior

Entries are sorted with directories first. Each entry can include:

- `name`
- `path`
- `type`: `directory`, `file`, `symlink`, `other`, or `unreadable`
- `size_bytes` for regular files
- `is_symlink`
- `error` for unreadable entries

The result also reports `returned_entries`, `total_entries`, and `truncated`.

### Example

```json
{
  "path": "src",
  "include_hidden": false,
  "max_entries": 1000
}
```

### Common mistakes

- Expecting recursive output. Call it again for child directories.
- Forgetting `include_hidden: true` when looking for `.gitignore`, `.env.example`, or `.darkstar`.
- Assuming a symlink is a normal file. Treat symlinks cautiously; many file tools reject them.

---

## `read_file_lines`

### Purpose

Read a bounded line range from a UTF-8 text file. Line numbers are one-based.

### Arguments

- `path` — file inside the workspace.
- `start_line` — first one-based line; default 1.
- `lines_to_read` — 1 to 5,000; default 500.

### Use it when

- Reading source code, Markdown, configuration, logs, or other line-oriented text.
- Inspecting a known section by line number.
- Obtaining a `sha256` before a safe edit.

### Important result fields

- `text`: exact selected text.
- `start_line`, `end_line`, `total_lines`
- `eof`
- `next_start_line` when more remains
- `sha256`: digest of the complete file, not only the selected range

### Pagination pattern

1. Read the first range.
2. If `eof` is false, call again with `start_line` equal to `next_start_line`.
3. Preserve the newest `sha256` if a later write will use conflict detection.

### Example

```json
{
  "path": "src/app.js",
  "start_line": 1,
  "lines_to_read": 300
}
```

### Common mistakes

- Passing zero-based line numbers. The first line is 1.
- Editing from an old digest after another operation changed the file.
- Reading thousands of irrelevant lines instead of narrowing the range.

---

## `read_file_chars`

### Purpose

Read a bounded Unicode-character range from a UTF-8 text file. Character offsets are zero-based and count decoded characters, not bytes.

### Arguments

- `path` — file inside the workspace.
- `start_char` — zero-based character offset; default 0.
- `chars_to_read` — 1 to 100,000; default 2,500.

### Use it when

- A file contains very long lines.
- Exact character positions matter.
- You need a bounded substring without line-based slicing.
- Continuing from a known character offset.

### Important result fields

- `text`
- `start_char`, `end_char`, `total_chars`
- `eof`
- `next_start_char`
- `sha256` of the complete file

### Example

```json
{
  "path": "data/large.json",
  "start_char": 0,
  "chars_to_read": 10000
}
```

### Choosing between line and character reads

Use `read_file_lines` for normal code and prose. Use `read_file_chars` for minified assets, generated JSON, huge single-line files, or precise character slicing.

---

## `replace_file`

### Purpose

Atomically create or rewrite a UTF-8 text file, or append text to an existing file.

### Arguments

- `path` — target file inside the project.
- `new_content` — UTF-8 text to write.
- `mode` — `replace` or `append`; defaults to `replace`.
- `expected_sha256` — optional digest from a prior read or write.

### Use it when

- Creating a new file.
- Replacing an entire file.
- The intended change is too broad or structurally complex for exact replacements.
- Writing generated HTML, CSS, JavaScript, configuration, or documentation.

### Large-content behavior

A complete valid payload can normally be sent in one call. Darkstar automatically uses a private file-backed transfer for large content before invoking the Python provider. The model-facing schema does not impose the former 4,000-character limit.

An internal safety maximum of 8 Mi characters remains. For exceptionally large output, use ordered calls:

1. First call with `mode: "replace"`.
2. Read the returned `sha256`.
3. Continue with `mode: "append"` and `expected_sha256` set to the latest digest.
4. Repeat until complete.

Appending to a nonexistent file fails; begin with `replace`.

### Atomicity and safety

- Parent folders are created automatically.
- Existing file permissions are preserved when possible.
- The write uses a temporary file and atomic replacement.
- Symbolic-link targets are rejected.
- Paths outside the workspace are rejected.

### Important result fields

- `created`
- `mode`
- `previous_sha256`
- `sha256`
- `characters_written`
- `total_characters`
- `bytes_written`
- `transport`: `inline` or `file-backed`

### Create example

```json
{
  "path": "src/config.json",
  "new_content": "{\n  \"enabled\": true\n}\n",
  "mode": "replace"
}
```

### Conflict-safe replacement example

```json
{
  "path": "README.md",
  "new_content": "# Revised project documentation\n",
  "mode": "replace",
  "expected_sha256": "<digest returned by the latest read>"
}
```

### Common mistakes

- Using append for the first chunk of a new file.
- Omitting `expected_sha256` when modifying a file that may have changed.
- Sending malformed JSON with an unterminated `new_content` string.
- Replacing a whole file when one exact edit would be safer.

---

## `safe_edit_tool`

### Purpose

Replace 1 to 100 exact, non-overlapping whole lines or consecutive line blocks in an existing UTF-8 file and commit them with one atomic write.

The tool does not use line numbers, fuzzy search, nearest-match behavior, or a required SHA-256 argument. Each edit is identified by:

- `target` — the exact complete line or consecutive line block to replace;
- optional `before` — exact unchanged line/block immediately before the target;
- optional `after` — exact unchanged line/block immediately after the target.

A target plus its supplied anchors must identify exactly one location. If it identifies zero or multiple locations, the entire call fails and nothing is written.

### Arguments

- `path` — existing UTF-8 file.
- `edits` — array of exact line-block replacements.

Each edit contains:

- `target` — exact complete line or line block. Indentation matters. A trailing newline is not required and is ignored if supplied.
- `replacement` — replacement line or block. Use an empty string to delete the target lines.
- `before` — optional exact unchanged line/block immediately before `target`.
- `after` — optional exact unchanged line/block immediately after `target`.

The tool automatically preserves LF or CRLF line endings. All edits are resolved against the original file, may be supplied in any order, and cannot overlap.

### Use it when

- Editing an existing source or text file.
- Replacing one or several known whole lines or line blocks.
- The same target appears more than once and stable neighboring lines can identify the intended occurrence.
- A wrong-location edit must be rejected rather than guessed.

### Example

After reading the target with its neighboring lines, call:

```json
{
  "path": "potato_file.html",
  "edits": [
    {
      "before": "    <pre><code>",
      "target": "line 1:  const potato = \"russet\";",
      "after": "line 2:  const size = \"large\";",
      "replacement": "line 1:  const potato = \"yukon gold\";"
    }
  ]
}
```

No line counting, file digest, or terminal `\n` is needed.

### Common mistakes

- Supplying only a repeated target without enough anchors to make it unique.
- Using partial-line text instead of copying the complete line.
- Omitting indentation from `target`, `before`, or `after`.
- Using an anchor that is not immediately adjacent to the target.
- Splitting one region into overlapping edits instead of one combined replacement.
- Using `replace_file` for a localized change.

---

## `create_folder`

### Purpose

Create one directory and any missing parent directories.

### Arguments

- `path` — folder path inside the project.

### Behavior

- If the folder already exists, the call succeeds and reports that it was not newly created.
- If a non-directory already exists at that path, the call fails.
- Paths outside the workspace are rejected.

### Use it when

- An empty directory must exist.
- Preparing a folder before operations that do not create parents themselves.

`replace_file`, `copy`, and `move` already create missing destination parents, so a separate folder call is often unnecessary.

### Example

```json
{
  "path": "assets/generated"
}
```

---

## `copy`

### Purpose

Copy one file or a complete directory tree to an exact final destination while preserving file metadata.

### Arguments

- `source` — existing project path.
- `destination` — exact final destination path.
- `overwrite` — optional boolean; default `false`.

### Use it when

- Duplicating a file or folder.
- Creating a backup before risky work.
- Copying a template tree to a new location.

### Important behavior

- Destination means the exact resulting path, not merely a parent directory.
- Missing destination parents are created.
- Existing destinations fail unless `overwrite: true`.
- Directory sources are checked recursively; any symbolic link causes rejection.
- A directory cannot be copied inside itself.
- Copying uses staging and backup paths to reduce partial replacement risk.

### Important result fields

- `source`, `destination`
- `copied_type`: `file` or `directory`
- `copied_entries`
- `replaced_existing`
- `cleanup_warning`, if temporary-backup cleanup failed after a successful copy

### Example

```json
{
  "source": "src/template",
  "destination": "src/template-backup",
  "overwrite": false
}
```

### Common mistakes

- Supplying a destination directory while expecting the source name to be added automatically.
- Enabling overwrite without first inspecting the destination.
- Attempting to copy a tree containing symlinks.

---

## `move`

### Purpose

Move or rename one file or folder to an exact final destination.

### Arguments

- `source` — existing project path.
- `destination` — exact final path.
- `overwrite` — optional boolean; default `false`.

### Use it when

- Renaming a file or folder.
- Reorganizing project structure.
- Moving generated output into its intended location.

### Important behavior

- The project root cannot be moved.
- Missing destination parents are created.
- Existing destinations fail unless `overwrite: true`.
- A folder cannot be moved inside itself.
- When overwriting, the previous destination is temporarily backed up and restored if the move fails.

### Example

```json
{
  "source": "draft/index.html",
  "destination": "public/index.html",
  "overwrite": true
}
```

### After moving code

Search or inspect the project for references to the old path. The move tool changes filesystem location only; it does not update imports, links, manifests, or configuration.

---

## `delete`

### Purpose

Permanently delete one file, symlink entry, or directory tree.

### Arguments

- `path` — target inside the project.

### Use it when

- The user explicitly requested deletion.
- A known temporary artifact should be removed.
- Cleanup is required after a verified replacement or migration.

### Safety rules

- The project root cannot be deleted.
- Paths outside the workspace are rejected.
- Directories are removed recursively.
- The operation is irreversible.

### Before deleting

1. Use `list_dir` to verify the exact target.
2. Consider `move` to a backup location when intent is uncertain.
3. Do not delete files merely because they appear unused without checking references.

### Example

```json
{
  "path": "tmp/obsolete-build"
}
```

### Important result fields

- `deleted_type`
- `deleted_entries`
- `path`

---

## `run_python`

### Purpose

Execute bounded Python code in a fresh per-call folder under:

```text
.darkstar/python_runs/<run-id>
```

### Arguments

- `code` — Python source, maximum 200,000 characters.
- `timeout_seconds` — 1 to 60; default 30.

### Good uses

- Deterministic calculations and data transformations.
- Parsing local data that is awkward to inspect manually.
- Creating charts, images, PDFs, DOCX, PPTX, or XLSX files.
- Validating generated data or source structure.
- Producing temporary analysis artifacts.

### Available libraries

The allowed import set includes standard utility modules and these document/image libraries:

- Pillow: `PIL`
- `pypdf`
- ReportLab: `reportlab`
- python-docx: `docx`
- python-pptx: `pptx`
- `openpyxl`

Other allowed roots include common modules such as `json`, `csv`, `math`, `statistics`, `re`, `pathlib`, `datetime`, `hashlib`, `zipfile`, and XML utilities.

### Sandbox behavior

- Network access is blocked.
- Child-process execution is blocked inside the submitted program.
- Writes are confined to the per-call run directory.
- Reads can access the workspace and installed package/runtime roots.
- Symlink and hard-link creation are blocked.
- Output is limited to approximately 2 MB.
- File size and resource limits are applied where supported.
- This is an application-level sandbox, not a hardened virtual machine. Do not run hostile or untrusted code.

### Runtime variables

The executed program receives:

- `OUTPUT_DIR` — absolute per-call output directory.
- `WORKSPACE_DIR` — absolute active project directory.

Relative writes go into the run directory. To create an artifact, write it beneath `OUTPUT_DIR` and then use `copy` or `move` if it must be placed elsewhere in the project.

### Result fields

- `success`
- `stdout`, `stderr`
- `traceback` on failure
- `exit_code`
- `duration_ms`
- `run_directory`
- `files`: generated file paths relative to the run directory, with sizes

### Example

```json
{
  "timeout_seconds": 30,
  "code": "from pathlib import Path\nimport json\nroot = Path(WORKSPACE_DIR)\ndata = json.loads((root / 'data.json').read_text(encoding='utf-8'))\nprint({'records': len(data)})\n"
}
```

### Common mistakes

- Trying to use `requests`, sockets, subprocesses, or shell commands.
- Writing directly into the workspace instead of `OUTPUT_DIR`.
- Assuming generated files appear in the project root; inspect `run_directory` and `files`.
- Printing huge payloads instead of writing them to an output file.
- Using Python for simple file reads or exact text edits that dedicated tools handle more safely.

---

## `browser_control`

### Purpose

Control the isolated internal browser with native pointer and keyboard events.

### Reliable operating loop

1. Open a workspace HTML page with `action: "open"`.
2. Request `action: "snapshot"`.
3. Prefer returned element refs for `click`, `type`, and `fill`.
4. Request another snapshot after navigation or a substantial UI change.
5. Use `screenshot` and viewport coordinates only when the target is visual or does not expose a useful element ref.

Refs are tied to the current document element. If the page replaces that element, the tool rejects the stale ref rather than guessing. Take a new snapshot and continue.

### Native input actions

- `click`, `move`, `mouse_down`, `mouse_up`, `drag`, and `wheel`
- `type` inserts at the current caret; `fill` replaces an editable field
- `key` presses and releases one key
- `key_down` and `key_up` support held-key interaction across tool calls
- `release_all` clears every held key and mouse button
- `dialog` accepts or dismisses a pending JavaScript dialog

Coordinates are CSS pixels in the current browser viewport. Use `snapshot_after: false` only for rapid low-level input where an immediate snapshot is unnecessary.

### Safety boundaries

The page must be inside the active tab's workspace. A browser session opened by another chat tab cannot be controlled until this tab opens its own page. Network access, downloads, permissions, popups, and files outside the workspace remain blocked.

## `screenshot_html`

### Purpose

Open a workspace `.html` or `.htm` file in Darkstar's visible, network-isolated right-side browser, capture the displayed browser viewport as PNG, and attach that screenshot to the model's next context turn.

### Requirements

- The target must be inside the active workspace.
- The target must be an HTML file.
- The loaded model must have a multimodal projector enabled; otherwise the screenshot cannot be attached to model context.

### Arguments

- `path` — workspace-relative `.html` or `.htm` path.
- `wait_ms` — optional extra delay from 0 to 10,000 milliseconds after normal render settling.
- `wait_ms` is only an additional millisecond delay; it is not the browser execution timeout. Browser initialization, loading, settling, and capture have separate bounded deadlines.
- If the tool reports an internal-browser timeout, inspect the page for synchronous infinite loops, blocking dialogs, or renderer overload instead of issuing the same screenshot call repeatedly.

### Use it when

- Verifying the visual result of generated or edited HTML/CSS/JavaScript.
- Checking layout, typography, spacing, overflow, responsiveness, and visible runtime errors.
- Comparing the rendered page with the user's requested design.

### Browser behavior

- The in-app browser is visible to the user.
- The requested page remains open for inspection.
- Internet access is blocked.
- Navigation is confined to workspace-local content.
- The screenshot reflects the browser's current viewport.

### Recommended visual QA loop

1. Write or edit the HTML and related assets.
2. Call `screenshot_html`.
3. Inspect the attached image carefully.
4. Identify concrete visual defects.
5. Edit the smallest relevant files.
6. Capture again until the result is correct.

### Example

```json
{
  "path": "public/index.html",
  "wait_ms": 500
}
```

### When to increase `wait_ms`

Use a modest delay when local animations, delayed scripts, web fonts, or asynchronous local asset setup need extra time. Do not use a large delay by default.

### Common mistakes

- Calling it before the HTML file exists.
- Expecting external CDN assets or internet resources to load.
- Using it without a vision-capable projector.
- Treating a successful screenshot as proof that all interaction logic works; separately validate behavior when needed.

---

# Skill-access functions

These functions appear when one or more Skills are connected. They are access functions, not ordinary workspace tools and not Skill names.

## `skills_list`

List connected Skills and their metadata.

### Arguments

```json
{}
```

### Use it when

- The user asks which Skills are available.
- The connected-skill catalog is absent or uncertain.
- You need the exact Skill name before calling `skill_view`.

Do not present ordinary tool function names as Skills.

## `skill_view`

Load the instructions for one connected Skill, or read one supporting file from that Skill's directory.

### Arguments

- `name` — exact Skill name.
- `file_path` — optional relative supporting-file path.

### Use pattern

1. Call `skills_list` only when needed to discover exact names.
2. Call `skill_view` with the exact Skill name before applying that Skill.
3. Omit `file_path` to load `SKILL.md`.
4. Request a supporting file only when the Skill instructions identify it as relevant.

### Example

```json
{
  "name": "darkstar-tool-usage"
}
```

---

# High-quality tool strategies

## Safe targeted edit

1. `read_file_lines` around the target.
2. Retain `sha256`.
3. `safe_edit_tool` with the exact whole-line target and stable adjacent anchors when needed.
4. Reread the changed range.

## New file creation

1. Inspect the destination folder with `list_dir`.
2. Call `replace_file` with `mode: "replace"`.
3. Inspect the result digest.
4. Read the file back if correctness matters.

## Large file generation

1. Prefer one complete `replace_file` call; Darkstar safely transports large valid payloads.
2. If the model cannot emit one valid call, split content at logical boundaries.
3. Use `replace` for the first segment and `append` for later segments.
4. Use the returned changed line/block as the target for any later edit.
5. Read the completed file and validate structure.

## HTML implementation and review

1. Inspect existing files.
2. Write or edit HTML/CSS/JS.
3. Call `screenshot_html`.
4. Correct visible defects.
5. Repeat capture until stable.
6. Do not rely on external network assets because the browser is offline. Packaged Three.js r184 is already available as `window.THREE` before page scripts run, so do not add a Three.js CDN script or core import.

## Rename or restructure

1. Inspect source and destination parents.
2. Use `move` with overwrite disabled unless replacement is explicitly intended.
3. Search or inspect references to the old path.
4. Update references with `safe_edit_tool`.
5. Validate the project structure.

## Backup before risky changes

1. Use `copy` to create a clearly named backup.
2. Perform the mutation.
3. Verify the result.
4. Delete the backup only when the user requested cleanup or the result is fully confirmed.

## Python-generated artifact

1. Use `run_python` and write beneath `OUTPUT_DIR`.
2. Inspect the returned `files` list.
3. Use `copy` or `move` from the reported run directory into the intended project location.
4. Verify the final artifact exists.

## Tool failure recovery

- **Path does not exist:** inspect with `list_dir`; correct path or create the prerequisite.
- **Path escapes workspace:** use a project-contained path; do not attempt bypasses.
- **Digest mismatch:** reread, recalculate, and retry with the new digest.
- **Ambiguous exact edit:** expand the search context; do not blindly use `replace_all`.
- **Malformed JSON:** issue a fresh, complete call with properly escaped strings.
- **Append target missing:** start with `mode: "replace"`.
- **Destination exists:** inspect it; choose another destination or set `overwrite: true` only when justified.
- **Screenshot requires projector:** explain that visual context requires a multimodal projector; do not repeatedly retry unchanged.
- **Python import blocked:** rewrite using an allowed library or dedicated Darkstar tools.
- **Python timeout:** reduce work, process less data, or increase `timeout_seconds` within the 60-second limit.

# Final checklist

Before finishing a tool-driven task, confirm:

- The correct workspace and target paths were used.
- Existing content was inspected before mutation.
- Destructive actions matched explicit intent.
- Important writes used current SHA-256 conflict protection.
- Tool errors were corrected rather than blindly repeated.
- The final files were reread or otherwise validated.
- HTML output was visually inspected when appearance mattered.
- The response states concrete outcomes, file locations, and any remaining limitation.
