"""Scraper Lambda：EventBridge Scheduler 每 4 小時觸發。

流程：讀 prefs → 組 URL → 爬 591 → dedup → 推 Telegram。
"""

from __future__ import annotations

import logging
import os
import time

from app._ssm import get_telegram_token
from app.core import telegram
from app.core.filters import build_url
from app.core.prefs import get_prefs, update_prefs
from app.core.scraper import scrape
from app.core.seen import mark_seen

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_PAGES = int(os.environ.get("MAX_PAGES", "5"))
DIGEST_BATCH = 5      # 每則訊息塞幾筆
NEW_ITEM_CAP = 25     # 單次掃描最多推幾筆，超過顯示 overflow 訊息


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def handler(event, context):  # noqa: ARG001
    prefs = get_prefs()
    chat_id = prefs.get("chat_id")
    enabled = prefs.get("enabled", True)
    is_first_scan = prefs.get("last_scan_at") is None

    if not chat_id:
        logger.info("還沒有 chat_id，跳過")
        return {"status": "no_chat_id"}

    if not enabled:
        logger.info("使用者已暫停，跳過")
        return {"status": "paused"}

    url = build_url(prefs)
    logger.info("Scraping URL: %s", url)

    start = time.time()
    listings = scrape(url, max_pages=MAX_PAGES)
    elapsed = time.time() - start
    logger.info("抓到 %d 筆（耗時 %.1fs）", len(listings), elapsed)

    token = get_telegram_token()

    # dedup：未見過的存進 new_items，已見過跳過
    new_items: list[dict] = []
    for item in listings:
        if not item.get("id"):
            continue
        if mark_seen(item["id"]):
            new_items.append(item)

    summary = f"本次新增 {len(new_items)} 筆 / 總 {len(listings)} 筆 / first_scan={is_first_scan}"
    logger.info(summary)

    if is_first_scan:
        # 第一次掃：不推 listings，只送基準資料訊息
        if new_items:
            telegram.send_message(
                token, chat_id,
                f"🌱 已建立 {len(new_items)} 筆基準資料，下次掃描起會推送新物件。",
                parse_mode=None,
            )
        else:
            telegram.send_message(
                token, chat_id,
                "⚠️ 沒抓到任何物件，可能 591 反爬或條件太嚴格。",
                parse_mode=None,
            )
    elif new_items:
        # 之後的掃描：digest 模式，cap 上限
        to_send = new_items[:NEW_ITEM_CAP]
        overflow = len(new_items) - len(to_send)
        for chunk in _chunks(to_send, DIGEST_BATCH):
            try:
                telegram.send_message(token, chat_id, telegram.format_digest(chunk))
            except Exception as e:  # noqa: BLE001
                logger.warning("digest 推送失敗: %s", e)
            time.sleep(0.5)  # 友善 Telegram per-chat rate limit (1 msg/s)
        if overflow > 0:
            telegram.send_message(
                token, chat_id,
                f"... 還有 {overflow} 筆新物件，建議收緊條件（按 📋 看條件）",
                parse_mode=None,
            )
    elif event.get("notify_when_empty"):
        # /run 觸發時即便 0 筆也要回報
        telegram.send_message(
            token, chat_id,
            f"⏰ 本次掃描無新物件（共看了 {len(listings)} 筆）",
            parse_mode=None,
        )

    # 更新 last_scan_at（只在成功抓到東西時更新，避免反爬 0 筆讓「first scan」標記提早消失）
    if listings:
        update_prefs({"last_scan_at": int(time.time())})

    return {
        "status": "ok",
        "scanned": len(listings),
        "new": len(new_items),
        "is_first_scan": is_first_scan,
        "elapsed_seconds": round(elapsed, 1),
    }


if __name__ == "__main__":
    import json
    result = handler({}, None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
