# 591 Taipei Rent Scraper

Scrapes 591 (Taipei rentals) once a day at noon, filters listings by personal
preferences, and pushes new matches via a Telegram bot. Filters can be
configured directly from within Telegram. Multi-user: anyone who `/start`s
the bot gets their own independent filters, dedup state, and notifications.

[繁體中文 README](docs/README.zh-TW.md)

## Architecture

```
EventBridge Scheduler ─daily at noon (Asia/Taipei)─▶ Scraper Lambda (container/Playwright)
                                       │  loops over every registered user
                                       ├─reads─▶ DynamoDB: rent_prefs (1 row/chat_id)
                                       ├─writes─▶ DynamoDB: rent_seen ((user_id, listing_id) key, liveness-refreshed TTL)
                                       └─sends─▶ Telegram Bot API (per user's own chat_id)
                                                       ▲
                                                       │
Webhook Lambda (Function URL) ◀──/commands── Telegram Bot
       │
       └─writes prefs─▶ DynamoDB: rent_prefs (scoped to the sending chat_id)
```

Deployed on AWS Tokyo (`ap-northeast-1`). Estimated cost < $0.50 USD/month.

Users are processed sequentially in one Scraper Lambda invocation, and each
distinct filter combination needs its own real (anti-bot-paced) Chromium
scrape. That puts a practical ceiling of roughly 10-15 distinct filter
setups per scan cycle (once a day) before the Lambda's 5-minute timeout —
this is a scraping-time limit, not an AWS billing one. Users who happen to
share identical filters currently still each trigger their own separate
scrape; deduplicating scrapes by filter combination would raise this
ceiling further (and reduce 591 anti-bot exposure) but isn't implemented
yet. Moving from every-4-hours to once-daily already cuts total requests
to 591 by 6x, which meaningfully reduces anti-bot exposure on its own.

## Run locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-cli.txt
python3 -m playwright install chromium

# Scrape 1 page, save to CSV
python3 scrape_cli.py --max-pages 1

# Scrape with a filter URL
python3 scrape_cli.py --url "https://rent.591.com.tw/list?region=1&section=3,5&rentprice=15000,30000" --max-pages 2
```

## Cloud deployment

### One-time setup

1. **AWS CLI credentials configured**
   ```bash
   aws configure  # use your personal account's access key
   aws sts get-caller-identity  # confirm the right account
   ```

2. **Docker Desktop running** (needed to build the scraper image)

3. **Terraform >= 1.6 installed**

4. **Create a Telegram Bot**
   - Find `@BotFather` on Telegram
   - `/newbot` → pick a name → get the token (you'll need it below)

### Deploy

```bash
# 1) build & push image, build webhook zip, run terraform apply
./scripts/deploy.sh

# 2) write the Telegram token into SSM Parameter Store
./scripts/put_secrets.sh
# paste the token @BotFather gave you

