# IAM for the deploy pipeline (R14) and the ceiling for the app's Lambda role (R13).
#
# Every resource the app module (infra/modules/app) creates is named risk-trainer-* in
# var.region, except the CloudFront-scope WAF web ACL, which AWS requires in us-east-1.
# Agents can't edit this file after it merges, so the actions below cover the whole app module.
# The app module references AWS-managed CloudFront policies by their fixed IDs, so no
# cloudfront:List*/Get*Policy access (which would need Resource "*") is granted.

# The aws/ssm key must already exist: create the two SecureString parameters first (README.md).
data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}

locals {
  acct = var.account_id
  rgn  = var.region

  plan_sub   = "repo:${var.github_repository}:ref:refs/heads/main"
  deploy_sub = "repo:${var.github_repository}:environment:prod"

  arn_function   = "arn:aws:lambda:${local.rgn}:${local.acct}:function:risk-trainer-*"
  arn_table      = "arn:aws:dynamodb:${local.rgn}:${local.acct}:table/risk-trainer-*"
  arn_log_groups = ["arn:aws:logs:${local.rgn}:${local.acct}:log-group:/aws/lambda/risk-trainer-*", "arn:aws:logs:${local.rgn}:${local.acct}:log-group:/aws/lambda/risk-trainer-*:*"]
  arn_parameters = "arn:aws:ssm:${local.rgn}:${local.acct}:parameter/risk-trainer/*"
  arn_app_role   = "arn:aws:iam::${local.acct}:role/risk-trainer-app-*"
  # Distribution IDs are generated, so the ARN needs a wildcard; writes are limited by tag below.
  arn_distribution = "arn:aws:cloudfront::${local.acct}:distribution/*"
  arn_web_acl      = "arn:aws:wafv2:us-east-1:${local.acct}:global/webacl/risk-trainer-*/*"
  arn_topic        = "arn:aws:sns:${local.rgn}:${local.acct}:risk-trainer-*"
  arn_alarm        = "arn:aws:cloudwatch:${local.rgn}:${local.acct}:alarm:risk-trainer-*"
  arn_budget       = "arn:aws:budgets::${local.acct}:budget/risk-trainer-*"
  arn_state        = "${aws_s3_bucket.state.arn}/prod/terraform.tfstate"

  # Decrypting SecureStrings: only the aws/ssm key, and only through SSM in the home region.
  kms_via_ssm = {
    Sid       = "DecryptSsmParameters"
    Effect    = "Allow"
    Action    = "kms:Decrypt"
    Resource  = data.aws_kms_alias.ssm.target_key_arn
    Condition = { StringEquals = { "kms:ViaService" = "ssm.${local.rgn}.amazonaws.com" } }
  }

  trust = {
    plan   = local.plan_sub
    deploy = local.deploy_sub
  }
}

# --- Roles assumed by GitHub Actions ---

resource "aws_iam_role" "gha" {
  for_each             = local.trust
  name                 = "risk-trainer-gha-${each.key}"
  description          = "GitHub Actions ${each.key} role for ${var.github_repository}"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Federated = local.oidc_provider_arn }
        Action    = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${local.oidc_host}:aud" = local.oidc_audience
            "${local.oidc_host}:sub" = each.value
          }
        }
      },
    ]
  })
}

# --- Read access for terraform plan (both roles) ---

