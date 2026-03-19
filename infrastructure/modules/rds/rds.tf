variable "project" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "app_sg_id" { type = string }
variable "db_password" {
  type      = string
  sensitive = true
}

resource "aws_security_group" "rds" {
  name        = "${var.project}-${var.environment}-rds-sg"
  description = "RDS PostgreSQL - allow access from app only"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.app_sg_id]
    description     = "PostgreSQL from app"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.environment}-rds-sg" }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-${var.environment}-db-subnet"
  subnet_ids = var.private_subnet_ids
  tags       = { Name = "${var.project}-${var.environment}-db-subnet" }
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${var.project}-${var.environment}-pg16"
  family = "postgres16"
  tags   = { Name = "${var.project}-${var.environment}-pg16" }
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.project}-${var.environment}-postgres"
  engine                 = "postgres"
  engine_version         = "16.3"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  max_allocated_storage  = 100
  storage_type           = "gp2"
  db_name                = var.project
  username               = var.project
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.postgres.name
  skip_final_snapshot    = true
  deletion_protection    = false
  tags                   = { Name = "${var.project}-${var.environment}-postgres" }
}

output "db_host" { value = aws_db_instance.postgres.address }
output "db_port" { value = aws_db_instance.postgres.port }
output "db_name" { value = aws_db_instance.postgres.db_name }
output "rds_sg_id" { value = aws_security_group.rds.id }