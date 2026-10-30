"""CLI: python -m przetargi fetch | rescore | jev | list | show | similar | prices | report | review."""

import argparse
import html
import os
import re
import sys
import time
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import bip, bk, bzp, db, filters, jev, notice, prices, pz, sarp, telegram

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "przetargi.db"
REPORTS = ROOT / "data" / "raporty"
# ogłoszenia, na które można złożyć ofertę
OPEN_TYPES = ("ContractNotice", bk.NOTICE_TYPE, pz.NOTICE_TYPE, sarp.NOTICE_TYPE, bip.NOTICE_TYPE)
# źródła bez terminu w danych: aktualne tyle dni od publikacji
NO_DEADLINE_DAYS = {sarp.NOTICE_TYPE: 60, bip.NOTICE_TYPE: bip.OPEN_DAYS}


def load_env(path: Path) -> None:
    """Minimalny loader .env (KEY=VALUE); nie nadpisuje zmiennych już ustawionych."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def local_time(iso: str | None) -> str:
    if not iso:
        return "–"
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def load_config(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def score_row(row: dict, cfg: dict) -> None:
    if row["notice_type"] == sarp.NOTICE_TYPE:
        # konkursy są z definicji architektoniczne i rzadkie – wszystkie idą do oceny
        row["score"], row["match_reason"], row["matched"] = cfg["filter"]["min_score"], "konkurs SARP", 1
        return
    row["match_text"] = notice.match_text(row)
    row["score"], row["match_reason"] = filters.evaluate(row, cfg["filter"])
    row["matched"] = int(row["score"] >= cfg["filter"]["min_score"])


def find_notice(conn, ref: str) -> dict:
    rows = conn.execute(
        "SELECT * FROM notices WHERE notice_number LIKE ? ORDER BY notice_number", (f"%{ref}%",)
    ).fetchall()
    if len(rows) != 1:
        sys.exit(f"Nie znaleziono jednoznacznie ogłoszenia '{ref}' ({len(rows)} trafień)")
    return dict(rows[0])


def windows(day_from: date, day_to: date) -> list[tuple[date, date]]:
    """Miesiące kalendarzowe pokrywające zakres – stałe granice, żeby fetch_log działał między dniami."""
    out = []
    start = day_from.replace(day=1)
    while start <= day_to:
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((start, min(next_month - timedelta(days=1), day_to)))
        start = next_month
    return out


def fetch_bk(conn, cfg) -> list[dict]:
    """Baza Konkurencyjności: cała lista otwartych, szczegóły tylko dla nowych kandydatów."""
    items = bk.list_published()
    known = {r[0] for r in conn.execute("SELECT notice_number FROM notices WHERE notice_type = ?",
                                        (bk.NOTICE_TYPE,))}
    candidates = []
    for item in items:
        row = bk.summary_row(item)
        if row["notice_number"] in known:
            continue
        score_row(row, cfg)
        if row["score"] > 0:
            candidates.append(item)
    print(f"  Baza Konkurencyjności: {len(items)} otwartych, nowych kandydatów: {len(candidates)}",
          file=sys.stderr)
    new_matches = []
    for item in candidates:
        row = bk.detail_row(item)
        score_row(row, cfg)
        db.upsert(conn, row)
        conn.commit()
        if row["matched"]:
            new_matches.append(row)
    return new_matches


def fetch_sarp(conn, cfg) -> list[dict]:
    known = {r[0] for r in conn.execute("SELECT notice_number FROM notices WHERE notice_type = ?",
                                        (sarp.NOTICE_TYPE,))}
    new = []
    for pid, path in sarp.list_entries():
        if f"SARP/{pid}" in known:
            continue
        row = sarp.entry_row(pid, path)
        score_row(row, cfg)
        db.upsert(conn, row)
        conn.commit()
        new.append(row)
    print(f"  SARP: nowych konkursów: {len(new)}", file=sys.stderr)
    return new


def fetch_pz(conn, cfg) -> list[dict]:
    """platformazakupowa.pl: profile wybranych gmin + kilka fraz w wyszukiwarce,
    15 min przerwy między zapytaniami (robots.txt)."""
    new_matches, seen = [], set()
    sources = [(f"profil {slug}", lambda s=slug: pz.organizer(s), org)
               for slug, org in cfg["fetch"]["pz"].get("organizers", {}).items()]
    sources += [(f"'{q}'", lambda q=q: pz.search(q), None) for q in cfg["fetch"]["pz"]["queries"]]
    for label, get, org in sources:
        items = get()
        print(f"  platformazakupowa {label}: {len(items)} ({datetime.now():%H:%M})", file=sys.stderr, flush=True)
        for item in items:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            row = pz.row(item)
            if org:  # profil gminy: znamy zamawiającego i miejscowość
                row.update(org_name=org["name"], org_city=org["city"], province="PL12")
            score_row(row, cfg)
            if db.upsert(conn, row) and row["matched"]:
                new_matches.append(row)
        conn.commit()
    return new_matches


def fetch_bip(conn, cfg) -> list[dict]:
    """BIP-y gmin: nowe artykuły w działach zamówień; szczegóły tylko dla pasujących."""
    known = {r[0] for r in conn.execute("SELECT notice_number FROM notices WHERE notice_type = ?",
                                        (bip.NOTICE_TYPE,))}
    new_matches, total = [], 0
    for unit, city in cfg["fetch"]["bip_units"].items():
        try:
            unit_name, targets = bip.sections(unit)
            for target in targets:
                for item in bip.articles(target):
                    total += 1
                    row = bip.row(item, unit_name, city)
                    if row["notice_number"] in known:
                        continue
                    known.add(row["notice_number"])
                    score_row(row, cfg)
                    if row["matched"]:
                        bip.add_details(row)
                        new_matches.append(row)
                    db.upsert(conn, row)
            conn.commit()
        except (OSError, ValueError, KeyError) as e:
            print(f"  BIP {unit}: błąd {e}", file=sys.stderr)
    print(f"  BIP: {len(cfg['fetch']['bip_units'])} jednostek, {total} artykułów, nowe pasujące: "
          f"{len(new_matches)}", file=sys.stderr)
    return [r for r in new_matches if not r.get("procedure_result")]


def cmd_fetch(args, cfg):
    conn = db.connect(DB_PATH)
    extra = []
    if args.source in ("all", "bip"):
        extra += fetch_bip(conn, cfg)
    if args.source in ("all", "bk"):
        extra += fetch_bk(conn, cfg)
    if args.source in ("all", "sarp"):
        extra += fetch_sarp(conn, cfg)
    if args.source in ("all", "pz"):
        extra += fetch_pz(conn, cfg)
    dups = mark_duplicates(conn)
    extra = [r for r in extra if r["notice_number"] not in dups]
    if args.source not in ("all", "bzp"):
        print(f"Nowe pasujące: {len(extra)}")
        for row in sorted(extra, key=lambda r: -r["score"]):
            print_notice(row)
        return
    bk_matches = extra
    bzp.REQUEST_DELAY = cfg["fetch"].get("request_delay", bzp.REQUEST_DELAY)
    today = date.today()
    days = args.days or cfg["fetch"]["days_back"]
    result_days = cfg["fetch"]["history_days"] if args.history else days
    plan = [
        ("ContractNotice", cfg["fetch"]["cpv_codes"], windows(today - timedelta(days=days), today)),
        ("TenderResultNotice", cfg["fetch"].get("result_cpv_codes", cfg["fetch"]["cpv_codes"]),
         windows(today - timedelta(days=result_days), today)),
    ]
    seen, new_matches = set(), bk_matches
    try:
        for notice_type, codes, wins in plan:
            for cpv in codes:
                for w_from, w_to in wins:
                    key = (notice_type, cpv, w_from.isoformat(), w_to.isoformat())
                    # okna zamknięte w przeszłości pobieramy tylko raz
                    if w_to < today and conn.execute(
                        "SELECT 1 FROM fetch_log WHERE notice_type=? AND cpv=? AND day_from=? AND day_to=?", key
                    ).fetchone():
                        continue
                    while True:
                        try:
                            items = bzp.fetch(notice_type, w_from, w_to, cpv)
                            break
                        except bzp.Blocked:
                            if not args.wait:
                                raise
                            print(f"  403 z WAF – czekam {args.wait} min ({datetime.now():%H:%M})",
                                  file=sys.stderr, flush=True)
                            time.sleep(args.wait * 60)
                    print(f"  {notice_type} {cpv} {w_from}–{w_to}: {len(items)}", file=sys.stderr)
                    for item in items:
                        if item["noticeNumber"] in seen:
                            continue
                        seen.add(item["noticeNumber"])
                        row = bzp.normalize(item)
                        score_row(row, cfg)
                        if db.upsert(conn, row) and row["matched"] and notice_type == "ContractNotice":
                            new_matches.append(row)
                    if w_to < today:
                        conn.execute("INSERT OR IGNORE INTO fetch_log VALUES (?, ?, ?, ?)", key)
                    conn.commit()
    except bzp.Blocked:
        conn.commit()
        print("\n! WAF e-Zamówień zablokował zapytania (403). Postęp zapisany – uruchom ponownie za ~15 min.")
        blocked = True
    else:
        blocked = False
    dups = mark_duplicates(conn)
    new_matches = [r for r in new_matches if r["notice_number"] not in dups]
    print(f"Pobrano {len(seen)} ogłoszeń, nowe pasujące: {len(new_matches)}")
    for row in sorted(new_matches, key=lambda r: -r["score"]):
        print_notice(row)
    if blocked:
        sys.exit(2)


BZP_NUMBER_RE = re.compile(r"(\d{4}/BZP \d{8})")


def mark_duplicates(conn) -> set[str]:
    """Ogłoszenia z innych źródeł, które powtarzają przetarg z BZP (numer BZP w tytule/treści):
    zdejmujemy je z kandydatów – oceniamy i pokazujemy wersję z BZP."""
    dups = set()
    rows = conn.execute(
        f"SELECT notice_number, title, text FROM notices WHERE matched = 1 "
        f"AND notice_type IN {OPEN_TYPES} AND notice_type != 'ContractNotice'"
    ).fetchall()
    for number, title, text in rows:
        m = BZP_NUMBER_RE.search(f"{title} {text or ''}")
        if not m:
            continue
        original = conn.execute(
            "SELECT notice_number FROM notices WHERE notice_type = 'ContractNotice' AND notice_number LIKE ?",
            (f"{m.group(1)}%",),
        ).fetchone()
        if original:
            conn.execute(
                "UPDATE notices SET matched = 0, match_reason = ? WHERE notice_number = ?",
                (f"duplikat {original[0]}", number),
            )
            dups.add(number)
    conn.commit()
    return dups


def cmd_rescore(args, cfg):
    conn = db.connect(DB_PATH)
    rows = conn.execute(f"SELECT * FROM notices WHERE notice_type IN {OPEN_TYPES}").fetchall()
    for r in rows:
        row = dict(r)
        score_row(row, cfg)
        conn.execute(
            "UPDATE notices SET score = ?, matched = ?, match_reason = ? WHERE notice_number = ?",
            (row["score"], row["matched"], row["match_reason"], row["notice_number"]),
        )
    conn.commit()
    dups = mark_duplicates(conn)
    n = conn.execute(f"SELECT count(*) FROM notices WHERE matched = 1 AND notice_type IN {OPEN_TYPES}").fetchone()[0]
    print(f"Przeliczono {len(rows)} ogłoszeń, pasujących: {n} (duplikatów BZP z innych źródeł: {len(dups)})")


def print_notice(row, verdict=None):
    print(f"\n[{row['score']} pkt] {row['title'][:160]}")
    print(f"  {row['org_name']} ({row['org_city']}, {row['province']}) | termin ofert: {local_time(row['deadline'])}")
    print(f"  {row['notice_number']} | {notice.url(row)}")
    print(f"  punkty: {row['match_reason']}")
    if row.get("fit"):
        print(f"  {jev_line(row)}")
    if verdict:
        print(f"  OCENA: {verdict['verdict'].upper()} – {verdict['note'] or ''}")


def jev_line(row) -> str:
    if not row.get("fit"):
        return ""
    conf = f" ({row['fit_conf']:.0%})" if row["fit_conf"] is not None else ""
    return (f"Jev: {row['fit']}{conf}; architektura {row['architecture']:.0%}; "
            f"skala: {jev.SCALE_LABELS[row['scale']]}; warunki do spełnienia {row['conditions_ok']:.0%}")


def open_candidates(conn, include_all=False, include_expired=False, include_reviewed=True):
    """Pasujące = próg punktów albo Jev uznał za warte oferty (łapie nietypowe tytuły)."""
    sql = f"""SELECT n.*, r.verdict, r.note, j.fit, j.fit_conf, j.architecture, j.scale, j.conditions_ok
             FROM notices n
             LEFT JOIN reviews r ON r.notice_number = n.notice_number
             LEFT JOIN jev j ON j.notice_number = n.notice_number
             WHERE n.notice_type IN {OPEN_TYPES}"""
    params = []
    if not include_all:
        sql += " AND (n.matched = 1 OR j.fit = 'tak')"
    if not include_expired:
        no_deadline = " OR ".join(
            "(n.deadline IS NULL AND n.notice_type = ? AND n.published >= ?)" for _ in NO_DEADLINE_DAYS)
        sql += f" AND (n.deadline >= ? OR {no_deadline}) AND COALESCE(n.procedure_result, '') NOT LIKE 'rozstrzygn%'"
        params.append(now_utc())
        for kind, days in NO_DEADLINE_DAYS.items():
            params += [kind, (date.today() - timedelta(days=days)).isoformat()]
    if not include_reviewed:
        sql += " AND r.verdict IS NULL"
    return [dict(r) for r in conn.execute(sql + " ORDER BY n.score DESC, n.deadline", params)]


def cmd_list(args, cfg):
    conn = db.connect(DB_PATH)
    rows = open_candidates(conn, args.all, args.expired)
    if args.verdict:
        rows = [r for r in rows if r["verdict"] == args.verdict]
    for row in rows:
        print_notice(row, row if row["verdict"] else None)
    print(f"\nRazem: {len(rows)}")


def cmd_show(args, cfg):
    conn = db.connect(DB_PATH)
    row = find_notice(conn, args.ref)
    print_notice(row)
    for name, body in notice.sections(row, limit=4000).items():
        print(f"\n## {name}\n{body}")


def print_similar(conn, row, out=print):
    sims = prices.similar(conn, row)
    s = prices.summary([r for _, r in sims])
    if not s:
        out("Brak podobnych rozstrzygnięć w bazie (uruchom: python -m przetargi fetch --history).")
        return
    offers = f", średnio ofert: {s['offers_avg']:.1f}" if s["offers_avg"] else ""
    out(f"Podobne zlecenia ({s['n']}): mediana {prices.zl(s['median'])} brutto, "
        f"zakres {prices.zl(s['min'])} – {prices.zl(s['max'])}{offers}")
    for sim, r in sims:
        out(f"- {prices.zl(r['price_winner'])} | ofert {r['offers'] or '?'} | {r['published'][:10]} | "
            f"{r['province']} | {r['title'][:110]} (podob. {sim:.2f})")


def cmd_similar(args, cfg):
    conn = db.connect(DB_PATH)
    row = find_notice(conn, args.ref)
    print(row["title"])
    print_similar(conn, row)


def cmd_prices(args, cfg):
    conn = db.connect(DB_PATH)
    since = (date.today() - timedelta(days=365)).isoformat()
    sql = """SELECT * FROM notices WHERE notice_type = 'TenderResultNotice'
             AND published >= ? AND price_winner IS NOT NULL"""
    params = [since]
    for word in args.words:
        sql += " AND lower(title) LIKE ?"
        params.append(f"%{word.lower()}%")
    if args.province:
        sql += " AND province = ?"
        params.append(args.province)
    rows = [dict(r) for r in conn.execute(sql + " ORDER BY published DESC", params)]
    for r in rows:
        print(f"\n• {r['title'][:140]}")
        print(f"  {r['org_name']} ({r['province']}) | {r['published'][:10]} | ofert: {r['offers']}")
        print(f"  wygrał: {r['winner']} za {prices.zl(r['price_winner'])} "
              f"(min {prices.zl(r['price_min'])}, max {prices.zl(r['price_max'])})")
    s = prices.summary(rows)
    if s:
        print(f"\n{s['n']} wyników, mediana ceny zwycięzcy: {prices.zl(s['median'])}")
    else:
        print("Brak wyników. Najpierw pobierz historię: python -m przetargi fetch --history")


def cmd_report(args, cfg):
    """Raport kandydatów do oceny w Claude Code (markdown)."""
    conn = db.connect(DB_PATH)
    rows = open_candidates(conn, include_reviewed=args.all)
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"kandydaci-{date.today().isoformat()}.md"
    lines = [f"# Kandydaci do oceny – {date.today().isoformat()}", "", f"Liczba: {len(rows)}", ""]
    for row in rows:
        lines += [
            f"## [{row['score']} pkt] {row['title']}",
            "",
            f"- Numer: {row['notice_number']}",
            f"- Zamawiający: {row['org_name']}, {row['org_city']} ({row['province']})",
            f"- Termin składania ofert: {local_time(row['deadline'])}",
            f"- Link: {notice.url(row)}",
            f"- Punkty: {row['match_reason']}",
        ]
        if row["fit"]:
            lines.append(f"- {jev_line(row)}")
        if row["verdict"]:
            lines.append(f"- Dotychczasowa ocena: {row['verdict']} – {row['note'] or ''}")
        for name, body in notice.sections(row).items():
            lines += ["", f"**{name}:** {body}"]
        lines.append("")
        print_similar(conn, row, out=lines.append)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} kandydatów -> {path}")


def cmd_jev(args, cfg):
    if not os.environ.get("JEV_API_KEY"):
        sys.exit("Brak JEV_API_KEY w .env")
    conn = db.connect(DB_PATH)
    ok, bad = jev.assess_pending(conn, args.limit)
    print(f"Jev ocenił {ok} ogłoszeń" + (f", niepoprawnych odpowiedzi: {bad}" if bad else ""))
    for verdict in ("tak", "moze", "nie"):
        n = conn.execute("SELECT count(*) FROM jev WHERE fit = ?", (verdict,)).fetchone()[0]
        print(f"  {verdict}: {n}")


def notice_card(row) -> str:
    """Karta przetargu do Telegrama (HTML); każda linia zamyka swoje tagi."""
    e = html.escape
    lines = [f"<b>[{row['score']} pkt] {e(row['title'][:200])}</b>",
             e(f"{row['org_name'] or ''}{', ' + row['org_city'] if row['org_city'] else ''}"),
             f"Termin: {e(local_time(row['deadline']))}" if row["deadline"] else "Termin: w ogłoszeniu"]
    if row.get("fit"):
        lines.append(f"<i>{e(jev_line(row))}</i>")
    lines.append(f'<a href="{e(notice.url(row))}">{e(row["notice_number"])}</a>')
    return "\n".join(lines)


def cmd_daily(args, cfg):
    """Automat: pobierz źródła (bez platformazakupowa – osobne zadanie), Jev, powiadomienie o nowych."""
    conn = db.connect(DB_PATH)
    problems = []
    for name, fn in (("BIP", fetch_bip), ("Baza Konkurencyjności", fetch_bk), ("SARP", fetch_sarp)):
        try:
            fn(conn, cfg)
        except (OSError, ValueError, KeyError) as e:
            problems.append(f"{name}: {e}")
    try:
        cmd_fetch(argparse.Namespace(source="bzp", days=None, history=False, wait=None), cfg)
    except SystemExit:
        problems.append("BZP: blokada WAF – dokończy się przy następnym uruchomieniu")
    except (OSError, ValueError) as e:
        problems.append(f"BZP: {e}")
    mark_duplicates(conn)
    if os.environ.get("JEV_API_KEY"):
        try:
            jev.assess_pending(conn)
        except OSError as e:
            problems.append(f"Jev: {e}")

    done = {r[0] for r in conn.execute("SELECT notice_number FROM notified")}
    new = [r for r in open_candidates(conn, include_reviewed=False) if r["notice_number"] not in done]
    if not new and not problems:
        print("Brak nowych przetargów.")
        return
    text = f"🏗 <b>Nowe przetargi: {len(new)}</b>\nOcena: /przetargi w Claude Code"
    if new:
        text += "\n\n" + "\n\n".join(notice_card(r) for r in new)
    if problems:
        text += "\n\n⚠️ " + "\n⚠️ ".join(html.escape(p) for p in problems)
    if args.dry_run or not telegram.configured():
        print(text if args.dry_run else "Brak TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID w .env:\n" + text)
        return
    telegram.send(text)
    now = datetime.now().isoformat(timespec="seconds")
    conn.executemany("INSERT OR IGNORE INTO notified VALUES (?, ?)", [(r["notice_number"], now) for r in new])
    conn.commit()
    print(f"Wysłano powiadomienie: {len(new)} przetargów")


def cmd_review(args, cfg):
    conn = db.connect(DB_PATH)
    row = find_notice(conn, args.ref)
    conn.execute(
        "INSERT OR REPLACE INTO reviews VALUES (?, ?, ?, ?)",
        (row["notice_number"], args.verdict, args.note, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    print(f"{row['notice_number']}: {args.verdict}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="przetargi")
    p.add_argument("--config", type=Path, default=ROOT / "config.toml")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="pobierz ogłoszenia z BZP i przefiltruj")
    f.add_argument("--days", type=int, help="ile dni wstecz (domyślnie z config.toml)")
    f.add_argument("--history", action="store_true", help="pobierz też rok ogłoszeń o wyniku (ceny)")
    f.add_argument("--wait", type=int, metavar="MIN", help="po blokadzie WAF odczekaj MIN minut i wznów")
    f.add_argument("--source", choices=["all", "bzp", "bk", "pz", "sarp", "bip"], default="all",
                   help="bzp = e-Zamówienia, bk = Baza Konkurencyjności, pz = platformazakupowa.pl "
                        "(wolne: 15 min między zapytaniami), sarp = konkursy SARP, bip = BIP-y gmin")

    sub.add_parser("rescore", help="przelicz punkty po zmianie config.toml (bez sieci)")

    j = sub.add_parser("jev", help="wstępna ocena otwartych przetargów modelem Jev")
    j.add_argument("--limit", type=int, help="maks. liczba zapytań w tym uruchomieniu")

    l = sub.add_parser("list", help="pokaż pasujące, otwarte przetargi")
    l.add_argument("--all", action="store_true", help="także poniżej progu punktów")
    l.add_argument("--expired", action="store_true", help="także po terminie składania ofert")
    l.add_argument("--verdict", choices=["tak", "moze", "nie"], help="tylko z daną oceną")

    s = sub.add_parser("show", help="szczegóły ogłoszenia (opis, warunki, kryteria)")
    s.add_argument("ref", help="numer ogłoszenia lub jego fragment, np. 00506260")

    si = sub.add_parser("similar", help="ceny podobnych rozstrzygniętych przetargów")
    si.add_argument("ref")

    pr = sub.add_parser("prices", help="ceny z rozstrzygniętych przetargów (12 mies.)")
    pr.add_argument("words", nargs="*", help="słowa w przedmiocie zamówienia")
    pr.add_argument("--province", help="np. PL12")

    r = sub.add_parser("report", help="raport kandydatów do oceny (markdown)")
    r.add_argument("--all", action="store_true", help="także już ocenione")

    rv = sub.add_parser("review", help="zapisz ocenę przetargu")
    rv.add_argument("ref")
    rv.add_argument("verdict", choices=["tak", "moze", "nie"])
    rv.add_argument("note", nargs="?", default="")

    d = sub.add_parser("daily", help="automat: pobierz, Jev, powiadom na Telegram o nowych")
    d.add_argument("--dry-run", action="store_true", help="tylko pokaż wiadomość, nie wysyłaj")

    args = p.parse_args()
    load_env(ROOT / ".env")
    cfg = load_config(args.config)
    commands = {
        "fetch": cmd_fetch, "rescore": cmd_rescore, "jev": cmd_jev, "list": cmd_list, "show": cmd_show,
        "similar": cmd_similar, "prices": cmd_prices, "report": cmd_report, "review": cmd_review,
        "daily": cmd_daily,
    }
    commands[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
