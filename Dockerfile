# Scraper Lambda image — 基於官方 Playwright Python（已含 Chromium）
# 注意：image tag 的 v1.49.0 必須對應 requirements.txt 內的 playwright==1.49.0
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# AWS Lambda 環境變數
ENV LAMBDA_TASK_ROOT=/var/task \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR ${LAMBDA_TASK_ROOT}

# 先裝依賴（會被 docker layer cache）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt awslambdaric==2.2.0

# 複製 app 程式碼
COPY app/ ./app/

# Lambda Runtime Interface Client
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["app.scraper_lambda.handler"]
