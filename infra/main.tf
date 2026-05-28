terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # local state — terraform.tfstate 在這個目錄；勿入 git
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
