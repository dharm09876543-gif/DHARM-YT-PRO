"""Telegram alert (optional). TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID na ho to chup-chaap skip.
Alert fail hone se upload kabhi nahi rukta."""
from __future__ import annotations

import os

import httpx

from src.utils.logging import get_logger, redact

log = get_logger("dharm_yt.alerts")


def send_alert(message: str, client: httpx.Client | None = None) -> bool:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    try:
        cl = client or httpx.Client(timeout=15)
        r = cl.post(f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": f"DHARM YT PRO\n{message}"[:4000]})
        return r.status_code == 200
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram alert nahi gaya: %s", redact(str(e)).replace(token, "***"))
        return False
