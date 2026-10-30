"""Archiwum ogłoszeń w SQLite."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS notices (
    notice_number    TEXT PRIMARY KEY,
    notice_type      TEXT NOT NULL,
    object_id        TEXT,
    tender_id        TEXT,
    published        TEXT,
    deadline         TEXT,
    title            TEXT,
    order_type       TEXT,
    cpv              TEXT,
    org_name         TEXT,
    org_city         TEXT,
    province         TEXT,
    below_eu         INTEGER,
    procedure_result TEXT,
    text             TEXT,
    estimate         REAL,
    offers           INTEGER,
    price_min        REAL,
    price_max        REAL,
    price_winner     REAL,
    winner           TEXT,
    matched          INTEGER,
    score            INTEGER,
    match_reason     TEXT,
    fetched_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_notices_type_pub ON notices(notice_type, published);
CREATE INDEX IF NOT EXISTS idx_notices_tender ON notices(tender_id);

-- Pobrane już okna dat (żeby pobieranie historii dało się wznowić po blokadzie WAF)
CREATE TABLE IF NOT EXISTS fetch_log (
    notice_type TEXT NOT NULL,
    cpv         TEXT NOT NULL,
    day_from    TEXT NOT NULL,
    day_to      TEXT NOT NULL,
    PRIMARY KEY (notice_type, cpv, day_from, day_to)
);

-- Wstępna ocena modelem Jev (przetargi/jev.py)
CREATE TABLE IF NOT EXISTS jev (
    notice_number TEXT PRIMARY KEY,
    fit           TEXT,
    fit_conf      REAL,
    fit_probs     TEXT,
    architecture  REAL,
    scale         INTEGER,
    conditions_ok REAL,
    model         TEXT,
    assessed_at   TEXT
);

-- Przetargi, o których już poszło powiadomienie (żeby nie powtarzać)
CREATE TABLE IF NOT EXISTS notified (
    notice_number TEXT PRIMARY KEY,
    notified_at   TEXT
);

-- Wysłane przypomnienia o terminie (etap: 3d / 1d)
CREATE TABLE IF NOT EXISTS reminders (
    notice_number TEXT NOT NULL,
    stage         TEXT NOT NULL,
    sent_at       TEXT,
    PRIMARY KEY (notice_number, stage)
);

-- Ocena przetargu (robiona w Claude Code): tak / moze / nie
CREATE TABLE IF NOT EXISTS reviews (
    notice_number TEXT PRIMARY KEY,
    verdict       TEXT NOT NULL,
    note          TEXT,
    reviewed_at   TEXT
);
"""

COLUMNS = [
    "notice_number", "notice_type", "object_id", "tender_id", "published", "deadline",
    "title", "order_type", "cpv", "org_name", "org_city", "province", "below_eu",
    "procedure_result", "text", "estimate", "offers", "price_min", "price_max",
    "price_winner", "winner", "matched", "score", "match_reason", "fetched_at",
]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # kilka procesów naraz (automat, pobieranie w tle, raport): czekamy na blokadę zamiast padać,
    # a WAL pozwala czytać w trakcie zapisu
    conn = sqlite3.connect(path, timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(notices)")}
    if "score" not in cols:
        conn.execute("ALTER TABLE notices ADD COLUMN score INTEGER")
    return conn


def upsert(conn: sqlite3.Connection, row: dict) -> bool:
    """Zapisuje ogłoszenie; zwraca True, jeśli jest nowe."""
    exists = conn.execute(
        "SELECT 1 FROM notices WHERE notice_number = ?", (row["notice_number"],)
    ).fetchone()
    values = [row.get(c) for c in COLUMNS]
    placeholders = ", ".join("?" for _ in COLUMNS)
    conn.execute(f"INSERT OR REPLACE INTO notices ({', '.join(COLUMNS)}) VALUES ({placeholders})", values)
    return exists is None
