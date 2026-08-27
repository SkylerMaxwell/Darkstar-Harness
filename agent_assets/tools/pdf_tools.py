# SPDX-License-Identifier: Apache-2.0
"""Darkstar PDF tools: safe, workspace-confined PDF inspection and editing."""
from __future__ import annotations

import html
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tools.registry import registry

from _pdf_core import (
    IMAGE_EXTENSIONS,
    PDF_EXTENSIONS,
    ToolInputError,
    atomic_bytes,
    atomic_writer_write,
    optional_import,
    parse_page_spec,
    pdf_reader,
    relative_display,
    require_pypdf,
    require_reportlab,
    resolve_output,
    resolve_pdf_input,
    resolve_regular_input,
    result,
    sha256_file,
)

PROVIDER_ID = "pdf_tools"
PROVIDER_NAME = "PDF Tools"


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None):
    return {
        "name": name,
        "description": description,
        "parameters": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


PATH = {"type": "string", "minLength": 1, "description": "Path relative to the current project workspace."}
OUT = {"type": "string", "minLength": 1, "description": "Output path relative to the current project workspace."}
OVERWRITE = {"type": "boolean", "description": "Replace an existing output. Defaults to false."}
PASSWORD = {"type": "string", "description": "Password for an encrypted input PDF. Never logged by the tool."}
PAGES = {"type": ["string", "array"], "description": "Optional 1-based pages, such as '1,3-5' or [1,3,4,5]. Omit for all pages."}


def pdf_get_capabilities(_args, **_kwargs):
    modules = {}
    for name in ("pypdf", "reportlab", "fitz", "pdfplumber", "pypdfium2", "PIL", "pytesseract"):
        try:
            module = __import__(name)
            modules[name] = {"available": True, "version": getattr(module, "__version__", None)}
        except Exception:
            modules[name] = {"available": False, "version": None}
    modules["tesseract_binary"] = {"available": bool(shutil.which("tesseract")), "version": None}
    return json.dumps({
        "success": True,
        "provider": PROVIDER_NAME,
        "modules": modules,
        "notes": [
            "Core inspection, text extraction, page editing, forms, encryption, and attachments use pypdf.",
            "Creation and overlays use ReportLab.",
            "True redaction and direct page annotation require PyMuPDF (fitz).",
            "Table extraction uses pdfplumber; page rendering uses pypdfium2 or PyMuPDF; OCR also requires the Tesseract executable.",
            "Visual analysis combines page screenshots, native geometry, scan detection, and coordinate-aware OCR in one call.",
        ],
    }, ensure_ascii=False)


CAP_SCHEMA = _schema(
    "pdf_get_capabilities",
    "Report which local PDF engines are available. Use this only after a missing-dependency error or before redaction, OCR, rendering, or table extraction.",
    {},
)


def pdf_inspect(args, **kwargs):
    root, path = resolve_pdf_input(args["input_file"], kwargs)
    reader = pdf_reader(path, args.get("password"))
    pages = []
    for index, page in enumerate(reader.pages):
        media = page.mediabox
        crop = page.cropbox
        pages.append({
            "page": index + 1,
            "width_points": float(media.width),
            "height_points": float(media.height),
            "rotation": int(page.get("/Rotate", 0) or 0),
            "crop_box": [float(crop.left), float(crop.bottom), float(crop.right), float(crop.top)],
            "annotations": len(page.get("/Annots", []) or []),
        })
    metadata = {str(key).lstrip("/"): str(value) for key, value in (reader.metadata or {}).items() if value is not None}
    fields = reader.get_fields() or {}
    attachments = []
    try:
        attachments = sorted((reader.attachments or {}).keys())
    except Exception:
        pass
    return result(
        root,
        input_file=relative_display(root, path),
        sha256=sha256_file(path),
        bytes=path.stat().st_size,
        pages=len(reader.pages),
        encrypted=bool(reader.is_encrypted),
        metadata=metadata,
        page_details=pages,
        form_fields=[{"name": name, "type": str(field.get("/FT", "")), "value": field.get("/V"), "flags": field.get("/Ff")} for name, field in fields.items()],
        attachments=attachments,
        outline_items=len(getattr(reader, "outline", []) or []),
    )


INSPECT_SCHEMA = _schema(
    "pdf_inspect",
    "Inspect a PDF without changing it. Returns page sizes and rotations, metadata, encryption state, form fields, annotations, attachments, outline count, size, and SHA-256.",
    {"input_file": PATH, "password": PASSWORD},
    ["input_file"],
)


def pdf_extract_text(args, **kwargs):
    root, path = resolve_pdf_input(args["input_file"], kwargs)
    reader = pdf_reader(path, args.get("password"))
    indexes = parse_page_spec(args.get("pages"), len(reader.pages))
    include_layout = bool(args.get("layout", False))
    page_results = []
    total = 0
    for index in indexes:
        page = reader.pages[index]
        try:
            text = page.extract_text(extraction_mode="layout") if include_layout else page.extract_text()
        except TypeError:
            text = page.extract_text()
        text = text or ""
        total += len(text)
        page_results.append({"page": index + 1, "text": text})
    max_chars = int(args.get("max_characters", 250000))
    if total > max_chars:
        remaining = max_chars
        for item in page_results:
            item["text"] = item["text"][:remaining]
            remaining -= len(item["text"])
            if remaining <= 0:
                break
        page_results = [item for item in page_results if item["text"]]
    return result(root, input_file=relative_display(root, path), pages=page_results, characters=min(total, max_chars), truncated=total > max_chars)


TEXT_SCHEMA = _schema(
    "pdf_extract_text",
    "Extract text from selected PDF pages. Returns text grouped by page and can use a layout-preserving extraction mode when supported.",
    {"input_file": PATH, "pages": PAGES, "password": PASSWORD, "layout": {"type": "boolean"}, "max_characters": {"type": "integer", "minimum": 1, "maximum": 1000000}},
    ["input_file"],
)


def pdf_extract_tables(args, **kwargs):
    try:
        import pdfplumber  # type: ignore
    except Exception as exc:
        raise ToolInputError("Table extraction requires pdfplumber. Install the bundled Python requirements or run: python -m pip install 'pdfplumber>=0.11'.") from exc
    root, path = resolve_pdf_input(args["input_file"], kwargs)
    password = args.get("password")
    max_tables = int(args.get("max_tables", 100))
    results = []
    with pdfplumber.open(str(path), password=password) as pdf:
        indexes = parse_page_spec(args.get("pages"), len(pdf.pages))
        for index in indexes:
            page = pdf.pages[index]
            tables = page.extract_tables(args.get("settings") or {})
            for table_index, table in enumerate(tables, start=1):
                results.append({"page": index + 1, "table": table_index, "rows": table})
                if len(results) >= max_tables:
                    return result(root, input_file=relative_display(root, path), tables=results, truncated=True)
    return result(root, input_file=relative_display(root, path), tables=results, truncated=False)


TABLE_SCHEMA = _schema(
    "pdf_extract_tables",
    "Extract detected tables from selected PDF pages as row arrays. Use for PDFs with visible table structure; scanned pages may require OCR first.",
    {"input_file": PATH, "pages": PAGES, "password": PASSWORD, "settings": {"type": "object", "additionalProperties": True}, "max_tables": {"type": "integer", "minimum": 1, "maximum": 1000}},
    ["input_file"],
)


def pdf_extract_images(args, **kwargs):
    root, path = resolve_pdf_input(args["input_file"], kwargs)
    reader = pdf_reader(path, args.get("password"))
    output_dir_raw = args["output_directory"]
    root2, output_dir = resolve_output(output_dir_raw + "/placeholder.png", kwargs, {".png"}, overwrite=True)
    output_dir = output_dir.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    indexes = parse_page_spec(args.get("pages"), len(reader.pages))
    extracted = []
    for index in indexes:
        images = getattr(reader.pages[index], "images", [])
        for image_index, image in enumerate(images, start=1):
            extension = Path(image.name or "image.bin").suffix or ".bin"
            name = f"page-{index+1:04d}-image-{image_index:03d}{extension}"
            destination = output_dir / name
            if destination.exists() and not args.get("overwrite", False):
                raise ToolInputError(f"Output image already exists: {relative_display(root, destination)}")
            atomic_bytes(destination, image.data)
            extracted.append({"page": index + 1, "file": relative_display(root, destination), "bytes": len(image.data)})
    return result(root, input_file=relative_display(root, path), output_directory=relative_display(root, output_dir), images=extracted)


IMAGE_SCHEMA = _schema(
    "pdf_extract_images",
    "Extract embedded raster images from selected PDF pages into a workspace directory. This extracts original image streams when available; it does not render whole pages.",
    {"input_file": PATH, "output_directory": {"type": "string", "minLength": 1}, "pages": PAGES, "password": PASSWORD, "overwrite": OVERWRITE},
    ["input_file", "output_directory"],
)


def _writer_metadata(reader, writer, preserve=True):
    if preserve and reader.metadata:
        writer.add_metadata({str(k): str(v) for k, v in reader.metadata.items() if v is not None})


def pdf_edit_pages(args, **kwargs):
    pypdf = require_pypdf()
    action = args["action"]
    overwrite = bool(args.get("overwrite", False))
    inputs = args.get("input_files") or ([args["input_file"]] if args.get("input_file") else [])
    if not inputs:
        raise ToolInputError("input_file or input_files is required.")
    resolved = [resolve_pdf_input(value, kwargs) for value in inputs]
    root = resolved[0][0]
    if action == "split":
        if len(resolved) != 1:
            raise ToolInputError("split accepts exactly one input PDF.")
        directory = args.get("output_directory")
        if not directory:
            raise ToolInputError("output_directory is required for split.")
        _, marker = resolve_output(directory + "/placeholder.pdf", kwargs, PDF_EXTENSIONS, overwrite=True)
        outdir = marker.parent
        outdir.mkdir(parents=True, exist_ok=True)
        reader = pdf_reader(resolved[0][1], args.get("password"))
        groups = args.get("groups") or [[index + 1] for index in range(len(reader.pages))]
        prefix = str(args.get("prefix") or resolved[0][1].stem)
        files = []
        for group_index, group in enumerate(groups, start=1):
            indexes = parse_page_spec(group, len(reader.pages))
            destination = outdir / f"{prefix}-{group_index:03d}.pdf"
            if destination.exists() and not overwrite:
                raise ToolInputError(f"Split output already exists: {relative_display(root, destination)}")
            split_writer = pypdf.PdfWriter()
            for index in indexes: split_writer.add_page(reader.pages[index])
            _writer_metadata(reader, split_writer, bool(args.get("preserve_metadata", True)))
            atomic_writer_write(split_writer, destination)
            files.append({"file": relative_display(root, destination), "pages": [index + 1 for index in indexes]})
        return result(root, input_file=relative_display(root, resolved[0][1]), output_directory=relative_display(root, outdir), action=action, files=files)
    if not args.get("output_file"):
        raise ToolInputError("output_file is required for this action.")
    _, output = resolve_output(args["output_file"], kwargs, PDF_EXTENSIONS, overwrite=overwrite)
    writer = pypdf.PdfWriter()
    if action == "merge":
        for _, path in resolved:
            reader = pdf_reader(path, args.get("password"))
            indexes = parse_page_spec(args.get("pages"), len(reader.pages)) if len(resolved) == 1 else list(range(len(reader.pages)))
            for index in indexes:
                writer.add_page(reader.pages[index])
        detail = {"inputs": [relative_display(root, p) for _, p in resolved]}
    else:
        if len(resolved) != 1:
            raise ToolInputError(f"{action} accepts exactly one input PDF.")
        source = resolved[0][1]
        reader = pdf_reader(source, args.get("password"))
        selected = parse_page_spec(args.get("pages"), len(reader.pages))
        if action == "select":
            indexes = selected
        elif action == "delete":
            remove = set(selected); indexes = [i for i in range(len(reader.pages)) if i not in remove]
            if not indexes: raise ToolInputError("Deleting those pages would produce an empty PDF.")
        elif action == "reorder":
            indexes = selected
            if len(indexes) != len(reader.pages): raise ToolInputError("reorder must list every page exactly once.")
        else:
            indexes = list(range(len(reader.pages)))
        for index in indexes:
            page = reader.pages[index]
            if action == "rotate" and index in set(selected):
                degrees = int(args.get("degrees", 90))
                if degrees % 90 != 0: raise ToolInputError("degrees must be a multiple of 90.")
                page.rotate(degrees)
            elif action == "crop" and index in set(selected):
                box = args.get("box")
                if not isinstance(box, list) or len(box) != 4: raise ToolInputError("box must be [left,bottom,right,top] in PDF points.")
                left, bottom, right, top = map(float, box)
                if right <= left or top <= bottom: raise ToolInputError("Crop box must have positive width and height.")
                page.cropbox.lower_left = (left, bottom); page.cropbox.upper_right = (right, top)
            writer.add_page(page)
        _writer_metadata(reader, writer, bool(args.get("preserve_metadata", True)))
        detail = {"input_file": relative_display(root, source), "pages_written": len(indexes)}
    atomic_writer_write(writer, output)
    return result(root, output_file=relative_display(root, output), action=action, **detail)


EDIT_SCHEMA = _schema(
    "pdf_edit_pages",
    "Merge or split PDFs, or select, delete, reorder, rotate, or crop pages. Page numbers are 1-based. Writes new files unless overwrite=true.",
    {
        "action": {"type": "string", "enum": ["merge", "split", "select", "delete", "reorder", "rotate", "crop"]},
        "input_file": PATH, "input_files": {"type": "array", "minItems": 1, "items": PATH}, "output_file": OUT,
        "output_directory": {"type": "string"}, "groups": {"type": "array", "items": {"type": ["string", "array"]}}, "prefix": {"type": "string"},
        "pages": PAGES, "degrees": {"type": "integer", "minimum": -360, "maximum": 360},
        "box": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "number"}},
        "password": PASSWORD, "preserve_metadata": {"type": "boolean"}, "overwrite": OVERWRITE,
    },
    ["action"],
)


