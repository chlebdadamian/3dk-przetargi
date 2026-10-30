"""Powiadomienia WhatsApp przez CallMeBot (darmowe, tylko na własny numer).

Aktywacja: dodaj do kontaktów numer bota z https://www.callmebot.com/blog/free-api-whatsapp-messages/,
wyślij mu „I allow callmebot to send me messages” – odpisze kluczem API.

WHATSAPP_PHONE    Twój numer z kierunkowym, np. +48600123456
WHATSAPP_APIKEY   klucz od CallMeBot
"""

import os
import re
import time
import urllib.parse
import urllib.request
from html import unescape

from .telegram import split_message

API_URL = "https://api.callmebot.com/whatsapp.php"
MAX_LEN = 1500  # tekst idzie w URL-u, więc krótsze części niż w Telegramie
SEND_DELAY = 5.0  # CallMeBot kolejkuje wiadomości; nie zasypujemy go


def from_html(text: str) -> str:
    """HTML Telegrama -> formatowanie WhatsApp (*pogrubienie*, _kursywa_, link jako goły adres)."""
    text = re.sub(r'<a href="([^"]*)">(.*?)</a>', lambda m: f"{m.group(2)}\n{unescape(m.group(1))}", text)
    text = re.sub(r"</?b>", "*", text)
    text = re.sub(r"</?i>", "_", text)
    return unescape(re.sub(r"<[^>]+>", "", text))


def configured() -> bool:
    return bool(os.environ.get("WHATSAPP_PHONE") and os.environ.get("WHATSAPP_APIKEY"))


def send(text: str) -> None:
    """Przyjmuje ten sam tekst co telegram.send (HTML)."""
    for i, part in enumerate(split_message(from_html(text), MAX_LEN)):
        if i:
            time.sleep(SEND_DELAY)
        query = urllib.parse.urlencode({"phone": os.environ["WHATSAPP_PHONE"], "text": part,
                                        "apikey": os.environ["WHATSAPP_APIKEY"]})
        body = urllib.request.urlopen(f"{API_URL}?{query}", timeout=60).read().decode("utf-8", "replace")
        if "APIKey is invalid" in body:
            raise OSError(f"CallMeBot: {re.sub(r'<[^>]+>', ' ', body).strip()[:200]}")
