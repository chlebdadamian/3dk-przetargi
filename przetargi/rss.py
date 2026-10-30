"""Kanały RSS serwisów przetargowych gmin (np. przetargi.myslenice.pl – WordPress).

RSS to oficjalnie udostępniona lista nowych wpisów, więc pobieramy tylko kanał, bez przeglądania stron.
Terminu w kanale nie ma: wpis uznajemy za aktualny przez OPEN_DAYS od publikacji (jak BIP).
"""

import json
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urljoin

from .bzp import USER_AGENT

NOTICE_TYPE = "RSSNotice"
OPEN_DAYS = 21


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _date(pub: str | None) -> str | None:
    """Format RSS (RFC 822) albo – jak w kanale UMK – „2026-10-29 08:46:13.0”."""
    if not pub:
        return None
    try:
        return parsedate_to_datetime(pub).date().isoformat()
    except ValueError:
        m = re.match(r"\d{4}-\d{2}-\d{2}", pub.strip())
        return m.group(0) if m else None


def _context():
    """Weryfikacja certyfikatów przez system (Windows dociąga brakujące certyfikaty pośrednie,
    np. imeriweb.um.krakow.pl ich nie wysyła); bez truststore – domyślna weryfikacja Pythona."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return None


def items(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=_context()) as resp:
        root = ET.fromstring(resp.read())
    out = []
    for it in root.iter("item"):
        # kanał UMK podaje linki względne („pages/zmw-og-detail.jsf?id=8721”)
        link = urljoin(url, (it.findtext("link") or "").strip())
        guid = (it.findtext("guid") or "").strip()
        pub = it.findtext("pubDate")
        out.append({
            "id": urljoin(url, guid) if guid and not guid.startswith("http") and "/" in guid else (guid or link),
            "title": _clean(it.findtext("title")),
            "link": link,
            "published": _date(pub),
            "description": _clean(it.findtext("description"))[:2000],
        })
    return out


def row(item: dict, org: str, city: str) -> dict:
    key = re.sub(r"^https?://", "", item["id"]).rstrip("/")
    return {
        "notice_number": f"RSS/{key}",
        "notice_type": NOTICE_TYPE,
        "object_id": item["link"],
        "title": item["title"],
        "org_name": org,
        "org_city": city,
        "province": "PL12",
        "order_type": None,
        "cpv": "",
        "published": item["published"],
        "deadline": None,
        "text": json.dumps({"opis": item["description"]}, ensure_ascii=False),
        "estimate": None,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
