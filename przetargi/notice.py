"""Funkcje wspólne dla ogłoszeń z różnych źródeł (BZP, Baza Konkurencyjności, platformazakupowa, SARP)."""

import json

from . import bip, bk, bzp, pz, rss, sarp

# Źródła, które trzymają sekcje jako JSON w kolumnie text (BZP ma pełny tekst ogłoszenia).
JSON_TEXT = {bk.NOTICE_TYPE, pz.NOTICE_TYPE, sarp.NOTICE_TYPE, bip.NOTICE_TYPE, rss.NOTICE_TYPE}


def sections(row: dict, limit: int = 1500) -> dict[str, str]:
    if row["notice_type"] not in JSON_TEXT:
        return bzp.sections(row["text"], limit)
    out = json.loads(row["text"] or "{}")
    return {k: v if len(v) <= limit else v[:limit] + "…" for k, v in out.items() if v}


def match_text(row: dict) -> str:
    """Tekst do słów kluczowych: w BK tytuły bywają ogólne („Zapytanie ofertowe 1/2026”),
    więc dokładamy początek opisu."""
    if row["notice_type"] != bk.NOTICE_TYPE:
        return row["title"]
    if row.get("match_text"):
        return row["match_text"]
    return f"{row['title']} {sections(row, limit=300).get('opis', '')}"


def url(row: dict) -> str:
    kind = row["notice_type"]
    if kind == bk.NOTICE_TYPE:
        return bk.url(row["object_id"])
    if kind == pz.NOTICE_TYPE:
        return pz.url(row["object_id"])
    if kind == sarp.NOTICE_TYPE:
        return sarp.url(row["object_id"])
    if kind == bip.NOTICE_TYPE:
        return bip.url(row["object_id"])
    if kind == rss.NOTICE_TYPE:
        return row["object_id"]
    tid = row.get("tender_id")
    return f"https://ezamowienia.gov.pl/mp-client/search/list/{tid}" if tid else ""
