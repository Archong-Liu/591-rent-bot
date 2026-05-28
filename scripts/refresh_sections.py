"""透過 Playwright 點擊每個行政區按鈕，抓出 591 真實的 section_id 映射。

用法： python scripts/refresh_sections.py
輸出： app/data/taipei_sections.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

TAIPEI_DISTRICTS = [
    "大安區", "內湖區", "士林區", "文山區",
    "北投區", "中山區", "信義區", "松山區",
    "萬華區", "中正區", "大同區", "南港區",
]

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "taipei_sections.json"


def main():
    sections: dict[str, str] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
            ),
            locale="zh-TW",
        )
        page = context.new_page()

        for district in TAIPEI_DISTRICTS:
            # 每次都重新載入乾淨的列表頁，避免 filter 累加
            page.goto("https://rent.591.com.tw/list?region=1", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)

            try:
                page.click(f'button:has-text("{district}")', timeout=5000)
                page.wait_for_timeout(1500)
            except Exception as e:  # noqa: BLE001
                print(f"[!] 點擊 {district} 失敗：{e}")
                continue

            m = re.search(r"section=(\d+)", page.url)
            if m:
                sections[district.rstrip("區")] = m.group(1)
                print(f"  {district} → section={m.group(1)}")
            else:
                print(f"[!] {district} 點擊後 URL 沒 section param: {page.url}")

        browser.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(sections, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n寫入 {OUTPUT_PATH}（{len(sections)} 區）")


if __name__ == "__main__":
    main()
