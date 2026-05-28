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
    reply_markup: dict | None = None,
) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    resp = requests.post(_bot_url(token, "sendMessage"), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


# --- Reply keyboard 常用功能按鈕 ---

QUICK_KEYBOARD = {
    "keyboard": [
        ["📋 看條件", "📑 看清單", "🚀 立刻掃"],
        ["⏸ 暫停", "▶️ 恢復"],
        ["🗑 清除條件", "♻️ 重新建立基準"],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}

# 按鈕文字 → 對應的 slash command
BUTTON_TO_COMMAND = {
    "📋 看條件": "/filters",
    "📑 看清單": "/list",
    "🚀 立刻掃": "/run",
    "⏸ 暫停": "/pause",
    "▶️ 恢復": "/resume",
    "🗑 清除條件": "/clear",
    "♻️ 重新建立基準": "/reset",
}


def set_webhook(token: str, url: str) -> dict:
    resp = requests.post(_bot_url(token, "setWebhook"), json={"url": url}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def format_digest(items: list[dict]) -> str:
    """把多筆 listing 合成一則精簡 Markdown 訊息（每筆一行）。"""

    def esc(s: str) -> str:
        for ch in ("_", "*", "[", "]"):
            s = s.replace(ch, f"\\{ch}")
        return s

    lines = [f"🆕 *{len(items)} 筆新物件*", ""]
    for i, item in enumerate(items, 1):
        district = esc(item.get("district", "").split("-")[0] or "?")
        house_type = esc(item.get("type", ""))
        price = item.get("price", "?")
        area = esc(item.get("area", ""))
        title = esc((item.get("title") or "(無標題)")[:25])
        link = item.get("link", "")
        lines.append(
            f"{i}. {district}｜{house_type}｜{price}元｜{area}\n   {title}\n   {link}"
        )
    return "\n".join(lines)


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
