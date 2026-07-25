resource "aws_lambda_function" "scraper" {
  function_name = "${local.project}-scraper"
  role          = aws_iam_role.scraper.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.scraper.repository_url}:${var.scraper_image_tag}"
  architectures = ["x86_64"]

  timeout     = 300 # 5 minutes
  memory_size = 2048

  ephemeral_storage {
    size = 2048 # /tmp size — Chromium needs the headroom
  }

  environment {
    variables = {
      PREFS_TABLE        = aws_dynamodb_table.prefs.name
      SEEN_TABLE         = aws_dynamodb_table.seen.name
      SSM_TELEGRAM_TOKEN = aws_ssm_parameter.telegram_token.name
      MAX_PAGES          = tostring(var.scraper_max_pages)
      LISTING_TTL_DAYS   = tostring(var.listing_ttl_days)
    }
  }

  tags = local.tags

  # The image tag only exists once deploy.sh has pushed it to ECR, so the
  # first `terraform apply` requires a build & push beforehand.
  depends_on = [aws_ecr_repository.scraper]
}

resource "aws_cloudwatch_log_group" "scraper" {
  name              = "/aws/lambda/${aws_lambda_function.scraper.function_name}"
  retention_in_days = 7
  tags              = local.tags
}
