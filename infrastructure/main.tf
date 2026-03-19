terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "omnisql-postgres"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

module "vpc" {
  source      = "./modules/vpc"
  project     = var.project
  environment = var.environment
  vpc_cidr    = var.vpc_cidr
  azs         = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "s3" {
  source      = "./modules/s3"
  project     = var.project
  environment = var.environment
  account_id  = data.aws_caller_identity.current.account_id
}

module "ecs" {
  source             = "./modules/ecs"
  project            = var.project
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
  account_id         = data.aws_caller_identity.current.account_id
  aws_region         = var.aws_region
  s3_bucket_name     = module.s3.model_bucket_name
  db_host            = module.rds.db_host
  db_name            = var.project
  db_user            = var.project
  db_password        = var.db_password
  app_image          = var.app_image
}

module "rds" {
  source             = "./modules/rds"
  project            = var.project
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  app_sg_id          = module.ecs.app_sg_id
  db_password        = var.db_password
}

module "sagemaker" {
  source         = "./modules/sagemaker"
  project        = var.project
  environment    = var.environment
  account_id     = data.aws_caller_identity.current.account_id
  aws_region     = var.aws_region
  s3_bucket_name = module.s3.model_bucket_name
}

module "lambda" {
  source         = "./modules/lambda"
  project        = var.project
  environment    = var.environment
  account_id     = data.aws_caller_identity.current.account_id
  aws_region     = var.aws_region
  s3_bucket_name = module.s3.model_bucket_name
}