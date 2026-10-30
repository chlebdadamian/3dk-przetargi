"""BIP-y gmin i powiatów na wspólnej platformie bip.malopolska.pl (system Madkom).

Tu trafiają zapytania ofertowe poniżej 130 tys. zł, których nie ma w BZP.
API: /api/contexts/{jednostka} -> defaultMenuId, /api/menu/{id} -> drzewo menu,
/api/menu/{targetId}/articles -> artykuły działu, /api/articles/{id} -> szczegóły i załączniki.
Treść zapytań jest w PDF-ach, więc terminu nie znamy: zapytanie uznajemy za aktualne przez
OPEN_DAYS od publikacji, chyba że w załącznikach jest już informacja o wyborze oferty.
"""

import json
import re
import time
import urllib.request
import urllib.robotparser
from datetime import datetime
from html import unescape

from . import docs
from .bzp import USER_AGENT

BASE = "https://bip.malopolska.pl"
NOTICE_TYPE = "BIPNotice"
REQUEST_DELAY = 1.0
OPEN_DAYS = 21
ARTICLES_PER_SECTION = 20

# działy menu z ogłoszeniami o zamówieniach (bez wyników, planów, naborów itp.)
SECTION_RE = re.compile(r"zapytani|zamówieni|zamowieni|przetarg", re.I)
SKIP_RE = re.compile(r"wynik|zawarci|plan|nabór|nabor|zgromadz|platforma|archiw|rejestr|sprawozd|unieważ", re.I)
CLOSED_RE = re.compile(r"wybor|wybór|wynik|uniewa", re.I)
# załączniki bez treści merytorycznej
SKIP_FILE_RE = re.compile(r"rodo|klauzul|formularz|oświadcz|oswiadcz|wzór|wzor|projekt umowy|wynik|wybor|wybór", re.I)
# gminy często dopisują wynik do treści tego samego artykułu
CLOSED_TEXT_RE = re.compile(r"informacja o wyniku|informacja o wyborze|wybrano ofert|unieważni", re.I)


def _get(path: str):
    time.sleep(REQUEST_DELAY)
    req = urllib.request.Request(f"{BASE}/api/{path}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def sections(unit: str) -> tuple[str, list[str]]:
    """(nazwa jednostki, targetId działów z zamówieniami)."""
    ctx = _get(f"contexts/{unit}")
    targets = []

    def walk(nodes, inside):
        for n in nodes or []:
            name = n.get("name") or ""
            match = inside or bool(SECTION_RE.search(name))
            if match and not SKIP_RE.search(name):
                targets.append(str(n["targetId"]))
            walk(n.get("children"), match and not SKIP_RE.search(name))

    walk(_get(f"menu/{ctx['defaultMenuId']}"), False)
    return ctx.get("unitFullName") or ctx.get("siteTitle") or unit, list(dict.fromkeys(targets))


def articles(target: str) -> list[dict]:
    data = _get(f"menu/{target}/articles?limit={ARTICLES_PER_SECTION}&offset=0")
    out = []
    for a in data.get("articles", []):
        fields = {f["fieldId"]: f["value"] for f in a.get("columnFields", [])}
        if fields.get("title"):
            out.append({"id": a["id"], "link": a["link"], "title": _clean(fields["title"]),
                        "published": fields.get("activeYMD")})
    return out


def url(link: str) -> str:
    return f"{BASE}/{link}"


def row(item: dict, unit_name: str, city: str) -> dict:
    return {
        "notice_number": f"BIP/{item['id']}",
        "notice_type": NOTICE_TYPE,
        "object_id": item["link"],
        "title": item["title"],
        "org_name": unit_name,
        "org_city": city,
        "province": "PL12",
        "order_type": None,
        "cpv": "",
        "published": item["published"],
        "deadline": None,
        "text": json.dumps({}),
        "estimate": None,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


_robots = None


def _allowed(url: str) -> bool:
    """robots.txt platformy blokuje pojedyncze pliki – szanujemy to przy pobieraniu załączników."""
    global _robots
    if _robots is None:
        _robots = urllib.robotparser.RobotFileParser()
        req = urllib.request.Request(f"{BASE}/robots.txt", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            _robots.parse(resp.read().decode("utf-8", "replace").splitlines())
    return _robots.can_fetch(USER_AGENT, url)


def _attachment_text(link: str, ext: str) -> str:
    url = f"{BASE}/{link}"
    if not _allowed(url):
        return ""
    time.sleep(REQUEST_DELAY)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    return docs.text(data, ext)


def add_details(r: dict) -> None:
    """Dla kandydata: treść artykułu, załączniki (PDF/DOCX) z terminem i warunkami,
    oraz czy już rozstrzygnięte."""
    art = _get(f"articles/{r['notice_number'].split('/')[1]}")
    attachments = art.get("attachments") or []
    files = [f"{a.get('name')}.{a.get('extension')}" for a in attachments]
    texts = []
    for a in attachments:
        name, ext = a.get("name") or "", (a.get("extension") or "").lower()
        if ext in ("pdf", "docx") and not SKIP_FILE_RE.search(name) and len(texts) < 3:
            try:
                texts.append(_attachment_text(a["link"], ext))
            except (OSError, ValueError) as e:
                texts.append(f"[{name}: nie udało się odczytać: {e}]")
    attached = "\n".join(t for t in texts if t)
    deadline = docs.deadline(attached)
    if deadline:
        r["deadline"] = deadline
    r["text"] = json.dumps({
        "opis": _clean(art.get("content")),
        "zalaczniki": ", ".join(files),
        "termin": docs.deadline_text(attached),
        "warunki": docs.snippet(attached, docs.CONDITIONS_RE),
        "z_zalacznika": attached[:2500],
    }, ensure_ascii=False)
    content = _clean(art.get("content"))
    if any(CLOSED_RE.search(f) for f in files) or CLOSED_TEXT_RE.search(content):
        r["procedure_result"] = "rozstrzygnięte (informacja o wyborze/wyniku/unieważnieniu)"
