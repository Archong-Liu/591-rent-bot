#!/usr/bin/env bash
# Packages the webhook Lambda zip: bundles app/ with requirements-webhook.txt's dependencies
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/infra/build/webhook"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/app"

# Copy application code
cp -R "$ROOT_DIR/app/." "$BUILD_DIR/app/"

# Install dependencies at the build root (alongside app/, so imports resolve)
# Uses manylinux2014_x86_64 wheels to avoid a platform mismatch when building on macOS
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
