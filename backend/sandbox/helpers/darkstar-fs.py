# SPDX-License-Identifier: LicenseRef-Darkstar-3.0
"""Darkstar's built-in workspace file tools, run inside a swarm element's sandbox.

Each call reads one JSON object (the tool arguments) from stdin and prints one
JSON object: {"ok": true, "result": ...} or {"ok": false, "error": "..."}.
The behaviour matches backend/agent/builtin/file-tools.js; the sandbox is the
boundary (Windows refuses everything outside it), so paths may be relative to
the workspace or absolute.

    darkstar-fs read_file | write_file | patch | text_read | text_write | search_files
"""

from __future__ import annotations

import json
import fnmatch
import hashlib
import tempfile
from pathlib import Path
import os
import re
import sys

WORKSPACE = os.environ["DARKSTAR_WORKSPACE"]
MAX_READ_LINES = 5_000
MAX_SEARCH_RESULTS = 1_000
MAX_TEXT_FILE_BYTES = 10 * 1024 * 1024


class ToolError(Exception):
    pass


def resolve(raw: object) -> str:
    text = str(raw or "").strip()
    if not text or "\0" in text:
        raise ToolError("A workspace path is required.")
    return os.path.normpath(text if os.path.isabs(text) else os.path.join(WORKSPACE, text))


def read_utf8(path: str) -> str:
    if not os.path.isfile(path):
        raise ToolError("Requested workspace path is not a file.")
    if os.path.getsize(path) > MAX_TEXT_FILE_BYTES:
        raise ToolError("Workspace text files are limited to 10 MiB.")
    with open(path, "rb") as handle:
        data = handle.read()
    if b"\0" in data:
        raise ToolError("Requested file appears to be binary.")
    return data.decode("utf-8", "replace")


def split_lines(content: str) -> list[str]:
    return re.split(r"\r?\n", content)


def read_file(args: dict) -> str:
    lines = split_lines(read_utf8(resolve(args.get("path"))))
    offset = max(1, int(args.get("offset") or 1))
    limit = min(MAX_READ_LINES, max(1, int(args.get("limit") or 500)))
    return "\n".join(f"{offset + index} | {line}" for index, line in enumerate(lines[offset - 1:offset - 1 + limit]))


