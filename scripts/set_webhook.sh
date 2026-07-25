#!/usr/bin/env bash
# Registers our webhook URL with Telegram's setWebhook (API Gateway HTTP API, see infra/apigateway.tf)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AWS_REGION="${AWS_REGION:-ap-northeast-1}"

# Read the webhook URL from terraform output
WEBHOOK_URL=$(cd "$ROOT_DIR/infra" && terraform output -raw webhook_url)

# Read the bot token
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
