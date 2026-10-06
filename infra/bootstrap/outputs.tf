output "state_bucket" {
  description = "Terraform state bucket; pass it to terraform init -backend-config and set it as the TF_STATE_BUCKET repo variable."
  value       = aws_s3_bucket.state.bucket
}

output "plan_role_arn" {
  description = "Role for the deploy workflow's plan job (push to main). Repo variable AWS_PLAN_ROLE_ARN."
  value       = aws_iam_role.gha["plan"].arn
}

output "deploy_role_arn" {
  description = "Role for the apply job in the prod environment. Environment variable AWS_DEPLOY_ROLE_ARN."
  value       = aws_iam_role.gha["deploy"].arn
}

output "app_boundary_arn" {
  description = "Permissions boundary the app module must attach to the Lambda role."
  value       = aws_iam_policy.app_boundary.arn
}
