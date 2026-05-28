output "ecr_repository_url" {
  description = "Scraper ECR repo（docker push 用）"
  value       = aws_ecr_repository.scraper.repository_url
}

output "scraper_function_name" {
  description = "Scraper Lambda 名稱"
  value       = aws_lambda_function.scraper.function_name
}

output "webhook_url" {
  description = "Telegram setWebhook 用的 URL（API Gateway HTTP API）"
  # invoke_url 的 trailing slash 不固定，用 trimsuffix 確保只有一條
  value = "${trimsuffix(aws_apigatewayv2_stage.webhook.invoke_url, "/")}/webhook"
}

output "ssm_telegram_token_name" {
  description = "SSM parameter 名稱，部署完用 aws ssm put-parameter 填入真值"
  value       = aws_ssm_parameter.telegram_token.name
}

output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  value = var.aws_region
}
