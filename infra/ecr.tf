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

  # Only clean up untagged intermediate images (left behind by BuildKit
  # pushes), and keep the newest 10 tagged production images.
  # Do NOT use tagStatus=any + imageCountMoreThan — that sweeps up the live
  # image along with everything else.
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images (BuildKit intermediates) older than 1 day"
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
        description  = "Keep only the newest 1 tagged image (the live image)"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["2"]
          countType     = "imageCountMoreThan"
          countNumber   = 1
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
