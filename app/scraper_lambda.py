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
from app.core.prefs import get_prefs
from app.core.scraper import scrape
from app.core.seen import mark_seen

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_PAGES = int(os.environ.get("MAX_PAGES", "5"))


def handler(event, context):  # noqa: ARG001
    prefs = get_prefs()
    chat_id = prefs.get("chat_id")
    enabled = prefs.get("enabled", True)

    if not chat_id:
        logger.info("還沒有 chat_id（使用者尚未對 bot 發過任何訊息），跳過")
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

    new_count = 0
    for item in listings:
        if not item.get("id"):
            continue
        if not mark_seen(item["id"]):
            continue  # 已見過
        new_count += 1
        try:
            telegram.send_message(token, chat_id, telegram.format_listing(item))
        except Exception as e:  # noqa: BLE001
            logger.warning("Telegram 傳送失敗 (id=%s): %s", item["id"], e)

    summary = f"本次新增 {new_count} 筆 / 總 {len(listings)} 筆"
    logger.info(summary)

    if new_count == 0 and event.get("notify_when_empty"):
        telegram.send_message(token, chat_id, f"⏰ 本次掃描無新物件（共看了 {len(listings)} 筆）")

    return {
        "status": "ok",
        "scanned": len(listings),
        "new": new_count,
        "elapsed_seconds": round(elapsed, 1),
    }


if __name__ == "__main__":
    # 本機測試用：python -m app.scraper_lambda
    import json

    result = handler({}, None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
