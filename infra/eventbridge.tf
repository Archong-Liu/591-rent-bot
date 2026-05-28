resource "aws_scheduler_schedule" "scraper_cron" {
  name = "${local.project}-cron"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.scraper_schedule_expression
  schedule_expression_timezone = "Asia/Taipei"

  target {
    arn      = aws_lambda_function.scraper.arn
    role_arn = aws_iam_role.scheduler.arn

    input = jsonencode({ source = "schedule" })

    retry_policy {
      maximum_event_age_in_seconds = 600
      maximum_retry_attempts       = 0
    }
  }
}
