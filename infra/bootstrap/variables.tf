variable "account_id" {
  description = "AWS account ID the bootstrap may run in (guards against the wrong profile)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account ID."
  }
}

variable "region" {
  description = "Home region for the app, the state bucket and the SSM parameters."
  type        = string
  default     = "us-east-2"
}

variable "github_repository" {
  description = "GitHub repository (owner/name) whose workflows may assume the roles."
  type        = string
  default     = "dustenatx/risk-trainer"
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set false if the account already has one."
  type        = bool
  default     = true
}

variable "state_bucket_name" {
  description = "Terraform state bucket name. Defaults to risk-trainer-tfstate-<account_id>."
  type        = string
  default     = null
}
