variable "project" { type = string }
variable "environment" { type = string }
variable "account_id" { type = string }
variable "aws_region" { type = string }
variable "s3_bucket_name" { type = string }

resource "aws_sqs_queue" "failures" {
  name                       = "${var.project}-${var.environment}-failures"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400
  tags                       = { Name = "${var.project}-${var.environment}-failures" }
}

resource "aws_iam_role" "lambda" {
  name = "${var.project}-${var.environment}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.project}-${var.environment}-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.failures.arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = ["arn:aws:s3:::${var.s3_bucket_name}", "arn:aws:s3:::${var.s3_bucket_name}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["sagemaker:CreateTrainingJob", "sagemaker:DescribeTrainingJob"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project}-${var.environment}-retraining"
  retention_in_days = 7
}

data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/lambda_placeholder.zip"

  source {
    content  = <<EOF
import json

def lambda_handler(event, context):
    print("Retraining trigger received:", json.dumps(event))
    return {"statusCode": 200, "body": "OK"}
EOF
    filename = "handler.py"
  }
}

resource "aws_lambda_function" "retraining_trigger" {
  function_name    = "${var.project}-${var.environment}-retraining"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  timeout          = 300
  memory_size      = 256
  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  environment {
    variables = {
      S3_BUCKET   = var.s3_bucket_name
      PROJECT     = var.project
      ENVIRONMENT = var.environment
      AWS_ACCOUNT = var.account_id
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_event_source_mapping" "sqs" {
  event_source_arn = aws_sqs_queue.failures.arn
  function_name    = aws_lambda_function.retraining_trigger.arn
  batch_size       = 100
  maximum_batching_window_in_seconds = 60
}

output "sqs_queue_url" { value = aws_sqs_queue.failures.url }
output "sqs_queue_arn" { value = aws_sqs_queue.failures.arn }
output "lambda_function_name" { value = aws_lambda_function.retraining_trigger.function_name }
output "lambda_function_arn" { value = aws_lambda_function.retraining_trigger.arn }