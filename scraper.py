"""591 台北租屋本機 CLI。

雲端 Lambda 不會走這支；它只是本機測試 / 備援的入口。
核心邏輯在 app/core/scraper.py。
"""

from __future__ import annotations

import argparse
import os
import smtplib
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd

from app.core.scraper import BASE_URL, scrape


def save_csv(listings: list[dict], path: str | None = None) -> str:
    if not listings:
        print("沒有資料可存")
        return ""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = path or f"taipei_rent_{timestamp}.csv"
    df = pd.DataFrame(listings)
    df.drop_duplicates(subset=["id"], inplace=True)
    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(lambda xs: " / ".join(xs) if isinstance(xs, list) else xs)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"已存至 {path}（{len(df)} 筆）")
    return path


def send_email(csv_path: str, recipient: str, smtp_user: str, smtp_password: str, count: int):
    subject = f"台北租屋資訊 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    body = f"附件共 {count} 筆台北租屋資訊（591 租屋網）。"

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with open(csv_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename={os.path.basename(csv_path)}",
    )
    msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient, msg.as_string())
    print(f"已寄信至 {recipient}")


def main():
    parser = argparse.ArgumentParser(description="591 台北租屋爬蟲（本機 CLI）")
    parser.add_argument("--url", type=str, default=f"{BASE_URL}/list?region=1", help="591 列表 URL")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--all", action="store_true", help="爬所有頁")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--show-browser", action="store_true")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--smtp-user", type=str, default=None)
    parser.add_argument("--smtp-password", type=str, default=None)
    parser.add_argument("--recipient", type=str, default="archong.futurenest@gmail.com")
    args = parser.parse_args()

    max_pages = 9999 if args.all else args.max_pages
    print(f"開始爬取 {args.url}，最多 {max_pages} 頁…")
    listings = scrape(args.url, max_pages=max_pages, headless=not args.show_browser)
    print(f"共 {len(listings)} 筆")
    csv_path = save_csv(listings, args.output)

    if args.email and csv_path:
        smtp_user = args.smtp_user or os.environ.get("SMTP_USER")
        smtp_password = args.smtp_password or os.environ.get("SMTP_PASSWORD")
        if not smtp_user or not smtp_password:
            print("寄信失敗：請提供 --smtp-user 和 --smtp-password（或 SMTP_USER / SMTP_PASSWORD）")
            return
        send_email(csv_path, args.recipient, smtp_user, smtp_password, len(listings))


if __name__ == "__main__":
    main()
