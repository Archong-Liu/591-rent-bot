resource "aws_dynamodb_table" "prefs" {
  name         = "${local.project}-prefs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  tags = local.tags
}

resource "aws_dynamodb_table" "seen" {
  name         = "${local.project}-seen"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "listing_id"

  attribute {
    name = "listing_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = local.tags
}
