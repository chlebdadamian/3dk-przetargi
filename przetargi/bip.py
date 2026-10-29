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
from datetime import datetime
from html import unescape

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


def add_details(r: dict) -> None:
    """Dla kandydata: treść artykułu i lista załączników (po nich widać, czy już rozstrzygnięte)."""
    art = _get(f"articles/{r['notice_number'].split('/')[1]}")
    files = [f"{a.get('name')}.{a.get('extension')}" for a in art.get("attachments") or []]
    r["text"] = json.dumps({
        "opis": _clean(art.get("content")),
        "zalaczniki": ", ".join(files),
    }, ensure_ascii=False)
    if any(CLOSED_RE.search(f) for f in files):
        r["procedure_result"] = "rozstrzygnięte (załącznik o wyborze/wyniku/unieważnieniu)"
