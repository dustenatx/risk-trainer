# Email alarms on sustained errors and throttles (R15). 3 of the 10 always-free alarms.
# Lambda's Errors metric doesn't see app-handled 500s, so 5xx is alarmed on the Function URL.

resource "aws_sns_topic" "alerts" {
  # No KMS: CloudWatch alarms can't publish to a topic encrypted with the AWS-managed aws/sns key,
  # and a customer-managed key is on the AGENTS.md cost list.
  name = "${var.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

locals {
  alarms = {
    "url-5xx" = {
      metric      = "Url5xxCount"
      threshold   = 5
      description = "Function URL returned 5xx responses for 10 minutes"
    }
    "lambda-errors" = {
      metric      = "Errors"
      threshold   = 1
      description = "Lambda invocations failed for 10 minutes"
    }
    "lambda-throttles" = {
      metric      = "Throttles"
      threshold   = 1
      description = "Lambda hit reserved concurrency for 10 minutes"
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "app" {
  for_each            = local.alarms
  alarm_name          = "${var.name}-${each.key}"
  alarm_description   = each.value.description
  namespace           = "AWS/Lambda"
  metric_name         = each.value.metric
  dimensions          = { FunctionName = aws_lambda_function.app.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = each.value.threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}
