"""rent_seen DynamoDB 去重 + 完整 listing 儲存 + 存活刷新。

mark_seen() 第一次見到寫入完整 item；之後每次見到刷新 last_seen_at 與
TTL，達成「物件下架 N 天後自動過期」的時效性保留。
list_recent() 只回傳最近仍確認在架的物件。
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get("SEEN_TABLE", "rent_seen")

# 物件「消失後」幾天從 DB 刪除（持續在架者每次掃描會刷新 TTL，不會被刪）
LISTING_TTL_DAYS = int(os.environ.get("LISTING_TTL_DAYS", "7"))
# /list 只顯示最近幾天內仍確認在架的物件
FRESH_WINDOW_DAYS = int(os.environ.get("FRESH_WINDOW_DAYS", "3"))

_table = None


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _table


def _serialize(value: Any) -> Any:
    """DynamoDB 不收 float / 純 None list；轉成它能存的型別。"""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_serialize(v) for v in value if v is not None]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items() if v is not None}
    return value


def mark_seen(item: dict, ttl_days: int = LISTING_TTL_DAYS) -> bool:
    """第一次見到回 True 並寫入完整 item；已見過回 False 但刷新存活時間。

    item 必須含 'id'。其餘欄位（title, price, …）一併存進去供 /list 顯示。
    無論新舊都會把 last_seen_at / ttl 推到「現在 + ttl_days」，
    所以持續出現的物件不會過期，消失的物件會在 ttl_days 後被 DynamoDB TTL 刪掉。
    """
    listing_id = str(item.get("id") or item.get("listing_id") or "")
    if not listing_id:
        return False

    now = int(time.time())
    ttl = now + ttl_days * 86400

    record = {
        "listing_id": listing_id,
        "first_seen_at": Decimal(now),
        "last_seen_at": Decimal(now),
        "ttl": Decimal(ttl),
    }
    for k, v in item.items():
        if k in ("id", "listing_id"):
            continue
        if v in (None, ""):
            continue
        record[k] = _serialize(v)

    try:
        _get_table().put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(listing_id)",
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # 已見過：刷新存活時間（last_seen_at + ttl），不重複通知
        _get_table().update_item(
            Key={"listing_id": listing_id},
            UpdateExpression="SET last_seen_at = :now, #ttl = :ttl",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":now": Decimal(now), ":ttl": Decimal(ttl)},
        )
        return False


def _scan_all() -> list[dict]:
    table = _get_table()
    items: list[dict] = []
    kwargs: dict = {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _seen_ts(item: dict) -> int:
    """取 last_seen_at，舊資料沒有就退回 first_seen_at。"""
    return int(item.get("last_seen_at") or item.get("first_seen_at") or 0)


def list_recent(
    offset: int = 0,
    limit: int = 5,
    fresh_within_days: int = FRESH_WINDOW_DAYS,
) -> tuple[list[dict], int]:
    """回傳 (這頁 items, 符合新鮮度的總筆數)。

    只保留最近 fresh_within_days 天內仍確認在架的物件，按 last_seen_at 由新到舊。
    fresh_within_days <= 0 表示不過濾（顯示全部）。
    """
    all_items = _scan_all()
    if fresh_within_days > 0:
        cutoff = int(time.time()) - fresh_within_days * 86400
        all_items = [x for x in all_items if _seen_ts(x) >= cutoff]
    all_items.sort(key=_seen_ts, reverse=True)
    return all_items[offset:offset + limit], len(all_items)


def clear_seen() -> int:
    """清空整張 rent_seen 表，回傳刪除筆數。"""
    table = _get_table()
    deleted = 0
    scan_kwargs = {"ProjectionExpression": "listing_id"}
    while True:
        resp = table.scan(**scan_kwargs)
        with table.batch_writer() as batch:
            for item in resp.get("Items", []):
                batch.delete_item(Key={"listing_id": item["listing_id"]})
                deleted += 1
        if "LastEvaluatedKey" not in resp:
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return deleted
