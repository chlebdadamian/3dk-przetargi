"""Ceny z rynku: podobne rozstrzygnięte przetargi z BZP."""

import re
import sqlite3
from datetime import date, timedelta

# Słowa, które są w prawie każdym tytule i nic nie mówią o podobieństwie.
STOP = {
    "opracowanie", "dokumentacji", "dokumentacja", "projektowej", "projektowo", "kosztorysowej",
    "wykonanie", "zadania", "zadanie", "ramach", "projektu", "wraz", "oraz", "dla", "pn",
    "budowlanego", "wykonawczego", "zakresie", "realizacji", "inwestycji", "gminy", "gminie",
    "miasta", "powiatu", "usługa", "usługi", "zamówienia", "uzyskaniem", "niezbędnych",
    "pełnobranżowej", "wielobranżowej", "kompletnej", "technicznej", "część", "części",
}
# CPV, które ma niemal każde ogłoszenie projektowe – nie świadczą o podobieństwie.
GENERIC_CPV = {"71000000", "71200000", "71300000", "71320000"}


def stems(title: str) -> set[str]:
    """Prymitywny stemming: pierwsze 6 liter słów dłuższych niż 3 znaki."""
    words = re.findall(r"[a-ząćęłńóśźż]+", title.lower())
    return {w[:6] for w in words if len(w) > 3 and w not in STOP}


def cpv_set(cpv: str) -> set[str]:
    return set(re.findall(r"(\d{8})-\d", cpv or "")) - GENERIC_CPV


def similarity(a: dict, b: dict) -> float:
    sa, sb = stems(a["title"]), stems(b["title"])
    words = len(sa & sb) / len(sa | sb) if sa and sb else 0.0
    ca, cb = cpv_set(a["cpv"]), cpv_set(b["cpv"])
    codes = len(ca & cb) / len(ca | cb) if ca and cb else 0.0
    return 0.7 * words + 0.3 * codes


def similar(conn: sqlite3.Connection, notice: dict, days: int = 365, top: int = 8,
            min_sim: float = 0.12) -> list[tuple[float, dict]]:
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT * FROM notices WHERE notice_type = 'TenderResultNotice'
           AND published >= ? AND price_winner IS NOT NULL""",
        (since,),
    ).fetchall()
    scored = []
    for r in rows:
        r = dict(r)
        s = similarity(notice, r)
        if r["province"] == notice.get("province"):
            s += 0.05
        if s >= min_sim:
            scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top]


def summary(rows: list[dict]) -> dict | None:
    prices = sorted(r["price_winner"] for r in rows if r["price_winner"])
    if not prices:
        return None
    offers = [r["offers"] for r in rows if r["offers"]]
    return {
        "n": len(prices),
        "median": prices[len(prices) // 2],
        "min": prices[0],
        "max": prices[-1],
        "offers_avg": sum(offers) / len(offers) if offers else None,
    }


def zl(v: float | None) -> str:
    return f"{v:,.0f} zł".replace(",", " ") if v is not None else "–"
