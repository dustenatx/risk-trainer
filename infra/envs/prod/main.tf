data "aws_caller_identity" "current" {}

module "app" {
  source = "../../modules/app"

  name                     = "risk-trainer-prod"
  lambda_zip_path          = var.lambda_zip_path
  permissions_boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/risk-trainer-app-boundary"
  ssm_kms_key_arn          = var.ssm_kms_key_arn
  session_secret_param     = "/risk-trainer/prod/session-secret"
  origin_verify_param      = "/risk-trainer/prod/origin-verify"
  alert_email              = var.alert_email

  lambda_reserved_concurrency     = var.lambda_reserved_concurrency
  requests_per_session_per_minute = var.requests_per_session_per_minute
  waf_rate_limit_per_5min         = var.waf_rate_limit_per_5min
  monthly_budget_usd              = var.monthly_budget_usd
}
