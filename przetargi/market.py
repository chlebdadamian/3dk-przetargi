"""Wywiad rynkowy z ogłoszeń o wyniku (BZP): kto wygrywa przetargi projektowe w regionie
(kandydaci na partnerów do konsorcjów) i jak skończyły się przetargi, które oceniliśmy."""

import re
import sqlite3
from collections import defaultdict
from datetime import date, timedelta


def _winner_details(text: str) -> dict:
    """NIP i miejscowość zwycięzcy z sekcji VII ogłoszenia o wyniku."""
    nip = re.search(r"7\.3\.2\) Krajowy Numer Identyfikacyjny:\s*(\d{10})", text or "")
    city = re.search(r"7\.3\.4\) Miejscowość:\s*(.+?)\s+7\.3\.", text or "")
    return {"nip": nip.group(1) if nip else None, "city": city.group(1).strip() if city else None}


def _norm(name: str) -> str:
    n = re.sub(r"[„”\"'.,]", "", (name or "").lower())
    n = re.sub(r"\b(sp z o ?o|spółka z ograniczoną odpowiedzialnością|sp k|sp j|spółka jawna|s ?a)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def partners(conn: sqlite3.Connection, provinces: list[str], days: int = 365, top: int = 25) -> list[dict]:
    """Zwycięzcy trafnych (score > 0) przetargów projektowych w danych województwach."""
    since = (date.today() - timedelta(days=days)).isoformat()
    marks = ",".join("?" * len(provinces))
    rows = conn.execute(
        f"""SELECT * FROM notices WHERE notice_type = 'TenderResultNotice' AND score > 0
            AND winner IS NOT NULL AND published >= ? AND province IN ({marks})""",
        (since, *provinces),
    ).fetchall()
    firms = defaultdict(lambda: {"wins": [], "names": set(), "nip": None, "city": None})
    for r in rows:
        r = dict(r)
        details = _winner_details(r["text"])
        key = details["nip"] or _norm(r["winner"])
        f = firms[key]
        f["wins"].append(r)
        f["names"].add(r["winner"])
        f["nip"] = f["nip"] or details["nip"]
        f["city"] = f["city"] or details["city"]
    out = []
    for key, f in firms.items():
        prices = sorted(w["price_winner"] for w in f["wins"] if w["price_winner"])
        offers = [w["offers"] for w in f["wins"] if w["offers"]]
        out.append({
            "name": min(f["names"], key=len),
            "nip": f["nip"],
            "city": f["city"],
            "wins": len(f["wins"]),
            "median": prices[len(prices) // 2] if prices else None,
            "max": prices[-1] if prices else None,
            "offers_avg": sum(offers) / len(offers) if offers else None,
            "examples": sorted(f["wins"], key=lambda w: w["price_winner"] or 0, reverse=True)[:3],
        })
    out.sort(key=lambda x: (x["wins"], x["max"] or 0), reverse=True)
    return out[:top]


def outcomes(conn: sqlite3.Connection) -> list[tuple[dict, dict | None]]:
    """Ocenione ogłoszenia z BZP i ich ogłoszenie o wyniku (to samo tender_id), jeśli już jest."""
    rows = conn.execute(
        """SELECT n.*, r.verdict, r.note FROM notices n JOIN reviews r ON r.notice_number = n.notice_number
           WHERE n.notice_type = 'ContractNotice' ORDER BY n.deadline"""
    ).fetchall()
    out = []
    for r in rows:
        result = conn.execute(
            "SELECT * FROM notices WHERE notice_type = 'TenderResultNotice' AND tender_id = ? "
            "ORDER BY published DESC", (r["tender_id"],)
        ).fetchone()
        out.append((dict(r), dict(result) if result else None))
    return out
