variable "name" {
  description = "Name for every resource, e.g. risk-trainer-prod. Must start with risk-trainer- (the deploy role is scoped to that prefix)."
  type        = string

  validation {
    condition     = can(regex("^risk-trainer-[a-z0-9-]+$", var.name))
    error_message = "name must start with risk-trainer- and use lowercase letters, digits and hyphens."
  }
}

variable "lambda_zip_path" {
  description = "Path to the package built by `make package`."
  type        = string
}

variable "permissions_boundary_arn" {
  description = "ARN of risk-trainer-app-boundary (bootstrap output app_boundary_arn)."
  type        = string
}

variable "session_secret_param" {
  description = "SSM SecureString holding the session-cookie secret (owner-created)."
  type        = string
}

variable "origin_verify_param" {
  description = "SSM SecureString holding the X-Origin-Verify value CloudFront sends (owner-created)."
  type        = string
}

variable "ssm_kms_key_arn" {
  description = "ARN of the AWS-managed aws/ssm KMS key. An input rather than a lookup, because the bootstrap roles have no kms:ListAliases."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:kms:[a-z0-9-]+:[0-9]{12}:key/[0-9a-f-]{36}$", var.ssm_kms_key_arn))
    error_message = "ssm_kms_key_arn must be a KMS key ARN (aws kms describe-key --key-id alias/aws/ssm)."
  }
}

variable "alert_email" {
  description = "Address for alarm and budget emails. From the ALERT_EMAIL GitHub secret; never committed."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "lambda_reserved_concurrency" {
  description = "Reserved concurrency: the hard cap on simultaneous Lambda executions (R13)."
  type        = number
  default     = 5

  validation {
    condition     = var.lambda_reserved_concurrency >= 1 && var.lambda_reserved_concurrency <= 20
    error_message = "lambda_reserved_concurrency must be between 1 and 20."
  }
}

variable "lambda_memory_mb" {
  description = "Lambda memory. 512 MB keeps about 800,000 seconds a month inside the 400,000 GB-s free tier."
  type        = number
  default     = 512
}

variable "requests_per_session_per_minute" {
  description = "REQUESTS_PER_SESSION_PER_MINUTE for the app (R13): submissions per session per minute."
  type        = number
  default     = 60
}

variable "dynamodb_read_capacity" {
  description = "Provisioned RCU. All tables in the Region share the 25 RCU always-free allowance."
  type        = number
  default     = 25
}

variable "dynamodb_write_capacity" {
  description = "Provisioned WCU. All tables in the Region share the 25 WCU always-free allowance."
  type        = number
  default     = 25
}

variable "waf_rate_limit_per_5min" {
  description = "Requests per client IP per 5 minutes before the WAF blocks it (minimum 10)."
  type        = number
  default     = 300

  validation {
    condition     = var.waf_rate_limit_per_5min >= 10
    error_message = "AWS WAF rate-based rules need a limit of at least 10."
  }
}

variable "monthly_budget_usd" {
  description = "MONTHLY_BUDGET_USD: email when actual or forecast spend exceeds this (R15)."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "CloudWatch log retention. R13 requires 14; longer is on the AGENTS.md cost list."
  type        = number
  default     = 14

  validation {
    condition     = var.log_retention_days >= 1 && var.log_retention_days <= 14
    error_message = "log_retention_days must be 14 or less (AGENTS.md cost rules)."
  }
}
