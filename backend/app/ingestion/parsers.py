"""Extract text + metadata from supported file types."""
from __future__ import annotations

import csv
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Tuple

SUPPORTED = {".txt", ".md", ".markdown", ".pdf", ".docx", ".html", ".htm", ".json", ".csv", ".rtf", ".log"}


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.title, self._skip, self._in_title = [], None, 0, False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and data.strip():
            self.title = data.strip()
        elif not self._skip:
            self.parts.append(data)


def _frontmatter(content: str, meta: Dict[str, Any]) -> str:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not m:
        return content
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return m.group(2)


def parse_bytes(name: str, data: bytes) -> Tuple[str, Dict[str, Any]]:
    ext = Path(name).suffix.lower()
    meta: Dict[str, Any] = {"source_file": name, "format": ext.lstrip(".")}
    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported file type '{ext or name}'. Supported: {', '.join(sorted(SUPPORTED))}")

    if ext in (".txt", ".md", ".markdown", ".log"):
        text = _frontmatter(data.decode("utf-8", errors="replace"), meta)
    elif ext == ".pdf":
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        meta["page_count"] = len(reader.pages)
        if reader.metadata:
            if reader.metadata.title:
                meta["title"] = str(reader.metadata.title)
            if reader.metadata.creation_date:
                meta["creation_date"] = reader.metadata.creation_date.isoformat()
        text = "\n\n".join((p.extract_text() or "").strip() for p in reader.pages)
    elif ext == ".docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        text = "\n\n".join(p.text for p in d.paragraphs if p.text.strip())
        cp = d.core_properties
        if cp.title:
            meta["title"] = cp.title
        if cp.created:
            meta["creation_date"] = cp.created.isoformat()
    elif ext in (".html", ".htm"):
        p = _HTMLText()
        p.feed(data.decode("utf-8", errors="replace"))
        text = re.sub(r"\n\s*\n+", "\n\n", "".join(p.parts))
        if p.title:
            meta["title"] = p.title
    elif ext == ".json":
        obj = json.loads(data.decode("utf-8", errors="replace"))
        text = _json_to_text(obj)
    elif ext == ".csv":
        rows = list(csv.reader(io.StringIO(data.decode("utf-8", errors="replace"))))
        header, body = (rows[0], rows[1:]) if rows else ([], [])
        text = "\n".join("; ".join(f"{h}: {v}" for h, v in zip(header, r) if v) for r in body)
    elif ext == ".rtf":
        raw = data.decode("utf-8", errors="replace")
        raw = re.sub(r"\\par[d]?", "\n", raw)
        raw = re.sub(r"\{\\\*[^{}]*\}|\\[a-z]+-?\d* ?|[{}]", "", raw)
        text = raw
    else:  # pragma: no cover
        text = data.decode("utf-8", errors="replace")

    text = text.replace("\r\n", "\n").strip()
    meta["char_count"] = len(text)
    return text, meta


def _json_to_text(obj: Any, depth: int = 0) -> str:
    """Flatten journal-style JSON (list of entries with text/date fields) into readable text."""
    if isinstance(obj, list):
        return "\n\n".join(_json_to_text(o, depth + 1) for o in obj)
    if isinstance(obj, dict):
        date = next((obj[k] for k in ("date", "created", "timestamp", "created_at") if k in obj), None)
        body = next((obj[k] for k in ("text", "content", "body", "entry", "note") if k in obj), None)
        if body is not None:
            return f"{date}\n{body}" if date else str(body)
        return "\n".join(f"{k}: {_json_to_text(v, depth + 1)}" for k, v in obj.items())
    return str(obj)
