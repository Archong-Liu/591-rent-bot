# Scraper Lambda image — based on the official Playwright Python image (Chromium included)
# Note: the v1.49.0 image tag must match the playwright==1.49.0 pin in requirements.txt
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# AWS Lambda environment variables
ENV LAMBDA_TASK_ROOT=/var/task \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR ${LAMBDA_TASK_ROOT}

# Install dependencies first (cached as its own Docker layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt awslambdaric==2.2.0

# Copy application code
COPY app/ ./app/

# Lambda Runtime Interface Client
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["app.scraper_lambda.handler"]
