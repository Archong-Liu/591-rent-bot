"""rent_seen DynamoDB 去重 + 完整 listing 儲存。

mark_seen() 存完整 item dict，list_recent() 提供分頁瀏覽。
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get("SEEN_TABLE", "rent_seen")
DEFAULT_TTL_DAYS = 30

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


def mark_seen(item: dict, ttl_days: int = DEFAULT_TTL_DAYS) -> bool:
    """如果是新物件回 True、寫入完整 item；如果已存在回 False。

    item 必須含 'id' 欄位。其他欄位（title, price, area, …）會一併存進去
    供 /list 顯示。
    """
    listing_id = str(item.get("id") or item.get("listing_id") or "")
    if not listing_id:
        return False

    now = int(time.time())
    ttl = now + ttl_days * 86400

    record = {
        "listing_id": listing_id,
        "first_seen_at": Decimal(now),
        "ttl": Decimal(ttl),
    }
    # 把 item 的其餘欄位也寫進去
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
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


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


def list_recent(offset: int = 0, limit: int = 5) -> tuple[list[dict], int]:
    """回傳 (這頁的 items, 總筆數)；items 按 first_seen_at 由新到舊排序。"""
    all_items = _scan_all()
    all_items.sort(key=lambda x: int(x.get("first_seen_at", 0)), reverse=True)
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
