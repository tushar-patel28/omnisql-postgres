variable "project" { type = string }
variable "environment" { type = string }
variable "account_id" { type = string }

resource "aws_s3_bucket" "models" {
  bucket        = "${var.project}-${var.environment}-models-${var.account_id}"
  force_destroy = true
  tags          = { Name = "model-artifacts" }
}

resource "aws_s3_bucket" "datasets" {
  bucket        = "${var.project}-${var.environment}-datasets-${var.account_id}"
  force_destroy = true
  tags          = { Name = "datasets" }
}

resource "aws_s3_bucket" "inference" {
  bucket        = "${var.project}-${var.environment}-inference-${var.account_id}"
  force_destroy = true
  tags          = { Name = "inference-outputs" }
}

resource "aws_s3_bucket_public_access_block" "models" {
  bucket                  = aws_s3_bucket.models.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "datasets" {
  bucket                  = aws_s3_bucket.datasets.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "inference" {
  bucket                  = aws_s3_bucket.inference.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "models" {
  bucket = aws_s3_bucket.models.id
  versioning_configuration { status = "Enabled" }
}

output "model_bucket_name" { value = aws_s3_bucket.models.bucket }
output "dataset_bucket_name" { value = aws_s3_bucket.datasets.bucket }
output "inference_bucket_name" { value = aws_s3_bucket.inference.bucket }
output "model_bucket_arn" { value = aws_s3_bucket.models.arn }
output "dataset_bucket_arn" { value = aws_s3_bucket.datasets.arn }
output "inference_bucket_arn" { value = aws_s3_bucket.inference.arn }