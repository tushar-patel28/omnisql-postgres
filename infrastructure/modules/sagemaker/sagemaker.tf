variable "project" { type = string }
variable "environment" { type = string }
variable "account_id" { type = string }
variable "aws_region" { type = string }
variable "s3_bucket_name" { type = string }

resource "aws_iam_role" "sagemaker" {
  name = "${var.project}-${var.environment}-sagemaker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "sagemaker.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "sagemaker_full" {
  role       = aws_iam_role.sagemaker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
}

resource "aws_iam_role_policy" "sagemaker_s3" {
  name = "${var.project}-${var.environment}-sagemaker-s3"
  role = aws_iam_role.sagemaker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
      Resource = [
        "arn:aws:s3:::${var.s3_bucket_name}",
        "arn:aws:s3:::${var.s3_bucket_name}/*",
        "arn:aws:s3:::${var.project}-${var.environment}-datasets-${var.account_id}",
        "arn:aws:s3:::${var.project}-${var.environment}-datasets-${var.account_id}/*"
      ]
    }]
  })
}

resource "aws_cloudwatch_log_group" "sagemaker" {
  name              = "/aws/sagemaker/${var.project}-${var.environment}"
  retention_in_days = 7
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project}-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          title   = "SageMaker Endpoint Invocations"
          region  = var.aws_region
          metrics = [["AWS/SageMaker", "Invocations", "EndpointName", "${var.project}-${var.environment}-endpoint"]]
          period  = 300
        }
      },
      {
        type = "metric"
        properties = {
          title   = "SageMaker Model Latency"
          region  = var.aws_region
          metrics = [["AWS/SageMaker", "ModelLatency", "EndpointName", "${var.project}-${var.environment}-endpoint"]]
          period  = 300
        }
      }
    ]
  })
}

output "role_arn" { value = aws_iam_role.sagemaker.arn }
output "role_name" { value = aws_iam_role.sagemaker.name }