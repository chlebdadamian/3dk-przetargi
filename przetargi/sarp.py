"""Konkursy architektoniczne SARP (sarp.pl) – szansa bez wymogu portfolio publicznego.

Strona SARP ma tylko krótki opis i link do strony konkursu (NNNN.konkurs.sarp.pl), bez terminów.
Konkursów jest kilka w miesiącu, więc bierzemy wszystkie nowe i oceniamy je w raporcie.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from html import unescape

from . import docs
from .bzp import USER_AGENT

BASE = "https://www.sarp.pl"
NOTICE_TYPE = "SARPCompetition"
CATEGORIES = ["/kat/konkursy_sarp,29", "/kat/inne_konkursy,31"]
REQUEST_DELAY = 2.0


def _get(path: str) -> str:
    time.sleep(REQUEST_DELAY)
    # ścieżki wpisów bywają z polskimi znakami / półpauzą – urllib wymaga ASCII
    req = urllib.request.Request(f"{BASE}{urllib.parse.quote(path, safe='/,:')}",
                                 headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def _text(html: str) -> str:
    html = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def list_entries() -> list[tuple[str, str]]:
    """(id, ścieżka) wpisów z kategorii konkursowych."""
    out = {}
    for cat in CATEGORIES:
        for path, pid in re.findall(r'href="(/pokaz/[^"]+,(\d+)/?)"[^>]*>\s*więcej', _get(cat)):
            out[pid] = path
    return list(out.items())


def url(path: str) -> str:
    return f"{BASE}{path}"


def entry_row(pid: str, path: str) -> dict:
    text = _text(_get(path))
    added = re.search(r"Data dodania: (\d{2}\.\d{2}\.\d{4})", text)
    published = datetime.strptime(added.group(1), "%d.%m.%Y").date().isoformat() if added else None
    # treść wpisu: od nagłówka z datą do stopki „Udostępnij na”
    body = text[added.end():] if added else text
    body = re.sub(r"^\s*\|\s*Aktualizacja: [\d.]+, [\d:]+\s*", "", body).split(" Udostępnij na")[0].strip()
    site = re.search(r"https?://\S+konkurs\.sarp\.pl/?", body)
    return {
        "notice_number": f"SARP/{pid}",
        "notice_type": NOTICE_TYPE,
        "object_id": path,
        "title": body[:300],
        "org_name": "SARP",
        "org_city": None,
        "province": None,
        "order_type": None,
        "cpv": "",
        "published": published,
        "deadline": docs.deadline(body),  # jeśli opis go podaje; inaczej jest na stronie konkursu
        "text": json.dumps({"opis": body, "strona_konkursu": site.group(0) if site else ""}, ensure_ascii=False),
        "estimate": None,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
