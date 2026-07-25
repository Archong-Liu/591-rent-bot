# 591 台北租屋雲端推播

每 4 小時自動爬 591 台北租屋、依個人偏好過濾、把新物件透過 Telegram bot 推播。
可在 Telegram 內直接設定篩選條件。

[English README](../README.md)

## 架構

```
EventBridge Scheduler ─every 4h─▶ Scraper Lambda (container/Playwright)
                                       │
                                       ├─reads─▶ DynamoDB: rent_prefs
                                       ├─writes─▶ DynamoDB: rent_seen (liveness-refreshed TTL)
                                       └─sends─▶ Telegram Bot API
                                                       ▲
                                                       │
Webhook Lambda (Function URL) ◀──/commands── Telegram Bot
       │
       └─writes prefs─▶ DynamoDB: rent_prefs
```

部署於 AWS Tokyo (`ap-northeast-1`)。預估月費 < $0.50 USD。

## 本機跑

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium

# 抓 1 頁存 CSV
python3 scraper.py --max-pages 1

# 帶 filter 抓
python3 scraper.py --url "https://rent.591.com.tw/list?region=1&section=3,5&rentprice=15000,30000" --max-pages 2
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
| `/set_price 15000 30000` | 設租金區間 |
| `/set_district 中山 大安 信義` | 設行政區（不加「區」也可） |
| `/set_kind 套房 整層` | 設房屋類型（整層／套房／分租／雅房） |
| `/set_area 10 30` | 設坪數 |
| `/set_pattern 1 2` | 設房數 |
| `/clear` | 清除所有篩選 |
| `/pause` ・ `/resume` | 暫停／恢復推播 |
| `/run` | 立即觸發一次掃描（測試用） |
| `/reset` | 清空 dedup 紀錄，下次掃描重新靜默建立基準 |
| `/list [page]` | 翻頁瀏覽最近仍在架的物件（5 筆/頁），顯示「最後確認」時間 |

也可以用聊天視窗下方的常用按鈕（看條件／看清單／立刻掃／暫停／恢復／清除條件／重新建立基準），效果等同對應的 slash command。

## 物件保留與時效性

- `mark_seen()` 每次掃描到物件（不論新舊）都會刷新其 `last_seen_at` 與 TTL，持續在架的物件不會過期。
- 物件從 591 下架後，會在 `LISTING_TTL_DAYS`（預設 7 天）後被 DynamoDB TTL 自動刪除。
- `/list` 只顯示 `FRESH_WINDOW_DAYS`（預設 3 天）內仍確認在架的物件，避免看到已經租掉/下架的舊資料。
- 兩個天數都可透過 Terraform 變數（`listing_ttl_days` / `fresh_window_days`）調整，不需改 code。
- 限制：存活刷新只發生在有掃描到的分頁（`MAX_PAGES`）內，若篩選條件很寬、物件落在掃描範圍外，可能提早被判定過期。目前針對單人窄範圍篩選沒問題。

## 變更篩選的 section ID（萬一 591 改了）

```bash
# 重新從 591 抓所有區的 section_id
python3 scripts/refresh_sections.py
# 寫進 app/data/taipei_sections.json，commit、重新部署
./scripts/deploy.sh
```

## 修改排程頻率

編輯 `infra/variables.tf` 內 `scraper_schedule_expression`，再跑：

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
scraper.py                   # 本機 CLI 入口
Dockerfile                   # Scraper Lambda image
```

## 注意

- `infra/terraform.tfstate` 含 AWS 資源細節，**已 gitignore**，請另外備份。
- 多裝置部署 / 多人共用時應改用 S3 backend，不適用 local state。
- 591 anti-bot 偶爾會 419／429；目前策略是 graceful return 不重試（4 小時後再試）。
