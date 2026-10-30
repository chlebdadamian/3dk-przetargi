"""Tekst z załączników (PDF, DOCX) i wyciąganie z niego terminu oraz warunków udziału."""

import io
import re
import zipfile
from datetime import datetime, timezone

MONTHS = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6, "lipca": 7,
    "sierpnia": 8, "września": 9, "października": 10, "listopada": 11, "grudnia": 12,
}
_DATE = (r"(?:(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})|(\d{4})-(\d{2})-(\d{2})|"
         r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4}))")
# minuty bywają indeksem górnym („12⁰⁰”), które PDF oddaje jako „1200”
_TIME = r"(?:[^\d]{0,40}?(?:godz(?:iny|inie|\.)?)\s*(\d{1,2})[:.]?(\d{2}))?"
# data bywa kilka linii pod nagłówkiem „TERMIN SKŁADANIA OFERT”
DEADLINE_RE = re.compile(
    r"(?:termin\w*\s+(?:składania|złożenia|złożenie|przesłania)\s+ofert|ofert[ęy]?\s+(?:należy\s+)?"
    r"(?:złożyć|składać|przesłać)|oferty\s+(?:należy\s+)?(?:składać|złożyć))"
    r"[\s\S]{0,300}?" + _DATE + _TIME,
    re.I,
)
# zapas: otwarcie ofert jest zwykle tego samego dnia, chwilę po terminie
OPENING_RE = re.compile(r"otwarci\w*\s+ofert[\s\S]{0,120}?" + _DATE + _TIME, re.I)
CONDITIONS_RE = re.compile(r"warunk\w*\s+udział|doświadczeni\w*|wykonał\w*\s+(?:co\s+najmniej|min)", re.I)


def text(data: bytes, ext: str) -> str:
    if ext == "pdf":
        from pypdf import PdfReader  # jedyna zależność spoza biblioteki standardowej

        reader = PdfReader(io.BytesIO(data))
        raw = "\n".join(page.extract_text() or "" for page in reader.pages[:15])
    elif ext == "docx":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        raw = re.sub(r"<w:p[ >].*?</w:p>", lambda m: re.sub(r"<[^>]+>", "", m.group(0)) + "\n", xml, flags=re.S)
        raw = re.sub(r"<[^>]+>", "", raw)
    else:
        return ""
    return re.sub(r"[ \t]+", " ", raw).strip()


# konkursy: „Zgłoszenia prac przyjmuje … do dnia 4 grudnia 2026 roku do godz. 16.00”
ENTRY_RE = re.compile(r"(?:zgłosze\w*|nadsył\w*|składani\w*\s+prac|nabór\s+trwa)[\s\S]{0,200}?" + _DATE + _TIME, re.I)


def _match_deadline(t: str):
    return DEADLINE_RE.search(t or "") or OPENING_RE.search(t or "") or ENTRY_RE.search(t or "")


def deadline(t: str) -> str | None:
    """Termin składania ofert jako UTC ISO (czas w dokumencie = polski); None, gdy nie znaleziono."""
    m = _match_deadline(t)
    if not m:
        return None
    g = m.groups()
    if g[0]:
        d, mo, y = int(g[0]), int(g[1]), int(g[2])
    elif g[3]:
        y, mo, d = int(g[3]), int(g[4]), int(g[5])
    else:
        d, mo, y = int(g[6]), MONTHS[g[7].lower()], int(g[8])
    hour, minute = (int(g[9]), int(g[10])) if g[9] else (23, 59)
    try:
        local = datetime(y, mo, d, hour, minute)  # naiwny = czas systemowy (PL)
    except ValueError:
        return None
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def deadline_text(t: str) -> str:
    m = _match_deadline(t)
    return re.sub(r"\s+", " ", m.group(0)) if m else ""


def snippet(t: str, pattern: re.Pattern, size: int = 1200) -> str:
    m = pattern.search(t or "")
    if not m:
        return ""
    return re.sub(r"\s+", " ", t[max(0, m.start() - 100): m.start() + size]).strip()
