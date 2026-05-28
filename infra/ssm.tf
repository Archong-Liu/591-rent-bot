# SSM SecureString placeholder — 部署完用 CLI / 腳本填入真值。
# value 設成 placeholder 避免 token 進 tfstate；後續 terraform apply 不會覆寫
# （因為 lifecycle ignore_changes value）。

resource "aws_ssm_parameter" "telegram_token" {
  name        = "/${local.project}/telegram_token"
  description = "Telegram Bot token"
  type        = "SecureString"
  value       = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }

  tags = local.tags
}
