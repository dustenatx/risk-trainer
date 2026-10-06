# One table for attempts, peer aggregates and the per-session submission counter (R9, R13).
# Provisioned inside the always-free 25 RCU / 25 WCU, auto scaling off: it throttles, never bills more.

resource "aws_dynamodb_table" "app" { # nosemgrep: terraform.aws.security.aws-dynamodb-table-unencrypted.aws-dynamodb-table-unencrypted
  # Owner-approved skips (2026-10-06, docs/decisions.md). Encrypted at rest with an AWS-owned key;
  # the data is low-value and re-creatable.
  #checkov:skip=CKV_AWS_28:Point-in-time recovery costs money.
  #checkov:skip=CKV_AWS_119:A customer-managed KMS key costs money (AGENTS.md cost rules).
  #checkov:skip=CKV2_AWS_16:R13 requires auto scaling off so capacity stays in the always-free 25/25.
  name                        = var.name
  billing_mode                = "PROVISIONED"
  read_capacity               = var.dynamodb_read_capacity
  write_capacity              = var.dynamodb_write_capacity
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = true

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # Raw attempts (180 days) and submission counters (2 minutes) expire; aggregates have no TTL.
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  lifecycle {
    precondition {
      condition     = var.dynamodb_read_capacity <= 25 && var.dynamodb_write_capacity <= 25
      error_message = "Provisioned capacity must stay within the 25 RCU / 25 WCU always-free allowance (R13)."
    }
  }
}
