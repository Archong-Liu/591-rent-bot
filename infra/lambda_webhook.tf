# Webhook Lambda 從預先建好的 build dir 打包
# build dir 由 scripts/build_webhook_zip.sh 產生（app/ + pip install requests）

data "archive_file" "webhook" {
  type        = "zip"
  source_dir  = "${path.module}/build/webhook"
  output_path = "${path.module}/build/webhook.zip"
}

resource "aws_lambda_function" "webhook" {
  function_name = "${local.project}-webhook"
  role          = aws_iam_role.webhook.arn

  filename         = data.archive_file.webhook.output_path
  source_code_hash = data.archive_file.webhook.output_base64sha256

  runtime     = "python3.12"
  handler     = "app.webhook_lambda.handler"
  timeout     = 30
  memory_size = 512

  environment {
    variables = {
      PREFS_TABLE        = aws_dynamodb_table.prefs.name
      SEEN_TABLE         = aws_dynamodb_table.seen.name
      SSM_TELEGRAM_TOKEN = aws_ssm_parameter.telegram_token.name
      SCRAPER_FN_NAME    = aws_lambda_function.scraper.function_name
    }
  }

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "webhook" {
  name              = "/aws/lambda/${aws_lambda_function.webhook.function_name}"
  retention_in_days = 14
  tags              = local.tags
}

# 對外 HTTPS 入口改用 API Gateway HTTP API（個人 AWS 帳號的 Function URL
# 因組織層級政策一直回 403，pivot 至 API Gateway 走另一條 IAM 路徑）。
# API 資源定義於 infra/apigateway.tf。
