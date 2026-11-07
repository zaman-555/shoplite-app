variable "aws_region" {
  description = "AWS region for the ShopLite cluster."
  type        = string
  default     = "eu-central-1"
}

variable "name" {
  description = "Name prefix used on every resource."
  type        = string
  default     = "shoplite"
}

variable "vpc_cidr" {
  description = "CIDR block for the ShopLite VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "instance_type" {
  description = "EC2 size for the control plane and both workers. t3.small has enough memory for k3s."
  type        = string
  default     = "t3.small"
}

variable "nat_instance_type" {
  description = "EC2 size for the NAT instance. A NAT instance is used instead of a NAT Gateway so the monthly cost can stay near the USD 20 budget."
  type        = string
  default     = "t3.nano"
}

variable "budget_alert_email" {
  description = "Email address that receives the USD 20 budget alarm."
  type        = string
}

variable "domain_name" {
  description = "Optional DNS name for the load balancer. Leave null when you have no domain."
  type        = string
  default     = null
}

variable "route53_zone_id" {
  description = "Optional Route 53 hosted zone id. Used only together with domain_name."
  type        = string
  default     = null
}

variable "certificate_arn" {
  description = "Optional ACM certificate ARN for an HTTPS listener."
  type        = string
  default     = null
}
