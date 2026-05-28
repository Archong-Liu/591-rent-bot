output "ecr_repository_url" {
  description = "Scraper ECR repo（docker push 用）"
  value       = aws_ecr_repository.scraper.repository_url
}

output "scraper_function_name" {
  description = "Scraper Lambda 名稱"
  value       = aws_lambda_function.scraper.function_name
}

output "webhook_url" {
  description = "Telegram setWebhook 用的 URL"
  value       = aws_lambda_function_url.webhook.function_url
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
