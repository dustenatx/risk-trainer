# R12, R13, R15 for the app module, against a mocked provider: no AWS credentials or calls.

mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      region = "us-east-2"
    }
  }

  mock_data "aws_ssm_parameter" {
    defaults = {
      arn     = "arn:aws:ssm:us-east-2:111122223333:parameter/risk-trainer/prod/x"
      value   = "mock-ciphertext"
      version = 1
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::111122223333:role/risk-trainer-app-prod"
    }
  }

  mock_resource "aws_lambda_function" {
    defaults = {
      arn = "arn:aws:lambda:us-east-2:111122223333:function:risk-trainer-prod"
    }
  }

  mock_resource "aws_lambda_function_url" {
    defaults = {
      function_url = "https://abc123.lambda-url.us-east-2.on.aws/"
    }
  }

  mock_resource "aws_wafv2_web_acl" {
    defaults = {
      arn = "arn:aws:wafv2:us-east-1:111122223333:global/webacl/risk-trainer-prod/0000"
    }
  }

  mock_resource "aws_sns_topic" {
    defaults = {
      arn = "arn:aws:sns:us-east-2:111122223333:risk-trainer-prod-alerts"
    }
  }

  mock_resource "aws_dynamodb_table" {
    defaults = {
      arn = "arn:aws:dynamodb:us-east-2:111122223333:table/risk-trainer-prod"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:us-east-2:111122223333:log-group:/aws/lambda/risk-trainer-prod"
    }
  }

  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      domain_name = "d111111abcdef8.cloudfront.net"
      arn         = "arn:aws:cloudfront::111122223333:distribution/EDFDVBD6EXAMPLE"
    }
  }
}

override_data {
  target = data.aws_ssm_parameter.origin_verify
  values = {
    arn     = "arn:aws:ssm:us-east-2:111122223333:parameter/risk-trainer/prod/origin-verify"
    value   = "ORIGIN-SECRET-0123456789abcdef0123456789abcdef"
    version = 3
  }
}

override_data {
  target = data.aws_ssm_parameter.session_secret
  values = {
    arn     = "arn:aws:ssm:us-east-2:111122223333:parameter/risk-trainer/prod/session-secret"
    value   = "AQICAH-ciphertext-only"
    version = 2
  }
}

variables {
  name                     = "risk-trainer-prod"
  lambda_zip_path          = "tests/lambda-stub.bin"
  permissions_boundary_arn = "arn:aws:iam::111122223333:policy/risk-trainer-app-boundary"
  ssm_kms_key_arn          = "arn:aws:kms:us-east-2:111122223333:key/00000000-0000-0000-0000-000000000000"
  session_secret_param     = "/risk-trainer/prod/session-secret"
  origin_verify_param      = "/risk-trainer/prod/origin-verify"
  alert_email              = "owner@example.com"
}

run "r12_https_and_managed_policies" {
  command = apply

  assert {
    condition = alltrue([
      aws_cloudfront_distribution.app.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https",
      alltrue([for b in aws_cloudfront_distribution.app.ordered_cache_behavior : b.viewer_protocol_policy == "redirect-to-https"]),
    ])
    error_message = "Every cache behavior must redirect HTTP to HTTPS."
  }

  assert {
    condition = alltrue(concat(
      [aws_cloudfront_distribution.app.default_cache_behavior[0].response_headers_policy_id == "67f7725c-6f97-4210-82d7-5512b31e9d03"],
      [for b in aws_cloudfront_distribution.app.ordered_cache_behavior : b.response_headers_policy_id == "67f7725c-6f97-4210-82d7-5512b31e9d03"],
    ))
    error_message = "Every behavior must attach the AWS-managed SecurityHeadersPolicy."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.app.default_cache_behavior[0].cache_policy_id == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
      && aws_cloudfront_distribution.app.default_cache_behavior[0].origin_request_policy_id == "b689b0a8-53d0-40ab-baf2-68738e2966ac"
      && length(aws_cloudfront_distribution.app.ordered_cache_behavior) == 1
      && aws_cloudfront_distribution.app.ordered_cache_behavior[0].path_pattern == "/static/*"
      && aws_cloudfront_distribution.app.ordered_cache_behavior[0].cache_policy_id == "658327ea-f89d-4fab-a63d-7e88639e58f6"
    )
    error_message = "Pages use CachingDisabled + AllViewerExceptHostHeader; only /static/* is cached."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.app.logging_config) == 0
    error_message = "CloudFront standard logging stays off (Privacy page)."
  }

  assert {
    condition = (
      one([for o in aws_cloudfront_distribution.app.origin : o.domain_name]) == "abc123.lambda-url.us-east-2.on.aws"
      && one(flatten([for o in aws_cloudfront_distribution.app.origin : [for c in o.custom_origin_config : c.origin_protocol_policy]])) == "https-only"
    )
    error_message = "The only origin is the Function URL, over HTTPS."
  }
}

