output "repository_urls" {
  description = "Repository URL keyed by image name."
  value       = { for name, repo in aws_ecr_repository.this : name => repo.repository_url }
}

output "repository_arns" {
  description = "Repository ARN keyed by image name."
  value       = { for name, repo in aws_ecr_repository.this : name => repo.arn }
}
