"""Powiadomienia Telegram (Bot API), jak w traderxtb/src/indextrading/notify/telegram.py.

TELEGRAM_BOT_TOKEN  z @BotFather
TELEGRAM_CHAT_ID    id czatu (napisz do bota, potem https://api.telegram.org/bot<TOKEN>/getUpdates)
"""

import json
import os
import urllib.request

MAX_LEN = 4096  # limit długości wiadomości Telegrama


def split_message(text: str, limit: int = MAX_LEN) -> list[str]:
    """Dzieli między blokami (pusta linia), żeby karta przetargu i jej tagi HTML były w jednej wiadomości."""
    parts, current = [], ""
    for block in text.split("\n\n"):
        block += "\n\n"
        if current and len(current) + len(block) > limit:
            parts.append(current)
            current = ""
        while len(block) > limit:
            parts.append(block[:limit])
            block = block[limit:]
        current += block
    if current.strip():
        parts.append(current)
    return [p.strip() for p in parts]


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def send(text: str) -> None:
    """Wysyła w trybie HTML (<b>, <i>, <a href>)."""
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    for part in split_message(text):
        body = json.dumps({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": part,
                           "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
