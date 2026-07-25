output "ecr_repository_url" {
  description = "Scraper ECR repo (used for docker push)"
  value       = aws_ecr_repository.scraper.repository_url
}

output "scraper_function_name" {
  description = "Scraper Lambda name"
  value       = aws_lambda_function.scraper.function_name
}

output "webhook_url" {
  description = "URL to register with Telegram setWebhook (the API Gateway HTTP API)"
  # invoke_url's trailing slash isn't guaranteed, so trimsuffix keeps exactly one.
  value = "${trimsuffix(aws_apigatewayv2_stage.webhook.invoke_url, "/")}/webhook"
}

output "ssm_telegram_token_name" {
  description = "SSM parameter name — fill in the real value post-deploy via aws ssm put-parameter"
  value       = aws_ssm_parameter.telegram_token.name
}

output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  value = var.aws_region
}
