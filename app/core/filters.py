"""將使用者 prefs 轉成 591 列表頁 URL。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlencode

LIST_URL = "https://rent.591.com.tw/list"
TAIPEI_REGION_ID = "1"

# 591 房屋類型代碼
KIND_NAME_TO_CODE: dict[str, str] = {
    "整層": "1",
    "整層住家": "1",
    "套房": "2",
    "獨立套房": "2",
    "分租": "3",
    "分租套房": "3",
    "雅房": "4",
}
KIND_CODE_TO_NAME = {"1": "整層", "2": "套房", "3": "分租", "4": "雅房"}

_SECTIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "taipei_sections.json"


def _load_sections() -> dict[str, str]:
    if not _SECTIONS_FILE.exists():
        return {}
    return json.loads(_SECTIONS_FILE.read_text(encoding="utf-8"))


SECTION_NAME_TO_ID = _load_sections()
SECTION_ID_TO_NAME = {v: k for k, v in SECTION_NAME_TO_ID.items()}


def normalize_district(name: str) -> str | None:
    """把使用者輸入正規化為 section_id；不認得回 None。"""
    name = name.strip().rstrip("區")
    return SECTION_NAME_TO_ID.get(name)


def normalize_kind(name: str) -> str | None:
    return KIND_NAME_TO_CODE.get(name.strip())


def build_url(prefs: dict) -> str:
    """根據 prefs dict 組 591 列表 URL。

    支援的 prefs key：sections, kinds, price_min, price_max,
    area_min, area_max, patterns
    """
    params: list[tuple[str, str]] = [("region", TAIPEI_REGION_ID)]

    sections = prefs.get("sections") or []
    if sections:
        params.append(("section", ",".join(str(s) for s in sections)))

    kinds = prefs.get("kinds") or []
    if kinds:
        params.append(("kind", ",".join(str(k) for k in kinds)))

    pmin = prefs.get("price_min")
    pmax = prefs.get("price_max")
    if pmin is not None or pmax is not None:
        params.append(("rentprice", f"{pmin or ''},{pmax or ''}"))

    amin = prefs.get("area_min")
    amax = prefs.get("area_max")
    if amin is not None or amax is not None:
        params.append(("area", f"{amin or ''},{amax or ''}"))

    patterns = prefs.get("patterns") or []
    if patterns:
        params.append(("pattern", ",".join(str(p) for p in patterns)))

    return f"{LIST_URL}?{urlencode(params, safe=',')}"


def describe_prefs(prefs: dict) -> str:
    """把 prefs 轉成人類可讀字串，用於 Telegram /filters 回覆。"""
    lines = ["📋 目前篩選條件"]

    sections = prefs.get("sections") or []
    if sections:
        names = [SECTION_ID_TO_NAME.get(str(s), str(s)) for s in sections]
        lines.append(f"行政區: {', '.join(names)}")
    else:
        lines.append("行政區: 不限")

    kinds = prefs.get("kinds") or []
    if kinds:
        names = [KIND_CODE_TO_NAME.get(str(k), str(k)) for k in kinds]
        lines.append(f"類型: {', '.join(names)}")
    else:
        lines.append("類型: 不限")

    pmin, pmax = prefs.get("price_min"), prefs.get("price_max")
    if pmin or pmax:
        lines.append(f"租金: {pmin or '0'} ~ {pmax or '∞'} 元/月")
    else:
        lines.append("租金: 不限")

    amin, amax = prefs.get("area_min"), prefs.get("area_max")
    if amin or amax:
        lines.append(f"坪數: {amin or '0'} ~ {amax or '∞'} 坪")
    else:
        lines.append("坪數: 不限")

    patterns = prefs.get("patterns") or []
    if patterns:
        lines.append(f"格局: {', '.join(f'{p}房' for p in patterns)}")
    else:
        lines.append("格局: 不限")

    enabled = prefs.get("enabled", True)
    lines.append(f"狀態: {'✅ 啟用' if enabled else '⏸ 暫停'}")

    return "\n".join(lines)