def pdf_create(args, **kwargs):
    require_reportlab()
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, LETTER, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    root, output = resolve_output(args["output_file"], kwargs, PDF_EXTENSIONS, overwrite=bool(args.get("overwrite", False)))
    page_size_name = args.get("page_size", "letter")
    page_size = {"letter": LETTER, "a4": A4}.get(page_size_name)
    if page_size is None: raise ToolInputError("page_size must be letter or a4.")
    if args.get("landscape", False): page_size = landscape(page_size)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".pdf", dir=str(output.parent)); os.close(fd)
    temp = Path(temp_name)
    try:
        doc = SimpleDocTemplate(str(temp), pagesize=page_size, rightMargin=0.6*inch, leftMargin=0.6*inch, topMargin=0.6*inch, bottomMargin=0.6*inch)
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10))
        story = []
        for block in args["blocks"]:
            if not isinstance(block, dict): raise ToolInputError("Each block must be an object.")
            kind = block.get("type", "paragraph")
            if kind == "title": story.append(Paragraph(html.escape(str(block.get("text", ""))), styles["Title"]))
            elif kind == "heading": story.append(Paragraph(html.escape(str(block.get("text", ""))), styles["Heading2"]))
            elif kind == "paragraph": story.append(Paragraph(html.escape(str(block.get("text", ""))).replace("\n", "<br/>"), styles["BodyText"]))
            elif kind == "spacer": story.append(Spacer(1, float(block.get("height", 12))))
            elif kind == "page_break": story.append(PageBreak())
            elif kind == "table":
                data = block.get("rows")
                if not isinstance(data, list) or not data: raise ToolInputError("Table block requires non-empty rows.")
                table = Table(data, repeatRows=1 if block.get("header", True) else 0)
                table.setStyle(TableStyle([
                    ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#777777")),
                    ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E8E8E8")),
                    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                    ("VALIGN", (0,0), (-1,-1), "TOP"),
                    ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
                ])); story.append(table)
            elif kind == "image":
                _, image_path = resolve_regular_input(block.get("path"), kwargs, IMAGE_EXTENSIONS)
                image = Image(str(image_path), width=block.get("width"), height=block.get("height")); story.append(image)
            else: raise ToolInputError(f"Unsupported PDF block type: {kind}")
            if kind not in {"spacer", "page_break"}: story.append(Spacer(1, 8))
        metadata = args.get("metadata") or {}
        doc.title = str(metadata.get("title") or "")
        doc.author = str(metadata.get("author") or "")
        doc.subject = str(metadata.get("subject") or "")
        doc.build(story)
        reader = pdf_reader(temp); _ = len(reader.pages)
        os.replace(temp, output)
        return result(root, output_file=relative_display(root, output), pages=len(reader.pages), blocks=len(args["blocks"]))
    except Exception:
        temp.unlink(missing_ok=True); raise


