# 591 台北租屋雲端推播

每天中午自動爬一次 591 台北租屋、依個人偏好過濾、把新物件透過 Telegram bot 推播。
可在 Telegram 內直接設定篩選條件。支援多使用者：任何人對 bot 送 `/start`
就會有自己獨立的篩選條件、去重狀態與推播。

[English README](../README.md)

## 架構

```
EventBridge Scheduler ─每天中午 (Asia/Taipei)─▶ Scraper Lambda (container/Playwright)
                                       │  逐一處理每個已註冊使用者
                                       ├─reads─▶ DynamoDB: rent_prefs（每個 chat_id 一筆）
                                       ├─writes─▶ DynamoDB: rent_seen（key 為 (user_id, listing_id)，liveness-refreshed TTL）
                                       └─sends─▶ Telegram Bot API（各自送到該使用者的 chat_id）
                                                       ▲
                                                       │
Webhook Lambda (Function URL) ◀──/commands── Telegram Bot
       │
       └─writes prefs─▶ DynamoDB: rent_prefs（只影響發送者所在的 chat_id）
```

部署於 AWS Tokyo (`ap-northeast-1`)。預估月費 < $0.50 USD。

使用者是在同一次 Scraper Lambda 呼叫內依序處理的，而每種不同的篩選組合
都需要各自跑一次真正的（且有意放慢速度避開反爬的）Chromium 爬取。這讓
每次掃描週期（每天一次）大概只能處理 10-15 種不同篩選組合，就會撞到
Lambda 5 分鐘的 timeout——這是爬蟲耗時造成的上限，不是 AWS 帳單額度的
問題。目前篩選條件完全相同的使用者仍會各自觸發一次獨立爬取；把「相同
篩選只爬一次」的邏輯做出來可以再拉高這個上限（同時降低 591 反爬風險），
但目前還沒做。從每 4 小時改成每天一次，本身就已經讓對 591 的請求量減少
6 倍，對降低反爬風險也有實質幫助。

## 本機跑

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-cli.txt
python3 -m playwright install chromium

# 抓 1 頁存 CSV
python3 scrape_cli.py --max-pages 1

# 帶 filter 抓
python3 scrape_cli.py --url "https://rent.591.com.tw/list?region=1&section=3,5&rentprice=15000,30000" --max-pages 2
```

## 雲端部署

### 一次性準備

1. **AWS CLI 設定好憑證**
   ```bash
   aws configure  # 用個人帳號的 access key
   aws sts get-caller-identity  # 確認對的帳號
   ```

2. **Docker Desktop 已啟動**（build scraper image 用）

3. **Terraform >= 1.6 已安裝**

4. **建 Telegram Bot**
   - Telegram 找 `@BotFather`
   - `/newbot` → 取 bot name → 取得 token（後面用得到）

### 部署

```bash
# 1) build & push image、build webhook zip、跑 terraform apply
./scripts/deploy.sh

# 2) 把 Telegram token 寫進 SSM Parameter Store
./scripts/put_secrets.sh
# 輸入剛才 @BotFather 給的 token

