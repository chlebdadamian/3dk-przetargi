"""Wstępny filtr bez AI: twarde wykluczenia + punktacja dopasowania do profilu biura."""


def _hits(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w in text]


def evaluate(row: dict, cfg: dict) -> tuple[int, str]:
    """Zwraca (punkty, uzasadnienie). Punkty 0 = odrzucone twardym warunkiem."""
    provinces = cfg.get("provinces") or {}
    if provinces and row["province"] not in provinces:
        return 0, f"województwo {row['province']}"

    order_types = cfg.get("order_types") or []
    if order_types and row["order_type"] not in order_types:
        return 0, f"typ {row['order_type']}"

    title = row["title"].lower()
    excluded = _hits(title, cfg.get("exclude_keywords", []))
    if excluded:
        return 0, f"wykluczone: {', '.join(excluded)}"
    if not _hits(title, cfg.get("require_any", [])):
        return 0, "nie dotyczy projektowania"

    score, reasons = 0, []
    if provinces:
        score += provinces[row["province"]]
        reasons.append(f"{row['province']} +{provinces[row['province']]}")

    near = cfg.get("near", {})
    city = (row["org_city"] or "").strip().lower()
    if city and city in {c.lower() for c in near.get("cities", [])}:
        score += near["points"]
        reasons.append(f"blisko ({row['org_city']}) +{near['points']}")

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

    value = cfg.get("value", {})
    if row.get("estimate") and value.get("max_value") and row["estimate"] > value["max_value"]:
        score -= value["penalty"]
        reasons.append(f"duża wartość {row['estimate']:,.0f} zł -{value['penalty']}".replace(",", " "))

    return max(score, 1), "; ".join(reasons)
