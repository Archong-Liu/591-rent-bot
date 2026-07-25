"""Scraper Lambda: triggered every 4 hours by EventBridge Scheduler.

Flow: for every registered user -> read prefs -> build URL -> scrape 591
-> dedup -> push to Telegram. Users are processed sequentially in one
invocation, so the number of *distinct* filter URLs that fit in the 300s
Lambda timeout (each scrape does several real, anti-bot-paced Chromium
page loads) is the practical ceiling on how many users one scan cycle
can serve -- not Lambda/DynamoDB request quotas.
"""

from __future__ import annotations

import logging
import os
import time

from app.core import telegram
from app.core.filters import build_url
from app.core.models import Listing
from app.core.prefs import list_all_prefs, update_prefs
from app.core.scraper import scrape
from app.core.seen import mark_seen
from app.ssm import get_telegram_token

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_PAGES = int(os.environ.get("MAX_PAGES", "5"))
DIGEST_BATCH = 5      # listings packed into each digest message
# Max listings pushed per scan; excess shown as an overflow notice. A once-daily
# scan accumulates roughly 6x the candidate listings a 4-hourly scan would have
# seen per run, so this is raised from the old 25 to match.
NEW_ITEM_CAP = 40


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _scan_one_user(prefs: dict, token: str, notify_when_empty: bool) -> dict:
    user_id = str(prefs["user_id"])
    chat_id = prefs.get("chat_id")
    enabled = prefs.get("enabled", True)
    is_first_scan = prefs.get("last_scan_at") is None

    if not chat_id:
        logger.info("使用者 %s 還沒有 chat_id，跳過", user_id)
        return {"user_id": user_id, "status": "no_chat_id"}

    if not enabled:
        logger.info("使用者 %s 已暫停，跳過", user_id)
        return {"user_id": user_id, "status": "paused"}

    url = build_url(prefs)
    logger.info("使用者 %s Scraping URL: %s", user_id, url)

    start = time.time()
    listings = scrape(url, max_pages=MAX_PAGES)
    elapsed = time.time() - start
    logger.info("使用者 %s 抓到 %d 筆（耗時 %.1fs）", user_id, len(listings), elapsed)

    # Dedup: unseen listings go into new_items; already-seen ones are skipped.
    new_items: list[Listing] = []
    for item in listings:
        if not item.get("id"):
            continue
        if mark_seen(user_id, item):
            new_items.append(item)

    logger.info(
        "使用者 %s 本次新增 %d 筆 / 總 %d 筆 / first_scan=%s",
        user_id, len(new_items), len(listings), is_first_scan,
    )

    if is_first_scan:
        # First-ever scan: don't push individual listings, just announce the baseline.
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
        # Subsequent scans: digest mode, capped.
        to_send = new_items[:NEW_ITEM_CAP]
        overflow = len(new_items) - len(to_send)
        for chunk in _chunks(to_send, DIGEST_BATCH):
            try:
                telegram.send_message(token, chat_id, telegram.format_digest(chunk))
            except Exception as e:  # noqa: BLE001
                logger.warning("使用者 %s digest 推送失敗: %s", user_id, e)
            time.sleep(0.5)  # stay under Telegram's 1 msg/s per-chat rate limit
        if overflow > 0:
            telegram.send_message(
                token, chat_id,
                f"... 還有 {overflow} 筆新物件，建議收緊條件（按 📋 看條件）",
                parse_mode=None,
            )
    elif notify_when_empty:
        # /run triggers a reply even when the scan finds 0 new listings.
        telegram.send_message(
            token, chat_id,
            f"⏰ 本次掃描無新物件（共看了 {len(listings)} 筆）",
            parse_mode=None,
        )

    # Only bump last_scan_at when the scan actually returned listings, so an
    # anti-bot 0-result scan doesn't prematurely clear the "first scan" flag.
    if listings:
        update_prefs({"last_scan_at": int(time.time())}, user_id=user_id)

    return {
        "user_id": user_id,
        "status": "ok",
        "scanned": len(listings),
        "new": len(new_items),
        "is_first_scan": is_first_scan,
        "elapsed_seconds": round(elapsed, 1),
    }


def handler(event, context):  # noqa: ARG001
    users = list_all_prefs()
    if not users:
        logger.info("目前沒有任何註冊使用者，跳過")
        return {"status": "no_users"}

    token = get_telegram_token()
    notify_when_empty = bool(event.get("notify_when_empty"))

    results = []
    for prefs in users:
        try:
            results.append(_scan_one_user(prefs, token, notify_when_empty))
        except Exception:  # noqa: BLE001
            # One user's scrape/send failure (bad filter, transient network
            # error, ...) must not stop the rest of the users from being scanned.
            logger.exception("使用者 %s 處理失敗，略過", prefs.get("user_id"))
            results.append({"user_id": prefs.get("user_id"), "status": "error"})

    return {"status": "ok", "users_processed": len(results), "results": results}


if __name__ == "__main__":
    import json
    result = handler({}, None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
