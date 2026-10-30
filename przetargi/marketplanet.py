"""Marketplanet (ezamawiajacy.pl) – wspólna wyszukiwarka postępowań wszystkich zamawiających
na oneplace.marketplanet.pl (np. Gmina Myślenice). robots.txt blokuje tylko regulaminy i formularze.

Lista podaje tytuł, zamawiającego, kategorię i termin; lokalizacji nie ma – bliskość rozpoznajemy
po nazwie zamawiającego (jak w platformazakupowa).
"""

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape

from .bzp import USER_AGENT

BASE = "https://oneplace.marketplanet.pl/pl/zapytania-ofertowe-przetargi/-/rfp/cat"
NOTICE_TYPE = "MarketplanetNotice"
P = "_7_WAR_organizationnoticeportlet_"
REQUEST_DELAY = 2.0
PAGES = 3  # po 12 wyników, najnowsze najpierw

ITEM_RE = re.compile(
    r'<a class="notice-url" href="([^"]*/rfp/view/(\d+)/[^"?]*)[^"]*"\s*>(.*?)</a>.*?'
    r'<span class="organization-name">(.*?)</span>.*?<span class="main-category">(.*?)</span>.*?'
    r'<span title="Termin składania ofert">\s*(.*?)\s*</span>',
    re.S,
)
CATEGORIES = {"Usługi": "Services", "Dostawy": "Supplies", "Roboty budowlane": "Works"}


def _get(params: dict) -> str:
    time.sleep(REQUEST_DELAY)
    req = urllib.request.Request(f"{BASE}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def _deadline(text: str) -> str | None:
    """„Fri Nov 06 09:00:00 GMT 2026” – strona podaje GMT, ale godzina to czas polski
    (09:00 to typowa godzina składania ofert), więc traktujemy ją jako lokalną."""
    try:
        local = datetime.strptime(text.replace(" GMT", ""), "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def search(query: str) -> list[dict]:
    out = []
    for page in range(1, PAGES + 1):
        html = _get({f"{P}keywords": query, f"{P}order": "createDateDesc", f"{P}cur": page})
        found = ITEM_RE.findall(html)
        for link, nid, title, org, category, deadline in found:
            category = unescape(category).strip()
            out.append({"id": nid, "link": link, "title": unescape(re.sub(r"\s+", " ", title)).strip(),
                        "org": unescape(org).strip(), "category": category,
                        "order_type": next((v for k, v in CATEGORIES.items() if category.startswith(k)), None),
                        "deadline": _deadline(deadline.strip())})
        if len(found) < 12:
            break
    return out


def row(item: dict) -> dict:
    return {
        "notice_number": f"MP/{item['id']}",
        "notice_type": NOTICE_TYPE,
        "object_id": item["link"],
        "title": item["title"],
        "org_name": item["org"],
        "org_city": None,
        "province": None,
        "order_type": item["order_type"],
        "cpv": "",
        "published": None,
        "deadline": item["deadline"],
        "text": json.dumps({"kategoria": item["category"]}, ensure_ascii=False),
        "estimate": None,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
