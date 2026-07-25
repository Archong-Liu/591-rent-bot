"""Webhook Lambda: handles Telegram bot commands.

Triggered by an API Gateway HTTP API route (HTTP POST; body is the
Telegram update JSON).
"""

from __future__ import annotations

import functools
import json
import logging
import os
import time
from typing import Callable

import boto3

from app.core import telegram
from app.core.filters import (
    KIND_CODE_TO_NAME,
    SECTION_ID_TO_NAME,
    describe_prefs,
    normalize_district,
    normalize_kind,
)
from app.core.prefs import clear_filters, get_prefs, update_prefs
from app.core.seen import SORT_KEYS, clear_seen, list_recent
from app.ssm import get_telegram_token

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SCRAPER_FN_NAME = os.environ.get("SCRAPER_FN_NAME", "")


@functools.cache
def _get_lambda_client():
    return boto3.client("lambda")


def _invoke_scraper_async() -> None:
    _get_lambda_client().invoke(
        FunctionName=SCRAPER_FN_NAME,
        InvocationType="Event",
        Payload=json.dumps({"notify_when_empty": True}).encode(),
    )


# -- command handlers -------------------------------------------------------
# Every handler receives the Telegram chat_id and scopes all prefs/seen
# access to str(chat_id) as the user_id, so each chat gets independent
# filters, dedup state, and notifications.


def cmd_start(args: list[str], chat_id: int) -> str:
    user_id = str(chat_id)
    update_prefs({"chat_id": chat_id}, user_id=user_id)
    prefs = get_prefs(user_id)
    return (
        "👋 哈囉！我是台北 591 租屋通知 bot。\n"
        "每天中午自動掃描符合你篩選的新物件，並推到這裡。\n\n"
        "可用指令:\n"
        "/filters - 看目前條件\n"
        "/set_price <min> <max> - 設租金區間\n"
        "/set_district <區1> <區2> ... - 設行政區（不加「區」字也可）\n"
        "/set_kind <整層|套房|分租|雅房>... - 設房屋類型\n"
        "/set_area <min> <max> - 設坪數\n"
        "/set_pattern <n>... - 設房數\n"
        "/clear - 清除所有篩選\n"
        "/pause | /resume - 暫停/恢復通知\n"
        "/run - 立即觸發一次掃描\n"
        "/reset - 清空 dedup 重新建立基準\n"
        "/list [page] [price|price_desc] - 翻頁看已抓到的物件（5 筆/頁），可依價格排序\n\n"
        f"{describe_prefs(prefs)}"
    )


def cmd_filters(args: list[str], chat_id: int) -> str:
    return describe_prefs(get_prefs(str(chat_id)))


def cmd_set_price(args: list[str], chat_id: int) -> str:
    if len(args) != 2:
        return "用法：/set_price <min> <max>，例如 /set_price 15000 30000"
    try:
        pmin, pmax = int(args[0]), int(args[1])
    except ValueError:
        return "min/max 必須是整數"
    update_prefs({"price_min": pmin, "price_max": pmax, "chat_id": chat_id}, user_id=str(chat_id))
    return f"✅ 已設租金 {pmin} ~ {pmax} 元/月"


def cmd_set_district(args: list[str], chat_id: int) -> str:
    if not args:
        return "用法：/set_district 中山 大安 信義"
    ids: list[str] = []
    unknown: list[str] = []
    for name in args:
        sid = normalize_district(name)
        if sid:
            ids.append(sid)
        else:
            unknown.append(name)
    if not ids:
        return f"無法識別任何行政區：{', '.join(unknown)}"
    update_prefs({"sections": ids, "chat_id": chat_id}, user_id=str(chat_id))
    names = [SECTION_ID_TO_NAME[i] for i in ids]
    msg = f"✅ 已設行政區：{', '.join(names)}"
    if unknown:
        msg += f"\n⚠️ 無法識別：{', '.join(unknown)}"
    return msg


def cmd_set_kind(args: list[str], chat_id: int) -> str:
    if not args:
        return "用法：/set_kind 套房 整層"
    codes: list[str] = []
    unknown: list[str] = []
    for name in args:
        code = normalize_kind(name)
        if code:
            codes.append(code)
        else:
            unknown.append(name)
    if not codes:
        return f"無法識別任何類型：{', '.join(unknown)}"
    update_prefs({"kinds": codes, "chat_id": chat_id}, user_id=str(chat_id))
    names = [KIND_CODE_TO_NAME[c] for c in codes]
    msg = f"✅ 已設類型：{', '.join(names)}"
    if unknown:
        msg += f"\n⚠️ 無法識別：{', '.join(unknown)}"
    return msg


