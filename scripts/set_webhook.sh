#!/usr/bin/env bash
# 對 Telegram setWebhook，把 webhook 指到我們的 Lambda Function URL
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AWS_REGION="${AWS_REGION:-ap-northeast-1}"

# 取得 webhook URL（從 terraform output）
WEBHOOK_URL=$(cd "$ROOT_DIR/infra" && terraform output -raw webhook_url)

# 取得 token
TOKEN=$(aws ssm get-parameter \
  --name /rent-scraper/telegram_token \
  --with-decryption \
  --region "$AWS_REGION" \
  --query Parameter.Value --output text)

if [[ "$TOKEN" == "REPLACE_ME" || -z "$TOKEN" ]]; then
  echo "❌ SSM 內的 token 還是 placeholder，請先跑 ./scripts/put_secrets.sh"
  exit 1
fi

echo "設定 webhook 至：$WEBHOOK_URL"
curl -s -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"${WEBHOOK_URL}\"}"
echo
echo "✅ 完成。打開 Telegram，跟你的 bot 送 /start 試試。"
