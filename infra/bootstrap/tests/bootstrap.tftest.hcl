# R14: OIDC trust is pinned to the sts.amazonaws.com audience and an exact subject per role.
# Runs against a mocked provider, so no AWS credentials or calls are needed.

mock_provider "aws" {
  mock_data "aws_kms_alias" {
    defaults = {
      target_key_arn = "arn:aws:kms:us-east-2:111122223333:key/00000000-0000-0000-0000-000000000000"
    }
  }

  mock_resource "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
    }
  }

  mock_resource "aws_iam_policy" {
    defaults = {
      arn = "arn:aws:iam::111122223333:policy/risk-trainer-app-boundary"
    }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::risk-trainer-tfstate-111122223333"
    }
  }
}

variables {
  account_id = "111122223333"
}

run "r14_oidc_audience_and_subjects" {
  command = apply

  assert {
    condition     = toset(aws_iam_openid_connect_provider.github[0].client_id_list) == toset(["sts.amazonaws.com"])
    error_message = "The OIDC provider must accept only the sts.amazonaws.com audience."
  }

  assert {
    condition     = aws_iam_openid_connect_provider.github[0].url == "https://token.actions.githubusercontent.com"
    error_message = "The OIDC provider must be GitHub Actions."
  }

  assert {
    condition = jsondecode(aws_iam_role.gha["plan"].assume_role_policy).Statement[0].Condition == {
      StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = "repo:dustenatx/risk-trainer:ref:refs/heads/main"
      }
    }
    error_message = "The plan role must trust only the main branch, with StringEquals on aud and sub."
  }

  assert {
    condition = jsondecode(aws_iam_role.gha["deploy"].assume_role_policy).Statement[0].Condition == {
      StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = "repo:dustenatx/risk-trainer:environment:prod"
      }
    }
    error_message = "The deploy role must trust only the prod environment, with StringEquals on aud and sub."
  }

  assert {
    condition = alltrue([
      for role in aws_iam_role.gha :
      length(jsondecode(role.assume_role_policy).Statement) == 1
    ])
    error_message = "Each trust policy must have exactly one statement."
  }
}

run "r13_kms_decrypt_only_via_ssm" {
  command = apply

  assert {
    condition = alltrue([
      for policy in [aws_iam_policy.read.policy, aws_iam_policy.app_boundary.policy] : anytrue([
        for s in jsondecode(policy).Statement :
        s.Action == "kms:Decrypt"
        && s.Resource == "arn:aws:kms:us-east-2:111122223333:key/00000000-0000-0000-0000-000000000000"
        && s.Condition == { StringEquals = { "kms:ViaService" = "ssm.us-east-2.amazonaws.com" } }
      ])
    ])
    error_message = "kms:Decrypt must be scoped to the aws/ssm key with kms:ViaService = ssm.us-east-2.amazonaws.com."
  }

  assert {
    condition = alltrue(flatten([
      for policy in [aws_iam_policy.read.policy, aws_iam_policy.deploy.policy, aws_iam_policy.app_boundary.policy] : [
        for s in jsondecode(policy).Statement :
        s.Resource != "*" if contains(flatten([s.Action]), "kms:Decrypt")
      ]
    ]))
    error_message = "No policy may grant kms:Decrypt on every key."
  }
}

run "r14_app_role_requires_boundary" {
  command = apply

  assert {
    condition = anytrue([
      for s in jsondecode(aws_iam_policy.deploy.policy).Statement :
      contains(s.Action, "iam:CreateRole")
      && s.Condition == { StringEquals = { "iam:PermissionsBoundary" = aws_iam_policy.app_boundary.arn } }
    ])
    error_message = "The deploy role may create the app role only with the permissions boundary."
  }

  assert {
    condition = anytrue([
      for s in jsondecode(aws_iam_policy.guardrails.policy).Statement :
      s.Effect == "Deny" && s.Action == "pricingplanmanager:*"
    ])
    error_message = "The pipeline must not be able to start a pricing plan subscription."
  }
}

run "r14_existing_oidc_provider" {
  command = apply

  variables {
    create_oidc_provider = false
  }

  override_data {
    target = data.aws_iam_openid_connect_provider.github[0]
    values = {
      arn = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
    }
  }

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "No provider is created when one already exists."
  }

  assert {
    condition     = jsondecode(aws_iam_role.gha["deploy"].assume_role_policy).Statement[0].Principal.Federated == "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
    error_message = "The roles must trust the existing provider."
  }
}

run "r14_managed_policies_fit_iam_limit" {
  command = apply

  # IAM managed policies are limited to 6,144 characters, not counting whitespace.
  assert {
    condition = alltrue([
      for p in concat(
        [aws_iam_policy.read, aws_iam_policy.deploy, aws_iam_policy.guardrails, aws_iam_policy.app_boundary],
        values(aws_iam_policy.state),
      ) : length(replace(p.policy, "/\\s/", "")) <= 6144
    ])
    error_message = "A managed policy is over the 6,144-character IAM limit; split it."
  }
}