# 3) 對 Telegram setWebhook
./scripts/set_webhook.sh
```

完成後在 Telegram 跟你的 bot 送 `/start`，應該會收到歡迎訊息。

## Telegram 指令

| 指令 | 行為 |
|------|------|
| `/start` | 顯示歡迎、可用指令、目前 filter |
| `/filters` | 看目前篩選條件 |
| `/price 15000 30000` | 設租金區間 |
| `/district 中山 大安 信義` | 設行政區（不加「區」也可） |
| `/kind 套房 整層` | 設房屋類型（整層／套房／分租／雅房） |
| `/area 10 30` | 設坪數 |
| `/pattern 1 2` | 設房數 |
| `/clear` | 清除所有篩選 |
| `/pause` ・ `/resume` | 暫停／恢復推播 |
| `/run` | 立即觸發一次掃描（可能需要幾分鐘） |
| `/reseed` | 清空你的記錄，下次掃描重新靜默建立基準 |
| `/list [page] [price\|price_desc]` | 翻頁瀏覽最近仍在架的物件（5 筆/頁），顯示「最後確認」時間。預設依最近確認時間排序；`price`/`price_desc` 依租金排序（無法解析的價格，例如「面議」，一律排最後）。page 跟 sort 順序不拘，例如 `/list price 2`。摘要訊息下方會附上翻頁／切換排序的按鈕，不用重打指令 |

也可以用聊天視窗下方的常用按鈕（看條件／看清單／立刻掃／暫停／恢復／清除條件／重新建立基準），效果等同對應的 slash command。

## 物件保留與時效性

- `mark_seen()` 每次掃描到物件（不論新舊）都會刷新其 `last_seen_at` 與 TTL，持續在架的物件不會過期。
- 物件從 591 下架後，會在 `LISTING_TTL_DAYS`（預設 7 天）後被 DynamoDB TTL 自動刪除。這是「大概一週沒再出現就當作已租掉/下架」的現實假設，跟掃描頻率無關，所以改成每天掃一次也不需要跟著調整。
- `/list` 只顯示 `FRESH_WINDOW_DAYS`（預設 2 天，因為改成每天掃一次）內仍確認在架的物件，避免看到已經租掉/下架的舊資料——2 天可以容忍剛好一次掃描失敗（例如 591 反爬回 419），還不會把仍在架的物件誤判為過期。
- 兩個天數都可透過 Terraform 變數（`listing_ttl_days` / `fresh_window_days`）調整，不需改 code。
- `NEW_ITEM_CAP`（推送前的筆數上限，超過會改顯示 overflow 通知）從 25 調高到 40：改成每天一次後，單次掃描累積的候選新物件量大概是原本 4 小時一次的 6 倍。
- 限制：存活刷新只發生在有掃描到的分頁（`MAX_PAGES`，預設 5 頁、每頁 30 筆）內。改成每天一次後，物件有整整 24 小時可能被新物件擠出這個分頁範圍才被下次掃描發現（相較於原本約 4 小時），對物件量大的篩選條件/行政區，漏掉物件的機率會提高。窄範圍篩選目前沒問題；要調高 `MAX_PAGES` 得拿反爬風險和 Lambda timeout 內能處理的使用者數（見上）來換，所以先當作「發現有漏掉再調」的旋鈕，不建議預先調高。
- 去重是依使用者區分的（`rent_seen` 的 key 是 `(user_id, listing_id)`），所以同一筆物件對篩選條件不同的多個使用者可以各自獨立判定為「新物件」。

## 變更篩選的 section ID（萬一 591 改了）

```bash
# 重新從 591 抓所有區的 section_id
python3 scripts/refresh_sections.py
# 寫進 app/data/taipei_sections.json，commit、重新部署
./scripts/deploy.sh
```

## 修改排程頻率

預設是每天中午（`cron(0 12 * * ? *)`，時區 `Asia/Taipei`）。編輯
`infra/variables.tf` 內 `scraper_schedule_expression`（EventBridge
Scheduler 的 `rate(...)` 或 `cron(...)` 表達式），再跑：

```bash
cd infra && terraform apply
```

## 主要檔案位置

```
app/
├── core/scraper.py          # Playwright 爬蟲核心
├── core/filters.py          # prefs → 591 URL
├── core/prefs.py            # DynamoDB rent_prefs CRUD
├── core/seen.py             # DynamoDB rent_seen 去重 + 存活刷新
├── core/telegram.py         # Telegram Bot API
├── core/models.py           # 共用的 `Listing` 型別
├── scraper_lambda.py        # 排程觸發入口
└── webhook_lambda.py        # Telegram webhook 入口

infra/                       # Terraform
scripts/                     # 部署 / 維運腳本
scrape_cli.py                # 本機 CLI 入口
Dockerfile                   # Scraper Lambda image
```

## 注意

- 如果你在多使用者支援上線前就已經部署過，`rent_seen` 的 key schema 會改變
  （`listing_id` → `(user_id, listing_id)`），這會逼 Terraform 把整張表
  destroy 重建——等於清空所有人的去重紀錄。重新部署後，跑一次
  `python3 scripts/migrate_default_user.py`，把舊的單一 "default" row
  搬到它真正的 `chat_id`，並重置 `last_scan_at`，這樣下次掃描才會靜默
  重新建立基準，而不是把目前所有在架物件都當成「新物件」轟炸出去。
- `infra/terraform.tfstate` 含 AWS 資源細節，**已 gitignore**，請另外備份。
- 多裝置部署 / 多人共用時應改用 S3 backend，不適用 local state。
- 591 anti-bot 偶爾會 419／429；目前策略是 graceful return 不重試（4 小時後再試）。
