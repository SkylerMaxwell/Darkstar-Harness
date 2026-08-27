# SPDX-License-Identifier: Apache-2.0
"""Internal helpers for Darkstar PDF tools. Registers no model-facing tools."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

_PARENT = Path(__file__).resolve().parent.parent
import sys
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from _darkstar_tool_common import ToolInputError, json_result, relative_display, resolve_workspace_path

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
MAX_PDF_BYTES = 512 * 1024 * 1024


def require_pypdf():
    try:
        import pypdf  # type: ignore
        return pypdf
    except Exception as exc:
        raise ToolInputError("PDF tools require pypdf. Install the bundled Python requirements or run: python -m pip install 'pypdf>=5'.") from exc


def require_reportlab():
    try:
        import reportlab  # type: ignore
        return reportlab
    except Exception as exc:
        raise ToolInputError("PDF creation requires ReportLab. Install the bundled Python requirements or run: python -m pip install 'ReportLab>=4'.") from exc


def optional_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None


def resolve_pdf_input(raw_path: Any, kwargs: dict[str, Any]):
    root, path = resolve_workspace_path(raw_path, kwargs, must_exist=True, allow_root=False)
    if path.suffix.lower() != ".pdf":
        raise ToolInputError("Input file must be a PDF.")
    if path.is_symlink() or not path.is_file():
        raise ToolInputError(f"PDF is not a regular file: {relative_display(root, path)}")
    if path.stat().st_size > MAX_PDF_BYTES:
        raise ToolInputError(f"PDF is too large ({path.stat().st_size} bytes; maximum {MAX_PDF_BYTES}).")
    return root, path


def resolve_regular_input(raw_path: Any, kwargs: dict[str, Any], extensions: set[str]):
    root, path = resolve_workspace_path(raw_path, kwargs, must_exist=True, allow_root=False)
    if path.suffix.lower() not in extensions:
        raise ToolInputError(f"Input file must use one of: {', '.join(sorted(extensions))}")
    if path.is_symlink() or not path.is_file():
        raise ToolInputError(f"Input is not a regular file: {relative_display(root, path)}")
    return root, path


def resolve_output(raw_path: Any, kwargs: dict[str, Any], extensions: set[str], *, overwrite: bool = False):
    root, path = resolve_workspace_path(raw_path, kwargs, must_exist=False, allow_root=False)
    if path.suffix.lower() not in extensions:
        raise ToolInputError(f"Output file must use one of: {', '.join(sorted(extensions))}")
    if path.exists() and path.is_symlink():
        raise ToolInputError("Refusing to replace a symbolic link.")
    if path.exists() and not overwrite:
        raise ToolInputError(f"Output already exists: {relative_display(root, path)}. Set overwrite=true to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return root, path


def atomic_writer_write(writer, destination: Path) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".pdf", dir=str(destination.parent))
    os.close(fd)
    temp = Path(temp_name)
    try:
        with temp.open("wb") as handle:
            writer.write(handle)
            handle.flush()
            os.fsync(handle.fileno())
        reader = require_pypdf().PdfReader(str(temp))
        _ = len(reader.pages)
        os.replace(temp, destination)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def atomic_bytes(destination: Path, data: bytes) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=destination.suffix, dir=str(destination.parent))
    os.close(fd)
    temp = Path(temp_name)
    try:
        temp.write_bytes(data)
        os.replace(temp, destination)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def parse_page_spec(spec: Any, page_count: int, *, allow_empty: bool = False) -> list[int]:
    if spec in (None, ""):
        return list(range(page_count))
    if isinstance(spec, list):
        values = spec
    elif isinstance(spec, str):
        values = []
        for part in spec.split(","):
            token = part.strip()
            if not token:
                continue
            if "-" in token:
                start_text, end_text = token.split("-", 1)
                try:
                    start, end = int(start_text), int(end_text)
                except ValueError as exc:
                    raise ToolInputError(f"Invalid page range: {token}") from exc
                if start > end:
                    raise ToolInputError(f"Page range must ascend: {token}")
                values.extend(range(start, end + 1))
            else:
                try:
                    values.append(int(token))
                except ValueError as exc:
                    raise ToolInputError(f"Invalid page number: {token}") from exc
    else:
        raise ToolInputError("pages must be a comma-separated string such as '1,3-5' or an integer array.")
    indexes = []
    seen = set()
    for page in values:
        if isinstance(page, bool) or not isinstance(page, int):
            raise ToolInputError("Page numbers must be integers.")
        if page < 1 or page > page_count:
            raise ToolInputError(f"Page {page} is outside the PDF range 1-{page_count}.")
        index = page - 1
        if index not in seen:
            indexes.append(index)
            seen.add(index)
    if not indexes and not allow_empty:
        raise ToolInputError("No pages were selected.")
    return indexes


def pdf_reader(path: Path, password: str | None = None):
    pypdf = require_pypdf()
    try:
        reader = pypdf.PdfReader(str(path))
        if reader.is_encrypted:
            if not password:
                raise ToolInputError("PDF is encrypted; provide password.")
            if reader.decrypt(password) == 0:
                raise ToolInputError("Incorrect PDF password.")
        return reader
    except ToolInputError:
        raise
    except Exception as exc:
        raise ToolInputError(f"Could not open PDF {path.name}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def result(root: Path, **payload: Any) -> str:
    return json_result(success=True, **payload)
