output "url" {
  description = "Public URL of the app."
  value       = module.app.url
}

output "distribution_arn" {
  description = "For the one-time Free flat-rate plan subscription."
  value       = module.app.distribution_arn
}

output "web_acl_arn" {
  description = "For the one-time Free flat-rate plan subscription."
  value       = module.app.web_acl_arn
}

output "function_url" {
  description = "Direct origin URL; returns 403 without the CloudFront header."
  value       = module.app.function_url
}
