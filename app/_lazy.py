"""Shared lazy-singleton helper for caching a factory's result across warm Lambda invocations."""

from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


def lazy(factory: Callable[[], T]) -> Callable[[], T]:
    """Wrap a zero-arg factory so its result is computed once and cached.

    Usage: `_get_table = lazy(lambda: boto3.resource("dynamodb").Table(NAME))`
    """
    cache: list[T] = []

    def get() -> T:
        if not cache:
            cache.append(factory())
        return cache[0]

    return get