CREATE_SCHEMA = _schema(
    "pdf_create",
    "Create a new PDF from ordered title, heading, paragraph, table, image, spacer, and page-break blocks. Use local images only. This is intended for clear business documents, not pixel-perfect reproduction of arbitrary layouts.",
    {
        "output_file": OUT, "blocks": {"type": "array", "minItems": 1, "maxItems": 1000, "items": {"type": "object", "additionalProperties": True}},
        "page_size": {"type": "string", "enum": ["letter", "a4"]}, "landscape": {"type": "boolean"},
        "metadata": {"type": "object", "additionalProperties": True}, "overwrite": OVERWRITE,
    },
    ["output_file", "blocks"],
)


def pdf_fill_form(args, **kwargs):
    pypdf = require_pypdf()
    root, source = resolve_pdf_input(args["input_file"], kwargs)
    _, output = resolve_output(args["output_file"], kwargs, PDF_EXTENSIONS, overwrite=bool(args.get("overwrite", False)))
    reader = pdf_reader(source, args.get("password")); writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(reader)
    fields = args["fields"]
    if not isinstance(fields, dict) or not fields: raise ToolInputError("fields must be a non-empty object mapping field names to values.")
    known = set((reader.get_fields() or {}).keys())
    unknown = sorted(set(fields) - known)
    if unknown and not args.get("allow_unknown", False): raise ToolInputError(f"Unknown form fields: {', '.join(unknown)}")
    flatten = bool(args.get("flatten", False))
    for page in writer.pages:
        writer.update_page_form_field_values(page, fields, auto_regenerate=not flatten)
    _writer_metadata(reader, writer, True)
    if not flatten:
        atomic_writer_write(writer, output)
    else:
        try:
            import fitz  # type: ignore
        except Exception as exc:
            raise ToolInputError("Flattening form fields requires PyMuPDF. Install the bundled Python requirements.") from exc
        fd,temp_name=tempfile.mkstemp(prefix=f".{output.name}.filled-",suffix=".pdf",dir=str(output.parent)); os.close(fd); temp=Path(temp_name)
        try:
            with temp.open("wb") as handle:
                writer.write(handle)
            doc=fitz.open(str(temp))
            if not hasattr(doc, "bake"):
                doc.close()
                raise ToolInputError("This PyMuPDF version does not support form flattening.")
            doc.bake(annots=False, widgets=True)
            fd2,flat_name=tempfile.mkstemp(prefix=f".{output.name}.flat-",suffix=".pdf",dir=str(output.parent)); os.close(fd2); flat=Path(flat_name)
            try:
                doc.save(str(flat),garbage=4,deflate=True,clean=True); doc.close(); _=pdf_reader(flat); os.replace(flat,output)
            except Exception:
                try: doc.close()
                except Exception: pass
                flat.unlink(missing_ok=True)
                raise
        finally:
            temp.unlink(missing_ok=True)
    return result(root, input_file=relative_display(root, source), output_file=relative_display(root, output), fields_written=len(fields), unknown_fields=unknown, flattened=flatten)


FORM_SCHEMA = _schema(
    "pdf_fill_form",
    "Fill named AcroForm fields in a PDF using a field-to-value object. Rejects unknown field names by default. Use pdf_inspect first to obtain exact field names and allowed values.",
    {"input_file": PATH, "output_file": OUT, "fields": {"type": "object", "additionalProperties": True}, "password": PASSWORD, "allow_unknown": {"type": "boolean"}, "flatten": {"type": "boolean"}, "overwrite": OVERWRITE},
    ["input_file", "output_file", "fields"],
)


def _overlay_pdf(page_width, page_height, operations):
    require_reportlab()
    from reportlab.pdfgen import canvas
    packet = io.BytesIO(); c = canvas.Canvas(packet, pagesize=(page_width, page_height))
    for op in operations:
        kind = op.get("type", "text")
        if kind == "text":
            c.setFont(str(op.get("font", "Helvetica")), float(op.get("size", 10)))
            c.setFillColorRGB(*[float(v) for v in op.get("color", [0,0,0])])
            c.drawString(float(op["x"]), float(op["y"]), str(op.get("text", "")))
        elif kind == "watermark":
            c.saveState(); c.setFillAlpha(float(op.get("opacity", 0.15))); c.setFont("Helvetica-Bold", float(op.get("size", 48))); c.translate(page_width/2,page_height/2); c.rotate(float(op.get("angle",45))); c.drawCentredString(0,0,str(op.get("text",""))); c.restoreState()
        elif kind == "rectangle":
            c.setStrokeColorRGB(*[float(v) for v in op.get("color", [1,0,0])]); c.setLineWidth(float(op.get("width",1))); c.rect(float(op["x"]),float(op["y"]),float(op["w"]),float(op["h"]),stroke=1,fill=0)
        else: raise ToolInputError(f"Unsupported annotation type: {kind}")
    c.save(); packet.seek(0); return packet


