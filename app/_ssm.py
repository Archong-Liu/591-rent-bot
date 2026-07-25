"""Shared SSM Parameter Store helper (with a module-level cache)."""

from __future__ import annotations

import os

import boto3

_ssm = None
_cache: dict[str, str] = {}


def get_parameter(name: str, with_decryption: bool = True) -> str:
    """Read an SSM parameter, cached across invocations so only a cold start hits SSM."""
    if name in _cache:
        return _cache[name]

    global _ssm
    if _ssm is None:
        _ssm = boto3.client("ssm")

    resp = _ssm.get_parameter(Name=name, WithDecryption=with_decryption)
    value = resp["Parameter"]["Value"]
    _cache[name] = value
    return value


def get_telegram_token() -> str:
    return get_parameter(os.environ["SSM_TELEGRAM_TOKEN"])
