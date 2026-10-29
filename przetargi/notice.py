"""Funkcje wspólne dla ogłoszeń z różnych źródeł (BZP, Baza Konkurencyjności)."""

import json

from . import bk, bzp


def is_bk(row: dict) -> bool:
    return row["notice_type"] == bk.NOTICE_TYPE


def sections(row: dict, limit: int = 1500) -> dict[str, str]:
    if not is_bk(row):
        return bzp.sections(row["text"], limit)
    out = json.loads(row["text"] or "{}")
    return {k: v if len(v) <= limit else v[:limit] + "…" for k, v in out.items()}


def match_text(row: dict) -> str:
    """Tekst do słów kluczowych: w BK tytuły bywają ogólne („Zapytanie ofertowe 1/2026”),
    więc dokładamy początek opisu."""
    if not is_bk(row):
        return row["title"]
    if row.get("match_text"):
        return row["match_text"]
    return f"{row['title']} {sections(row, limit=300).get('opis', '')}"


def url(row: dict) -> str:
    if is_bk(row):
        return bk.url(row["object_id"])
    tid = row.get("tender_id")
    return f"https://ezamowienia.gov.pl/mp-client/search/list/{tid}" if tid else ""
