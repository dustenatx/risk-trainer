# Owner applies this once with the rt-admin profile; agents never change it (AGENTS.md).
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67"
    }
  }

  # Partial config: pass the bucket at init with -backend-config="bucket=<state_bucket output>".
  # The first apply runs on local state through a gitignored *_override.tf (see README.md).
  backend "s3" {
    key          = "bootstrap/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]

  default_tags {
    tags = {
      project = "risk-trainer"
      env     = "shared"
    }
  }
}
