"""platformazakupowa.pl – postępowania gmin i powiatów, w tym zamówienia poniżej 130 tys. zł.

robots.txt: Crawl-delay 900 – między zapytaniami czekamy 15 minut, dlatego pytamy tylko
wyszukiwarkę (/all?query=…) kilkoma frazami, a nie przechodzimy całej listy.
Lista podaje tytuł, zamawiającego i termin; lokalizacji nie ma.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape

from .bzp import USER_AGENT

BASE = "https://platformazakupowa.pl"
NOTICE_TYPE = "PZProceeding"
CRAWL_DELAY = 900  # sekundy, z robots.txt
PAGE_LIMIT = 100

ITEM_RE = re.compile(
    r'<a href="/transakcja/(\d+)"[^>]*class="gray-link auction-title">\s*(.*?)\s*</a>\s*</b>\s*<br/>\s*'
    r'(.*?)<br/>.*?countdown-\1"?[^>]*>\s*([\d-]+ [\d:]+)',
    re.S,
)

_last_request = 0.0


def _get(path: str, params: dict) -> str:
    global _last_request
    wait = _last_request + CRAWL_DELAY - time.monotonic()
    if _last_request and wait > 0:
        time.sleep(wait)
    url = f"{BASE}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", "replace")
    finally:
        _last_request = time.monotonic()


def search(query: str) -> list[dict]:
    html = _get("/all", {"page": 1, "limit": PAGE_LIMIT, "query": query})
    out = []
    for pid, title, org, deadline in ITEM_RE.findall(html):
        title = re.sub(r"\s*\(ID \d+\)\s*$", "", unescape(re.sub(r"\s+", " ", title))).strip()
        out.append({"id": pid, "title": title, "org": unescape(org).strip(), "deadline": deadline})
    return out


ROW_RE = re.compile(
    r"<tr>\s*<td>(\d+)</td>\s*<td>(.*?)</td>\s*<td>.*?</td>\s*<td>([\d-]+ [\d:]+)</td>\s*<td>.*?</td>\s*"
    r'<td class="text-center">(.*?)</td>',
    re.S,
)
CATEGORIES = {"Usługa": "Services", "Robota budowlana": "Works", "Dostawa": "Supplies"}


def organizer(slug: str) -> list[dict]:
    """Postępowania jednego zamawiającego (/pn/{slug}/proceedings) – z rodzajem zamówienia."""
    html = _get(f"/pn/{slug}/proceedings", {})
    out = []
    for pid, title, deadline, category in ROW_RE.findall(html):
        category = unescape(category).strip()
        out.append({"id": pid, "title": unescape(re.sub(r"\s+", " ", title)).strip(), "org": "",
                     "deadline": datetime.strptime(deadline, "%Y-%m-%d %H:%M").strftime("%d-%m-%Y %H:%M:%S"),
                     "order_type": CATEGORIES.get(category, category)})
    return out


def url(pid) -> str:
    return f"{BASE}/transakcja/{pid}"


def row(item: dict) -> dict:
    # termin w czasie polskim: "30-10-2026 07:30:00"; naiwny = czas systemowy (PL)
    local = datetime.strptime(item["deadline"], "%d-%m-%Y %H:%M:%S")
    return {
        "notice_number": f"PZ/{item['id']}",
        "notice_type": NOTICE_TYPE,
        "object_id": item["id"],
        "title": item["title"],
        "org_name": item["org"],
        "org_city": None,  # nieznane – bliskość szukamy w nazwie zamawiającego
        "province": None,
        "order_type": item.get("order_type"),
        "cpv": "",
        "deadline": local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "published": None,
        "text": json.dumps({}),
        "estimate": None,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
