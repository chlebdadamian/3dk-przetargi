"""Kanały RSS serwisów przetargowych gmin (np. przetargi.myslenice.pl – WordPress).

RSS to oficjalnie udostępniona lista nowych wpisów, więc pobieramy tylko kanał, bez przeglądania stron.
Terminu w kanale nie ma: wpis uznajemy za aktualny przez OPEN_DAYS od publikacji (jak BIP).
"""

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape

from .bzp import USER_AGENT

NOTICE_TYPE = "RSSNotice"
OPEN_DAYS = 21


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def items(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        root = ET.fromstring(resp.read())
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        out.append({
            "id": it.findtext("guid") or link,
            "title": _clean(it.findtext("title")),
            "link": link,
            "published": parsedate_to_datetime(pub).date().isoformat() if pub else None,
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
