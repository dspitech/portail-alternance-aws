terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Recommandé pour un vrai projet d'entreprise : backend distant (S3 + DynamoDB lock)
  # Décommenter et adapter une fois le bucket de state créé.
  # backend "s3" {
  #   bucket         = "tfstate-alternance-alerts"
  #   key            = "envs/dev/terraform.tfstate"
  #   region         = "eu-west-3"
  #   dynamodb_table = "tfstate-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
