# SSM SecureString placeholder — filled in with the real value post-deploy via
# a CLI command / script.
# The value starts as a placeholder so the real token never lands in tfstate;
# subsequent `terraform apply` runs won't overwrite it (see lifecycle
# ignore_changes on value below).

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
