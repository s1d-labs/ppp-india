"""Shared document handling for every source in this family: look at downloaded bytes, decide where they go in the bucket.

OCR is off (personal rule: OCR = False). A PDF without a usable text layer is stored under ocr-needed/ so a later OCR pass finds
every scan in one place; a PDF with text is stored under docs/ and its text under text/ (gzip), so analysis never re-parses PDFs.
"""
import gzip
import hashlib
import io
import logging
import re

OCR = False
TEXT_PAGES = 80            # read text from at most this many pages (big scans are slow and have no text anyway)
HEAD_CHARS = 1500          # text kept in the record itself (searchable in Metabase); the full text goes to the bucket

logging.getLogger("pypdf").setLevel(logging.ERROR)

EXT = {"application/pdf": "pdf", "application/msword": "doc", "text/html": "html", "application/zip": "zip",
       "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
       "application/vnd.ms-excel": "xls", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
       "image/jpeg": "jpg", "image/png": "png"}


def kind_of(data, content_type="", name=""):
    """File type from the bytes first (servers lie), then the content type, then the file name."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:4] == b"PK\x03\x04":
        n = name.lower()
        return "docx" if n.endswith(".docx") else "xlsx" if n.endswith(".xlsx") else "zip"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls" if name.lower().endswith(".xls") else "doc"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    head = data[:600].lstrip().lower()
    if head.startswith((b"<!doctype", b"<html", b"<?xml")) or b"<html" in head:
        return "html"
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in EXT:
        return EXT[ct]
    m = re.search(r"\.([a-z0-9]{2,5})$", name.lower())
    return m.group(1) if m else "bin"


def pdf_text(data):
    """(pages, text) of a PDF; (None, '') when pypdf cannot read it."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=False)
        n = len(reader.pages)
        parts = []
        for page in reader.pages[:TEXT_PAGES]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                parts.append("")
        return n, "\n\f".join(parts)
    except Exception:
        return None, ""


def has_text(pages, txt):
    """A usable text layer: at least 200 letters or digits, and about 40 per page read."""
    n = len(re.findall(r"[A-Za-z0-9]", txt))
    return n >= 200 and n >= 40 * min(pages or 1, TEXT_PAGES)


def inspect(data, content_type="", name=""):
    """Facts about one downloaded file, plus its text (for PDFs with a text layer)."""
    kind = kind_of(data, content_type, name)
    info = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "type": kind}
    txt = ""
    if kind == "pdf":
        pages, txt = pdf_text(data)
        info.update(pages=pages, text_chars=len(txt), has_text=has_text(pages, txt), readable=pages is not None)
        if not info["has_text"]:
            txt = ""
    return info, txt


def uploads(info, data, txt, section, prefix=""):
    """[(path, bytes, content type)] for upload_many, and the record fields that point to them. Content-addressed: the same
    bytes always land at the same path, so a file seen twice (or in the Wayback Machine too) is stored once."""
    sha, kind = info["sha256"], info["type"]
    scan = kind == "pdf" and not info.get("has_text")
    base = "ocr-needed" if scan else "docs"
    path = f"{prefix}{base}/{section}/{sha}.{kind}"
    ctype = {"pdf": "application/pdf", "html": "text/html"}.get(kind, "application/octet-stream")
    files = [(path, data, ctype)]
    fields = {"bucket_path": path, "ocr_needed": scan}
    if txt:
        tpath = f"{prefix}text/{sha}.txt.gz"
        files.append((tpath, gzip.compress(txt.encode("utf-8", "replace")), "application/gzip"))
        fields.update(text_path=tpath, text_head=txt[:HEAD_CHARS])
    return files, fields


def is_not_found_page(data):
    """WBMSC (Apache) answers a missing file with a small HTML 'Object not found!' page."""
    return len(data) < 4000 and b"Object not found" in data
