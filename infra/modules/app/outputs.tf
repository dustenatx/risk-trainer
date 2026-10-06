# No output exposes the origin-verify value or the alert email.

output "url" {
  description = "Public URL of the app."
  value       = "https://${aws_cloudfront_distribution.app.domain_name}/"
}

output "distribution_arn" {
  description = "For the one-time Free flat-rate plan subscription (README)."
  value       = aws_cloudfront_distribution.app.arn
}

output "web_acl_arn" {
  description = "For the one-time Free flat-rate plan subscription (README)."
  value       = aws_wafv2_web_acl.app.arn
}

output "function_url" {
  description = "Direct origin URL. Requests here get 403 without the CloudFront header."
  value       = aws_lambda_function_url.app.function_url
}

output "table_name" {
  description = "DynamoDB table."
  value       = aws_dynamodb_table.app.name
}
