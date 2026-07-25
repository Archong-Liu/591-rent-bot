"""One-time migration: move the legacy "default" rent_prefs row to be keyed
by its real Telegram chat_id, now that prefs/seen are scoped per user.

Run this once, after deploying the multi-user code AND after the
rent_seen table has been recreated with its new (user_id, listing_id)
key schema (that recreation wipes all prior dedup history, which is why
this script also resets last_scan_at -- otherwise the next scan would
treat every currently-live listing as "new" and flood the chat instead
of silently reseeding).

Usage: python scripts/migrate_default_user.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.prefs import DEFAULT_USER_ID, delete_prefs, get_prefs, update_prefs  # noqa: E402


def main():
    old = get_prefs(DEFAULT_USER_ID)
    chat_id = old.get("chat_id")

    if not chat_id:
        print("沒有找到 legacy 'default' prefs（或它沒有 chat_id），不需要遷移。")
        return

    new_user_id = str(chat_id)
    existing = get_prefs(new_user_id)
    if existing.get("chat_id"):
        print(f"user_id={new_user_id} 已經有 prefs 資料，不覆寫。請手動確認後再刪除 'default' row。")
        return

    fields = {k: v for k, v in old.items() if k not in ("user_id",)}
    fields["last_scan_at"] = None  # force a silent re-seed (rent_seen history is gone)
    update_prefs(fields, user_id=new_user_id)
    delete_prefs(DEFAULT_USER_ID)

    print(f"已將 'default' 遷移至 user_id={new_user_id}，並重置 last_scan_at（下次掃描會靜默建立基準）。")


if __name__ == "__main__":
    main()
