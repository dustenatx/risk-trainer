# Risk Trainer

A hosted, no-login web app that teaches security risk prioritization: five findings, limited remediation capacity, and a CISSP risk response (avoid, mitigate, transfer, accept) for each. Requirements live in [`docs/PRD.md`](docs/PRD.md). Rules for every contributor and AI agent are in [`AGENTS.md`](AGENTS.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.14 from `.python-version`.

```sh
uv sync --locked
make check      # ruff, mypy, pytest with coverage (≥ 85% on domain + content), rt validate
make audit      # pip-audit against the locked dependencies
uv run playwright install chromium   # once, for the browser tests
make e2e        # Playwright tests of the exercise form (keyboard, 360 px, slot limit)
make package    # Lambda zip at dist/lambda.zip (arm64, Python 3.14, approved scenarios only)
```

## The `rt` CLI

| Command | What it does |
|---|---|
| `rt validate` | Validates every scenario file under `content/` and prints `file: field.path: message` for each error. Exits 1 on any error. |
| `rt approve <id> --reviewer "<name>"` | **Owner only.** Validates a draft, sets `status: approved`, `reviewed_by` and `reviewed_on` (today), and moves it from `content/drafts/` to `content/scenarios/`. |
| `rt retire <id>` | **Owner only.** Sets an approved scenario to `status: retired`. The file stays in `content/scenarios/`, and the build excludes it. |
| `rt package --out <zip> [--site-packages <dir>]` | Builds the Lambda zip: the installed dependencies plus approved scenarios only (no drafts, no retired). Writes nothing and exits 1 if any approved scenario is invalid. The zip is byte-for-byte reproducible. `make package` runs it with arm64 Python 3.14 wheels and writes `dist/lambda.zip`. |
| `rt preview [--port 8000]` | Runs the app at `http://127.0.0.1:<port>` with approved scenarios and valid drafts (DRAFT banner), in-memory storage and a random per-run session secret. It always binds to 127.0.0.1; there's no host option. |

Every command takes `--content-dir` (default `content`).

## Content layout

- `content/drafts/`: drafts only (`status: draft`, review fields null). Never deployed.
- `content/scenarios/`: approved or retired scenarios. Only approved ones are packaged.
- Each file is named `<id>.yaml`. The scenario schema is `src/risk_trainer/domain/models.py`, and the cross-field rules are in `src/risk_trainer/domain/rules.py`.

## Configuration

| Setting | Default | Notes |
|---|---|---|
| `--content-dir` (CLI option) | `content` | Content root holding `drafts/` and `scenarios/`. |
| `STORAGE_BACKEND` | **required** (no default) | `dynamodb` or `memory`. Only `rt preview` sets `memory`; the app refuses `memory` inside Lambda. |
| `SESSION_SECRET` | **required** outside Lambda | At least 32 characters; signs the session cookie. Never commit it. Refused in Lambda, which uses `SESSION_SECRET_PARAM`. |
| `SESSION_SECRET_PARAM` | none | Name of the SSM SecureString holding the session secret. Required in Lambda. |
| `ORIGIN_VERIFY_PARAM` | none | Name of the SSM SecureString holding the value CloudFront sends in `X-Origin-Verify`. Required in Lambda; requests without it get 403 (R12). |
| `ORIGIN_VERIFY_SECRET` | none | The origin header value set directly, for local testing only. Refused in Lambda. |
| `REQUESTS_PER_SESSION_PER_MINUTE` | `60` | Exercise submissions (POST) allowed per session per minute before HTTP 429 (R13). GETs aren't counted. |
| `METRICS_NAMESPACE` | `RiskTrainer` | CloudWatch namespace for the embedded-metric-format lines (`Attempts`, `RateLimited`, `RateLimitUnavailable`). |
| `DYNAMODB_TABLE` | none | Required when `STORAGE_BACKEND=dynamodb`. |
| `AWS_REGION` | boto3 default | Region of the DynamoDB table and the SSM parameters. Lambda sets it. |
| `SESSION_COOKIE_SECURE` | `true` | Sets the cookie's `Secure` flag. `rt preview` turns it off for plain-HTTP localhost. |
| `PEER_MIN_SAMPLE` | `10` | Attempts on a scenario version before the debrief shows how others answered. |
| `CONTENT_DIR` | `content` | Content root the web app loads approved scenarios from. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. Logs are JSON with a request ID. |

`src/risk_trainer/config.py` is the only place environment variables are read.

## Web app

| Route | What it shows |
|---|---|
| `/` | What the exercise is, and the approved scenarios (R5) |
| `/s/<id>` | The exercise form; POST scores it and returns the debrief (R6–R9) |
| `/responses`, `/about`, `/privacy` | Static pages (R10) |

POST bodies over 32 KB get 413 before parsing, and every POST needs the session's CSRF token. Submissions over `REQUESTS_PER_SESSION_PER_MINUTE` get 429 with `Retry-After: 60`. The app sends every security header itself (CSP, HSTS, nosniff, Referrer-Policy, frame-ancestors).

In AWS, the Lambda entry point is `risk_trainer.web.lambda_handler.handler` (Mangum, Function URL events). On first invocation it reads both secrets from SSM. When `ORIGIN_VERIFY_PARAM` is set, any request without the matching `X-Origin-Verify` header gets a bare 403, so only CloudFront can reach the app. The slot limit and accept fields use `static/app.js` (first party, no build step), and htmx 2.0.11 is vendored in `static/`.

## Infrastructure

Terraform lives in `infra/`. The owner applies `infra/bootstrap/` once (state bucket, GitHub OIDC roles); its runbook is [`infra/bootstrap/README.md`](infra/bootstrap/README.md). The app infrastructure and deploy workflow follow in group 5.3.

## CI

`.github/workflows/ci.yml` runs on every pull request: `check` (ruff, mypy, pytest, rt validate), `gitleaks`, `semgrep`, `pip-audit`, `iac` (terraform fmt, validate, `terraform test` with a mocked provider, and checkov), and `e2e` (Playwright; not a required check yet). `claude-code-review.yml` runs the read-only Claude reviewer. CodeQL runs through GitHub's default setup.
