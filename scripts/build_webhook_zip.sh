#!/usr/bin/env bash
# 打包 webhook Lambda 用的 zip：把 app/ 跟 requirements-webhook.txt 的依賴放一起
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/infra/build/webhook"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/app"

# 複製 app 程式碼
cp -R "$ROOT_DIR/app/." "$BUILD_DIR/app/"

# 裝依賴到 build 根目錄（與 app 同層，import 時找得到）
# 用 manylinux2014_x86_64 wheels，避免 macOS 開發機上的 platform mismatch
python3 -m pip install \
  --quiet \
  --platform manylinux2014_x86_64 \
  --target "$BUILD_DIR" \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --upgrade \
  -r "$ROOT_DIR/requirements-webhook.txt"

echo "Webhook build dir 已準備好：$BUILD_DIR"
