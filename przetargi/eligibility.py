"""Sprawdzanie warunków udziału (doświadczenie) względem karty doświadczenia biura (portfolio.toml).

To wsparcie oceny, nie decyzja: wymagania wyciągamy z tekstu wzorcami, więc nietypowo
sformułowany warunek może umknąć. Brak danych w karcie = „nie wiadomo”, nigdy zgadywanie.
"""

import re
import tomllib
from datetime import date
from pathlib import Path

WORDS = {"jedn": 1, "dw": 2, "trz": 3, "czter": 4, "pięć": 5, "pięciu": 5, "dziesięciu": 10}


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _num(s: str) -> float:
    return float(re.sub(r"[\s.]", "", s).replace(",", "."))


def _word_num(s: str) -> int:
    if s.isdigit():
        return int(s)
    return next((v for k, v in WORDS.items() if s.lower().startswith(k)), 1)


def requirements(text: str) -> dict:
    t = re.sub(r"\s+", " ", text or "")
    req = {}
    if m := re.search(r"ostatnich (\d+|trzech|pięciu|dziesięciu) lat", t, re.I):
        req["lata"] = _word_num(m.group(1))
    if m := re.search(r"(?:co najmniej|min\.?|minimum)\s*(\d+|jedn\w+|dw\w+|trz\w+)\s*(?:\(\w+\)\s*)?"
                      r"(?:usług|dokumentacj|projekt|opracowa)", t, re.I):
        req["liczba"] = _word_num(m.group(1))
    if m := re.search(r"kubatur\w*[^\d]{0,40}?(\d[\d\s.]*)\s*m(?:3|³|\s*sześc)", t, re.I):
        req["kubatura_m3"] = _num(m.group(1))
    if m := re.search(r"powierzchni\w*[^\d]{0,40}?(\d[\d\s.]*)\s*m(?:2|²|\s*kw)", t, re.I):
        req["powierzchnia_m2"] = _num(m.group(1))
    if m := re.search(r"warto\w*[^\d]{0,50}?(\d[\d\s.]*(?:,\d+)?)\s*(?:zł|pln)", t, re.I):
        req["wartosc_zl"] = _num(m.group(1))
    if re.search(r"użyteczności publicznej", t, re.I):
        req["publiczny"] = True
    if re.search(r"zabytk|rejestr\w* zabytków|ewidencj\w* zabytków", t, re.I):
        req["zabytek"] = True
    return req


def check(text: str, portfolio: dict) -> str:
    """Jednolinijkowy werdykt dla raportu / Jev."""
    req = requirements(text)
    if not req or set(req) <= {"lata"}:
        return "brak rozpoznanych wymagań co do doświadczenia (sprawdź warunki ręcznie)"
    projects = portfolio.get("projekt", [])
    if not projects:
        return "brak karty doświadczenia (portfolio.toml)"
    unknown, ok = set(), []
    for p in projects:
        fails = False
        if "lata" in req:
            if not p.get("rok_zakonczenia"):
                unknown.add("rok")
            elif p["rok_zakonczenia"] < date.today().year - req["lata"]:
                fails = True
        if req.get("publiczny") and not p.get("publiczny"):
            fails = True
        if req.get("zabytek") and not p.get("zabytek"):
            fails = True
        for key in ("kubatura_m3", "powierzchnia_m2", "wartosc_zl"):
            if key in req:
                if not p.get(key):
                    unknown.add(key)
                    fails = fails or None  # nieznane – nie przesądzamy
                elif p[key] < req[key]:
                    fails = True
        if fails is False:
            ok.append(p["nazwa"])
    need = req.get("liczba", 1)
    desc = ", ".join(f"{k}={'tak' if v is True else f'{v:g}'}" for k, v in req.items())
    # sam okres i liczba usług nie mówią, JAKIEJ usługi wymagają (np. „przestrzeń wystawiennicza”) –
    # wtedy nie twierdzimy, że spełnia
    measurable = set(req) & {"kubatura_m3", "powierzchnia_m2", "wartosc_zl", "publiczny", "zabytek"}
    if len(ok) >= need and not measurable:
        return (f"DO SPRAWDZENIA ({desc}) – okres i liczba OK, ale rodzaj wymaganej usługi "
                f"trzeba porównać ręcznie")
    if len(ok) >= need:
        return f"SPEŁNIA ({desc}; rodzaj usługi sprawdź w treści): {', '.join(ok[:3])}"
    if unknown:
        return f"NIE WIADOMO ({desc}) – uzupełnij w karcie: {', '.join(sorted(unknown))}"
    return f"NIE SPEŁNIA ({desc}) – w karcie {len(ok)} z {need} wymaganych"


def summary(portfolio: dict) -> str:
    """Krótki opis doświadczenia dla Jev."""
    projects = portfolio.get("projekt", [])
    if not projects:
        return ""
    parts = []
    for p in projects:
        facts = [p.get("obiekt", "")]
        for key, unit in (("powierzchnia_m2", "m²"), ("kubatura_m3", "m³"), ("wartosc_zl", "zł")):
            if p.get(key):
                facts.append(f"{p[key]:g} {unit}")
        if p.get("rok_zakonczenia"):
            facts.append(str(p["rok_zakonczenia"]))
        if p.get("publiczny"):
            facts.append("obiekt publiczny")
        parts.append(f"{p['nazwa']} ({', '.join(f for f in facts if f)})")
    return "Doświadczenie: " + "; ".join(parts)
