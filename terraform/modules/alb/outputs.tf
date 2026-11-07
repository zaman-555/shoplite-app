output "dns_name" {
  description = "Public DNS name of the load balancer."
  value       = aws_lb.this.dns_name
}

output "arn" {
  description = "Load balancer ARN."
  value       = aws_lb.this.arn
}

output "zone_id" {
  description = "Hosted zone id of the load balancer."
  value       = aws_lb.this.zone_id
}

output "target_group_arn" {
  description = "Target group that forwards to the Kubernetes ingress NodePort."
  value       = aws_lb_target_group.ingress.arn
}

output "route53_fqdn" {
  description = "Record created for the load balancer, or null."
  value       = try(aws_route53_record.app[0].fqdn, null)
}
