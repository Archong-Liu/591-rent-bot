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

部署於 AWS Tokyo (`ap-northeast-1`)。預估月費 < $0.50 USD。設計理由與
取捨（掃描頻率、多使用者爬取上限、保留期限調整、封裝方式選擇）記錄在
[DESIGN.md](DESIGN.md)（英文），不放在這裡。

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
- `LISTING_TTL_DAYS`（預設 7 天）：物件從 591 下架後，幾天後會被 DynamoDB TTL 自動刪除。
- `FRESH_WINDOW_DAYS`（預設 2 天）：`/list` 只顯示這幾天內仍確認在架的物件。
- 兩個天數都可透過 Terraform 變數（`listing_ttl_days` / `fresh_window_days`）調整，不需改 code。
- `NEW_ITEM_CAP`（40）：推送前的筆數上限，超過會改顯示 overflow 通知。`MAX_PAGES`（5）：每次掃描抓幾頁。
- 去重是依使用者區分的（`rent_seen` 的 key 是 `(user_id, listing_id)`），所以同一筆物件對篩選條件不同的多個使用者可以各自獨立判定為「新物件」。

這些預設值背後的理由記錄在 [DESIGN.md](DESIGN.md)。

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

- `infra/terraform.tfstate` 含 AWS 資源細節，**已 gitignore**，請另外備份。
- 多裝置部署 / 多人共用時應改用 S3 backend，不適用 local state。
- 591 anti-bot 偶爾會 419／429；目前策略是 graceful return 不重試（等下次排定的掃描再試）。
- 從多使用者支援上線前的版本升級？遷移步驟記錄在 [DESIGN.md](DESIGN.md)。
