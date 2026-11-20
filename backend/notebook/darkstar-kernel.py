#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Darkstar-3.0
"""Darkstar's notebook kernel.

Runs the cells of one notebook in a single persistent namespace. Requests arrive as JSON lines on standard input and
everything a cell produces is reported as JSON lines on the stream Darkstar reads; what the cell writes to standard
output and standard error, from Python or from native code, is captured and reported too.
"""

from __future__ import annotations

import _thread
import ast
import base64
import builtins
import codecs
import importlib
import io
import json
import linecache
import math
import os
import platform
import queue
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import traceback
import types

MAX_TEXT_CHARS = 200_000
MAX_TABLE_ROWS = 60
MAX_TABLE_COLUMNS = 24
MAX_TABLE_CELL_CHARS = 240
MAX_CHART_BARS = 24
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_PREVIEW_CHARS = 120
MAX_VARIABLES = 500
MAX_SUMMARY_NAMES = 3
STREAM_FLUSH_SECONDS = 0.05
STREAM_FLUSH_CHARS = 64_000
PROGRESS_SECONDS = 0.1
SYNC_MARKER = "\x00darkstar-sync\x00"
SYNC_SECONDS = 0.5
KERNEL_FILE = os.path.abspath(__file__)
PIP_LINE = re.compile(r"^(\s*)%pip\s+(.*)$")
SHELL_LINE = re.compile(r"^(\s*)!(?!=)(.*)$")
PIP_COMMAND = re.compile(r"^(?:pip3?|python3?\s+-m\s+pip)\s+(.*)$")


class Channel:
    def __init__(self, stream):
        self.stream = stream
        self.lock = threading.Lock()

    def send(self, message):
        line = json.dumps(message, ensure_ascii=False, default=str)
        with self.lock:
            self.stream.write(line + "\n")
            self.stream.flush()


class StreamWriter(io.TextIOBase):
    def __init__(self, kernel, name, descriptor):
        super().__init__()
        self.kernel = kernel
        self.name = name
        self.descriptor = descriptor

    @property
    def encoding(self):
        return "utf-8"

    def writable(self):
        return True

    def isatty(self):
        return False

    def fileno(self):
        return self.descriptor

    def write(self, text):
        text = str(text)
        self.kernel.buffer(self.name, text)
        return len(text)

    def flush(self):
        self.kernel.flush_streams()


class NoInput(io.TextIOBase):
    def readable(self):
        return True

    def read(self, size=-1):
        raise EOFError("Notebook cells cannot read from standard input; put the values in the code.")

    def readline(self, size=-1):
        raise EOFError("Notebook cells cannot read from standard input; put the values in the code.")


def cell_text(value):
    if isinstance(value, float):
        text = "nan" if math.isnan(value) else f"{value:.6g}"
    else:
        text = str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    return text if len(text) <= MAX_TABLE_CELL_CHARS else text[: MAX_TABLE_CELL_CHARS - 1] + "…"


def clipped(text, limit=MAX_TEXT_CHARS):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def describe(value):
    kind = type(value).__name__
    shape = getattr(value, "shape", None)
    if isinstance(shape, tuple) and shape and all(isinstance(size, int) for size in shape):
        return kind, " × ".join(f"{size:,}" for size in shape)
    if isinstance(value, (str, bytes)) or not hasattr(value, "__len__"):
        return kind, ""
    try:
        return kind, f"{len(value):,}"
    except Exception:
        return kind, ""


def is_matplotlib(value):
    if (type(value).__module__ or "").startswith("matplotlib"):
        return True
    return isinstance(value, (list, tuple)) and bool(value) and all((type(item).__module__ or "").startswith("matplotlib") for item in value)


def assigned_names(tree):
    names = []

    def collect(target):
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                collect(element)

    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                collect(target)
        elif isinstance(statement, (ast.AnnAssign, ast.AugAssign)):
            collect(statement.target)
    unique = []
    for name in names:
        if not name.startswith("_") and name not in unique:
            unique.append(name)
    return unique


def command_arguments(text):
    arguments = shlex.split(text, posix=os.name != "nt")
    if os.name != "nt":
        return arguments
    return [argument[1:-1] if len(argument) > 1 and argument[0] == argument[-1] and argument[0] in "\"'" else argument
            for argument in arguments]