def pdf_annotate(args, **kwargs):
    pypdf = require_pypdf(); root, source = resolve_pdf_input(args["input_file"], kwargs); _, output = resolve_output(args["output_file"], kwargs, PDF_EXTENSIONS, overwrite=bool(args.get("overwrite", False)))
    reader = pdf_reader(source, args.get("password")); writer = pypdf.PdfWriter(); selected=set(parse_page_spec(args.get("pages"),len(reader.pages)))
    operations=args["operations"]
    if not operations and not args.get("page_numbers", False):
        raise ToolInputError("Provide at least one operation or set page_numbers=true.")
    for index,page in enumerate(reader.pages):
        if index in selected:
            page_ops=[op for op in operations if not op.get("page") or int(op["page"])==index+1]
            if args.get("page_numbers",False): page_ops=page_ops+[{"type":"text","x":float(page.mediabox.width)/2-10,"y":18,"text":str(index+1),"size":9,"color":[0.3,0.3,0.3]}]
            if page_ops:
                overlay_reader=pypdf.PdfReader(_overlay_pdf(float(page.mediabox.width),float(page.mediabox.height),page_ops)); page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)
    _writer_metadata(reader,writer,True); atomic_writer_write(writer,output)
    return result(root,input_file=relative_display(root,source),output_file=relative_display(root,output),pages_annotated=len(selected),operations=len(operations))


ANNOTATE_SCHEMA = _schema(
    "pdf_annotate",
    "Add text, watermarks, rectangles, or page numbers to selected PDF pages using PDF-point coordinates from the bottom-left. Writes a new PDF and preserves the original.",
    {"input_file":PATH,"output_file":OUT,"pages":PAGES,"operations":{"type":"array","minItems":0,"maxItems":1000,"items":{"type":"object","additionalProperties":True}},"page_numbers":{"type":"boolean"},"password":PASSWORD,"overwrite":OVERWRITE},
    ["input_file","output_file","operations"])


def pdf_redact(args, **kwargs):
    try:
        import fitz  # type: ignore
    except Exception as exc:
        raise ToolInputError("True PDF redaction requires PyMuPDF. Install the bundled Python requirements or run: python -m pip install 'PyMuPDF>=1.24'.") from exc
    root,source=resolve_pdf_input(args["input_file"],kwargs); _,output=resolve_output(args["output_file"],kwargs,PDF_EXTENSIONS,overwrite=bool(args.get("overwrite",False)))
    doc=fitz.open(str(source)); password=args.get("password")
    if doc.needs_pass and (not password or not doc.authenticate(password)): doc.close(); raise ToolInputError("Incorrect or missing PDF password.")
    redactions=0; method=args["method"]
    selected=set(parse_page_spec(args.get("pages"),doc.page_count))
    for index in selected:
        page=doc[index]
        if method=="text":
            query=str(args.get("text") or "")
            if not query: doc.close(); raise ToolInputError("text is required for text redaction.")
            for rect in page.search_for(query): page.add_redact_annot(rect,fill=(0,0,0),text=args.get("replacement") or ""); redactions+=1
        elif method=="regex":
            pattern=str(args.get("pattern") or "")
            if not pattern: doc.close(); raise ToolInputError("pattern is required for regex redaction.")
            compiled=re.compile(pattern)
            words=page.get_text("words")
            for word in words:
                if compiled.search(str(word[4])): page.add_redact_annot(fitz.Rect(word[:4]),fill=(0,0,0),text=args.get("replacement") or ""); redactions+=1
        elif method=="rectangles":
            rectangles=args.get("rectangles") or []
            for item in rectangles:
                if item.get("page") and int(item["page"])!=index+1: continue
                rect=item.get("rect")
                if not isinstance(rect,list) or len(rect)!=4: doc.close(); raise ToolInputError("Each rectangle needs rect=[left,top,right,bottom] in PDF points.")
                page.add_redact_annot(fitz.Rect(*map(float,rect)),fill=(0,0,0),text=str(item.get("replacement") or "")); redactions+=1
        else: doc.close(); raise ToolInputError("method must be text, regex, or rectangles.")
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
    fd,temp_name=tempfile.mkstemp(prefix=f".{output.name}.",suffix=".pdf",dir=str(output.parent)); os.close(fd); temp=Path(temp_name)
    try:
        doc.save(str(temp),garbage=4,deflate=True,clean=True); doc.close(); _=pdf_reader(temp); os.replace(temp,output)
    except Exception:
        doc.close(); temp.unlink(missing_ok=True); raise
    return result(root,input_file=relative_display(root,source),output_file=relative_display(root,output),redactions=redactions,method=method)


REDACT_SCHEMA = _schema(
    "pdf_redact",
    "Permanently remove underlying PDF content by exact text, word-level regex, or explicit rectangles. This is true redaction, not a visual black box. Always review the output afterward.",
    {"input_file":PATH,"output_file":OUT,"method":{"type":"string","enum":["text","regex","rectangles"]},"pages":PAGES,"text":{"type":"string"},"pattern":{"type":"string"},"rectangles":{"type":"array","items":{"type":"object","additionalProperties":True}},"replacement":{"type":"string"},"password":PASSWORD,"overwrite":OVERWRITE},
    ["input_file","output_file","method"])


def pdf_secure(args, **kwargs):
    pypdf=require_pypdf(); action=args["action"]; root,source=resolve_pdf_input(args["input_file"],kwargs); _,output=resolve_output(args["output_file"],kwargs,PDF_EXTENSIONS,overwrite=bool(args.get("overwrite",False)))
    reader=pdf_reader(source,args.get("password")); writer=pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
        if action == "safe_copy":
            safe_page = writer.pages[-1]
            for key in ("/Annots", "/AA", "/A", "/PresSteps"):
                safe_page.pop(key, None)
    if action=="encrypt":
        user_password=args.get("user_password")
        if not user_password: raise ToolInputError("user_password is required for encryption.")
        writer.encrypt(user_password=user_password,owner_password=args.get("owner_password") or user_password,algorithm=args.get("algorithm") or "AES-256")
    elif action=="decrypt": pass
    elif action in {"remove_metadata","safe_copy"}: writer.add_metadata({})
    elif action=="safe_copy": pass
    else: raise ToolInputError("action must be encrypt, decrypt, remove_metadata, or safe_copy.")
    if action not in {"remove_metadata","safe_copy"}: _writer_metadata(reader,writer,True)
    if action=="safe_copy":
        # Omit attachments, JavaScript, forms, and document-level actions by rebuilding pages only.
        writer.add_metadata({})
    atomic_writer_write(writer,output)
    return result(root,input_file=relative_display(root,source),output_file=relative_display(root,output),action=action,pages=len(reader.pages))


