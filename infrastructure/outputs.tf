output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.db_host
  sensitive   = true
}

output "ecr_repository_url" {
  description = "ECR repository URL for FastAPI app"
  value       = module.ecs.ecr_repository_url
}

output "alb_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = module.ecs.alb_dns_name
}

output "model_bucket_name" {
  description = "S3 bucket for model artifacts"
  value       = module.s3.model_bucket_name
}

output "sagemaker_role_arn" {
  description = "SageMaker execution role ARN"
  value       = module.sagemaker.role_arn
}

output "api_url" {
  description = "Full API URL"
  value       = "http://${module.ecs.alb_dns_name}"
}