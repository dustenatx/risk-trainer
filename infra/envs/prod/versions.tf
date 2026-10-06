# Applied only by the deploy workflow's apply job, after the owner approves it in the
# protected prod environment (R14). Agents never run terraform apply.
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67"
    }
  }

  # Partial config: the workflow passes -backend-config="bucket=${{ vars.TF_STATE_BUCKET }}".
  backend "s3" {
    key          = "prod/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "us-east-2"

  default_tags {
    tags = {
      project = "risk-trainer"
      env     = "prod"
    }
  }
}