# 3) register the Telegram webhook
./scripts/set_webhook.sh
```

Once done, send `/start` to your bot on Telegram — you should get a welcome message.

## Telegram commands

| Command | Behavior |
|---|---|
| `/start` | Show welcome message, available commands, current filters |
| `/filters` | View current filter settings |
| `/set_price 15000 30000` | Set rent price range |
| `/set_district 中山 大安 信義` | Set districts (the trailing 「區」 suffix is optional) |
| `/set_kind 套房 整層` | Set listing type (整層／套房／分租／雅房) |
| `/set_area 10 30` | Set floor area range (坪) |
| `/set_pattern 1 2` | Set number of rooms |
| `/clear` | Clear all filters |
| `/pause` / `/resume` | Pause/resume notifications |
| `/run` | Trigger a scan immediately (for testing) |
| `/reset` | Wipe your dedup history so your next scan re-seeds silently |
| `/list [page] [price\|price_desc]` | Page through currently-live listings (5 per page), showing "last confirmed" time. Default sort is most-recently-reconfirmed first; `price`/`price_desc` sort by rent (unparseable prices, e.g. "面議", always sort last). Page and sort can be given in either order, e.g. `/list price 2`. The summary message also carries an inline keyboard (prev/next page, switch sort) so paging doesn't require retyping the command |

The chat's reply keyboard also exposes shortcut buttons (filters / list /
scan now / pause / resume / clear filters / reseed baseline) that map to
the same slash commands.

## Listing retention & freshness

- `mark_seen()` refreshes a listing's `last_seen_at` and TTL every time it's
  re-observed in a scan, so listings still live on 591 never expire.
- Once a listing disappears from 591, it's auto-deleted via DynamoDB TTL
  `LISTING_TTL_DAYS` (default 7) after its last sighting. This is a
  real-world "assume it's rented/delisted after about a week of not
  reappearing" judgment call, not tied to scan frequency, so it didn't need
  to change when the schedule moved to once-daily.
- `/list` only shows listings confirmed present within `FRESH_WINDOW_DAYS`
  (default 2, since the schedule moved to once-daily — this tolerates
  exactly one missed/failed scan, e.g. a 591 anti-bot 419, before a
  still-live listing would incorrectly drop out of `/list`).
- Both windows are tunable via Terraform variables (`listing_ttl_days` /
  `fresh_window_days`) without code changes.
- `NEW_ITEM_CAP` (max listings pushed before an overflow notice) was raised
  from 25 to 40: a once-daily scan accumulates roughly 6x the candidate new
  listings a 4-hourly scan would have seen per run.
- Caveat: liveness refresh only happens for listings within the scanned
  page range (`MAX_PAGES`, default 5 pages/30 listings each). A once-daily
  scan gives listings a full 24h to get pushed past that page range by
  newer postings before the next scan catches them (vs. ~4h before), which
  raises the chance of missing a listing entirely for high-volume
  filters/districts. Fine for narrow per-user filters; raising `MAX_PAGES`
  trades this off against more anti-bot exposure and more per-user
  scraping time within the Lambda timeout (see above), so treat it as a
  "watch and tune if you notice gaps" knob rather than a default to bump
  preemptively.
- Dedup is scoped per user (`rent_seen`'s key is `(user_id, listing_id)`),
  so the same listing can independently be "new" to multiple users with
  different filters.

## Changing the district `section` IDs (if 591 changes them)

```bash
# re-scrape all district section_ids from 591
python3 scripts/refresh_sections.py
# writes app/data/taipei_sections.json — commit and redeploy
./scripts/deploy.sh
```

## Changing the scan schedule

Default is once a day at noon (`cron(0 12 * * ? *)`, `Asia/Taipei`). Edit
`scraper_schedule_expression` in `infra/variables.tf` (an EventBridge Scheduler
`rate(...)` or `cron(...)` expression), then run:

```bash
cd infra && terraform apply
```

## Key file locations

```
app/
├── core/scraper.py          # Playwright scraper core
├── core/filters.py          # prefs → 591 URL
├── core/prefs.py            # DynamoDB rent_prefs CRUD
├── core/seen.py             # DynamoDB rent_seen dedup + liveness refresh
├── core/telegram.py         # Telegram Bot API
├── core/models.py           # Shared `Listing` type
├── scraper_lambda.py        # Scheduled scan entry point
└── webhook_lambda.py        # Telegram webhook entry point

infra/                       # Terraform
scripts/                     # Deploy / ops scripts
scrape_cli.py                # Local CLI entry point
Dockerfile                   # Scraper Lambda image
```

## Notes

- If you deployed this before multi-user support existed, `rent_seen`'s key
  schema changes (`listing_id` → `(user_id, listing_id)`), which forces
  Terraform to destroy and recreate that table — wiping dedup history for
  everyone. After redeploying, run `python3 scripts/migrate_default_user.py`
  once to move the old single "default" row to its real `chat_id` and reset
  `last_scan_at`, so the next scan silently re-seeds instead of blasting
  every currently-live listing as "new".
- `infra/terraform.tfstate` contains AWS resource details, is
  **gitignored**, and should be backed up separately.
- For multi-device deployment or shared use, switch to an S3 backend —
  local state doesn't support that.
- 591's anti-bot occasionally returns 419/429; the current strategy is a
  graceful return without retry (tries again in 4 hours).
