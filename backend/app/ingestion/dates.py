"""Temporal grounding: document dates (when written) vs event dates (when it happened)."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from app.models.schemas import DateGranularity, DateSource

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
YEAR = r"(19[5-9]\d|20\d{2})"
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "a": 1, "a couple of": 2, "a few": 3, "several": 4}


RETRO_RE = re.compile(
    r"looking back|in hindsight|compared (?:to|with)|\bthan (?:i|we)\b|\bsince\b|\bself\b|revers|"
    r"\b(?:my|our) (?:19|20)\d{2}\b|did(?: not|n't) in|anymore|no longer|used to|back then", re.I)


def _month_end(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def _r(start: str, end: str, gran: DateGranularity, conf: float, src: DateSource) -> Dict[str, Any]:
    return {"start": start, "end": end, "granularity": gran, "confidence": conf, "source": src}


def parse_date(text: str) -> Optional[str]:
    """Parse a single date-ish string into YYYY-MM-DD (best effort)."""
    if not text:
        return None
    t = str(text).strip().rstrip(".,")
    m = re.search(rf"\b{YEAR}-(\d{{1,2}})-(\d{{1,2}})", t)
    if m:
        y, mo, d = map(int, m.groups())
        if 1 <= mo <= 12 and 1 <= d <= _month_end(y, mo):
            return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(rf"\b{YEAR}/(\d{{1,2}})/(\d{{1,2}})\b", t)
    if m:
        y, mo, d = map(int, m.groups())
        if 1 <= mo <= 12 and 1 <= d <= _month_end(y, mo):
            return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+{YEAR}\b", t, re.I)
    if m:
        mo, d, y = MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{min(d, _month_end(y, mo)):02d}"
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?,?\s+{YEAR}\b", t, re.I)
    if m:
        d, mo, y = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
        return f"{y:04d}-{mo:02d}-{min(d, _month_end(y, mo)):02d}"
    m = re.search(rf"\b(\d{{1,2}})[/.](\d{{1,2}})[/.]{YEAR}\b", t)
    if m:  # ambiguous: prefer DD/MM when the first part > 12, otherwise MM/DD
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        d, mo = (a, b) if a > 12 else (b, a)
        if 1 <= mo <= 12 and 1 <= d <= _month_end(y, mo):
            return f"{y:04d}-{mo:02d}-{d:02d}"
    m = re.search(rf"\b({_MON})\.?\s+{YEAR}\b", t, re.I)
    if m:
        return f"{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}-01"
    m = re.fullmatch(rf"\s*{YEAR}\s*", t)
    if m:
        return f"{m.group(1)}-01-01"
    return None


def infer_document_date(filename: str, text: str, meta: Dict[str, Any]) -> Tuple[Optional[str], float]:
    for key in ("date", "document_date", "created", "creation_date"):
        if meta.get(key):
            parsed = parse_date(str(meta[key]))
            if parsed:
                return parsed, 0.95
    m = re.search(rf"{YEAR}[-_.](\d{{2}})[-_.](\d{{2}})", filename)
    if m:
        parsed = parse_date(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        if parsed:
            return parsed, 0.9
    head = "\n".join(text.splitlines()[:12])
    m = re.search(r"(?:date|entry|written|logged|updated|dated)\s*[:\-]\s*([^\n]{4,40})", head, re.I)
    if m and (parsed := parse_date(m.group(1))):
        return parsed, 0.88
    for line in text.splitlines()[:5]:
        parsed = parse_date(line.strip("#*- \t"))
        if parsed and len(line.strip()) < 60:
            return parsed, 0.82
    m = re.search(rf"(?<!\d){YEAR}(?!\d)", filename)
    if m:
        return f"{m.group(1)}-01-01", 0.7
    return None, 0.0


def extract_event_date(statement: str, document_date: Optional[str] = None) -> Dict[str, Any]:
    t = statement
    doc: Optional[date] = None
    if document_date:
        try:
            doc = datetime.fromisoformat(document_date[:10]).date()
        except ValueError:
            doc = None
    E, R = DateSource.EXPLICIT_IN_TEXT, DateSource.RELATIVE_INFERRED

    full = parse_date(t) if re.search(rf"\d{{1,2}}.*{YEAR}|{YEAR}[-/]\d", t) else None
    if full and re.search(rf"({_MON})\.?\s+\d|\d\s+({_MON})|{YEAR}[-/]\d|\d[/.]\d", t, re.I):
        return _r(full, full, DateGranularity.DAY, 0.95, E)

    m = re.search(rf"\b({_MON})\.?\s+(?:of\s+)?{YEAR}\b", t, re.I)
    if m:
        y, mo = int(m.group(2)), MONTHS[m.group(1).lower()]
        return _r(f"{y}-{mo:02d}-01", f"{y}-{mo:02d}-{_month_end(y, mo)}", DateGranularity.MONTH, 0.9, E)

    m = re.search(rf"\b(spring|summer|fall|autumn|winter)\s+(?:of\s+)?{YEAR}\b", t, re.I)
    if m:
        s, y = m.group(1).lower(), int(m.group(2))
        bounds = {"spring": ((3, 1), (5, 31)), "summer": ((6, 1), (8, 31)), "fall": ((9, 1), (11, 30)),
                  "autumn": ((9, 1), (11, 30))}
        if s == "winter":
            return _r(f"{y}-12-01", f"{y + 1}-02-{_month_end(y + 1, 2)}", DateGranularity.SEASON, 0.85, E)
        (sm, sd), (em, ed) = bounds[s]
        return _r(f"{y}-{sm:02d}-{sd:02d}", f"{y}-{em:02d}-{ed:02d}", DateGranularity.SEASON, 0.85, E)

    m = re.search(rf"\bq([1-4])\s+{YEAR}\b", t, re.I)
    if m:
        q, y = int(m.group(1)), int(m.group(2))
        sm, em = 3 * q - 2, 3 * q
        return _r(f"{y}-{sm:02d}-01", f"{y}-{em:02d}-{_month_end(y, em)}", DateGranularity.SEASON, 0.85, E)

    years = re.findall(rf"(?<![\d$£€])\b{YEAR}\b(?!\s*(?:%|dollars|users|people|km|kg))", t)
    if years:
        y = years[0]
        # A past year used as a reference point ("looking back at my 2019 self", "more than I thought in 2019")
        # describes the writer's present view, so it belongs to the document date.
        if doc and int(y) < doc.year and RETRO_RE.search(t):
            return _r(doc.isoformat(), doc.isoformat(), DateGranularity.DAY, 0.75, DateSource.DOC_METADATA)
        return _r(f"{y}-01-01", f"{y}-12-31", DateGranularity.YEAR, 0.8, E)

    if doc:
        low = t.lower()
        if re.search(r"\byesterday\b", low):
            d = doc - timedelta(days=1)
            return _r(d.isoformat(), d.isoformat(), DateGranularity.DAY, 0.85, R)
        if re.search(r"\blast week\b", low):
            d = doc - timedelta(days=7)
            return _r(d.isoformat(), doc.isoformat(), DateGranularity.DAY, 0.7, R)
        if re.search(r"\blast month\b", low):
            y, mo = (doc.year, doc.month - 1) if doc.month > 1 else (doc.year - 1, 12)
            return _r(f"{y}-{mo:02d}-01", f"{y}-{mo:02d}-{_month_end(y, mo)}", DateGranularity.MONTH, 0.75, R)
        if re.search(r"\blast year\b", low):
            y = doc.year - 1
            return _r(f"{y}-01-01", f"{y}-12-31", DateGranularity.YEAR, 0.75, R)
        m = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|a couple of|a few|several)\s+"
                      r"(year|month)s?\s+ago\b", low)
        if m:
            n = int(m.group(1)) if m.group(1).isdigit() else WORDNUM.get(m.group(1), 1)
            if m.group(2) == "year":
                y = doc.year - n
                return _r(f"{y}-01-01", f"{y}-12-31", DateGranularity.YEAR, 0.7, R)
            total = doc.year * 12 + (doc.month - 1) - n
            y, mo = divmod(total, 12)
            mo += 1
            return _r(f"{y}-{mo:02d}-01", f"{y}-{mo:02d}-{_month_end(y, mo)}", DateGranularity.MONTH, 0.7, R)
        if re.search(r"\bearlier this year\b", low):
            return _r(f"{doc.year}-01-01", doc.isoformat(), DateGranularity.SEASON, 0.7, R)

    if document_date:
        return _r(document_date[:10], document_date[:10], DateGranularity.DAY, 0.6, DateSource.DOC_METADATA)
    return {"start": None, "end": None, "granularity": DateGranularity.UNRECORDED, "confidence": 0.0,
            "source": DateSource.DOC_METADATA}
