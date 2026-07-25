# Design notes

Rationale behind non-obvious defaults and trade-offs in this project. For
what the project does and how to run it, see the [README](../README.md).

## Scan cadence and the multi-user scraping ceiling

Users are processed sequentially in one Scraper Lambda invocation, and each
distinct filter combination needs its own real (anti-bot-paced) Chromium
scrape. That puts a practical ceiling of roughly 10-15 distinct filter
setups per scan cycle (once a day) before the Lambda's 5-minute timeout —
this is a scraping-time limit, not an AWS billing one. Users who happen to
share identical filters currently still each trigger their own separate
scrape; deduplicating scrapes by filter combination would raise this
ceiling further (and reduce 591 anti-bot exposure) but isn't implemented
yet.

Scanning once a day (rather than more frequently) also keeps total
requests to 591 low, which helps limit anti-bot exposure on its own.

## Listing retention & freshness

- `mark_seen()` refreshes a listing's `last_seen_at` and TTL every time it's
  re-observed in a scan, so listings still live on 591 never expire.
- Once a listing disappears from 591, it's auto-deleted via DynamoDB TTL
  `LISTING_TTL_DAYS` (default 7) after its last sighting. This is a
  real-world "assume it's rented/delisted after about a week of not
  reappearing" judgment call, independent of scan frequency.
- `/list` only shows listings confirmed present within `FRESH_WINDOW_DAYS`
  (default 2) — this tolerates exactly one missed/failed scan (e.g. a 591
  anti-bot 419) before a still-live listing would incorrectly drop out of
  `/list`.
- `NEW_ITEM_CAP` (40) caps how many listings get pushed before switching to
  an overflow notice; kept generous since a once-a-day scan cadence lets
  more candidate new listings accumulate between runs than a more frequent
  cadence would.
- Caveat: liveness refresh only happens for listings within the scanned
  page range (`MAX_PAGES`, default 5 pages/30 listings each). A once-a-day
  scan gives listings up to 24h to get pushed past that page range by newer
  postings before the next scan catches them, which raises the chance of
  missing a listing entirely for high-volume filters/districts. Fine for
  narrow per-user filters; raising `MAX_PAGES` trades this off against more
  anti-bot exposure and more per-user scraping time within the Lambda
  timeout (see above), so treat it as a "watch and tune if you notice gaps"
  knob rather than a default to bump preemptively.
- Dedup is scoped per user (`rent_seen`'s key is `(user_id, listing_id)`),
  so the same listing can independently be "new" to multiple users with
  different filters.

## Packaging: zip vs. container

The scraper Lambda is a container image; the webhook Lambda is a zip. This
isn't inconsistency for its own sake — each uses the packaging strategy its
actual dependencies require. Playwright + Chromium genuinely can't fit in a
zip package at all (well past the 250MB unzipped Lambda limit with browser
binaries included), so the scraper has no choice. The webhook's dependencies
(`boto3` + `requests`) are lightweight and comfortably fit a zip (current
build: ~33MB unzipped, ~18MB compressed, against a 250MB/50MB limit) — zip
deploys are also meaningfully faster (no ECR build/push round-trip), which
matters more for the webhook since it's the interactive command-handling
path. Unifying both to containers would trade that speed away for no
functional benefit.

## Migration notes

If you deployed this before multi-user support existed, `rent_seen`'s key
schema changes (`listing_id` → `(user_id, listing_id)`), which forces
Terraform to destroy and recreate that table — wiping dedup history for
everyone. After redeploying, run `python3 scripts/migrate_default_user.py`
once to move the old single "default" row to its real `chat_id` and reset
`last_scan_at`, so the next scan silently re-seeds instead of blasting
every currently-live listing as "new".
