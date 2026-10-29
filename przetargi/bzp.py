"""Klient publicznego API Biuletynu Zamówień Publicznych (e-Zamówienia)."""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from html import unescape

API_URL = "https://ezamowienia.gov.pl/mo-board/api/v1/notice"
PAGE_SIZE = 500  # API ignoruje PageNumber, więc przy pełnej stronie dzielimy okno dat
USER_AGENT = "przetargi-monitor/0.1"  # WAF blokuje domyślny UA urllib i podszywanie się pod przeglądarkę
REQUEST_DELAY = 5.0  # sekundy między zapytaniami; WAF ma limit, nadpisywane z config.toml


class Blocked(Exception):
    """WAF e-Zamówień zwrócił 403 – trzeba odczekać, nie ponawiać od razu."""


def _get(params: dict) -> list[dict]:
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    time.sleep(REQUEST_DELAY)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except OSError as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 403:
                raise Blocked() from e
            if attempt == 2 or (isinstance(e, urllib.error.HTTPError) and e.code < 500):
                raise
            time.sleep(2 * (attempt + 1))
    return []


def fetch(notice_type: str, day_from: date, day_to: date, cpv: str) -> list[dict]:
    """Pobiera ogłoszenia danego typu i kodu CPV z zakresu dni (włącznie)."""
    items = _get({
        "NoticeType": notice_type,
        "CpvCode": cpv,
        "PublicationDateFrom": f"{day_from.isoformat()}T00:00:00",
        "PublicationDateTo": f"{day_to.isoformat()}T23:59:59",
        "PageSize": PAGE_SIZE,
    })
    if len(items) >= PAGE_SIZE and day_from < day_to:
        mid = day_from + (day_to - day_from) // 2
        return fetch(notice_type, day_from, mid, cpv) + fetch(notice_type, mid + timedelta(days=1), day_to, cpv)
    return items


def html_to_text(html: str) -> str:
    html = re.sub(r"(?s)<(style|script)[^>]*>.*?</\1>", " ", html or "")
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"\s+", " ", text).strip()


def _amount(text: str, label: str) -> float | None:
    m = re.search(re.escape(label) + r"[^:]*:\s*([\d\s.]+(?:,\d+)?)\s*PLN", text)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_result(text: str) -> dict:
    """Wyciąga z ogłoszenia o wyniku liczbę ofert, ceny i zwycięzcę."""
    offers = re.search(r"6\.1\.\) Liczba otrzymanych ofert[^:]*:\s*(\d+)", text)
    winner = re.search(r"7\.3\.1\) Nazwa \(firma\) wykonawcy[^:]*:\s*(.+?)\s+7\.3\.2\)", text)
    return {
        "offers": int(offers.group(1)) if offers else None,
        "price_min": _amount(text, "6.2.) Cena lub koszt oferty z najniższą"),
        "price_max": _amount(text, "6.3.) Cena lub koszt oferty z najwyższą"),
        "price_winner": _amount(text, "6.4.) Cena lub koszt oferty wykonawcy"),
        "winner": winner.group(1) if winner else None,
    }


# (nazwa, początek sekcji, wzorzec końca) w tekście ogłoszenia o zamówieniu
SECTIONS = [
    ("opis", "4.2.2.) Krótki opis przedmiotu zamówienia", r"4\.2\.[3-9]\.\)|4\.2\.1\d\.\)|4\.3\.\)"),
    ("okres", "4.2.10.) Okres realizacji zamówienia albo umowy ramowej:", r"4\.2\.1[1-9]\.\)|4\.3\.\)"),
    ("kryteria", "4.3.3.) Stosowane kryteria oceny ofert:", r"4\.3\.10\.\)|SEKCJA V"),
    ("warunki", "5.4.) Nazwa i opis warunków udziału w postępowaniu.", r"5\.5\.\)|5\.6\.\)|SEKCJA VI"),
    ("wadium", "6.4.) Zamawiający wymaga wadium:", r"6\.5\.\)"),
]


def sections(text: str, limit: int = 1500) -> dict[str, str]:
    """Najważniejsze fragmenty ogłoszenia o zamówieniu."""
    out = {}
    for name, start, end in SECTIONS:
        i = text.find(start)
        if i < 0:
            continue
        body = text[i + len(start):]
        m = re.search(end, body)
        body = body[: m.start()] if m else body
        body = body.strip(" :")
        out[name] = body if len(body) <= limit else body[:limit] + "…"
    return out


def parse_estimate(text: str) -> float | None:
    """Wartość zamówienia z ogłoszenia o zamówieniu, jeśli zamawiający ją podał."""
    return _amount(text, "Wartość zamówienia")


def normalize(item: dict) -> dict:
    text = html_to_text(item.get("htmlBody", ""))
    row = {
        "notice_number": item["noticeNumber"],
        "notice_type": item["noticeType"],
        "object_id": item.get("objectId"),
        "tender_id": item.get("tenderId"),
        "published": item.get("publicationDate"),
        "deadline": item.get("submittingOffersDate"),
        "title": (item.get("orderObject") or "").strip(),
        "order_type": item.get("orderType"),
        "cpv": item.get("cpvCode") or "",
        "org_name": item.get("organizationName"),
        "org_city": item.get("organizationCity"),
        "province": item.get("organizationProvince"),
        "below_eu": item.get("isTenderAmountBelowEU"),
        "procedure_result": item.get("procedureResult"),
        "text": text,
        "estimate": parse_estimate(text) if item["noticeType"] == "ContractNotice" else None,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    if item["noticeType"] == "TenderResultNotice":
        row.update(parse_result(text))
    return row
