variable "name" {
  description = "Name prefix."
  type        = string
}

variable "vpc_id" {
  description = "VPC that contains the load balancer."
  type        = string
}

variable "subnet_ids" {
  description = "Public subnet ids. Two, in different availability zones."
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group for the load balancer."
  type        = string
}

variable "target_port" {
  description = "NodePort where the Kubernetes ingress listens."
  type        = number
  default     = 30080
}

variable "health_check_path" {
  description = "HTTP path the load balancer probes."
  type        = string
  default     = "/"
}

variable "certificate_arn" {
  description = "ACM certificate for the HTTPS listener. Null skips that listener."
  type        = string
  default     = null
}

variable "domain_name" {
  description = "Optional record name inside the hosted zone."
  type        = string
  default     = null
}

variable "route53_zone_id" {
  description = "Optional hosted zone id."
  type        = string
  default     = null
}