run "r12_origin_header_and_waf" {
  command = apply

  assert {
    condition = nonsensitive(one(flatten([
      for o in aws_cloudfront_distribution.app.origin : [
        for h in o.custom_header : h.name == "X-Origin-Verify" && h.value == "ORIGIN-SECRET-0123456789abcdef0123456789abcdef"
      ]
    ])))
    error_message = "CloudFront must send the SSM origin-verify value in X-Origin-Verify."
  }

  assert {
    condition     = aws_lambda_function_url.app.authorization_type == "NONE"
    error_message = "Function URL auth is NONE; the app's origin check protects it (R12)."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.app.web_acl_id == aws_wafv2_web_acl.app.arn
      && aws_wafv2_web_acl.app.region == "us-east-1"
      && aws_wafv2_web_acl.app.scope == "CLOUDFRONT"
    )
    error_message = "The distribution uses the CLOUDFRONT-scope web ACL in us-east-1."
  }

  assert {
    condition = one([
      for r in aws_wafv2_web_acl.app.rule : (
        length(r.action[0].block) == 1
        && r.statement[0].rate_based_statement[0].aggregate_key_type == "IP"
        && r.statement[0].rate_based_statement[0].limit == 300
      )
    ])
    error_message = "One WAF rule: block above 300 requests per IP per 5 minutes."
  }

  assert {
    condition = alltrue([
      for v in [output.url, output.distribution_arn, output.web_acl_arn, output.function_url, output.table_name] :
      !strcontains(v, "ORIGIN-SECRET") && !strcontains(v, "owner@example.com")
    ])
    error_message = "No output may contain the origin secret or the alert email."
  }
}

run "r13_lambda_and_secrets" {
  command = apply

  assert {
    condition = (
      aws_lambda_function.app.runtime == "python3.14"
      && aws_lambda_function.app.architectures == tolist(["arm64"])
      && aws_lambda_function.app.handler == "risk_trainer.web.lambda_handler.handler"
      && aws_lambda_function.app.reserved_concurrent_executions == 5
    )
    error_message = "Python 3.14 on arm64, the Mangum handler, reserved concurrency 5 by default."
  }

  assert {
    condition = (
      aws_lambda_function.app.environment[0].variables["SESSION_SECRET_PARAM"] == "/risk-trainer/prod/session-secret"
      && aws_lambda_function.app.environment[0].variables["ORIGIN_VERIFY_PARAM"] == "/risk-trainer/prod/origin-verify"
      && aws_lambda_function.app.environment[0].variables["STORAGE_BACKEND"] == "dynamodb"
      && aws_lambda_function.app.environment[0].variables["SECRETS_VERSION"] == "2.3"
      && length(setintersection(keys(aws_lambda_function.app.environment[0].variables), ["SESSION_SECRET", "ORIGIN_VERIFY_SECRET"])) == 0
    )
    error_message = "Lambda gets parameter names and versions only, never a secret (R13)."
  }

  assert {
    condition = alltrue([
      for v in values(aws_lambda_function.app.environment[0].variables) :
      !strcontains(v, "ORIGIN-SECRET") && !strcontains(v, "ciphertext")
    ])
    error_message = "No Lambda environment value may contain a secret."
  }

  assert {
    condition = (
      aws_cloudwatch_log_group.app.retention_in_days == 14
      && aws_lambda_function.app.logging_config[0].log_group == aws_cloudwatch_log_group.app.name
      && aws_lambda_function.app.logging_config[0].log_format == "Text"
    )
    error_message = "14-day log group, Text format so EMF lines stay bare JSON."
  }

  assert {
    condition     = aws_iam_role.app.permissions_boundary == "arn:aws:iam::111122223333:policy/risk-trainer-app-boundary"
    error_message = "The Lambda role must carry the bootstrap permissions boundary."
  }

  assert {
    condition = toset(flatten([
      for s in jsondecode(aws_iam_role_policy.app.policy).Statement : flatten([s.Action])
      ])) == toset([
      "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
      "ssm:GetParameter", "kms:Decrypt", "logs:CreateLogStream", "logs:PutLogEvents",
    ])
    error_message = "The Lambda role grants exactly the app's actions."
  }

  assert {
    condition = anytrue([
      for s in jsondecode(aws_iam_role_policy.app.policy).Statement :
      s.Action == "kms:Decrypt"
      && s.Resource == "arn:aws:kms:us-east-2:111122223333:key/00000000-0000-0000-0000-000000000000"
      && s.Condition == { StringEquals = { "kms:ViaService" = "ssm.us-east-2.amazonaws.com" } }
    ])
    error_message = "kms:Decrypt only on the aws/ssm key, only through SSM in us-east-2."
  }

  assert {
    condition = alltrue(flatten([
      for s in jsondecode(aws_iam_role_policy.app.policy).Statement : [
        for r in flatten([s.Resource]) : r != "*"
      ]
    ]))
    error_message = "No wildcard resource in the Lambda role."
  }
}

