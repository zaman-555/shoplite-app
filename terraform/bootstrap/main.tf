terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      project = "shoplite"
    }
  }
}

data "aws_caller_identity" "current" {}

variable "aws_region" {
  description = "Region for the state bucket and lock table."
  type        = string
  default     = "eu-central-1"
}

variable "name" {
  description = "Name prefix."
  type        = string
  default     = "shoplite"
}

resource "aws_s3_bucket" "state" {
  bucket = "${var.name}-tfstate-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "lock" {
  name         = "${var.name}-tfstate-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

output "bucket" {
  description = "State bucket name. Copy this into backend.hcl."
  value       = aws_s3_bucket.state.bucket
}

output "dynamodb_table" {
  description = "Lock table name. Copy this into backend.hcl."
  value       = aws_dynamodb_table.lock.name
}

output "region" {
  description = "Region of the state bucket."
  value       = var.aws_region
}
