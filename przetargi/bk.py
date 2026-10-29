"""Klient Bazy Konkurencyjności (zamówienia w projektach z funduszy UE).

API strony: GET /api/announcements/search (lista, max 200 na stronę) i /api/announcements/{id}.
Lista ma tylko skrót, więc szczegóły pobieramy wyłącznie dla kandydatów po wstępnym filtrze.
"""

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .bzp import USER_AGENT

BASE = "https://bazakonkurencyjnosci.funduszeeuropejskie.gov.pl"
NOTICE_TYPE = "BKAnnouncement"
PAGE_SIZE = 200
REQUEST_DELAY = 1.0

PROVINCES = {
    "dolnośląskie": "PL02", "kujawsko-pomorskie": "PL04", "lubelskie": "PL06", "lubuskie": "PL08",
    "łódzkie": "PL10", "małopolskie": "PL12", "mazowieckie": "PL14", "opolskie": "PL16",
    "podkarpackie": "PL18", "podlaskie": "PL20", "pomorskie": "PL22", "śląskie": "PL24",
    "świętokrzyskie": "PL26", "warmińsko-mazurskie": "PL28", "wielkopolskie": "PL30",
    "zachodniopomorskie": "PL32",
}
CATEGORIES = {"Usługa": "Services", "Robota budowlana": "Works", "Dostawa": "Supplies"}


def _get(path: str, params: list[tuple[str, str]] | None = None) -> dict:
    url = f"{BASE}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    time.sleep(REQUEST_DELAY)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)["data"]


def list_published() -> list[dict]:
    """Wszystkie opublikowane (otwarte) ogłoszenia – skróty."""
    items, page = [], 1
    while True:
        data = _get("/api/announcements/search", [
            ("page", str(page)), ("limit", str(PAGE_SIZE)), ("sort", "publicationDate"),
            ("status[]", "PUBLISHED"),
        ])
        items += data["advertisements"]
        if not data["advertisements"] or len(items) >= data["meta"]["total"]:
            return items
        page += 1


def url(announcement_id) -> str:
    return f"{BASE}/ogloszenia/{announcement_id}"


def _place(text: str) -> tuple[str, str | None]:
    """'Bytom, śląskie' -> ('Bytom', 'PL24')."""
    city, _, province = (text or "").rpartition(", ")
    return city or text, PROVINCES.get(province.strip().lower())


def _num(value) -> float | None:
    """Wartość szacunkowa przychodzi jako tekst, np. '45000.00' lub '45 000,00'."""
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(" ", "").replace("\xa0", "").replace(",", "."))
    except ValueError:
        return None


def _utc(local: str | None) -> str | None:
    """Termin BK jest w czasie polskim (bez strefy) – zapisujemy w UTC jak w BZP."""
    if not local:
        return None
    dt = datetime.fromisoformat(local).astimezone(timezone.utc)  # naiwny = czas systemowy (PL)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def summary_row(item: dict) -> dict:
    """Wstępny wiersz ze skrótu z listy – wystarcza do filtra przed pobraniem szczegółów."""
    city, province = _place(item.get("fulfillment_place", ""))
    return {
        "notice_number": f"BK/{item['id']}",
        "notice_type": NOTICE_TYPE,
        "object_id": str(item["id"]),
        "title": item["title"].strip(),
        "org_city": city,
        "province": province,
        "order_type": None,  # znany dopiero ze szczegółów
        "cpv": "",
        "match_text": f"{item['title']} {item.get('content') or ''}",
        "estimate": None,
    }


def detail_row(item: dict) -> dict:
    """Pełny wiersz ogłoszenia (format tabeli notices)."""
    ad = _get(f"/api/announcements/{item['id']}")["advertisement"]
    orders = ad.get("orders") or []
    order_items = [oi for o in orders for oi in o.get("order_items", [])]
    first = order_items[0] if order_items else {}
    place = (first.get("fulfillment_places") or [{}])[0]
    cpv = ",".join(f"{c['code']} ({c['name']})" for oi in order_items for c in oi.get("cpv_items", []))
    category = (first.get("category") or {}).get("name")
    sections = {
        "opis": "\n".join(oi.get("description") or "" for oi in order_items).strip(),
        "okres": "; ".join(t.get("description") or "" for oi in order_items
                           for t in oi.get("timetable_items", []) if isinstance(t, dict)),
        "kryteria": "; ".join(c.get("description") or "" for o in orders
                              for c in (o.get("evaluation_criteria") or []) if isinstance(c, dict)),
        "warunki": "\n".join(c.get("description") or "" for oi in order_items
                             for c in oi.get("participation_conditions", [])),
    }
    estimates = [v for v in (_num(o.get("estimated_value")) for o in orders) if v]
    advertiser = ad.get("advertiser_address_details") or {}
    return {
        **summary_row(item),
        "published": ad.get("publication_date"),
        "deadline": _utc(ad.get("submission_deadline")),
        "order_type": CATEGORIES.get(category, category),
        "cpv": cpv,
        "org_name": advertiser.get("name"),
        "org_city": place.get("locality") or summary_row(item)["org_city"],
        "province": PROVINCES.get((place.get("voivodeship") or "").lower()) or summary_row(item)["province"],
        "text": json.dumps({k: v for k, v in sections.items() if v}, ensure_ascii=False),
        "estimate": float(sum(estimates)) if estimates else None,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