resource "aws_iam_policy" "read" {
  name        = "risk-trainer-gha-read"
  description = "Read the risk-trainer app resources for terraform plan."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "LambdaRead"
        Effect   = "Allow"
        Action   = ["lambda:Get*", "lambda:List*"]
        Resource = local.arn_function
      },
      {
        Sid      = "DynamoDbRead"
        Effect   = "Allow"
        Action   = ["dynamodb:Describe*", "dynamodb:ListTagsOfResource"]
        Resource = local.arn_table
      },
      {
        Sid      = "LogsRead"
        Effect   = "Allow"
        Action   = ["logs:ListTagsForResource", "logs:ListTagsLogGroup"]
        Resource = local.arn_log_groups
      },
      {
        # DescribeLogGroups has no resource-level permissions; it returns names and settings only.
        Sid      = "LogsDescribe"
        Effect   = "Allow"
        Action   = "logs:DescribeLogGroups"
        Resource = "*"
      },
      {
        Sid      = "AppRoleRead"
        Effect   = "Allow"
        Action   = ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole"]
        Resource = local.arn_app_role
      },
      {
        Sid      = "BoundaryRead"
        Effect   = "Allow"
        Action   = ["iam:GetPolicy", "iam:GetPolicyVersion"]
        Resource = aws_iam_policy.app_boundary.arn
      },
      {
        Sid      = "DistributionRead"
        Effect   = "Allow"
        Action   = ["cloudfront:GetDistribution", "cloudfront:GetDistributionConfig", "cloudfront:ListTagsForResource"]
        Resource = local.arn_distribution
      },
      {
        Sid      = "WebAclRead"
        Effect   = "Allow"
        Action   = ["wafv2:GetWebACL", "wafv2:ListTagsForResource"]
        Resource = local.arn_web_acl
      },
      {
        Sid      = "AlertsRead"
        Effect   = "Allow"
        Action   = ["sns:GetTopicAttributes", "sns:ListTagsForResource", "sns:ListSubscriptionsByTopic", "sns:GetSubscriptionAttributes"]
        Resource = local.arn_topic
      },
      {
        Sid      = "AlarmsRead"
        Effect   = "Allow"
        Action   = ["cloudwatch:DescribeAlarms", "cloudwatch:ListTagsForResource"]
        Resource = local.arn_alarm
      },
      {
        Sid      = "BudgetsRead"
        Effect   = "Allow"
        Action   = ["budgets:ViewBudget", "budgets:ListTagsForResource"]
        Resource = local.arn_budget
      },
      {
        Sid      = "ParametersRead"
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = local.arn_parameters
      },
      local.kms_via_ssm,
    ]
  })
}

# --- Write access for terraform apply (deploy role only) ---

resource "aws_iam_policy" "deploy" {
  name        = "risk-trainer-gha-deploy"
  description = "Create and update the risk-trainer app resources."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaWrite"
        Effect = "Allow"
        Action = [
          "lambda:CreateFunction", "lambda:DeleteFunction",
          "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration",
          "lambda:PutFunctionConcurrency", "lambda:DeleteFunctionConcurrency",
          "lambda:CreateFunctionUrlConfig", "lambda:UpdateFunctionUrlConfig", "lambda:DeleteFunctionUrlConfig",
          "lambda:AddPermission", "lambda:RemovePermission",
          "lambda:TagResource", "lambda:UntagResource",
        ]
        Resource = local.arn_function
      },
      {
        # The app role may only be created or given inline policies with the boundary attached.
        Sid      = "AppRoleWithBoundary"
        Effect   = "Allow"
        Action   = ["iam:CreateRole", "iam:PutRolePolicy", "iam:DeleteRolePolicy"]
        Resource = local.arn_app_role
        Condition = {
          StringEquals = { "iam:PermissionsBoundary" = aws_iam_policy.app_boundary.arn }
        }
      },
      {
        # No UpdateAssumeRolePolicy: a trust change needs a new role, created with the boundary.
        Sid      = "AppRoleManage"
        Effect   = "Allow"
        Action   = ["iam:DeleteRole", "iam:TagRole", "iam:UntagRole", "iam:UpdateRoleDescription"]
        Resource = local.arn_app_role
      },
      {
        Sid       = "PassAppRoleToLambda"
        Effect    = "Allow"
        Action    = "iam:PassRole"
        Resource  = local.arn_app_role
        Condition = { StringEquals = { "iam:PassedToService" = "lambda.amazonaws.com" } }
      },
      {
        Sid    = "DynamoDbWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:CreateTable", "dynamodb:DeleteTable", "dynamodb:UpdateTable",
          "dynamodb:UpdateTimeToLive", "dynamodb:UpdateContinuousBackups",
          "dynamodb:TagResource", "dynamodb:UntagResource",
        ]
        Resource = local.arn_table
      },
      {
        Sid    = "LogsWrite"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup", "logs:DeleteLogGroup",
          "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy",
          "logs:TagResource", "logs:UntagResource", "logs:TagLogGroup", "logs:UntagLogGroup",
        ]
        Resource = local.arn_log_groups
      },
      {
        Sid       = "DistributionCreate"
        Effect    = "Allow"
        Action    = ["cloudfront:CreateDistribution", "cloudfront:TagResource"]
        Resource  = local.arn_distribution
        Condition = { StringEquals = { "aws:RequestTag/project" = "risk-trainer" } }
      },
      {
        Sid       = "DistributionManage"
        Effect    = "Allow"
        Action    = ["cloudfront:UpdateDistribution", "cloudfront:DeleteDistribution", "cloudfront:UntagResource"]
        Resource  = local.arn_distribution
        Condition = { StringEquals = { "aws:ResourceTag/project" = "risk-trainer" } }
      },
      {
        Sid    = "WebAclWrite"
        Effect = "Allow"
        Action = [
          "wafv2:CreateWebACL", "wafv2:UpdateWebACL", "wafv2:DeleteWebACL",
          "wafv2:TagResource", "wafv2:UntagResource",
        ]
        Resource = local.arn_web_acl
      },
      {
        Sid    = "AlertsWrite"
        Effect = "Allow"
        Action = [
          "sns:CreateTopic", "sns:DeleteTopic", "sns:SetTopicAttributes",
          "sns:Subscribe", "sns:Unsubscribe", "sns:SetSubscriptionAttributes",
          "sns:TagResource", "sns:UntagResource",
        ]
        Resource = local.arn_topic
      },
      {
        Sid      = "AlarmsWrite"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:TagResource", "cloudwatch:UntagResource"]
        Resource = local.arn_alarm
      },
      {
        Sid      = "BudgetsWrite"
        Effect   = "Allow"
        Action   = ["budgets:ModifyBudget", "budgets:TagResource", "budgets:UntagResource"]
        Resource = local.arn_budget
      },
    ]
  })
}

