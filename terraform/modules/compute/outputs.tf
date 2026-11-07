output "control_plane_instance_id" {
  description = "Control plane instance id."
  value       = aws_instance.node["control-plane"].id
}

output "worker_instance_ids" {
  description = "Worker instance ids."
  value       = [aws_instance.node["worker-a"].id, aws_instance.node["worker-b"].id]
}

output "private_ips" {
  description = "Private IP of each Kubernetes node."
  value       = { for name, instance in aws_instance.node : name => instance.private_ip }
}
