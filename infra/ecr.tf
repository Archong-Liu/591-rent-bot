resource "aws_ecr_repository" "scraper" {
  name                 = local.project
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.tags
}

resource "aws_ecr_lifecycle_policy" "scraper" {
  repository = aws_ecr_repository.scraper.name

  # 只清理「無 tag」的中間產物（BuildKit 推送會留下這些），
  # 並保留最新 10 個有 tag 的正式 image。
  # 不要用 tagStatus=any + imageCountMoreThan，那會把 live image 一起掃掉。
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "清掉 1 天前的無 tag image（BuildKit 中間產物）"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "保留最新 10 個有 tag 的 image"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["2"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
