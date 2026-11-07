data "aws_caller_identity" "current" {}

module "network" {
  source = "./modules/network"

  name              = var.name
  vpc_cidr          = var.vpc_cidr
  nat_instance_type = var.nat_instance_type
}

module "ecr" {
  source = "./modules/ecr"

  name = var.name
  repositories = [
    "web",
    "catalog-api",
    "order-worker",
  ]
}

module "alb" {
  source = "./modules/alb"

  name              = var.name
  vpc_id            = module.network.vpc_id
  subnet_ids        = module.network.public_subnet_ids
  security_group_id = module.network.alb_security_group_id
  target_port       = 30080
  health_check_path = "/"
  certificate_arn   = var.certificate_arn
  domain_name       = var.domain_name
  route53_zone_id   = var.route53_zone_id
}

module "compute" {
  source = "./modules/compute"

  name               = var.name
  private_subnet_ids = module.network.private_subnet_ids
  security_group_id  = module.network.node_security_group_id
  instance_type      = var.instance_type
  target_group_arn   = module.alb.target_group_arn
}

resource "aws_s3_bucket" "ansible" {
  bucket = "${var.name}-ssm-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "ansible" {
  bucket = aws_s3_bucket.ansible.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ansible" {
  bucket = aws_s3_bucket.ansible.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_budgets_budget" "shoplite" {
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = "20"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  time_period_start = "2026-01-01_00:00"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
