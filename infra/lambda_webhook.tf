# Webhook Lambda is packaged from a pre-built build dir
# (produced by scripts/build_webhook_zip.sh: app/ + `pip install requests`)

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
      FRESH_WINDOW_DAYS  = tostring(var.fresh_window_days)
    }
  }

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "webhook" {
  name              = "/aws/lambda/${aws_lambda_function.webhook.function_name}"
  retention_in_days = 7
  tags              = local.tags
}

# The public HTTPS entry point uses an API Gateway HTTP API rather than a
# Lambda Function URL: on this personal AWS account, Function URLs kept
# returning 403 due to an org-level policy, so we pivoted to API Gateway,
# which uses a different IAM path.
# API resources are defined in infra/apigateway.tf.
