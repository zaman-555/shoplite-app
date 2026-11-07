variable "name" {
  description = "Name prefix."
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block."
  type        = string
}

variable "nat_instance_type" {
  description = "Instance type for the NAT instance."
  type        = string
}
