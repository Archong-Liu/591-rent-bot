"""591 台北租屋爬蟲核心。

對外提供 `scrape(url, max_pages)` 函式，被 CLI 與 Lambda 共用。
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://rent.591.com.tw"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_RE_PAGE = re.compile(r"page=(\d+)")
_RE_UPDATE = re.compile(r"(分鐘|小時|天|剛剛|昨日).*(更新|瀏覽|前)")


def _parse_item(item_el) -> dict:
    listing_id = item_el.get("data-id", "")

    link_el = item_el.select_one("a.link.v-middle")
    title = link_el.get_text(strip=True) if link_el else ""
    href = link_el.get("href", "") if link_el else ""
    link = href if href.startswith("http") else f"{BASE_URL}{href}"

    tags = [t.get_text(strip=True) for t in item_el.select("span.tag")]

    line_spans = item_el.select("span.line")
    area = line_spans[0].get_text(strip=True) if len(line_spans) > 0 else ""
    floor = line_spans[1].get_text(strip=True) if len(line_spans) > 1 else ""
    updated = next(
        (s.get_text(strip=True) for s in line_spans if _RE_UPDATE.search(s.get_text())),
        "",
    )

    price_el = item_el.select_one("strong.text-26px, strong.font-arial")
    price = price_el.get_text(strip=True).replace(",", "") if price_el else ""

    plain_spans = [
        s.get_text(strip=True)
        for s in item_el.find_all("span", class_=False)
        if s.get_text(strip=True)
    ]
    house_type = plain_spans[0] if plain_spans else ""
    district = next((s for s in plain_spans if re.search(r"[縣市區][-—]", s)), "")
    agent = next(
        (s for s in plain_spans if any(k in s for k in ("仲介", "房東", "管理員"))),
        "",
    )

    return {
        "id": listing_id,
        "title": title,
        "type": house_type,
        "tags": tags,
        "price": price,
        "area": area,
        "floor": floor,
        "district": district,
        "agent": agent,
        "updated": updated,
        "link": link,
    }


def _parse_page_html(html: str) -> tuple[list[dict], int]:
    """回傳 (本頁 listings, total_pages)。"""
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("div", class_="item", attrs={"data-id": True})
    results = [_parse_item(item) for item in items]

    total_pages = 1
    page_links = soup.select('a[href*="page="]')
    nums = [int(m.group(1)) for a in page_links if (m := _RE_PAGE.search(a.get("href", "")))]
    if nums:
        total_pages = max(nums)

    return results, total_pages


def scrape(
    url: str,
    max_pages: int = 5,
    delay_ms: int = 2500,
    headless: bool = True,
) -> list[dict]:
    """爬取 591 列表頁，回傳 listings。

    `url` 必須是已組好的列表 URL（含 region / section / rentprice 等 filter）。
    第一頁就是 url 原樣；後續頁透過附加 &page=N 取得。
    """
    listings: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--single-process",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
            ],
        )
        context = browser.new_context(user_agent=USER_AGENT, locale="zh-TW")
        page = context.new_page()

        for page_num in range(1, max_pages + 1):
            target = url if page_num == 1 else _with_page(url, page_num)
            try:
                page.goto(target, wait_until="networkidle", timeout=30000)
            except Exception as e:  # noqa: BLE001
                print(f"[scraper] 第 {page_num} 頁載入失敗：{e}")
                break

            page.wait_for_timeout(delay_ms)
            items, total_pages = _parse_page_html(page.content())

            if not items:
                break

            listings.extend(items)

            if page_num >= total_pages:
                break

        browser.close()

    return listings


def _with_page(url: str, page_num: int) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}page={page_num}"


if __name__ == "__main__":
    import json
    import sys

    target_url = sys.argv[1] if len(sys.argv) > 1 else f"{BASE_URL}/list?region=1"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    result = scrape(target_url, max_pages=pages)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n共 {len(result)} 筆", file=sys.stderr)
