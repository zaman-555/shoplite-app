output "vpc_id" {
  description = "ShopLite VPC id."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "ShopLite VPC CIDR."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Two public subnet ids, one per availability zone."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Two private subnet ids, one per availability zone."
  value       = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  description = "Security group attached to the load balancer."
  value       = aws_security_group.alb.id
}

output "node_security_group_id" {
  description = "Security group attached to the Kubernetes nodes."
  value       = aws_security_group.nodes.id
}