def transform(code):
    lines = code.split("\n")
    changed = False
    for index, line in enumerate(lines):
        match = PIP_LINE.match(line)
        if match:
            lines[index] = f"{match.group(1)}__darkstar_pip__({match.group(2).strip()!r})"
            changed = True
            continue
        match = SHELL_LINE.match(line)
        if match:
            command = match.group(2).strip()
            pip = PIP_COMMAND.match(command)
            call = f"__darkstar_pip__({pip.group(1)!r})" if pip else f"__darkstar_shell__({command!r})"
            lines[index] = f"{match.group(1)}{call}"
            changed = True
    return "\n".join(lines) if changed else code


class Kernel:
    def __init__(self, channel):
        self.channel = channel
        self.current = None
        self.executing = threading.Event()
        self.buffers = {}
        self.buffer_lock = threading.Lock()
        self.descriptors = {}
        self.injected = {
            "progress": self.progress,
            "display": self.display_values,
            "__darkstar_pip__": self.pip,
            "__darkstar_shell__": self.shell,
        }
        self.namespace = {"__name__": "__main__", "__builtins__": builtins}
        self.namespace.update(self.injected)

    def capture_descriptor(self, descriptor, name):
        read_end, write_end = os.pipe()
        os.dup2(write_end, descriptor)
        os.close(write_end)
        synced = threading.Event()
        self.descriptors[descriptor] = synced

        def pump():
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            carry = ""
            while True:
                try:
                    data = os.read(read_end, 65536)
                except OSError:
                    return
                if not data:
                    return
                text = carry + decoder.decode(data)
                carry = ""
                while SYNC_MARKER in text:
                    before, text = text.split(SYNC_MARKER, 1)
                    self.buffer(name, before)
                    synced.set()
                for length in range(len(SYNC_MARKER) - 1, 0, -1):
                    if text.endswith(SYNC_MARKER[:length]):
                        text, carry = text[:-length], text[-length:]
                        break
                self.buffer(name, text)

        threading.Thread(target=pump, name=f"darkstar-{name}", daemon=True).start()

    def sync_descriptors(self):
        if os.name != "nt":
            try:
                import ctypes
                ctypes.CDLL(None).fflush(None)
            except Exception:
                pass
        for descriptor, synced in self.descriptors.items():
            synced.clear()
            try:
                os.write(descriptor, SYNC_MARKER.encode("utf-8"))
            except OSError:
                continue
            synced.wait(SYNC_SECONDS)

    def buffer(self, name, text):
        if not text:
            return
        with self.buffer_lock:
            self.buffers.setdefault(name, []).append(text)
            size = sum(len(part) for part in self.buffers[name])
        if size >= STREAM_FLUSH_CHARS:
            self.flush_streams()

    def flush_streams(self):
        with self.buffer_lock:
            pending = {name: "".join(parts) for name, parts in self.buffers.items() if parts}
            self.buffers = {}
        request = self.current
        if request is None:
            return
        for name, text in pending.items():
            self.channel.send({"id": request, "event": "stream", "name": name, "text": text})

    def flush_loop(self):
        while True:
            time.sleep(STREAM_FLUSH_SECONDS)
            if self.executing.is_set():
                self.flush_streams()

    def interrupt(self):
        if not self.executing.is_set():
            return
        if os.name == "nt":
            _thread.interrupt_main()
        else:
            os.kill(os.getpid(), signal.SIGINT)

    def send_output(self, output):
        if output is None or self.current is None:
            return
        self.flush_streams()
        self.channel.send({"id": self.current, "event": "display", "output": output})

    def display_values(self, *values):
        for value in values:
            self.send_output(self.render(value))

    def progress(self, iterable, total=None, label="items"):
        if total is None:
            try:
                total = len(iterable)
            except TypeError:
                total = None
        request = self.current
        label = clipped(label, 60)
        started = time.monotonic()
        last = 0.0
        done = 0

        def report():
            if request is not None:
                self.channel.send({"id": request, "event": "progress", "progress": {
                    "label": label, "done": done, "total": total, "seconds": round(time.monotonic() - started, 3)}})

        report()
        for item in iterable:
            yield item
            done += 1
            now = time.monotonic()
            if now - last >= PROGRESS_SECONDS:
                last = now
                report()
        report()

    def run_process(self, arguments, shell):
        process = subprocess.Popen(arguments, shell=shell, cwd=os.getcwd(), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            while True:
                data = os.read(process.stdout.fileno(), 65536)
                if not data:
                    break
                self.buffer("stdout", decoder.decode(data))
            return process.wait()
        except KeyboardInterrupt:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdout.close()

    def pip(self, arguments):
        code = self.run_process([sys.executable, "-m", "pip"] + command_arguments(arguments), False)
        importlib.invalidate_caches()
        if code != 0:
            raise RuntimeError(f"pip exited with code {code}.")

    def shell(self, command):
        code = self.run_process(command, True)
        if code != 0:
            self.buffer("stderr", f"The command exited with code {code}.\n")

    def png_output(self, data):
        if len(data) > MAX_IMAGE_BYTES:
            return {"type": "text", "text": f"(An image of {len(data):,} bytes is too large to show.)"}
        return {"type": "image", "mimeType": "image/png", "base64": base64.b64encode(data).decode("ascii")}

    def figure_output(self, figure):
        stream = io.BytesIO()
        figure.savefig(stream, format="png", dpi=110, bbox_inches="tight")
        return self.png_output(stream.getvalue())

    def capture_figures(self):
        pyplot = sys.modules.get("matplotlib.pyplot")
        if pyplot is None:
            return
        for number in pyplot.get_fignums():
            self.send_output(self.figure_output(pyplot.figure(number)))
        pyplot.close("all")

    def table_output(self, frame, chart):
        rows_total, columns_total = frame.shape
        shown = frame.iloc[:MAX_TABLE_ROWS, :MAX_TABLE_COLUMNS]
        numeric = []
        for dtype in shown.dtypes:
            numeric.append(dtype.kind in "iufc")
        output = {
            "type": "table",
            "index": cell_text(frame.index.name) if frame.index.name is not None else "",
            "columns": [cell_text(column) for column in shown.columns],
            "numeric": numeric,
            "rows": [[cell_text(index)] + [cell_text(value) for value in row]
                     for index, row in zip(shown.index, shown.itertuples(index=False, name=None))],
            "totalRows": int(rows_total),
            "totalColumns": int(columns_total),
        }
        if chart:
            output["chart"] = chart
        return output

    def series_chart(self, series):
        if len(series) == 0 or len(series) > MAX_CHART_BARS or series.dtype.kind not in "iuf":
            return None
        bars = []
        for label, value in series.items():
            number = float(value)
            if not math.isfinite(number):
                return None
            bars.append({"label": cell_text(label), "value": number})
        title = series.index.name if series.index.name is not None else series.name
        return {"title": cell_text(title) if title is not None else "", "bars": bars}

    def render(self, value):
        if value is None or is_matplotlib(value):
            return None
        module = type(value).__module__ or ""
        try:
            if module.startswith("PIL.") and hasattr(value, "save"):
                stream = io.BytesIO()
                image = value if value.mode in ("1", "L", "LA", "P", "RGB", "RGBA") else value.convert("RGBA")
                image.save(stream, format="PNG")
                return self.png_output(stream.getvalue())
            if module.startswith("pandas"):
                if hasattr(value, "columns") and hasattr(value, "iloc"):
                    return self.table_output(value, None)
                if hasattr(value, "to_frame") and hasattr(value, "iloc"):
                    name = value.name if value.name is not None else "value"
                    return self.table_output(value.to_frame(name=name), self.series_chart(value))
        except Exception:
            pass
        try:
            text = repr(value)
        except Exception as error:
            text = f"<{type(value).__name__} could not be shown: {error}>"
        return {"type": "text", "text": clipped(text)}

    def describe_error(self, error):
        frames = [frame for frame in traceback.extract_tb(error.__traceback__)
                  if os.path.abspath(frame.filename) != KERNEL_FILE]
        text = ""
        if frames:
            text = "Traceback (most recent call last):\n" + "".join(traceback.format_list(frames))
        text += "".join(traceback.format_exception_only(type(error), error))
        return {"name": type(error).__name__, "message": clipped(str(error), 2000), "traceback": clipped(text, 20_000)}

    def parse(self, code, filename):
        try:
            return ast.parse(code, filename=filename, mode="exec")
        except SyntaxError:
            transformed = transform(code)
            if transformed == code:
                raise
            return ast.parse(transformed, filename=filename, mode="exec")

    def summary(self, names):
        items = []
        for name in names:
            if name not in self.namespace or name in self.injected:
                continue
            kind, size = describe(self.namespace[name])
            items.append({"name": name, "type": kind, "size": size})
            if len(items) >= MAX_SUMMARY_NAMES:
                break
        return items

    def execute(self, request, code, label):
        filename = f"<{label}>"
        self.current = request
        started = time.monotonic()
        status, error, names = "ok", None, []
        self.executing.set()
        try:
            tree = self.parse(code, filename)
            linecache.cache[filename] = (len(code), None, code.splitlines(True), filename)
            names = assigned_names(tree)
            last = None
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                last = ast.Expression(tree.body.pop().value)
            exec(compile(tree, filename, "exec"), self.namespace)
            if last is not None:
                value = eval(compile(last, filename, "eval"), self.namespace)
                if value is not None:
                    self.namespace["_"] = value
                    self.send_output(self.render(value))
        except KeyboardInterrupt:
            status = "interrupted"
        except BaseException as caught:
            status, error = "error", self.describe_error(caught)
        finally:
            self.executing.clear()
        try:
            self.capture_figures()
        except Exception as caught:
            self.send_output({"type": "text", "text": f"A figure could not be drawn: {caught}"})
        try:
            summary = self.summary(names) if status == "ok" else []
        except Exception:
            summary = []
        self.sync_descriptors()
        self.flush_streams()
        self.channel.send({"id": request, "event": "done", "status": status, "error": error, "summary": summary,
                           "seconds": round(time.monotonic() - started, 3)})
        self.current = None

    def variables(self):
        items = []
        for name, value in list(self.namespace.items()):
            if name.startswith("_") or name in self.injected or isinstance(value, types.ModuleType):
                continue
            kind, size = describe(value)
            preview = ""
            if value is None or isinstance(value, (bool, int, float, complex, str, bytes)):
                try:
                    preview = clipped(repr(value), MAX_PREVIEW_CHARS)
                except Exception:
                    preview = ""
            items.append({"name": name, "type": kind, "size": size, "preview": preview})
            if len(items) >= MAX_VARIABLES:
                break
        return items

    def handle(self, message):
        request = message.get("id")
        operation = message.get("op")
        if operation == "execute":
            self.execute(request, str(message.get("code") or ""), str(message.get("cell") or "cell"))
        elif operation == "variables":
            self.channel.send({"id": request, "event": "variables", "variables": self.variables()})
        else:
            self.channel.send({"id": request, "event": "rejected", "message": "Unknown request."})


def read_commands(stream, requests, kernel):
    for line in stream:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        if message.get("op") == "interrupt":
            kernel.interrupt()
        else:
            requests.put(message)
    requests.put(None)


def main():
    protocol = os.fdopen(os.dup(1), "w", encoding="utf-8", errors="replace", newline="\n")
    commands = os.fdopen(os.dup(0), "r", encoding="utf-8", errors="replace")
    null_input = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null_input, 0)
    os.close(null_input)
    kernel = Kernel(Channel(protocol))
    kernel.capture_descriptor(1, "stdout")
    kernel.capture_descriptor(2, "stderr")
    sys.stdout = StreamWriter(kernel, "stdout", 1)
    sys.stderr = StreamWriter(kernel, "stderr", 2)
    sys.stdin = NoInput()
    signal.signal(signal.SIGINT, signal.default_int_handler)
    requests = queue.Queue()
    threading.Thread(target=read_commands, args=(commands, requests, kernel), name="darkstar-commands", daemon=True).start()
    threading.Thread(target=kernel.flush_loop, name="darkstar-flush", daemon=True).start()
    kernel.channel.send({"event": "ready", "python": platform.python_version(), "cwd": os.getcwd()})
    while True:
        try:
            message = requests.get()
        except KeyboardInterrupt:
            continue
        if message is None:
            break
        try:
            kernel.handle(message)
        except KeyboardInterrupt:
            continue
    os._exit(0)


if __name__ == "__main__":
    main()