def write_file(args: dict) -> dict:
    path = resolve(args.get("path"))
    content = str(args.get("content", ""))
    os.makedirs(os.path.dirname(path) or WORKSPACE, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    return {"path": args.get("path"), "bytes": len(content.encode("utf-8"))}


def patch(args: dict) -> dict:
    path = resolve(args.get("path"))
    content = read_utf8(path)
    old = str(args.get("old_string", ""))
    first = content.find(old)
    if not old or first < 0:
        raise ToolError("The exact old_string was not found.")
    if content.find(old, first + len(old)) >= 0:
        raise ToolError("old_string occurs more than once; provide a more specific patch.")
    updated = content[:first] + str(args.get("new_string", "")) + content[first + len(old):]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(updated)
    return {"path": args.get("path"), "replacements": 1}


def text_read(args: dict) -> dict:
    path = resolve(args.get("path"))
    if not os.path.lexists(path):
        if args.get("allow_missing") is True:
            return {"missing": True, "text": ""}
        raise ToolError(f"{args.get('path')} does not exist.")
    if os.path.islink(path) or not os.path.isfile(path):
        raise ToolError(f"{args.get('path')} is not a file.")
    if os.path.getsize(path) > MAX_TEXT_FILE_BYTES:
        raise ToolError(f"{args.get('path')} is larger than 10 MiB.")
    with open(path, "rb") as handle:
        data = handle.read()
    if b"\0" in data:
        raise ToolError(f"{args.get('path')} is a binary file.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ToolError(f"{args.get('path')} is not UTF-8 text.") from error
    return {"missing": False, "text": text}


def text_write(args: dict) -> dict:
    path = resolve(args.get("path"))
    text = args.get("text")
    if not isinstance(text, str):
        raise ToolError("text must be a string.")
    if os.path.islink(path):
        raise ToolError(f"{args.get('path')} is a symbolic link; it is not replaced.")
    directory = os.path.dirname(path) or WORKSPACE
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".darkstar-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return {"path": args.get("path"), "bytes": len(text.encode("utf-8"))}


def glob_regex(glob: str) -> re.Pattern[str]:
    source = (glob or "**/*").replace("\\", "/")
    pattern = "^"
    index = 0
    while index < len(source):
        character = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if character == "*" and following == "*":
            index += 1
            if index + 1 < len(source) and source[index + 1] == "/":
                index += 1
                pattern += "(?:.*/)?"
            else:
                pattern += ".*"
        elif character == "*":
            pattern += "[^/]*"
        elif character == "?":
            pattern += "[^/]"
        else:
            pattern += re.escape(character)
        index += 1
    return re.compile(pattern + "$")


def search_files(args: dict) -> str:
    needle = str(args.get("pattern", ""))
    if not needle:
        raise ToolError("pattern is required.")
    matcher = glob_regex(str(args.get("file_glob") or "**/*"))
    results: list[str] = []
    for directory, folders, files in os.walk(WORKSPACE):
        folders[:] = sorted(name for name in folders if name != ".git" and not os.path.islink(os.path.join(directory, name)))
        for name in sorted(files):
            full = os.path.join(directory, name)
            if os.path.islink(full):
                continue
            relative = os.path.relpath(full, WORKSPACE).replace(os.sep, "/")
            if not matcher.match(relative):
                continue
            try:
                content = read_utf8(full)
            except (ToolError, OSError):
                continue
            for number, line in enumerate(split_lines(content), start=1):
                if needle in line:
                    results.append(f"{relative}:{number}: {line}")
                    if len(results) >= MAX_SEARCH_RESULTS:
                        return "\n".join(results)
    return "\n".join(results) if results else "No matches found."



# The embedded Browser Control tool's local-HTML operations stay inside this
# element's restricted Windows token, just like its other filesystem tools.
# The host never reads or writes an element workspace for these operations.
_BROWSER_HTML_LIMIT = 16 * 1024 * 1024
_BROWSER_DEBUG_MARKER = "DARKSTAR THREE DEBUG COPY"


def _browser_html_path(raw: object) -> Path:
    path = Path(resolve(raw))
    if path.suffix.lower() not in {".html", ".htm"}:
        raise ToolError("path must identify an .html or .htm file")
    if path.is_symlink() or not path.is_file():
        raise ToolError("HTML path is missing, symbolic, or not a regular file")
    if path.stat().st_size > _BROWSER_HTML_LIMIT:
        raise ToolError("HTML exceeds the 16 MiB limit")
    return path


def _browser_utf8(path: Path) -> str:
    data = path.read_bytes()
    if b"\0" in data:
        raise ToolError("HTML file appears to be binary")
    return data.decode("utf-8-sig")


def _browser_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _browser_atomic_replace(path: Path, content: str) -> None:
    data = content.encode("utf-8")
    if len(data) > _BROWSER_HTML_LIMIT:
        raise ToolError("HTML exceeds the 16 MiB limit")
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".darkstar-browser-", delete=False) as handle:
            temp_name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def browser_file(args: dict) -> object:
    op = str(args.get("operation") or "")
    if op == "exists_many":
        candidates = args.get("paths")
        if not isinstance(candidates, list) or len(candidates) > 256 or not all(isinstance(item, str) for item in candidates):
            raise ToolError("Browser asset check requires up to 256 paths")
        return {"exists": [os.path.exists(resolve(item)) for item in candidates]}
    if op == "cleanup_debug":
        raw = args.get("path")
        if raw:
            original = _browser_html_path(raw)
            candidates = [original.with_name(f".{original.stem}.darkstar-three-debug{original.suffix.lower()}")]
        else:
            candidates = []
            visited = 0
            excluded = {".git", "node_modules", ".venv", "venv", "dist", "build", "coverage"}
            for directory, names, files in os.walk(WORKSPACE):
                names[:] = [n for n in names if n not in excluded and not os.path.islink(os.path.join(directory, n))]
                visited += len(names) + len(files)
                if visited > 50000:
                    break
                candidates.extend(Path(directory, name) for name in files
                    if name.startswith(".") and name.endswith((".darkstar-three-debug.html", ".darkstar-three-debug.htm")))
        removed = []
        for candidate in candidates:
            if not candidate.is_file() or candidate.is_symlink():
                continue
            try:
                with candidate.open("rb") as handle:
                    prefix = handle.read(4096).decode("utf-8-sig")
            except (OSError, UnicodeError):
                continue
            if _BROWSER_DEBUG_MARKER not in prefix:
                continue
            candidate.unlink()
            removed.append(os.path.relpath(candidate, WORKSPACE).replace(os.sep, "/"))
        return {"success": True, "action": "threejs_cleanup_debug", "removed": removed, "removed_count": len(removed)}

    original = _browser_html_path(args.get("path"))
    source = _browser_utf8(original)
    shown = os.path.relpath(original, WORKSPACE).replace(os.sep, "/")
    if op == "read":
        return {"content": source, "path": shown, "sha256": _browser_hash(source),
                "bytes": len(source.encode("utf-8"))}
    if op not in {"write_debug", "write_recipe"}:
        raise ToolError("Unknown browser file operation")
    expected = str(args.get("expected_sha256") or "")
    if not expected or _browser_hash(source) != expected:
        raise ToolError("The HTML file changed since it was inspected")
    content = args.get("content")
    if not isinstance(content, str):
        raise ToolError("HTML content must be a string")
    if op == "write_recipe":
        target = original
    else:
        if _BROWSER_DEBUG_MARKER not in content[:1000]:
            raise ToolError("Debug copy marker is missing")
        target = original.with_name(f".{original.stem}.darkstar-three-debug{original.suffix.lower()}")
        if target.exists():
            if target.is_symlink() or not target.is_file() or _BROWSER_DEBUG_MARKER not in _browser_utf8(target)[:1000]:
                raise ToolError("Refusing to overwrite a non-debug file")
    _browser_atomic_replace(target, content)
    return {"path": os.path.relpath(target, WORKSPACE).replace(os.sep, "/"),
            "bytes": len(content.encode("utf-8")), "sha256": _browser_hash(content)}


def coe_read_file(args: dict) -> dict:
    """Read-only briefing from this element's own workspace, never an attached or host folder."""
    raw = args.get("path")
    if not isinstance(raw, str) or not raw.strip() or "\0" in raw:
        raise ToolError("A non-empty workspace file path is required.")
    workspace = Path(WORKSPACE).resolve(strict=True)
    requested = Path(raw) if os.path.isabs(raw) else workspace / raw
    candidate = requested.resolve(strict=False)
    if not candidate.is_relative_to(workspace):
        raise ToolError("Central Orchestration Element file reads must remain inside its own sandbox working tree.")
    if requested.is_symlink() or not candidate.is_file():
        raise ToolError("Requested workspace path is not a regular file.")
    if candidate.stat().st_size > 32 * 1024 * 1024:
        raise ToolError("Text file is too large (maximum 32 MiB).")
    with candidate.open("rb") as handle:
        data = handle.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024:
        raise ToolError("Text file is too large (maximum 32 MiB).")
    if b"\0" in data:
        raise ToolError("File appears to be binary and cannot be read as UTF-8 text.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ToolError("File is not valid UTF-8.") from error
    start_line = args.get("start_line", 1)
    lines_to_read = args.get("lines_to_read", 500)
    for key, value, maximum in (("start_line", start_line, 2147483647), ("lines_to_read", lines_to_read, 5000)):
        if type(value) is not int or value < 1 or value > maximum:
            raise ToolError(f"{key} must be an integer between 1 and {maximum}.")
    lines = text.splitlines(keepends=True)
    start_index = min(start_line - 1, len(lines))
    selected = lines[start_index:start_index + lines_to_read]
    end_line = start_index + len(selected)
    eof = end_line >= len(lines)
    return {
        "success": True, "path": candidate.relative_to(workspace).as_posix(),
        "start_line": start_line, "end_line": end_line,
        "total_lines": len(lines), "eof": eof,
        "next_start_line": None if eof else end_line + 1,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": "".join(selected),
    }


# Discovery tools are Core-owned. Their implementation runs in this helper only
# for swarm elements, so all directory and file reads retain the restricted token.
_DISCOVERY_EXCLUDED = frozenset({'.git', '.hg', '.svn', '.venv', 'venv', 'node_modules', '__pycache__'})


def _discovery_int(value, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    if type(value) is not int or not minimum <= value <= maximum:
        raise ToolError(f'{name} must be an integer between {minimum} and {maximum}.')
    return value


def _discovery_bool(value, name: str, default: bool = False) -> bool:
    if value is None:
        return default
    if type(value) is not bool:
        raise ToolError(f'{name} must be a boolean.')
    return value


def _discovery_root(value: object) -> Path:
    raw = '.' if value is None or value == '' else value
    if not isinstance(raw, str) or not raw.strip() or '\0' in raw:
        raise ToolError('path must be a non-empty string when supplied.')
    workspace = Path(WORKSPACE).resolve(strict=True)
    requested = Path(raw) if os.path.isabs(raw) else workspace / raw
    candidate = requested.parent.resolve(strict=False) / requested.name
    if not candidate.is_relative_to(workspace) or not candidate.resolve(strict=False).is_relative_to(workspace):
        raise ToolError('Path escapes the element working directory.')
    if not candidate.exists() and not candidate.is_symlink():
        raise ToolError(f'Path does not exist: {raw}')
    return candidate


def discovery_list_dir(args: dict) -> str:
    raw = args.get('path') or '.'
    folder = _discovery_root(raw)
    if not folder.is_dir():
        raise ToolError(f'Path is not a directory: {raw}')
    hidden = _discovery_bool(args.get('include_hidden'), 'include_hidden')
    maximum = _discovery_int(args.get('max_entries'), 'max_entries', 1000, 1, 10000)
    rows = []
    for child in folder.iterdir():
        if not hidden and child.name.startswith('.'):
            continue
        shown = str(child.relative_to(WORKSPACE)).replace('\\', '/')
        try:
            stat = child.lstat()
            kind = 'symlink' if child.is_symlink() else 'directory' if child.is_dir() else 'file' if child.is_file() else 'other'
            rows.append({'name': child.name, 'path': shown, 'type': kind,
                         'size_bytes': stat.st_size if kind == 'file' else None,
                         'is_symlink': child.is_symlink()})
        except OSError as exc:
            rows.append({'name': child.name, 'path': shown, 'type': 'unreadable', 'error': str(exc)})
    rows.sort(key=lambda item: (item['type'] != 'directory', item['name'].casefold(), item['name']))
    shown = str(folder.relative_to(WORKSPACE)).replace('\\', '/') or '.'
    return json.dumps({'success': True, 'path': shown, 'entries': rows[:maximum],
                       'returned_entries': min(len(rows), maximum), 'total_entries': len(rows),
                       'truncated': len(rows) > maximum}, ensure_ascii=False, separators=(',', ':'))


def _discovery_globs(value: object, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 100:
        raise ToolError(f'{name} must be an array of at most 100 glob strings.')
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 500:
            raise ToolError(f'{name}[{index}] must be a non-empty glob of at most 500 characters.')
        result.append(item.strip().replace('\\', '/'))
    return result


def _discovery_matches(text: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if (fnmatch.fnmatchcase(text, pattern)
                or (pattern.startswith('**/') and fnmatch.fnmatchcase(text, pattern[3:]))
                or ('/' not in pattern and fnmatch.fnmatchcase(Path(text).name, pattern))):
            return True
    return False


def _discovery_candidates(root: Path, is_file: bool, *, hidden: bool, common: bool,
                          includes: list[str], excludes: list[str]):
    if is_file:
        yield root
        return
    workspace = Path(WORKSPACE)
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        base = Path(current)
        kept = []
        for name in sorted(dirs, key=lambda item: (item.casefold(), item)):
            candidate = base / name
            if candidate.is_symlink() or (not hidden and name.startswith('.')) or (not common and name in _DISCOVERY_EXCLUDED):
                continue
            shown = candidate.relative_to(workspace).as_posix()
            if _discovery_matches(shown, excludes):
                continue
            kept.append(name)
        dirs[:] = kept
        for name in sorted(files, key=lambda item: (item.casefold(), item)):
            candidate = base / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if not hidden and any(bit.startswith('.') for bit in candidate.relative_to(root).parts):
                continue
            shown = candidate.relative_to(workspace).as_posix()
            if (includes and not _discovery_matches(shown, includes)) or _discovery_matches(shown, excludes):
                continue
            yield candidate


def _discovery_utf8(candidate: Path, maximum: int):
    try:
        size = candidate.stat().st_size
    except OSError:
        return None, 'unreadable', 0
    if size > maximum:
        return None, 'too_large', size
    try:
        data = candidate.read_bytes()
    except OSError:
        return None, 'unreadable', size
    if b'\0' in data:
        return None, 'binary', len(data)
    try:
        return data.decode('utf-8-sig'), None, len(data)
    except UnicodeDecodeError:
        return None, 'non_utf8', len(data)


def discovery_file_search(args: dict) -> str:
    query = args.get('query')
    if not isinstance(query, str) or not query or len(query) > 10000 or '\n' in query or '\r' in query:
        raise ToolError('query must be a nonempty single-line text fragment (up to 10,000 characters).')
    root = _discovery_root(args.get('path', '.'))
    if root.is_symlink() or not (root.is_file() or root.is_dir()):
        raise ToolError('Search path must be a non-symbolic regular file or directory.')
    case = _discovery_bool(args.get('case_sensitive'), 'case_sensitive', True)
    word = _discovery_bool(args.get('whole_word'), 'whole_word', False)
    hidden = _discovery_bool(args.get('include_hidden'), 'include_hidden')
    common = _discovery_bool(args.get('include_common_excluded_directories'), 'include_common_excluded_directories')
    includes = _discovery_globs(args.get('include_globs'), 'include_globs')
    excludes = _discovery_globs(args.get('exclude_globs'), 'exclude_globs')
    offset = _discovery_int(args.get('offset'), 'offset', 0, 0, 1000000)
    maximum = _discovery_int(args.get('max_results'), 'max_results', 200, 1, 1000)
    line_chars = _discovery_int(args.get('max_line_chars'), 'max_line_chars', 1200, 80, 10000)
    max_file = _discovery_int(args.get('max_file_bytes'), 'max_file_bytes', 8388608, 1024, 32 * 1024 * 1024)
    max_files = _discovery_int(args.get('max_files'), 'max_files', 20000, 1, 100000)
    max_total = _discovery_int(args.get('max_total_bytes'), 'max_total_bytes', 268435456, 1024, 1024 * 1024 * 1024)
    expression = re.escape(query)
    if word:
        expression = rf'(?<!\w){expression}(?!\w)'
    pattern = re.compile(expression, 0 if case else re.IGNORECASE)
    matches, seen, considered, scanned, scanned_bytes = [], 0, 0, 0, 0
    skipped = {'binary': 0, 'non_utf8': 0, 'too_large': 0, 'unreadable': 0}
    truncated, reason = False, None
    for candidate in _discovery_candidates(root, root.is_file(), hidden=hidden, common=common, includes=includes, excludes=excludes):
        if considered >= max_files:
            truncated, reason = True, 'max_files'
            break
        considered += 1
        content, error, byte_count = _discovery_utf8(candidate, max_file)
        if error:
            skipped[error] += 1
            continue
        if scanned_bytes + byte_count > max_total:
            truncated, reason = True, 'max_total_bytes'
            break
        scanned += 1
        scanned_bytes += byte_count
        for number, line in enumerate(content.splitlines(), 1):
            first = pattern.search(line)
            if first is None:
                continue
            if seen < offset:
                seen += 1
                continue
            if len(matches) >= maximum:
                truncated, reason = True, 'max_results'
                break
            occurrences = 0
            for _ in pattern.finditer(line):
                occurrences += 1
                if occurrences >= 10000:
                    break
            length = len(line)
            start = 0
            end = length
            if length > line_chars:
                start = max(0, first.start() - line_chars // 3)
                end = min(length, start + line_chars)
                start = max(0, end - line_chars)
            matches.append({'path': candidate.relative_to(WORKSPACE).as_posix(), 'line_number': number,
                            'column': first.start() + 1, 'match_end_column': first.end() + 1,
                            'occurrences_in_line': occurrences, 'occurrences_capped': occurrences >= 10000,
                            'line': line[start:end], 'line_length': length, 'line_truncated': length > line_chars,
                            'snippet_start_column': start + 1, 'snippet_end_column': end})
            seen += 1
        if truncated:
            break
    return json.dumps({'success': True, 'query': query, 'search_path': root.relative_to(WORKSPACE).as_posix() or '.',
                       'case_sensitive': case, 'whole_word': word, 'matches': matches,
                       'returned_matches': len(matches), 'offset': offset, 'truncated': truncated,
                       'limit_reason': reason, 'next_offset': offset + len(matches) if truncated and reason == 'max_results' else None,
                       'files_considered': considered, 'files_scanned': scanned, 'bytes_scanned': scanned_bytes,
                       'skipped_files': skipped, 'default_excluded_directories': [] if common else sorted(_DISCOVERY_EXCLUDED)},
                      ensure_ascii=False, separators=(',', ':'))


ACTIONS = {"read_file": read_file, "write_file": write_file, "patch": patch, "text_read": text_read, "text_write": text_write, "search_files": search_files, "browser_file": browser_file, "coe_read_file": coe_read_file, "list_dir": discovery_list_dir, "file_search": discovery_file_search}


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    handler = ACTIONS.get(action)
    try:
        if handler is None:
            raise ToolError(f"Unknown file tool: {action}")
        args = json.loads(sys.stdin.read() or "{}")
        if not isinstance(args, dict):
            raise ToolError("Tool arguments must be a JSON object.")
        print(json.dumps({"ok": True, "result": handler(args)}, ensure_ascii=False))
    except (ToolError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
