"""Lightweight Telegram Bot API client."""

from __future__ import annotations

import os
import time

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


# --- Reply keyboard: shortcut buttons for common actions ---

QUICK_KEYBOARD = {
    "keyboard": [
        ["📋 看條件", "📑 看清單", "🚀 立刻掃"],
        ["⏸ 暫停", "▶️ 恢復"],
        ["🗑 清除條件", "♻️ 重新建立基準"],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}

# Button label -> the slash command it maps to.
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
    """Combine several listings into one compact Markdown message (one line each)."""

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
    """Format a single scraped listing as a Telegram Markdown message."""

    def esc(s: str) -> str:
        # Telegram Markdown v1 treats _ * [ ] as special; escape only those.
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


def _relative_time(epoch: int) -> str:
    """epoch seconds -> "just now" / "X hours ago" / "X days ago" (in zh-TW)."""
    if not epoch:
        return ""
    diff = int(time.time()) - int(epoch)
    if diff < 3600:
        return "剛剛"
    if diff < 86400:
        return f"{diff // 3600} 小時前"
    return f"{diff // 86400} 天前"


def format_list_item(item: dict, index: int = 0) -> str:
    """Format one listing as plain text, with the URL on its own last line so
    Telegram renders a link preview for it."""
    listing_id = item.get("listing_id") or item.get("id", "?")
    title = (item.get("title") or "(無詳細資料)")[:40]
    price = item.get("price", "?")
    area = item.get("area", "")
    floor = item.get("floor", "")
    district = (item.get("district") or "").split("-")[0]
    house_type = item.get("type", "")
    link = item.get("link") or f"https://rent.591.com.tw/{listing_id}"

    seen_ts = int(item.get("last_seen_at") or item.get("first_seen_at") or 0)
    seen_rel = _relative_time(seen_ts)

    prefix = f"{index}. " if index else ""
    parts = [district, house_type, f"{price}元", area, floor]
    head = "｜".join(p for p in parts if p)
    tail = f"\n🕒 最後確認 {seen_rel}" if seen_rel else ""
    return f"{prefix}{head}\n{title}{tail}\n{link}"