SECURE_SCHEMA = _schema(
    "pdf_secure",
    "Encrypt, decrypt, remove metadata, or create a conservative safe copy of a PDF. A safe copy rebuilds pages without document-level attachments, scripts, forms, or actions.",
    {"input_file":PATH,"output_file":OUT,"action":{"type":"string","enum":["encrypt","decrypt","remove_metadata","safe_copy"]},"password":PASSWORD,"user_password":{"type":"string"},"owner_password":{"type":"string"},"algorithm":{"type":"string","enum":["AES-256","AES-128","RC4-128"]},"overwrite":OVERWRITE},
    ["input_file","output_file","action"])


def pdf_manage_attachments(args, **kwargs):
    pypdf=require_pypdf(); action=args["action"]; root,source=resolve_pdf_input(args["input_file"],kwargs); reader=pdf_reader(source,args.get("password"))
    if action=="extract":
        directory=args.get("output_directory")
        if not directory: raise ToolInputError("output_directory is required for extract.")
        _, marker=resolve_output(directory+"/placeholder.bin",kwargs,{".bin"},overwrite=True); outdir=marker.parent; outdir.mkdir(parents=True,exist_ok=True)
        saved=[]
        for name,contents in (reader.attachments or {}).items():
            items=contents if isinstance(contents,list) else [contents]
            for idx,data in enumerate(items,start=1):
                safe=Path(name).name; target=outdir/(safe if len(items)==1 else f"{Path(safe).stem}-{idx}{Path(safe).suffix}")
                if target.exists() and not args.get("overwrite",False): raise ToolInputError(f"Attachment exists: {relative_display(root,target)}")
                atomic_bytes(target,data); saved.append(relative_display(root,target))
        return result(root,input_file=relative_display(root,source),action=action,files=saved)
    _,output=resolve_output(args["output_file"],kwargs,PDF_EXTENSIONS,overwrite=bool(args.get("overwrite",False))); writer=pypdf.PdfWriter()
    for page in reader.pages: writer.add_page(page)
    _writer_metadata(reader,writer,True)
    if action=="add":
        files=args.get("attachment_files") or []
        if not files: raise ToolInputError("attachment_files is required for add.")
        for file in files:
            _,attachment=resolve_regular_input(file,kwargs,{Path(file).suffix.lower()})
            writer.add_attachment(attachment.name,attachment.read_bytes())
    elif action=="remove_all": pass
    else: raise ToolInputError("action must be add, extract, or remove_all.")
    atomic_writer_write(writer,output)
    return result(root,input_file=relative_display(root,source),output_file=relative_display(root,output),action=action)


ATTACH_SCHEMA = _schema(
    "pdf_manage_attachments",
    "Add local files as PDF attachments, extract all PDF attachments to a workspace directory, or remove all attachments by rebuilding the PDF pages.",
    {"input_file":PATH,"output_file":OUT,"action":{"type":"string","enum":["add","extract","remove_all"]},"attachment_files":{"type":"array","items":PATH},"output_directory":{"type":"string"},"password":PASSWORD,"overwrite":OVERWRITE},
    ["input_file","action"])


def _render_pages(path: Path, indexes: list[int], output_dir: Path, dpi: int, fmt: str, *, overwrite: bool = False):
    scale = dpi / 72.0
    files = []
    try:
        import pypdfium2 as pdfium  # type: ignore
    except Exception:
        pdfium = None
    if pdfium is not None:
        try:
            pdf = pdfium.PdfDocument(str(path))
            for index in indexes:
                target = output_dir / f"page-{index+1:04d}.{fmt}"
                if target.exists() and not overwrite:
                    raise ToolInputError(f"Rendered page already exists: {target.name}")
                page = pdf[index]
                bitmap = page.render(scale=scale)
                pil = bitmap.to_pil()
                pil.save(target)
                files.append(target)
                try: pil.close()
                except Exception: pass
                try: bitmap.close()
                except Exception: pass
                try: page.close()
                except Exception: pass
            try: pdf.close()
            except Exception: pass
            return files, "pypdfium2"
        except ToolInputError:
            raise
        except Exception:
            files.clear()
    try:
        import fitz  # type: ignore
    except Exception as exc:
        raise ToolInputError("Page rendering requires pypdfium2 or PyMuPDF. Install the bundled Python requirements.") from exc
    doc = fitz.open(str(path))
    try:
        for index in indexes:
            target = output_dir / f"page-{index+1:04d}.{fmt}"
            if target.exists() and not overwrite:
                raise ToolInputError(f"Rendered page already exists: {target.name}")
            pix = doc[index].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            pix.save(str(target))
            files.append(target)
        return files, "PyMuPDF"
    finally:
        doc.close()


def pdf_convert(args, **kwargs):
    action=args["action"]; overwrite=bool(args.get("overwrite",False))
    if action=="render_images":
        root,source=resolve_pdf_input(args["input_file"],kwargs); reader=pdf_reader(source,args.get("password")); directory=args["output_directory"]
        _,marker=resolve_output(directory+"/placeholder.png",kwargs,{".png"},overwrite=True); outdir=marker.parent; outdir.mkdir(parents=True,exist_ok=True)
        indexes=parse_page_spec(args.get("pages"),len(reader.pages)); fmt=args.get("image_format","png"); dpi=int(args.get("dpi",150))
        files,engine=_render_pages(source,indexes,outdir,dpi,fmt,overwrite=overwrite)
        return result(root,input_file=relative_display(root,source),output_directory=relative_display(root,outdir),files=[relative_display(root,p) for p in files],engine=engine,dpi=dpi)
    if action=="images_to_pdf":
        pypdf=require_pypdf(); files=args.get("input_files") or []
        if not files: raise ToolInputError("input_files is required for images_to_pdf.")
        root,first=resolve_regular_input(files[0],kwargs,IMAGE_EXTENSIONS); _,output=resolve_output(args["output_file"],kwargs,PDF_EXTENSIONS,overwrite=overwrite)
        try:
            from PIL import Image  # type: ignore
        except Exception as exc: raise ToolInputError("images_to_pdf requires Pillow.") from exc
        images=[]
        for raw in files:
            _,path=resolve_regular_input(raw,kwargs,IMAGE_EXTENSIONS); image=Image.open(path).convert("RGB"); images.append(image)
        fd,temp_name=tempfile.mkstemp(prefix=f".{output.name}.",suffix=".pdf",dir=str(output.parent)); os.close(fd); temp=Path(temp_name)
        try:
            images[0].save(temp,save_all=True,append_images=images[1:]); _=pdf_reader(temp); os.replace(temp,output)
        finally:
            for image in images: image.close()
            temp.unlink(missing_ok=True)
        return result(root,output_file=relative_display(root,output),images=len(files))
    raise ToolInputError("action must be render_images or images_to_pdf.")


CONVERT_SCHEMA = _schema(
    "pdf_convert",
    "Render selected PDF pages to PNG/JPEG screenshots or combine local images into a PDF. Use pdf_analyze_visual when geometry, OCR coordinates, or scan detection is also needed.",
    {"action":{"type":"string","enum":["render_images","images_to_pdf"]},"input_file":PATH,"input_files":{"type":"array","items":PATH},"output_file":OUT,"output_directory":{"type":"string"},"pages":PAGES,"image_format":{"type":"string","enum":["png","jpg","jpeg"]},"dpi":{"type":"integer","minimum":36,"maximum":600},"password":PASSWORD,"overwrite":OVERWRITE},
    ["action"])



