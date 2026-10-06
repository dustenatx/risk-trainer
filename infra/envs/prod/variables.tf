# Values come from the deploy workflow as TF_VAR_* (README "Deploying"). Nothing secret is committed.

variable "lambda_zip_path" {
  description = "Package built by `make package`."
  type        = string
  default     = "../../../dist/lambda.zip"
}

variable "ssm_kms_key_arn" {
  description = "ARN of the aws/ssm KMS key. Repository variable SSM_KMS_KEY_ARN."
  type        = string
}

variable "alert_email" {
  description = "Alarm and budget email. GitHub secret ALERT_EMAIL."
  type        = string
  sensitive   = true
}

variable "lambda_reserved_concurrency" {
  description = "LAMBDA_RESERVED_CONCURRENCY (R13)."
  type        = number
  default     = 5
}

variable "requests_per_session_per_minute" {
  description = "REQUESTS_PER_SESSION_PER_MINUTE (R13)."
  type        = number
  default     = 60
}

variable "waf_rate_limit_per_5min" {
  description = "WAF requests per IP per 5 minutes (R12)."
  type        = number
  default     = 300
}

variable "monthly_budget_usd" {
  description = "MONTHLY_BUDGET_USD (R15)."
  type        = number
  default     = 1
}
