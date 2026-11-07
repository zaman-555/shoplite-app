variable "name" {
  description = "Name prefix."
  type        = string
}

variable "private_subnet_ids" {
  description = "Two private subnet ids. The control plane uses the first. Workers use one each."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) == 2
    error_message = "Provide both private subnet ids."
  }
}

variable "security_group_id" {
  description = "Security group for every Kubernetes node."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type for the control plane and workers."
  type        = string
}

variable "target_group_arn" {
  description = "Load balancer target group for the ingress NodePort."
  type        = string
}
