output "alb_dns_name" {
  description = "Public DNS name of the load balancer."
  value       = module.alb.dns_name
}

output "route53_fqdn" {
  description = "DNS name created when a hosted zone and domain were supplied."
  value       = module.alb.route53_fqdn
}

output "control_plane_instance_id" {
  description = "Instance id used with Session Manager and the kubeconfig port forward."
  value       = module.compute.control_plane_instance_id
}

output "worker_instance_ids" {
  description = "Worker instance ids."
  value       = module.compute.worker_instance_ids
}

output "node_private_ips" {
  description = "Private IPs of the control plane and workers."
  value       = module.compute.private_ips
}

output "ecr_repository_urls" {
  description = "ECR URLs for web, catalog-api, and order-worker."
  value       = module.ecr.repository_urls
}

output "ansible_ssm_bucket" {
  description = "S3 bucket Ansible uses while connected through Session Manager."
  value       = aws_s3_bucket.ansible.bucket
}