def cmd_set_area(args: list[str], chat_id: int) -> str:
    if len(args) != 2:
        return "用法：/set_area <min> <max>，例如 /set_area 10 30"
    try:
        amin, amax = int(args[0]), int(args[1])
    except ValueError:
        return "min/max 必須是整數"
    update_prefs({"area_min": amin, "area_max": amax, "chat_id": chat_id}, user_id=str(chat_id))
    return f"✅ 已設坪數 {amin} ~ {amax} 坪"


def cmd_set_pattern(args: list[str], chat_id: int) -> str:
    if not args:
        return "用法：/set_pattern 1 2"
    try:
        patterns = [int(x) for x in args]
    except ValueError:
        return "格局必須是整數，例如 /set_pattern 1 2"
    update_prefs({"patterns": patterns, "chat_id": chat_id}, user_id=str(chat_id))
    return f"✅ 已設格局：{', '.join(f'{p}房' for p in patterns)}"


def cmd_clear(args: list[str], chat_id: int) -> str:
    user_id = str(chat_id)
    update_prefs({"chat_id": chat_id}, user_id=user_id)
    clear_filters(user_id=user_id)
    return "✅ 已清除所有篩選條件"


def cmd_pause(args: list[str], chat_id: int) -> str:
    update_prefs({"enabled": False, "chat_id": chat_id}, user_id=str(chat_id))
    return "⏸ 已暫停通知。輸入 /resume 恢復。"


def cmd_resume(args: list[str], chat_id: int) -> str:
    update_prefs({"enabled": True, "chat_id": chat_id}, user_id=str(chat_id))
    return "▶️ 已恢復通知。"


def cmd_run(args: list[str], chat_id: int) -> str:
    update_prefs({"chat_id": chat_id}, user_id=str(chat_id))
    if not SCRAPER_FN_NAME:
        return "❌ Scraper Lambda 名稱未設定（環境變數 SCRAPER_FN_NAME）"
    try:
        _invoke_scraper_async()
    except Exception as e:  # noqa: BLE001
        return f"❌ 觸發失敗：{e}"
    return "🚀 已觸發掃描（會重新掃描所有已註冊使用者），新物件會陸續推送到這裡。"


_SORT_SUMMARY_LABEL = {"price": "｜依價格由低到高排序", "price_desc": "｜依價格由高到低排序"}