# --- Guardrails on both roles: explicit denies win over any allow ---

resource "aws_iam_policy" "guardrails" {
  name        = "risk-trainer-gha-guardrails"
  description = "Stops the pipeline from changing its own access or starting paid plans."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "NoBoundaryRemoval"
        Effect   = "Deny"
        Action   = ["iam:DeleteRolePermissionsBoundary", "iam:PutRolePermissionsBoundary", "iam:AttachRolePolicy", "iam:UpdateAssumeRolePolicy"]
        Resource = "*"
      },
      {
        Sid    = "NoBootstrapChanges"
        Effect = "Deny"
        Action = "iam:*"
        Resource = [
          "arn:aws:iam::${local.acct}:role/risk-trainer-gha-*",
          "arn:aws:iam::${local.acct}:policy/risk-trainer-gha-*",
          "arn:aws:iam::${local.acct}:policy/risk-trainer-app-boundary",
          "arn:aws:iam::${local.acct}:oidc-provider/*",
        ]
      },
      {
        # Subscribing to a CloudFront flat-rate plan is the owner's manual step.
        Sid      = "NoPricingPlans"
        Effect   = "Deny"
        Action   = "pricingplanmanager:*"
        Resource = "*"
      },
      {
        Sid      = "NoBootstrapState"
        Effect   = "Deny"
        Action   = ["s3:PutObject", "s3:DeleteObject", "s3:PutBucketPolicy", "s3:DeleteBucket", "s3:PutBucketVersioning", "s3:PutLifecycleConfiguration"]
        Resource = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/bootstrap/*"]
      },
    ]
  })
}

# --- State access: plan only takes the lock; deploy also writes state ---

resource "aws_iam_policy" "state" {
  for_each    = local.trust
  name        = "risk-trainer-gha-state-${each.key}"
  description = "Terraform state access for the ${each.key} role (prod key only)."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ListProdState"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = aws_s3_bucket.state.arn
        Condition = { StringLike = { "s3:prefix" = ["prod/*"] } }
      },
      {
        Sid      = "ReadProdState"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = [local.arn_state, "${local.arn_state}.tflock"]
      },
      {
        Sid      = "WriteProdState"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = each.key == "deploy" ? [local.arn_state, "${local.arn_state}.tflock"] : ["${local.arn_state}.tflock"]
      },
      {
        Sid      = "ReleaseLock"
        Effect   = "Allow"
        Action   = "s3:DeleteObject"
        Resource = "${local.arn_state}.tflock"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "read" {
  for_each   = aws_iam_role.gha
  role       = each.value.name
  policy_arn = aws_iam_policy.read.arn
}

resource "aws_iam_role_policy_attachment" "guardrails" {
  for_each   = aws_iam_role.gha
  role       = each.value.name
  policy_arn = aws_iam_policy.guardrails.arn
}

resource "aws_iam_role_policy_attachment" "state" {
  for_each   = aws_iam_role.gha
  role       = each.value.name
  policy_arn = aws_iam_policy.state[each.key].arn
}

resource "aws_iam_role_policy_attachment" "deploy" {
  role       = aws_iam_role.gha["deploy"].name
  policy_arn = aws_iam_policy.deploy.arn
}

# --- Ceiling for the app's Lambda role (attached as its permissions boundary in PR 3) ---

resource "aws_iam_policy" "app_boundary" {
  name        = "risk-trainer-app-boundary"
  description = "Maximum permissions for the risk-trainer Lambda role."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AppTable"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"]
        Resource = local.arn_table
      },
      {
        Sid      = "AppParameters"
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = local.arn_parameters
      },
      local.kms_via_ssm,
      {
        Sid      = "AppLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = local.arn_log_groups
      },
    ]
  })
}