def _visual_bbox(value: Any) -> list[float]:
    """Return a stable top-left PDF-point bounding box."""
    try:
        values = list(value)
    except Exception:
        values = [value.x0, value.y0, value.x1, value.y1]
    if len(values) != 4:
        raise ToolInputError("Visual region bounding boxes must contain four coordinates.")
    return [round(float(item), 2) for item in values]


def _visual_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _visual_crop(
    image,
    bbox: list[float],
    page_width: float,
    page_height: float,
    destination: Path,
    *,
    overwrite: bool,
) -> bool:
    if destination.exists() and not overwrite:
        raise ToolInputError(f"Visual crop already exists: {destination.name}")
    pixel_width, pixel_height = image.size
    left = max(0, min(pixel_width, int(math.floor((bbox[0] / page_width) * pixel_width))))
    top = max(0, min(pixel_height, int(math.floor((bbox[1] / page_height) * pixel_height))))
    right = max(0, min(pixel_width, int(math.ceil((bbox[2] / page_width) * pixel_width))))
    bottom = max(0, min(pixel_height, int(math.ceil((bbox[3] / page_height) * pixel_height))))
    if right - left < 2 or bottom - top < 2:
        return False
    crop = image.crop((left, top, right, bottom))
    try:
        crop.save(destination)
    finally:
        crop.close()
    return True


def _ocr_visual_page(
    image_path: Path,
    page_width: float,
    page_height: float,
    *,
    language: str,
    config: str,
    minimum_confidence: float,
    max_elements: int,
) -> dict[str, Any]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception as exc:
        raise ToolInputError("Structured visual OCR requires pytesseract and Pillow.") from exc
    image = Image.open(image_path)
    try:
        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            lang=language,
            config=config,
        )
        pixel_width, pixel_height = image.size
    finally:
        image.close()
    scale_x = page_width / max(1, pixel_width)
    scale_y = page_height / max(1, pixel_height)
    words: list[dict[str, Any]] = []
    line_groups: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    total = len(data.get("text", []))
    for index in range(total):
        raw_text = str(data["text"][index] or "").strip()
        if not raw_text:
            continue
        try:
            confidence = float(data.get("conf", ["-1"] * total)[index])
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence < minimum_confidence:
            continue
        left = int(data["left"][index]); top = int(data["top"][index])
        width = int(data["width"][index]); height = int(data["height"][index])
        bbox = [
            round(left * scale_x, 2),
            round(top * scale_y, 2),
            round((left + width) * scale_x, 2),
            round((top + height) * scale_y, 2),
        ]
        word = {"text": raw_text, "bbox": bbox, "confidence": round(confidence, 1), "source": "ocr"}
        words.append(word)
        key = (
            int(data.get("block_num", [0] * total)[index]),
            int(data.get("par_num", [0] * total)[index]),
            int(data.get("line_num", [0] * total)[index]),
        )
        line_groups.setdefault(key, []).append(word)
        if len(words) >= max_elements:
            break
    lines: list[dict[str, Any]] = []
    for group in line_groups.values():
        group.sort(key=lambda item: (item["bbox"][0], item["bbox"][1]))
        lines.append({
            "text": " ".join(item["text"] for item in group),
            "bbox": [
                min(item["bbox"][0] for item in group),
                min(item["bbox"][1] for item in group),
                max(item["bbox"][2] for item in group),
                max(item["bbox"][3] for item in group),
            ],
            "confidence": round(sum(item["confidence"] for item in group) / len(group), 1),
            "source": "ocr",
        })
    lines.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    return {
        "words": words,
        "lines": lines[:max_elements],
        "text": "\n".join(item["text"] for item in lines),
        "truncated": len(words) >= max_elements,
    }


