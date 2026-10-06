# The app on Lambda behind a Function URL (R13), with the role capped by the bootstrap boundary.

data "aws_region" "current" {}

# Only the version is used, so the session secret's ciphertext (not its value) is in state.
data "aws_ssm_parameter" "session_secret" {
  name            = var.session_secret_param
  with_decryption = false
}

# CloudFront must send this value, so it is decrypted; the provider marks it sensitive.
data "aws_ssm_parameter" "origin_verify" {
  name            = var.origin_verify_param
  with_decryption = true
}

locals {
  region         = data.aws_region.current.region
  log_group_name = "/aws/lambda/${var.name}"
  parameter_arns = [data.aws_ssm_parameter.session_secret.arn, data.aws_ssm_parameter.origin_verify.arn]
}

resource "aws_cloudwatch_log_group" "app" { # nosemgrep: terraform.aws.security.aws-cloudwatch-log-group-unencrypted.aws-cloudwatch-log-group-unencrypted
  # Owner-approved skips (2026-10-06, docs/decisions.md):
  #checkov:skip=CKV_AWS_158:A customer-managed KMS key costs money (AGENTS.md cost rules).
  #checkov:skip=CKV_AWS_338:R13 and the AGENTS.md cost rules cap retention at 14 days.
  name              = local.log_group_name
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "app" {
  name                 = "risk-trainer-app-${trimprefix(var.name, "risk-trainer-")}"
  description          = "Lambda role for ${var.name}"
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      },
    ]
  })
}

# Inline only: the pipeline is denied iam:AttachRolePolicy.
resource "aws_iam_role_policy" "app" {
  name = "app"
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AppTable"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.app.arn
      },
      {
        Sid      = "AppParameters"
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = local.parameter_arns
      },
      {
        Sid       = "DecryptSsmParameters"
        Effect    = "Allow"
        Action    = "kms:Decrypt"
        Resource  = var.ssm_kms_key_arn
        Condition = { StringEquals = { "kms:ViaService" = "ssm.${local.region}.amazonaws.com" } }
      },
      {
        Sid      = "AppLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.app.arn}:*"
      },
    ]
  })
}

resource "aws_lambda_function" "app" { # nosemgrep: terraform.aws.security.aws-lambda-x-ray-tracing-not-active.aws-lambda-x-ray-tracing-not-active
  # Owner-approved skips (2026-10-06, docs/decisions.md):
  #checkov:skip=CKV_AWS_50:Would require changing the bootstrap boundary; revisit after launch.
  #checkov:skip=CKV_AWS_173:The environment holds no secrets (tested); a customer-managed KMS key costs money.
  #checkov:skip=CKV_AWS_272:Code signing needs an S3 deploy bucket and signing jobs; the gated pipeline builds and deploys the package.
  #checkov:skip=CKV_AWS_116:Invoked synchronously by the Function URL; a DLQ applies only to async invocations.
  #checkov:skip=CKV_AWS_117:No private resources; a VPC needs NAT or endpoints (AGENTS.md cost rules).
  function_name                  = var.name
  description                    = "Risk Trainer web app (FastAPI via Mangum)"
  role                           = aws_iam_role.app.arn
  runtime                        = "python3.14"
  architectures                  = ["arm64"]
  handler                        = "risk_trainer.web.lambda_handler.handler"
  filename                       = var.lambda_zip_path
  source_code_hash               = filebase64sha256(var.lambda_zip_path)
  memory_size                    = var.lambda_memory_mb
  timeout                        = 10
  reserved_concurrent_executions = var.lambda_reserved_concurrency

  # Parameter names only: Lambda reads both secrets from SSM at cold start (R13).
  environment { # nosemgrep: terraform.aws.security.aws-lambda-environment-unencrypted.aws-lambda-environment-unencrypted
    variables = {
      STORAGE_BACKEND                 = "dynamodb"
      DYNAMODB_TABLE                  = aws_dynamodb_table.app.name
      SESSION_SECRET_PARAM            = var.session_secret_param
      ORIGIN_VERIFY_PARAM             = var.origin_verify_param
      CONTENT_DIR                     = "/var/task/content"
      REQUESTS_PER_SESSION_PER_MINUTE = tostring(var.requests_per_session_per_minute)
      METRICS_NAMESPACE               = "RiskTrainer"
      LOG_LEVEL                       = "INFO"
      # Changes when either secret is rotated, so warm instances are replaced and reload it.
      SECRETS_VERSION = "${data.aws_ssm_parameter.session_secret.version}.${data.aws_ssm_parameter.origin_verify.version}"
    }
  }

  # Text format: EMF metric lines must reach CloudWatch Logs as bare JSON (R15).
  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.app.name
  }

  depends_on = [aws_iam_role_policy.app]
}

# Auth NONE: CloudFront can't sign form POSTs. The app rejects requests without the
# X-Origin-Verify header (R12). The provider adds the public invoke permissions.
resource "aws_lambda_function_url" "app" {
  #checkov:skip=CKV_AWS_258:Owner-approved (R12, 2026-10-06). OAC can't sign form POSTs; the app rejects requests without X-Origin-Verify.
  function_name      = aws_lambda_function.app.function_name
  authorization_type = "NONE"
  invoke_mode        = "BUFFERED"
}
