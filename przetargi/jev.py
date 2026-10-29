"""Ocena przetargów modelem decyzyjnym Jev (TypeSafe AI).

API: POST https://api.typesafe.ai/v1/systemone, body {model, state, questions}
(ten sam kontrakt co w traderxtb/src/indextrading/analysis/jev.py).
Konfiguracja z .env: JEV_API_KEY (wymagany), JEV_MODEL, JEV_URL, JEV_DAILY_REQUEST_LIMIT.
"""

import json
import os
import sqlite3
import urllib.request
from datetime import date, datetime, timezone

from . import bzp

JEV_URL = "https://api.typesafe.ai/v1/systemone"

PROFILE = (
    "Małe biuro architektoniczne z Krakowa i Nowego Sącza (architekt + podwykonawcy branżowi: "
    "konstrukcja, instalacje). Specjalność: projekty budynków (głównie domy jednorodzinne), "
    "elewacje, termomodernizacje, wnętrza, adaptacje, koncepcje, wizualizacje, nadzór autorski, "
    "trudny teren (skarpy). Architekt ma uprawnienia do projektowania bez ograniczeń w specjalności "
    "architektonicznej. Brak doświadczenia w projektach budynków użyteczności publicznej "
    "(jedno małe zlecenie publiczne: projekt łazienki) i przy zabytkach. Największe dotychczasowe "
    "zlecenie ok. 90 tys. zł. Kosztorysy i branże (konstrukcja, instalacje) robią podwykonawcy. "
    "Projekty domów prywatnych liczą się tam, gdzie warunek nie wymaga obiektu publicznego ani zabytku."
)

QUESTIONS = {
    "fit": {
        "type": "choice",
        "instructions": "Czy biuro opisane w 'profil_biura' powinno złożyć ofertę w tym przetargu?",
        "criteria": {
            "tak": "Zakres i skala pasują do biura, a warunki udziału są realne do spełnienia",
            "moze": "Zakres pasuje, ale jest istotne ryzyko (skala, warunki udziału, termin) – warto sprawdzić SWZ",
            "nie": "Nie pasuje: inna branża, za duża skala albo warunki udziału wykluczają biuro",
        },
    },
    "architecture": {
        "type": "noul",
        "instructions": "Czy głównym przedmiotem zamówienia jest projekt architektoniczny budynku, "
                        "jego wnętrz lub elewacji (a nie drogi, sieci, instalacje, urbanistyka)?",
    },
    "scale": {
        "type": "score",
        "instructions": "Jak duży jest projektowany obiekt?",
        "criteria": [
            "Bardzo mały: pomieszczenie, wnętrze, elewacja, mała wiata",
            "Mały budynek: świetlica, remiza, dom, mały pawilon",
            "Średni budynek: szkoła, przedszkole, przychodnia, dom kultury",
            "Duży obiekt: szpital, hala, kompleks, wiele budynków",
        ],
    },
    "conditions_ok": {
        "type": "noul",
        "instructions": "Czy biuro bez portfolio projektów budynków użyteczności publicznej spełni "
                        "warunki udziału w postępowaniu (doświadczenie, osoby, uprawnienia)?",
    },
}

SCALE_LABELS = ["bardzo mały", "mały budynek", "średni budynek", "duży obiekt"]


class JevClient:
    def __init__(self):
        self.api_key = os.environ["JEV_API_KEY"]
        self.model = os.environ.get("JEV_MODEL", "jev-latest")
        self.url = os.environ.get("JEV_URL", JEV_URL)
        self.daily_limit = int(os.environ.get("JEV_DAILY_REQUEST_LIMIT", "2000"))

    def ask(self, state: dict, questions: dict) -> tuple[dict, str]:
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode()
        req = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return data.get("answers", {}), data.get("model", self.model)


def state_for(row: dict) -> dict:
    sec = bzp.sections(row["text"], limit=1500)
    return {
        "profil_biura": PROFILE,
        "przedmiot": row["title"],
        "zamawiajacy": f"{row['org_name']}, {row['org_city']}",
        "opis": sec.get("opis", ""),
        "okres_realizacji": sec.get("okres", ""),
        "warunki_udzialu": sec.get("warunki", ""),
        "kryteria_oceny": sec.get("kryteria", ""),
    }


def parse(answers: dict) -> dict | None:
    """Odpowiedź Jev -> wiersz tabeli; None przy niepoprawnej odpowiedzi (nigdy nie zgadujemy)."""
    try:
        fit = answers["fit"]
        if fit["choice"] not in QUESTIONS["fit"]["criteria"]:
            return None
        return {
            "fit": fit["choice"],
            "fit_conf": float(fit.get("confidence")) if fit.get("confidence") is not None else None,
            "fit_probs": json.dumps(fit.get("probabilities", {})),
            "architecture": float(answers["architecture"]["noul"]),
            "scale": int(answers["scale"]["score"]),
            "conditions_ok": float(answers["conditions_ok"]["noul"]),
        }
    except (KeyError, ValueError, TypeError):
        return None


def assess_pending(conn: sqlite3.Connection, limit: int | None = None) -> tuple[int, int]:
    """Ocenia otwarte ogłoszenia, które przeszły twarde wykluczenia i nie mają jeszcze oceny Jev."""
    client = JevClient()
    used_today = conn.execute(
        "SELECT count(*) FROM jev WHERE assessed_at >= ?", (date.today().isoformat(),)
    ).fetchone()[0]
    budget = client.daily_limit - used_today
    if limit is not None:
        budget = min(budget, limit)
    rows = conn.execute(
        """SELECT n.* FROM notices n LEFT JOIN jev j ON j.notice_number = n.notice_number
           WHERE n.notice_type = 'ContractNotice' AND n.score > 0 AND j.notice_number IS NULL
             AND n.deadline >= ? ORDER BY n.score DESC LIMIT ?""",
        (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), max(budget, 0)),
    ).fetchall()
    ok = bad = 0
    for r in rows:
        answers, version = client.ask(state_for(dict(r)), QUESTIONS)
        parsed = parse(answers)
        if parsed is None:
            bad += 1
            continue
        conn.execute(
            """INSERT OR REPLACE INTO jev VALUES
               (:notice_number, :fit, :fit_conf, :fit_probs, :architecture, :scale, :conditions_ok, :model, :assessed_at)""",
            {**parsed, "notice_number": r["notice_number"], "model": version,
             "assessed_at": datetime.now().isoformat(timespec="seconds")},
        )
        conn.commit()
        ok += 1
    return ok, bad
