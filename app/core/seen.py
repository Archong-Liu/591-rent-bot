"""rent_seen DynamoDB dedup + full listing storage + liveness refresh, per user.

mark_seen() writes the full item dict the first time a (user, listing) pair
is seen; every time after that it refreshes last_seen_at and the TTL, giving
listings a "delisted -> auto-expires after N days" retention policy.
list_recent() only returns listings confirmed present recently.

Table key is (user_id hash, listing_id range): each user's dedup/liveness
state is independent, and a `Query` scoped to one user_id is far cheaper
than the full-table `Scan` this used before user accounts existed.
"""

from __future__ import annotations

import functools
import os
import time
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app.core.models import Listing

# "rent_seen" is only a local-dev fallback; the deployed table is actually
# named "rent-scraper-seen" (see infra/dynamodb.tf) and is always supplied
# via the SEEN_TABLE env var in both Lambdas. A missing env var here is
# exactly what caused a past production AccessDenied bug (SEEN_TABLE wasn't
# wired into the webhook Lambda, so it silently fell back to this name).
TABLE_NAME = os.environ.get("SEEN_TABLE", "rent_seen")

# Days after a listing *disappears* before it's deleted from the table
# (listings still live get their TTL refreshed on every scan, so they never hit this).
LISTING_TTL_DAYS = int(os.environ.get("LISTING_TTL_DAYS", "7"))
# /list only shows listings confirmed live within this many days. With a
# once-daily scan, 2 tolerates exactly one missed/failed scan before a
# still-live listing would be treated as stale.
FRESH_WINDOW_DAYS = int(os.environ.get("FRESH_WINDOW_DAYS", "2"))


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


def mark_seen(user_id: str, item: Listing, ttl_days: int = LISTING_TTL_DAYS) -> bool:
    """Return True and store the full item on first sighting for this user;
    return False (without re-notifying) on subsequent sightings, but still
    refresh liveness.

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
        "user_id": user_id,
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
            Key={"user_id": user_id, "listing_id": listing_id},
            UpdateExpression="SET last_seen_at = :now, #ttl = :ttl",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":now": Decimal(now), ":ttl": Decimal(ttl)},
        )
        return False


def _query_user(user_id: str) -> list[Listing]:
    table = _get_table()
    items: list[Listing] = []
    kwargs: dict = {"KeyConditionExpression": Key("user_id").eq(user_id)}
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _seen_ts(item: Listing) -> int:
    """Return last_seen_at, falling back to first_seen_at for older records."""
    return int(item.get("last_seen_at") or item.get("first_seen_at") or 0)


def _price_value(item: Listing) -> int | None:
    """Parse the listing's price string; None for missing/non-numeric (e.g. "面議")."""
    try:
        return int(item.get("price") or "")
    except (ValueError, TypeError):
        return None


SORT_KEYS = ("recent", "price", "price_desc")


def _sort_items(items: list[Listing], sort_by: str) -> list[Listing]:
    if sort_by == "price" or sort_by == "price_desc":
        descending = sort_by == "price_desc"

        def key(item: Listing):
            price = _price_value(item)
            # Unknown price always sorts last, regardless of direction.
            if price is None:
                return (1, 0)
            return (0, -price if descending else price)

        return sorted(items, key=key)
    return sorted(items, key=_seen_ts, reverse=True)


def list_recent(
    user_id: str,
    offset: int = 0,
    limit: int = 5,
    fresh_within_days: int = FRESH_WINDOW_DAYS,
    sort_by: str = "recent",
) -> tuple[list[Listing], int]:
    """Return (this page's items, total count matching the freshness filter)
    for one user.

    Only keeps listings confirmed live within the last fresh_within_days days.
    sort_by is one of SORT_KEYS: "recent" (default, last_seen_at descending),
    "price" (cheapest first), or "price_desc" (most expensive first); listings
    with an unparseable price (e.g. "面議") always sort last.
    fresh_within_days <= 0 disables the freshness filter (shows everything).
    """
    all_items = _query_user(user_id)
    if fresh_within_days > 0:
        cutoff = int(time.time()) - fresh_within_days * 86400
        all_items = [x for x in all_items if _seen_ts(x) >= cutoff]
    all_items = _sort_items(all_items, sort_by)
    return all_items[offset:offset + limit], len(all_items)


def clear_seen(user_id: str) -> int:
    """Wipe one user's rows from rent_seen; returns the number of items deleted."""
    table = _get_table()
    deleted = 0
    kwargs: dict = {
        "KeyConditionExpression": Key("user_id").eq(user_id),
        "ProjectionExpression": "user_id, listing_id",
    }
    while True:
        resp = table.query(**kwargs)
        with table.batch_writer() as batch:
            for item in resp.get("Items", []):
                batch.delete_item(Key={"user_id": item["user_id"], "listing_id": item["listing_id"]})
                deleted += 1
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return deleted
