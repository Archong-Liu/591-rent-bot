"""Telegram Bot API 輕量客戶端。"""

from __future__ import annotations

import os

import requests

API_BASE = "https://api.telegram.org"


def _bot_url(token: str, method: str) -> str:
    return f"{API_BASE}/bot{token}/{method}"


def send_message(
    token: str,
    chat_id: int | str,
    text: str,
    parse_mode: str | None = "Markdown",
    disable_web_page_preview: bool = False,
) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    resp = requests.post(_bot_url(token, "sendMessage"), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def set_webhook(token: str, url: str) -> dict:
    resp = requests.post(_bot_url(token, "setWebhook"), json={"url": url}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def format_listing(item: dict) -> str:
    """把 scraper 回來的物件格式化成 Telegram Markdown 訊息。"""

    def esc(s: str) -> str:
        # Telegram Markdown v1 對 _ * [ ] 敏感；只轉這些
        for ch in ("_", "*", "[", "]"):
            s = s.replace(ch, f"\\{ch}")
        return s

    title = esc(item.get("title", "(無標題)"))
    price = item.get("price", "?")
    area = item.get("area", "")
    floor = item.get("floor", "")
    house_type = item.get("type", "")
    district = item.get("district", "")
    link = item.get("link", "")

    parts = [
        f"🏠 *{title}*",
        f"💰 {price} 元/月  |  📐 {esc(area)}  |  🏢 {esc(floor)}",
        f"🏘 {esc(house_type)}  |  📍 {esc(district)}",
        f"🔗 {link}",
    ]
    return "\n".join(parts)
