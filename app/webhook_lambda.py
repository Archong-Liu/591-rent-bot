"""Webhook Lambda：處理 Telegram bot 指令。

由 Lambda Function URL 觸發（HTTP POST，body 是 Telegram update JSON）。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Callable

import boto3

from app._ssm import get_telegram_token
from app.core import telegram
from app.core.filters import (
    KIND_CODE_TO_NAME,
    SECTION_ID_TO_NAME,
    describe_prefs,
    normalize_district,
    normalize_kind,
)
from app.core.prefs import clear_filters, get_prefs, update_prefs
from app.core.seen import clear_seen

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SCRAPER_FN_NAME = os.environ.get("SCRAPER_FN_NAME", "")
_lambda = None


def _invoke_scraper_async() -> None:
    global _lambda
    if _lambda is None:
        _lambda = boto3.client("lambda")
    _lambda.invoke(
        FunctionName=SCRAPER_FN_NAME,
        InvocationType="Event",
        Payload=json.dumps({"notify_when_empty": True}).encode(),
    )


# -- 指令 handlers --------------------------------------------------------


def cmd_start(args: list[str], chat_id: int) -> str:
    update_prefs({"chat_id": chat_id})
    prefs = get_prefs()
    return (
        "👋 哈囉！我是台北 591 租屋通知 bot。\n"
        "每 4 小時自動掃描符合你篩選的新物件，並推到這裡。\n\n"
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
        "/reset - 清空 dedup 重新建立基準\n\n"
        f"{describe_prefs(prefs)}"
    )


def cmd_filters(args: list[str], chat_id: int) -> str:
    return describe_prefs(get_prefs())


def cmd_set_price(args: list[str], chat_id: int) -> str:
    if len(args) != 2:
        return "用法：/set_price <min> <max>，例如 /set_price 15000 30000"
    try:
        pmin, pmax = int(args[0]), int(args[1])
    except ValueError:
        return "min/max 必須是整數"
    update_prefs({"price_min": pmin, "price_max": pmax, "chat_id": chat_id})
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
    update_prefs({"sections": ids, "chat_id": chat_id})
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
    update_prefs({"kinds": codes, "chat_id": chat_id})
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
    update_prefs({"area_min": amin, "area_max": amax, "chat_id": chat_id})
    return f"✅ 已設坪數 {amin} ~ {amax} 坪"


def cmd_set_pattern(args: list[str], chat_id: int) -> str:
    if not args:
        return "用法：/set_pattern 1 2"
    try:
        patterns = [int(x) for x in args]
    except ValueError:
        return "格局必須是整數，例如 /set_pattern 1 2"
    update_prefs({"patterns": patterns, "chat_id": chat_id})
    return f"✅ 已設格局：{', '.join(f'{p}房' for p in patterns)}"


def cmd_clear(args: list[str], chat_id: int) -> str:
    update_prefs({"chat_id": chat_id})
    clear_filters()
    return "✅ 已清除所有篩選條件"


def cmd_pause(args: list[str], chat_id: int) -> str:
    update_prefs({"enabled": False, "chat_id": chat_id})
    return "⏸ 已暫停通知。輸入 /resume 恢復。"


def cmd_resume(args: list[str], chat_id: int) -> str:
    update_prefs({"enabled": True, "chat_id": chat_id})
    return "▶️ 已恢復通知。"


def cmd_run(args: list[str], chat_id: int) -> str:
    update_prefs({"chat_id": chat_id})
    if not SCRAPER_FN_NAME:
        return "❌ Scraper Lambda 名稱未設定（環境變數 SCRAPER_FN_NAME）"
    try:
        _invoke_scraper_async()
    except Exception as e:  # noqa: BLE001
        return f"❌ 觸發失敗：{e}"
    return "🚀 已觸發掃描，新物件會陸續推送到這裡。"


def cmd_reset(args: list[str], chat_id: int) -> str:
    update_prefs({"chat_id": chat_id, "last_scan_at": None})
    n = clear_seen()
    return (
        f"♻️ 已清除 {n} 筆 dedup 紀錄，下次掃描會重新建立基準資料。\n"
        "（不會推送 listings，只送一則「已建立基準資料」）"
    )


COMMANDS: dict[str, Callable[[list[str], int], str]] = {
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
}


# -- entry point ----------------------------------------------------------


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

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"statusCode": 200, "body": "ok"}

    text = (message.get("text") or "").strip()
    chat_id = message["chat"]["id"]

    # 將快捷按鈕文字（例如「📋 看條件」）轉成對應的 slash command
    text = telegram.BUTTON_TO_COMMAND.get(text, text)

    # 取出指令（去掉 @botname suffix）
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
