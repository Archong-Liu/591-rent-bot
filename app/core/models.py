"""Shared listing shape used across the scraper, dedup store, and Telegram formatters."""

from __future__ import annotations

from typing import TypedDict


class Listing(TypedDict, total=False):
    id: str
    listing_id: str
    title: str
    type: str
    tags: list[str]
    price: str
    area: str
    floor: str
    district: str
    agent: str
    updated: str
    link: str
    first_seen_at: int
    last_seen_at: int
    ttl: int