def pdf_analyze_visual(args, **kwargs):
    """Render pages and return visual geometry, with OCR fallback for textless scans."""
    try:
        import fitz  # type: ignore
        from PIL import Image  # type: ignore
    except Exception as exc:
        raise ToolInputError("Visual PDF analysis requires PyMuPDF and Pillow. Install the bundled Python requirements.") from exc

    root, source = resolve_pdf_input(args["input_file"], kwargs)
    reader = pdf_reader(source, args.get("password"))
    indexes = parse_page_spec(args.get("pages"), len(reader.pages))
    max_pages = int(args.get("max_pages", 25))
    if len(indexes) > max_pages:
        raise ToolInputError(
            f"Visual analysis selected {len(indexes)} pages, above max_pages={max_pages}. "
            "Select fewer pages or deliberately raise max_pages."
        )
    output_directory = args.get("output_directory") or f"{source.stem}-visual"
    _, marker = resolve_output(str(output_directory).rstrip("/\\") + "/placeholder.png", kwargs, {".png"}, overwrite=True)
    outdir = marker.parent
    outdir.mkdir(parents=True, exist_ok=True)
    dpi = int(args.get("dpi", 160))
    overwrite = bool(args.get("overwrite", False))
    rendered, render_engine = _render_pages(source, indexes, outdir, dpi, "png", overwrite=overwrite)

    password = args.get("password")
    doc = fitz.open(str(source))
    if getattr(doc, "needs_pass", False):
        if not password or not doc.authenticate(password):
            doc.close()
            raise ToolInputError("Incorrect PDF password for visual analysis.")

    ocr_mode = args.get("ocr", "auto")
    native_threshold = int(args.get("native_text_threshold", 40))
    minimum_confidence = float(args.get("minimum_ocr_confidence", 35))
    max_elements = int(args.get("max_elements_per_page", 2000))
    crop_mode = args.get("save_region_crops", "none")
    max_crops = int(args.get("max_region_crops", 50))
    include_words = bool(args.get("include_word_boxes", True))
    tesseract_available = bool(shutil.which("tesseract"))
    warnings: list[str] = []
    page_results: list[dict[str, Any]] = []

    try:
        for sequence, (page_index, rendered_path) in enumerate(zip(indexes, rendered)):
            page = doc[page_index]
            page_width = float(page.rect.width); page_height = float(page.rect.height)
            page_area = max(1.0, page_width * page_height)
            native_text = page.get_text("text", sort=True) or ""
            native_characters = len(native_text.strip())

            native_words = []
            if include_words:
                for word in page.get_text("words", sort=True)[:max_elements]:
                    native_words.append({
                        "text": str(word[4]),
                        "bbox": _visual_bbox(word[:4]),
                        "block": int(word[5]),
                        "line": int(word[6]),
                        "word": int(word[7]),
                        "source": "native",
                    })

            text_blocks = []
            try:
                page_dict = page.get_text("dict", sort=True)
            except TypeError:
                page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                parts = []
                for line in block.get("lines", []):
                    line_text = "".join(str(span.get("text", "")) for span in line.get("spans", []))
                    if line_text.strip():
                        parts.append(line_text)
                block_text = "\n".join(parts).strip()
                if block_text:
                    text_blocks.append({"bbox": _visual_bbox(block.get("bbox", [0, 0, 0, 0])), "text": block_text, "source": "native"})
                if len(text_blocks) >= max_elements:
                    break

            images = []
            image_area = 0.0
            for info in page.get_image_info(xrefs=True)[:max_elements]:
                bbox = _visual_bbox(info.get("bbox", [0, 0, 0, 0]))
                area = _visual_area(bbox)
                image_area += area
                images.append({
                    "bbox": bbox,
                    "width_pixels": int(info.get("width", 0) or 0),
                    "height_pixels": int(info.get("height", 0) or 0),
                    "xref": int(info.get("xref", 0) or 0),
                    "coverage": round(min(1.0, area / page_area), 4),
                })
            image_coverage = round(min(1.0, image_area / page_area), 4)

            drawing_regions = []
            drawing_counts = {"lines": 0, "rectangles": 0, "curves": 0, "other": 0}
            try:
                drawings = page.get_drawings()
            except Exception:
                drawings = []
            for drawing in drawings[:max_elements]:
                for item in drawing.get("items", []):
                    kind = item[0] if item else ""
                    if kind == "l": drawing_counts["lines"] += 1
                    elif kind == "re": drawing_counts["rectangles"] += 1
                    elif kind in {"c", "qu"}: drawing_counts["curves"] += 1
                    else: drawing_counts["other"] += 1
                drawing_regions.append({
                    "bbox": _visual_bbox(drawing.get("rect", [0, 0, 0, 0])),
                    "items": len(drawing.get("items", [])),
                    "fill": bool(drawing.get("fill")),
                    "stroke": bool(drawing.get("color")),
                })

            tables = []
            try:
                finder = page.find_tables()
                for table in getattr(finder, "tables", [])[:100]:
                    rows = table.extract() or []
                    tables.append({
                        "bbox": _visual_bbox(table.bbox),
                        "rows": len(rows),
                        "columns": max((len(row or []) for row in rows), default=0),
                        "preview": rows[:8],
                        "source": "visual",
                    })
            except Exception:
                pass

            form_fields = []
            widgets = page.widgets()
            if widgets is not None:
                for widget in widgets:
                    form_fields.append({
                        "name": str(widget.field_name or ""),
                        "type": str(getattr(widget, "field_type_string", "") or ""),
                        "value": widget.field_value,
                        "bbox": _visual_bbox(widget.rect),
                    })

            annotations = []
            annots = page.annots()
            if annots is not None:
                for annot in annots:
                    annotations.append({
                        "type": str((annot.type or (None, ""))[1] or ""),
                        "bbox": _visual_bbox(annot.rect),
                        "content": str((annot.info or {}).get("content", ""))[:500],
                    })

            likely_scanned = native_characters < native_threshold and image_coverage >= 0.5
            if native_characters >= native_threshold:
                classification = "mixed" if image_coverage >= 0.25 else "digital-text"
            elif likely_scanned:
                classification = "scanned-or-image-only"
            elif sum(drawing_counts.values()) >= 10:
                classification = "graphics-heavy"
            else:
                classification = "sparse-or-empty"

            should_ocr = ocr_mode == "always" or (ocr_mode == "auto" and native_characters < native_threshold)
            ocr_data = {"words": [], "lines": [], "text": "", "truncated": False}
            if should_ocr:
                if not tesseract_available:
                    if ocr_mode == "always":
                        raise ToolInputError("ocr='always' requires the Tesseract executable on PATH.")
                    warnings.append(f"Page {page_index + 1} appears textless, but Tesseract is unavailable; the rendered page and geometry were still returned.")
                    ocr_status = "unavailable"
                else:
                    ocr_data = _ocr_visual_page(
                        rendered_path,
                        page_width,
                        page_height,
                        language=args.get("ocr_language") or "eng",
                        config=args.get("ocr_config") or "",
                        minimum_confidence=minimum_confidence,
                        max_elements=max_elements,
                    )
                    ocr_status = "completed" if ocr_data["words"] else "completed-no-text"
            else:
                ocr_status = "disabled" if ocr_mode == "never" else "not-needed"

            crops = []
            if crop_mode != "none" and max_crops > 0:
                image = Image.open(rendered_path)
                try:
                    candidates: list[tuple[str, list[float]]] = []
                    if crop_mode in {"images", "all"}:
                        candidates.extend(("image", item["bbox"]) for item in images if item["coverage"] < 0.95)
                    if crop_mode in {"tables", "all"}:
                        candidates.extend(("table", item["bbox"]) for item in tables)
                    if crop_mode in {"forms", "all"}:
                        candidates.extend(("form", item["bbox"]) for item in form_fields)
                    for crop_index, (kind, bbox) in enumerate(candidates[:max_crops], start=1):
                        destination = outdir / f"page-{page_index+1:04d}-{kind}-{crop_index:03d}.png"
                        if _visual_crop(image, bbox, page_width, page_height, destination, overwrite=overwrite):
                            crops.append({"type": kind, "bbox": bbox, "file": relative_display(root, destination)})
                finally:
                    image.close()

            if ocr_data["words"]:
                text_source = "native+ocr" if native_characters else "ocr"
            elif native_characters:
                text_source = "native"
            else:
                text_source = "none"

            page_results.append({
                "page": page_index + 1,
                "rendered_file": relative_display(root, rendered_path),
                "width_points": round(page_width, 2),
                "height_points": round(page_height, 2),
                "classification": classification,
                "likely_scanned": likely_scanned,
                "native_text_characters": native_characters,
                "text_source": text_source,
                "ocr_status": ocr_status,
                "native_text_blocks": text_blocks,
                "native_words": native_words,
                "ocr_text": ocr_data["text"],
                "ocr_lines": ocr_data["lines"],
                "ocr_words": ocr_data["words"] if include_words else [],
                "images": images,
                "image_coverage": image_coverage,
                "drawings": {"regions": drawing_regions, **drawing_counts},
                "tables": tables,
                "form_fields": form_fields,
                "annotations": annotations,
                "region_crops": crops,
                "truncated": {
                    "native_words": len(native_words) >= max_elements,
                    "native_text_blocks": len(text_blocks) >= max_elements,
                    "ocr": bool(ocr_data["truncated"]),
                    "drawings": len(drawings) > max_elements,
                    "images": len(images) >= max_elements,
                },
            })
    finally:
        doc.close()

    return result(
        root,
        input_file=relative_display(root, source),
        output_directory=relative_display(root, outdir),
        render_engine=render_engine,
        dpi=dpi,
        coordinate_system={
            "origin": "top-left",
            "units": "PDF points",
            "bbox": "[left, top, right, bottom]",
        },
        ocr={
            "mode": ocr_mode,
            "available": tesseract_available,
            "language": args.get("ocr_language") or "eng",
            "minimum_confidence": minimum_confidence,
        },
        pages=page_results,
        warnings=warnings,
    )


