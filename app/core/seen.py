"""rent_seen DynamoDB dedup + full listing storage + liveness refresh.

mark_seen() writes the full item dict the first time a listing is seen;
every time after that it refreshes last_seen_at and the TTL, giving
listings a "delisted -> auto-expires after N days" retention policy.
list_recent() only returns listings confirmed present recently.
"""

from __future__ import annotations

import functools
import os
import time
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.models import Listing

TABLE_NAME = os.environ.get("SEEN_TABLE", "rent_seen")

# Days after a listing *disappears* before it's deleted from the table
# (listings still live get their TTL refreshed on every scan, so they never hit this).
LISTING_TTL_DAYS = int(os.environ.get("LISTING_TTL_DAYS", "7"))
# /list only shows listings confirmed live within this many days.
FRESH_WINDOW_DAYS = int(os.environ.get("FRESH_WINDOW_DAYS", "3"))


@functools.cache
def _get_table():
    return boto3.resource("dynamodb").Table(TABLE_NAME)


def _serialize(value: Any) -> Any:
    """DynamoDB rejects float and bare-None list entries; coerce to storable types."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_serialize(v) for v in value if v is not None]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items() if v is not None}
    return value


def mark_seen(item: Listing, ttl_days: int = LISTING_TTL_DAYS) -> bool:
    """Return True and store the full item on first sighting; return False
    (without re-notifying) on subsequent sightings, but still refresh liveness.

    `item` must have an 'id'. The remaining fields (title, price, ...) are
    stored too so /list can display them.
    Either way, last_seen_at/ttl are pushed to "now + ttl_days", so a listing
    that keeps reappearing never expires, while one that stops appearing gets
    deleted by DynamoDB TTL ttl_days after its last sighting.
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
        # Already seen: refresh liveness (last_seen_at + ttl) without re-notifying.
        _get_table().update_item(
            Key={"listing_id": listing_id},
            UpdateExpression="SET last_seen_at = :now, #ttl = :ttl",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":now": Decimal(now), ":ttl": Decimal(ttl)},
        )
        return False


def _scan_all() -> list[Listing]:
    table = _get_table()
    items: list[Listing] = []
    kwargs: dict = {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _seen_ts(item: Listing) -> int:
    """Return last_seen_at, falling back to first_seen_at for older records."""
    return int(item.get("last_seen_at") or item.get("first_seen_at") or 0)


def list_recent(
    offset: int = 0,
    limit: int = 5,
    fresh_within_days: int = FRESH_WINDOW_DAYS,
) -> tuple[list[Listing], int]:
    """Return (this page's items, total count matching the freshness filter).

    Only keeps listings confirmed live within the last fresh_within_days days,
    sorted by last_seen_at descending.
    fresh_within_days <= 0 disables the filter (shows everything).
    """
    all_items = _scan_all()
    if fresh_within_days > 0:
        cutoff = int(time.time()) - fresh_within_days * 86400
        all_items = [x for x in all_items if _seen_ts(x) >= cutoff]
    all_items.sort(key=_seen_ts, reverse=True)
    return all_items[offset:offset + limit], len(all_items)


def clear_seen() -> int:
    """Wipe the entire rent_seen table; returns the number of items deleted."""
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
