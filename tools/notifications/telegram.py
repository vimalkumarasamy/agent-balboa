import os
import requests

API = "https://api.telegram.org/bot{token}/{method}"


def _token():
    t = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not t:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in .env")
    return t


def send_message(text: str) -> bool:
    """Send a message to the configured Telegram chat. Returns True on success."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID not set in .env — run scripts/telegram_setup.py")
    resp = requests.post(
        API.format(token=_token(), method="sendMessage"),
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
    )
    resp.raise_for_status()
    return True


def get_updates() -> list:
    """Fetch recent messages sent to the bot — used to discover chat_id."""
    resp = requests.get(API.format(token=_token(), method="getUpdates"))
    resp.raise_for_status()
    return resp.json().get("result", [])