def _send_list_page(user_id: str, chat_id: int, page: int, sort_by: str, token: str) -> str | None:
    """Send one page of /list results: one message per listing (for URL
    previews) plus a final summary message carrying the pagination/sort
    inline keyboard.

    Returns an error string for the caller to send normally (nothing to
    page through); otherwise sends everything itself and returns None.
    """
    PAGE_SIZE = 5
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE

    items, total = list_recent(user_id, offset=offset, limit=PAGE_SIZE, sort_by=sort_by)
    if total == 0:
        return "目前 dedup 表沒有任何資料，按 🚀 立刻掃 開始記錄。"
    if not items:
        last_page = (total - 1) // PAGE_SIZE + 1
        return f"已沒有第 {page} 頁（總共 {last_page} 頁）。輸入 /list 1 從頭看。"

    last_page = (total - 1) // PAGE_SIZE + 1

    # Send one message per listing so each URL gets its own Telegram preview thumbnail.
    for i, item in enumerate(items, start=offset + 1):
        try:
            telegram.send_message(
                token,
                chat_id,
                telegram.format_list_item(item, index=i),
                parse_mode=None,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("/list 推送 item %s 失敗: %s", item.get("listing_id"), e)
        time.sleep(0.4)  # stay under Telegram's 1 msg/s per-chat rate limit

    summary = f"📑 第 {page} / {last_page} 頁（共 {total} 筆）{_SORT_SUMMARY_LABEL.get(sort_by, '')}"
    telegram.send_message(
        token,
        chat_id,
        summary,
        parse_mode=None,
        reply_markup=telegram.build_list_keyboard(page, last_page, sort_by),
    )
    return None


def cmd_list(args: list[str], chat_id: int) -> str | None:
    """Parse /list's args (page and sort, either order, e.g. /list 2 price)
    and delegate to _send_list_page.
    """
    user_id = str(chat_id)
    update_prefs({"chat_id": chat_id}, user_id=user_id)

    page, sort_by = 1, "recent"
    for arg in args:
        if arg in SORT_KEYS:
            sort_by = arg
            continue
        try:
            page = int(arg)
        except ValueError:
            return "用法：/list [page] [price|price_desc]"

    return _send_list_page(user_id, chat_id, page, sort_by, get_telegram_token())


def handle_list_callback(chat_id: int, data: str, token: str) -> None:
    """Handle a tap on /list's inline keyboard. data is "list:{page}:{sort_by}"."""
    try:
        _, page_str, sort_by = data.split(":", 2)
        page = int(page_str)
    except ValueError:
        logger.warning("無法解析 /list callback_data: %s", data)
        return
    if sort_by not in SORT_KEYS:
        logger.warning("/list callback_data 帶未知 sort_by: %s", data)
        return
    _send_list_page(str(chat_id), chat_id, page, sort_by, token)


def cmd_reset(args: list[str], chat_id: int) -> str:
    user_id = str(chat_id)
    update_prefs({"chat_id": chat_id, "last_scan_at": None}, user_id=user_id)
    n = clear_seen(user_id)
    return (
        f"♻️ 已清除 {n} 筆 dedup 紀錄，下次掃描會重新建立基準資料。\n"
        "（不會推送 listings，只送一則「已建立基準資料」）"
    )


COMMANDS: dict[str, Callable[[list[str], int], str | None]] = {
    "/start": cmd_start,
    "/help": cmd_start,
    "/filters": cmd_filters,
    "/set_price": cmd_set_price,
    "/set_district": cmd_set_district,
    "/set_kind": cmd_set_kind,
    "/set_area": cmd_set_area,
    "/set_pattern": cmd_set_pattern,
    "/clear": cmd_clear,
    "/pause": cmd_pause,
    "/resume": cmd_resume,
    "/run": cmd_run,
    "/reset": cmd_reset,
    "/list": cmd_list,
}


# -- entry point -------------------------------------------------------------


def handler(event, context):  # noqa: ARG001
    body_raw = event.get("body", "{}")
    if event.get("isBase64Encoded"):
        import base64
        body_raw = base64.b64decode(body_raw).decode("utf-8")

    try:
        update = json.loads(body_raw)
    except json.JSONDecodeError:
        logger.warning("非 JSON body")
        return {"statusCode": 200, "body": "ok"}

    # Inline-keyboard button press (e.g. /list's pagination/sort buttons),
    # a distinct Telegram update type from a regular text message.
    callback_query = update.get("callback_query")
    if callback_query:
        token = get_telegram_token()
        data = callback_query.get("data", "")
        chat_id = callback_query["message"]["chat"]["id"]
        try:
            if data.startswith("list:"):
                handle_list_callback(chat_id, data, token)
        except Exception:  # noqa: BLE001
            logger.exception("callback_query 處理失敗: %s", data)
        try:
            telegram.answer_callback_query(token, callback_query["id"])
        except Exception as e:  # noqa: BLE001
            logger.exception("answerCallbackQuery 失敗：%s", e)
        return {"statusCode": 200, "body": "ok"}

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"statusCode": 200, "body": "ok"}

    text = (message.get("text") or "").strip()
    chat_id = message["chat"]["id"]

    # Map a quick-keyboard button label (e.g. "📋 看條件") to its slash command.
    text = telegram.BUTTON_TO_COMMAND.get(text, text)

    # Extract the command (strip any @botname suffix, used in group chats).
    parts = text.split()
    if not parts or not parts[0].startswith("/"):
        reply = "輸入 /start 查看可用指令。"
    else:
        cmd = parts[0].split("@", 1)[0].lower()
        args = parts[1:]
        handler_fn = COMMANDS.get(cmd)
        if handler_fn is None:
            reply = "不認識的指令，輸入 /start 查看用法。"
        else:
            try:
                reply = handler_fn(args, chat_id)
            except Exception as e:  # noqa: BLE001
                logger.exception("指令 %s 處理失敗", cmd)
                reply = f"❌ 處理失敗：{e}"

    # reply is None when the handler already sent its own message(s) with a
    # custom reply_markup (e.g. cmd_list's inline pagination keyboard).
    if reply is not None:
        try:
            token = get_telegram_token()
            telegram.send_message(
                token,
                chat_id,
                reply,
                parse_mode=None,
                reply_markup=telegram.QUICK_KEYBOARD,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("回覆 Telegram 失敗：%s", e)

    return {"statusCode": 200, "body": "ok"}
