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
Design rationale and trade-offs (scan cadence, the multi-user scraping
ceiling, retention tuning, packaging choices) live in
[docs/DESIGN.md](docs/DESIGN.md), not here.

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
| `/price 15000 30000` | Set rent price range |
| `/district 中山 大安 信義` | Set districts (the trailing 「區」 suffix is optional) |
| `/kind 套房 整層` | Set listing type (整層／套房／分租／雅房) |
| `/area 10 30` | Set floor area range (坪) |
| `/pattern 1 2` | Set number of rooms |
| `/clear` | Clear all filters |
| `/pause` / `/resume` | Pause/resume notifications |
| `/run` | Trigger a scan immediately (may take a few minutes) |
| `/reseed` | Wipe your history so your next scan re-seeds silently |
| `/list [page] [price\|price_desc]` | Page through currently-live listings (5 per page), showing "last confirmed" time. Default sort is most-recently-reconfirmed first; `price`/`price_desc` sort by rent (unparseable prices, e.g. "面議", always sort last). Page and sort can be given in either order, e.g. `/list price 2`. The summary message also carries an inline keyboard (prev/next page, switch sort) so paging doesn't require retyping the command |

The chat's reply keyboard also exposes shortcut buttons (filters / list /
scan now / pause / resume / clear filters / reseed baseline) that map to
the same slash commands.

## Listing retention & freshness

- `mark_seen()` refreshes a listing's `last_seen_at` and TTL every time it's
  re-observed in a scan, so listings still live on 591 never expire.
- `LISTING_TTL_DAYS` (default 7): days after a listing disappears before
  it's auto-deleted via DynamoDB TTL.
- `FRESH_WINDOW_DAYS` (default 2): `/list` only shows listings confirmed
  present within this many days.
- Both are tunable via Terraform variables (`listing_ttl_days` /
  `fresh_window_days`) without code changes.
- `NEW_ITEM_CAP` (40): max listings pushed per scan before switching to an
  overflow notice. `MAX_PAGES` (5): pages scraped per scan.
- Dedup is scoped per user (`rent_seen`'s key is `(user_id, listing_id)`),
  so the same listing can independently be "new" to multiple users with
  different filters.

See [docs/DESIGN.md](docs/DESIGN.md) for the reasoning behind these defaults.

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

- `infra/terraform.tfstate` contains AWS resource details, is
  **gitignored**, and should be backed up separately.
- For multi-device deployment or shared use, switch to an S3 backend —
  local state doesn't support that.
- 591's anti-bot occasionally returns 419/429; the current strategy is a
  graceful return without retry (tries again on the next scheduled scan).
- Upgrading from a pre-multi-user deployment? See the migration note in
  [docs/DESIGN.md](docs/DESIGN.md).
