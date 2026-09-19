# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A 591 (Taipei rentals) scraper that runs daily on AWS, filters listings per user, and pushes new matches through a Telegram bot. Filters are configured from inside Telegram. See `README.md` for user-facing docs and `docs/DESIGN.md` for the rationale behind defaults (scan cadence, retention windows, packaging choices).

## Commands

```bash
# Local setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-cli.txt
python3 -m playwright install chromium

# Run the scraper locally (CSV output; no AWS needed)
python3 scrape_cli.py --max-pages 1
python3 -m app.core.scraper "https://rent.591.com.tw/list?region=1" 2   # raw JSON, no CSV/pandas

# Full deploy: build+push scraper image, build webhook zip, terraform apply
./scripts/deploy.sh
./scripts/put_secrets.sh    # one-time: write Telegram token into SSM
./scripts/set_webhook.sh    # one-time: register webhook with Telegram

# Infra-only change (no code change)
cd infra && terraform apply

# Re-scrape 591's district section_id mapping into app/data/taipei_sections.json
python3 scripts/refresh_sections.py

# Logs
aws logs tail /aws/lambda/rent-scraper-scraper --follow --region ap-northeast-1
aws logs tail /aws/lambda/rent-scraper-webhook --follow --region ap-northeast-1
```

There is **no test suite and no linter config**. Verification is manual: run the CLI locally for scraper-parsing changes, and deploy + exercise the bot in Telegram for webhook changes. CI (`.github/workflows/`) only runs CodeQL and tfsec — neither builds or runs the app.

## Architecture

Two Lambdas share one `app/core/` library but are packaged, permissioned, and deployed differently:

| | Scraper Lambda | Webhook Lambda |
|---|---|---|
| Trigger | EventBridge Scheduler (daily noon, Asia/Taipei) or async `Invoke` from `/run` | API Gateway HTTP API `POST /webhook` |
| Package | Container image (`Dockerfile` → ECR) — Playwright/Chromium can't fit a zip | Zip (`scripts/build_webhook_zip.sh`) |
| Entry | `app/scraper_lambda.py:handler` | `app/webhook_lambda.py:handler` |
| Deps | `requirements.txt` | `requirements-webhook.txt` (boto3 + requests only) |

State lives in two DynamoDB tables: `rent-scraper-prefs` (hash `user_id`, one row per Telegram chat) and `rent-scraper-seen` (hash `user_id`, range `listing_id`, TTL-expired).

### Multi-tenancy invariant

`user_id` is always `str(chat_id)`. Every prefs/seen access must be scoped to it — there is no global state. The scraper loops `list_all_prefs()` sequentially in one invocation; one user's failure is caught and must not abort the rest (`_scan_one_user` is wrapped per-user in `handler`).

Multi-tenancy is deliberately **invisible to users** — no bot copy mentions accounts, other users, or registration. Every webhook command calls `update_prefs({"chat_id": chat_id}, ...)` so simply using the bot registers the chat.

### Cross-cutting things to update together

- **Adding a DynamoDB call** → also widen the matching inline policy in `infra/iam.tf`. The two roles have deliberately narrow, non-overlapping action sets (scraper: Scan/Put/Update; webhook: Get/Update/Query/BatchWriteItem). A missing action fails only at runtime in CloudWatch, not at deploy — this has shipped as a bug before.
- **Adding a bot command** → `COMMANDS` dict in `app/webhook_lambda.py`, the `/start` help text in `cmd_start`, optionally `QUICK_KEYBOARD` + `BUTTON_TO_COMMAND` in `app/core/telegram.py`, and the command tables in **both** `README.md` and `docs/README.zh-TW.md`.
- **Adding a tunable constant** → most exist twice: as an env-var-read module constant (`MAX_PAGES`, `LISTING_TTL_DAYS`, `FRESH_WINDOW_DAYS`) and as a Terraform variable in `infra/variables.tf` wired through the Lambda `environment` block. Change both or the deployed value won't move.
- **Bumping `playwright` in `requirements.txt`** → bump the `mcr.microsoft.com/playwright/python:v<X>-jammy` tag in `Dockerfile` to match.

## Non-obvious behaviors

- **Table-name env vars are load-bearing.** `prefs.py`/`seen.py` fall back to `rent_prefs`/`rent_seen`, which are *not* the deployed table names (`rent-scraper-*`). A Lambda missing `PREFS_TABLE`/`SEEN_TABLE` silently targets a nonexistent table and fails with AccessDenied. Keep the fallbacks; don't rely on them.
- **`update_prefs` semantics:** a value of `None` or `[]` emits `REMOVE` (this is how `/clear` works). Lists of all-int or all-str become DynamoDB **sets** — order is not preserved, so never depend on `sections`/`kinds`/`patterns` ordering.
- **First scan is silent.** `last_scan_at is None` means seed-only: record everything, push a single "baseline created" message instead of individual listings. `last_scan_at` is only bumped when the scan returned listings, so an anti-bot 0-result scan doesn't falsely consume the first-scan flag. `/reseed` restores this state.
- **`mark_seen()` returns True exactly once per (user, listing)**; every later sighting refreshes `last_seen_at` + TTL instead. This is what makes live listings never expire while delisted ones age out.
- **Command handlers return `str | None`.** Returning `None` means the handler already sent its own messages with custom markup (e.g. `cmd_list`); the entry point then skips the default reply.
- **Two message formats, on purpose:** `format_digest` uses Markdown and must run values through `_escape_markdown`; `format_list_item` is sent with `parse_mode=None` (one message per listing so each URL gets a Telegram link preview) and intentionally does not escape.
- **`time.sleep(0.4–0.5)` between Telegram sends** keeps under the 1 msg/s per-chat rate limit — don't remove when batching.
- **Scraper parsing is positional/heuristic.** 591 doesn't class-tag house type, district, or poster role, so `_parse_item` picks them out of classless spans by pattern. Expect this to break when 591 changes markup; verify against real HTML via `scrape_cli.py`, not by reasoning.
- **Chromium launch flags** (`--single-process --no-sandbox --disable-dev-shm-usage`) are required in Lambda; removing them causes `TargetClosedError`.
- 591 anti-bot returns 419/429 occasionally. The deliberate strategy is graceful return with no retry — the next scheduled scan tries again.

## Conventions

- Code comments and docstrings are **English**; all user-facing bot strings and log messages are **zh-TW**.
- `README.md` (English) and `docs/README.zh-TW.md` are parallel translations — keep in sync. Rationale/trade-off prose belongs in `docs/DESIGN.md`, not the README.
- Terraform state is **local** (`infra/terraform.tfstate`, gitignored). No S3 backend; single-machine deploys only.
- `infra/build/` is gitignored and must be regenerated by `build_webhook_zip.sh` before `terraform apply`, since `archive_file` zips that directory. `deploy.sh` handles this ordering — a bare `terraform apply` after editing `app/` will ship stale webhook code.