VISUAL_SCHEMA = _schema(
    "pdf_analyze_visual",
    "Render PDF pages to PNG screenshots and analyze their visual layout. Returns text and OCR word coordinates, text blocks, embedded-image regions, vector drawing regions, tables, form fields, annotations, and scan detection. OCR runs automatically only for textless pages. Use pdf_convert when only page screenshots are needed.",
    {
        "input_file": PATH,
        "output_directory": {"type": "string", "minLength": 1, "description": "Directory for rendered page PNGs and optional region crops. Defaults to '<pdf-name>-visual'."},
        "pages": PAGES,
        "dpi": {"type": "integer", "minimum": 72, "maximum": 400, "description": "Rendering resolution. Defaults to 160 DPI."},
        "ocr": {"type": "string", "enum": ["auto", "always", "never"], "description": "auto OCRs only pages with little native text; always OCRs every selected page; never disables OCR."},
        "ocr_language": {"type": "string", "minLength": 1, "description": "Tesseract language code. Defaults to eng."},
        "ocr_config": {"type": "string", "description": "Optional Tesseract configuration string."},
        "minimum_ocr_confidence": {"type": "number", "minimum": 0, "maximum": 100, "description": "Discard OCR words below this confidence. Defaults to 35."},
        "native_text_threshold": {"type": "integer", "minimum": 0, "maximum": 5000, "description": "Pages below this native-character count are candidates for automatic OCR. Defaults to 40."},
        "include_word_boxes": {"type": "boolean", "description": "Return individual native and OCR word boxes. Defaults to true."},
        "save_region_crops": {"type": "string", "enum": ["none", "images", "tables", "forms", "all"], "description": "Optionally save PNG crops of detected regions. Defaults to none."},
        "max_region_crops": {"type": "integer", "minimum": 0, "maximum": 200, "description": "Maximum crops per page. Defaults to 50."},
        "max_elements_per_page": {"type": "integer", "minimum": 50, "maximum": 10000, "description": "Safety cap for returned words, blocks, images, and drawings. Defaults to 2000."},
        "max_pages": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Safety cap for pages in one call. Defaults to 25."},
        "password": PASSWORD,
        "overwrite": OVERWRITE,
    },
    ["input_file"],
)

def pdf_compare(args, **kwargs):
    root,left_path=resolve_pdf_input(args["left_file"],kwargs); _,right_path=resolve_pdf_input(args["right_file"],kwargs)
    left=pdf_reader(left_path,args.get("left_password")); right=pdf_reader(right_path,args.get("right_password")); max_pages=max(len(left.pages),len(right.pages)); pages=[]
    for index in range(max_pages):
        lt=left.pages[index].extract_text() or "" if index<len(left.pages) else None
        rt=right.pages[index].extract_text() or "" if index<len(right.pages) else None
        if lt!=rt:
            pages.append({"page":index+1,"left_characters":len(lt or ""),"right_characters":len(rt or ""),"left_preview":(lt or "")[:300],"right_preview":(rt or "")[:300]})
            if len(pages)>=int(args.get("max_differences",100)): break
    return result(root,left_file=relative_display(root,left_path),right_file=relative_display(root,right_path),left_pages=len(left.pages),right_pages=len(right.pages),different=bool(pages or len(left.pages)!=len(right.pages)),page_differences=pages)


COMPARE_SCHEMA = _schema(
    "pdf_compare",
    "Compare two PDFs by page count and extracted page text. Returns changed page previews. Use rendered-image comparison externally when exact visual parity is required.",
    {"left_file":PATH,"right_file":PATH,"left_password":PASSWORD,"right_password":PASSWORD,"max_differences":{"type":"integer","minimum":1,"maximum":1000}},["left_file","right_file"])


def pdf_ocr(args, **kwargs):
    if not shutil.which("tesseract"):
        raise ToolInputError("OCR requires the Tesseract executable to be installed and available on PATH.")
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception as exc:
        raise ToolInputError("OCR requires pytesseract and Pillow. Install the bundled Python requirements.") from exc
    pypdf=require_pypdf(); root,source=resolve_pdf_input(args["input_file"],kwargs); _,output=resolve_output(args["output_file"],kwargs,PDF_EXTENSIONS,overwrite=bool(args.get("overwrite",False)))
    reader=pdf_reader(source,args.get("password")); indexes=parse_page_spec(args.get("pages"),len(reader.pages)); tempdir=Path(tempfile.mkdtemp(prefix="darkstar-ocr-")); rendered=[]
    try:
        rendered,_engine=_render_pages(source,indexes,tempdir,int(args.get("dpi",300)),"png",overwrite=True)
        writer=pypdf.PdfWriter()
        selected_map={page_index:path for page_index,path in zip(indexes,rendered)}
        for index,page in enumerate(reader.pages):
            if index in selected_map:
                image=Image.open(selected_map[index]); pdf_bytes=pytesseract.image_to_pdf_or_hocr(image,extension="pdf",lang=args.get("language") or "eng",config=args.get("config") or ""); image.close()
                ocr_reader=pypdf.PdfReader(io.BytesIO(pdf_bytes)); writer.add_page(ocr_reader.pages[0])
            else: writer.add_page(page)
        atomic_writer_write(writer,output)
        return result(root,input_file=relative_display(root,source),output_file=relative_display(root,output),ocr_pages=[i+1 for i in indexes],dpi=int(args.get("dpi",300)))
    finally:
        shutil.rmtree(tempdir,ignore_errors=True)


OCR_SCHEMA = _schema(
    "pdf_ocr",
    "Create a searchable PDF by OCR-processing selected pages locally with Tesseract. This replaces selected pages with OCR-rendered pages; verify visual fidelity after use.",
    {"input_file":PATH,"output_file":OUT,"pages":PAGES,"language":{"type":"string"},"config":{"type":"string"},"dpi":{"type":"integer","minimum":150,"maximum":600},"password":PASSWORD,"overwrite":OVERWRITE},
    ["input_file","output_file"])


for name, schema, handler in [
    ("pdf_get_capabilities", CAP_SCHEMA, pdf_get_capabilities),
    ("pdf_inspect", INSPECT_SCHEMA, pdf_inspect),
    ("pdf_extract_text", TEXT_SCHEMA, pdf_extract_text),
    ("pdf_extract_tables", TABLE_SCHEMA, pdf_extract_tables),
    ("pdf_extract_images", IMAGE_SCHEMA, pdf_extract_images),
    ("pdf_analyze_visual", VISUAL_SCHEMA, pdf_analyze_visual),
    ("pdf_edit_pages", EDIT_SCHEMA, pdf_edit_pages),
    ("pdf_create", CREATE_SCHEMA, pdf_create),
    ("pdf_fill_form", FORM_SCHEMA, pdf_fill_form),
    ("pdf_annotate", ANNOTATE_SCHEMA, pdf_annotate),
    ("pdf_redact", REDACT_SCHEMA, pdf_redact),
    ("pdf_secure", SECURE_SCHEMA, pdf_secure),
    ("pdf_manage_attachments", ATTACH_SCHEMA, pdf_manage_attachments),
    ("pdf_convert", CONVERT_SCHEMA, pdf_convert),
    ("pdf_compare", COMPARE_SCHEMA, pdf_compare),
    ("pdf_ocr", OCR_SCHEMA, pdf_ocr),
]:
    registry.register(name=name, toolset="pdf", schema=schema, handler=handler)
