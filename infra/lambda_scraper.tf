resource "aws_lambda_function" "scraper" {
  function_name = "${local.project}-scraper"
  role          = aws_iam_role.scraper.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.scraper.repository_url}:${var.scraper_image_tag}"
  architectures = ["x86_64"]

  timeout     = 300 # 5 分鐘
  memory_size = 2048

  ephemeral_storage {
    size = 2048 # /tmp 大小，Chromium 需要
  }

  environment {
    variables = {
      PREFS_TABLE        = aws_dynamodb_table.prefs.name
      SEEN_TABLE         = aws_dynamodb_table.seen.name
      SSM_TELEGRAM_TOKEN = aws_ssm_parameter.telegram_token.name
      MAX_PAGES          = tostring(var.scraper_max_pages)
    }
  }

  tags = local.tags

  # 由於 image tag 是 deploy.sh 推上 ECR 後才存在，
  # 首次 terraform apply 前必須先 build & push。
  depends_on = [aws_ecr_repository.scraper]
}

resource "aws_cloudwatch_log_group" "scraper" {
  name              = "/aws/lambda/${aws_lambda_function.scraper.function_name}"
  retention_in_days = 14
  tags              = local.tags
}
