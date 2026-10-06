# HTTPS-only edge in front of the Function URL (R12). Built for the CloudFront Free flat-rate
# plan: AWS-managed policies only (by their fixed IDs), 2 of the 5 allowed cache behaviors,
# standard logging off (privacy).

locals {
  # AWS-managed policy IDs, from the CloudFront Developer Guide.
  cache_policy_caching_disabled         = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  cache_policy_caching_optimized        = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  origin_request_all_viewer_except_host = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
  response_headers_security_headers     = "67f7725c-6f97-4210-82d7-5512b31e9d03"

  origin_id     = "lambda-function-url"
  origin_domain = trimsuffix(trimprefix(aws_lambda_function_url.app.function_url, "https://"), "/")
}

resource "aws_cloudfront_distribution" "app" {
  enabled         = true
  comment         = var.name
  is_ipv6_enabled = true
  http_version    = "http2and3"
  web_acl_id      = aws_wafv2_web_acl.app.arn

  origin {
    origin_id   = local.origin_id
    domain_name = local.origin_domain

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    # The app returns 403 without this header (R12). CloudFront replaces any viewer-sent copy.
    custom_header {
      name  = "X-Origin-Verify"
      value = sensitive(data.aws_ssm_parameter.origin_verify.value)
    }
  }

  # Pages and form posts: never cached; all viewer headers and cookies except Host.
  default_cache_behavior {
    target_origin_id           = local.origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = local.cache_policy_caching_disabled
    origin_request_policy_id   = local.origin_request_all_viewer_except_host
    response_headers_policy_id = local.response_headers_security_headers
    compress                   = true
  }

  # Vendored htmx, app.js and CSS: cached at the edge, so they rarely reach Lambda.
  ordered_cache_behavior {
    path_pattern               = "/static/*"
    target_origin_id           = local.origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    cache_policy_id            = local.cache_policy_caching_optimized
    response_headers_policy_id = local.response_headers_security_headers
    compress                   = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
      locations        = []
    }
  }

  # The default *.cloudfront.net certificate (no custom domain in v1, PRD §10).
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
