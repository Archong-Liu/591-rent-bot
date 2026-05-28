"""rent_seen DynamoDB 去重表。"""

from __future__ import annotations

import os
import time
from decimal import Decimal

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


def mark_seen(listing_id: str, ttl_days: int = DEFAULT_TTL_DAYS) -> bool:
    """如果是新物件回 True、寫入；如果已存在回 False。"""
    now = int(time.time())
    ttl = now + ttl_days * 86400
    try:
        _get_table().put_item(
            Item={
                "listing_id": str(listing_id),
                "first_seen_at": Decimal(now),
                "ttl": Decimal(ttl),
            },
            ConditionExpression="attribute_not_exists(listing_id)",
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def clear_seen() -> int:
    """清空整張 rent_seen 表，回傳刪除筆數。供 /reset 使用。"""
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
