"""Wstępny filtr bez AI: twarde wykluczenia + punktacja dopasowania do profilu biura."""


def _hits(text: str, words: list[str]) -> list[str]:
    # słowo zaczynające się spacją pasuje tylko od początku wyrazu (" wnętrz" ≠ "zewnętrznymi")
    text = f" {text}"
    return [w.strip() for w in words if w in text]


def evaluate(row: dict, cfg: dict) -> tuple[int, str]:
    """Zwraca (punkty, uzasadnienie). Punkty 0 = odrzucone twardym warunkiem."""
    provinces = cfg.get("provinces") or {}
    # brak województwa = źródło bez lokalizacji (platformazakupowa, SARP) – nie odrzucamy
    if provinces and row["province"] and row["province"] not in provinces:
        return 0, f"województwo {row['province']}"

    order_types = cfg.get("order_types") or []
    # brak typu = wstępny wiersz z listy BK, typ sprawdzimy po pobraniu szczegółów
    if order_types and row["order_type"] and row["order_type"] not in order_types:
        return 0, f"typ {row['order_type']}"

    title = row.get("match_text", row["title"]).lower()
    excluded = _hits(title, cfg.get("exclude_keywords", []))
    if excluded:
        return 0, f"wykluczone: {', '.join(excluded)}"
    if not _hits(title, cfg.get("require_any", [])):
        return 0, "nie dotyczy projektowania"

    score, reasons = 0, []
    if provinces and row["province"]:
        score += provinces[row["province"]]
        reasons.append(f"{row['province']} +{provinces[row['province']]}")

    near = cfg.get("near", {})
    city = (row["org_city"] or "").strip().lower()
    if city and city in {c.lower() for c in near.get("cities", [])}:
        score += near["points"]
        reasons.append(f"blisko ({row['org_city']}) +{near['points']}")
    elif not row["province"]:
        # bez lokalizacji: szukamy miejscowości / powiatu w nazwie zamawiającego
        org = (row.get("org_name") or "").lower()
        hit = next((w for w in [c.lower() for c in near.get("cities", [])] + near.get("org_words", [])
                    if w in org), None)
        if not hit:
            return 1, "lokalizacja nieznana – w nazwie zamawiającego brak miejscowości z okolicy"
        bonus_pl = provinces.get("PL12", 0)
        score += near["points"] + bonus_pl
        reasons.append(f"blisko z nazwy zamawiającego ({hit}) +{near['points'] + bonus_pl}")

    for group, spec in cfg.get("keywords", {}).items():
        hits = _hits(title, spec["words"])
        if hits:
            score += spec["points"]
            reasons.append(f"{group}: {', '.join(hits)} +{spec['points']}")

    bonus = cfg.get("cpv_bonus", {})
    cpv_hits = [c for c in bonus.get("codes", []) if c in row["cpv"]]
    if cpv_hits:
        score += bonus["points"]
        reasons.append(f"CPV {', '.join(cpv_hits)} +{bonus['points']}")

    # sama lokalizacja nie wystarcza – musi trafić przedmiot (specjalność / budynek albo CPV)
    content = cfg.get("content_groups") or list(cfg.get("keywords", {}))
    if not any(r.split(":")[0] in content for r in reasons) and not cpv_hits:
        return 1, "; ".join(reasons + ["brak dopasowania przedmiotu"])

    value = cfg.get("value", {})
    if row.get("estimate") and value.get("max_value") and row["estimate"] > value["max_value"]:
        score -= value["penalty"]
        reasons.append(f"duża wartość {row['estimate']:,.0f} zł -{value['penalty']}".replace(",", " "))

    return max(score, 1), "; ".join(reasons)