run "r13_dynamodb_free_tier" {
  command = apply

  assert {
    condition = (
      aws_dynamodb_table.app.billing_mode == "PROVISIONED"
      && aws_dynamodb_table.app.read_capacity <= 25
      && aws_dynamodb_table.app.write_capacity <= 25
      && aws_dynamodb_table.app.deletion_protection_enabled
    )
    error_message = "Provisioned within 25 RCU / 25 WCU, with deletion protection."
  }

  assert {
    condition     = aws_dynamodb_table.app.ttl[0].enabled && aws_dynamodb_table.app.ttl[0].attribute_name == "expires_at"
    error_message = "TTL on expires_at."
  }
}

run "r13_capacity_over_free_tier_refused" {
  command = plan

  variables {
    dynamodb_write_capacity = 26
  }

  expect_failures = [aws_dynamodb_table.app]
}

run "r13_log_retention_over_14_refused" {
  command = plan

  variables {
    log_retention_days = 30
  }

  expect_failures = [var.log_retention_days]
}

run "r12_waf_limit_below_minimum_refused" {
  command = plan

  variables {
    waf_rate_limit_per_5min = 5
  }

  expect_failures = [var.waf_rate_limit_per_5min]
}

run "r15_alarms_and_budgets" {
  command = apply

  assert {
    condition     = toset([for a in aws_cloudwatch_metric_alarm.app : a.metric_name]) == toset(["Url5xxCount", "Errors", "Throttles"])
    error_message = "Alarms on Function URL 5xx, Lambda errors and Lambda throttles."
  }

  assert {
    condition = alltrue([
      for a in aws_cloudwatch_metric_alarm.app :
      a.alarm_actions == toset([aws_sns_topic.alerts.arn]) && a.evaluation_periods == 2 && a.datapoints_to_alarm == 2
    ])
    error_message = "Each alarm emails through SNS after 2 of 2 five-minute periods (sustained)."
  }

  assert {
    condition     = aws_sns_topic_subscription.email.protocol == "email"
    error_message = "Alarms go to the owner by email."
  }

  assert {
    condition = (
      aws_budgets_budget.zero_spend.limit_amount == "0.01"
      && aws_budgets_budget.monthly.limit_amount == "1.00"
      && toset([for n in aws_budgets_budget.monthly.notification : n.notification_type]) == toset(["ACTUAL", "FORECASTED"])
    )
    error_message = "A zero-spend budget and a MONTHLY_BUDGET_USD (default 1) budget on actual and forecast."
  }
}
