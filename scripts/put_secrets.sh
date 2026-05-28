#!/usr/bin/env bash
# 互動輸入 Telegram bot token，寫進 SSM Parameter Store
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
PARAM_NAME="/rent-scraper/telegram_token"

echo "Telegram bot token（從 @BotFather 取得，不會顯示）："
read -r -s TOKEN
echo

if [[ -z "$TOKEN" ]]; then
  echo "❌ token 不能空白"
  exit 1
fi

aws ssm put-parameter \
  --name "$PARAM_NAME" \
  --value "$TOKEN" \
  --type SecureString \
  --overwrite \
  --region "$AWS_REGION" >/dev/null

echo "✅ 已寫入 $PARAM_NAME"
