#!/usr/bin/env bash
# 全流程部署：build & push scraper image → build webhook zip → terraform apply
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"

echo "==> 1/5 取得 AWS 帳號 ID"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_HOST="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

echo "==> 2/5 在 ECR 建 repo（terraform 已建立則跳過）"
cd "$ROOT_DIR/infra"
if ! aws ecr describe-repositories --repository-names rent-scraper --region "$AWS_REGION" >/dev/null 2>&1; then
  echo "    ECR repo 尚未建立，先跑 terraform 建基礎設施"
  terraform init -upgrade
  terraform apply -auto-approve -target=aws_ecr_repository.scraper
fi

echo "==> 3/5 build & push scraper image: $ECR_HOST/rent-scraper:$IMAGE_TAG"
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_HOST"

cd "$ROOT_DIR"
docker build --platform linux/amd64 --provenance=false -t "$ECR_HOST/rent-scraper:$IMAGE_TAG" .
docker push "$ECR_HOST/rent-scraper:$IMAGE_TAG"

echo "==> 4/5 build webhook Lambda zip"
bash "$ROOT_DIR/scripts/build_webhook_zip.sh"

echo "==> 5/5 terraform apply"
cd "$ROOT_DIR/infra"
terraform init -upgrade
terraform apply -auto-approve -var "scraper_image_tag=$IMAGE_TAG"

echo
echo "✅ 部署完成。"
echo "下一步："
echo "  1. ./scripts/put_secrets.sh   # 把 Telegram bot token 寫進 SSM"
echo "  2. ./scripts/set_webhook.sh   # 設定 Telegram webhook"
