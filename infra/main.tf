terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.56"
    }
  }
  # Local state — terraform.tfstate lives in this directory; keep it out of git.
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  project = "rent-scraper"
  tags = {
    Project   = local.project
    ManagedBy = "terraform"
  }
}
