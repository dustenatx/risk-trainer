# WAF web ACL for the distribution (R12). CloudFront-scope web ACLs must be in us-east-1.
# Covered by the Free flat-rate plan once the owner subscribes (1 of its 5 rules). Until then
# it bills pay-as-you-go: $5 per month for the web ACL plus $1 per rule, prorated hourly.

resource "aws_wafv2_web_acl" "app" {
  # Owner-approved skips (2026-10-06, docs/decisions.md):
  #checkov:skip=CKV_AWS_192:Python app, no Java; the Log4j managed rule set doesn't apply.
  #checkov:skip=CKV2_AWS_31:WAF request logging needs the Pro plan (cost).
  region      = "us-east-1"
  name        = var.name
  description = "Per-IP rate limit for ${var.name}"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "rate-limit-per-ip"
    priority = 0

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit                 = var.waf_rate_limit_per_5min
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-limit-per-ip"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = var.name
    sampled_requests_enabled   = true
  }
}
