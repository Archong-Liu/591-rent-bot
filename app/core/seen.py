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
