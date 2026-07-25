# API Gateway HTTP API -> webhook Lambda
# Replaces a Lambda Function URL as the Telegram webhook entry point.

resource "aws_apigatewayv2_api" "webhook" {
  name          = "${local.project}-webhook-api"
  protocol_type = "HTTP"
  description   = "Telegram webhook entry, proxies to ${aws_lambda_function.webhook.function_name}"

  tags = local.tags
}

resource "aws_apigatewayv2_integration" "webhook" {
  api_id                 = aws_apigatewayv2_api.webhook.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.webhook.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.webhook.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.webhook.id}"
}

resource "aws_apigatewayv2_stage" "webhook" {
  api_id      = aws_apigatewayv2_api.webhook.id
  name        = "$default"
  auto_deploy = true

  tags = local.tags
}

resource "aws_lambda_permission" "webhook_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  # Any route/stage may invoke it — this API only has the one route, so
  # there's no need to lock the source ARN down further.
  source_arn = "${aws_apigatewayv2_api.webhook.execution_arn}/*/*"
}
