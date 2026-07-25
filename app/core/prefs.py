"""rent_prefs DynamoDB CRUD (single-user; user_id is hardcoded to "default")."""

from __future__ import annotations

import functools
import os
from decimal import Decimal
from typing import Any

import boto3

DEFAULT_USER_ID = "default"
TABLE_NAME = os.environ.get("PREFS_TABLE", "rent_prefs")


@functools.cache
def _get_table():
    return boto3.resource("dynamodb").Table(TABLE_NAME)


def _from_ddb(item: dict | None) -> dict:
    """Convert a DynamoDB item (with Decimal/Set values) into plain Python types."""
    if not item:
        return {"user_id": DEFAULT_USER_ID, "enabled": True}

    out: dict[str, Any] = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            out[k] = int(v) if v == v.to_integral() else float(v)
        elif isinstance(v, set):
            # DynamoDB SS / NS -> Python list (elements converted to int/str)
            items = list(v)
            if items and all(isinstance(x, Decimal) for x in items):
                out[k] = [int(x) if x == x.to_integral() else float(x) for x in items]
            else:
                out[k] = items
        else:
            out[k] = v
    return out


def get_prefs(user_id: str = DEFAULT_USER_ID) -> dict:
    resp = _get_table().get_item(Key={"user_id": user_id})
    return _from_ddb(resp.get("Item"))


def update_prefs(updates: dict, user_id: str = DEFAULT_USER_ID) -> dict:
    """Partially update prefs; fields not present in `updates` are left untouched.

    Special case: a value of None or an empty list removes that field
    (this is what lets /clear wipe filters).
    """
    if not updates:
        return get_prefs(user_id)

    set_clauses: list[str] = []
    remove_clauses: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {}

    for i, (key, value) in enumerate(updates.items()):
        name_ph = f"#k{i}"
        val_ph = f":v{i}"
        expr_names[name_ph] = key

        if value is None or (isinstance(value, (list, set)) and len(value) == 0):
            remove_clauses.append(name_ph)
            continue

        if isinstance(value, list) and all(isinstance(x, int) for x in value):
            expr_values[val_ph] = set(value)  # NS
        elif isinstance(value, list) and all(isinstance(x, str) for x in value):
            expr_values[val_ph] = set(value)  # SS
        elif isinstance(value, float):
            expr_values[val_ph] = Decimal(str(value))
        else:
            expr_values[val_ph] = value

        set_clauses.append(f"{name_ph} = {val_ph}")

    update_parts: list[str] = []
    if set_clauses:
        update_parts.append("SET " + ", ".join(set_clauses))
    if remove_clauses:
        update_parts.append("REMOVE " + ", ".join(remove_clauses))

    resp = _get_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression=" ".join(update_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values or None,
        ReturnValues="ALL_NEW",
    )
    return _from_ddb(resp.get("Attributes"))


def clear_filters(user_id: str = DEFAULT_USER_ID) -> dict:
    """Clear all filter fields, keeping chat_id and enabled intact."""
    return update_prefs(
        {
            "sections": None,
            "kinds": None,
            "price_min": None,
            "price_max": None,
            "area_min": None,
            "area_max": None,
            "patterns": None,
        },
        user_id=user_id,
    )
