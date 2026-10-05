# Risk Trainer

A hosted, no-login web app that teaches security risk prioritization: five findings, limited remediation capacity, and a CISSP risk response (avoid, mitigate, transfer, accept) for each. Requirements live in [`docs/PRD.md`](docs/PRD.md). Rules for every contributor and AI agent are in [`AGENTS.md`](AGENTS.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.14 from `.python-version`.

```sh
uv sync --locked
make check      # ruff, mypy, pytest with coverage (≥ 85% on domain + content), rt validate
make audit      # pip-audit against the locked dependencies
```

## The `rt` CLI

| Command | What it does |
|---|---|
| `rt validate` | Validates every scenario file under `content/` and prints `file: field.path: message` for each error. Exits 1 on any error. |
| `rt approve <id> --reviewer "<name>"` | **Owner only.** Validates a draft, sets `status: approved`, `reviewed_by` and `reviewed_on` (today), and moves it from `content/drafts/` to `content/scenarios/`. |
| `rt retire <id>` | **Owner only.** Sets an approved scenario to `status: retired`. The file stays in `content/scenarios/`, and the build excludes it. |

Every command takes `--content-dir` (default `content`).

## Content layout

- `content/drafts/`: drafts only (`status: draft`, review fields null). Never deployed.
- `content/scenarios/`: approved or retired scenarios. Only approved ones are packaged.
- Each file is named `<id>.yaml`. The scenario schema is `src/risk_trainer/domain/models.py`, and the cross-field rules are in `src/risk_trainer/domain/rules.py`.

## Configuration

| Setting | Default | Notes |
|---|---|---|
| `--content-dir` (CLI option) | `content` | Content root holding `drafts/` and `scenarios/`. |

Group 5.1 reads no environment variables. Later groups add them in `src/risk_trainer/config.py` and list them here.

## CI

`.github/workflows/ci.yml` runs on every pull request: `check` (ruff, mypy, pytest, rt validate), `gitleaks`, `semgrep`, `pip-audit`, and `iac` (terraform fmt/validate and checkov once `infra/` has Terraform). `claude-code-review.yml` runs the read-only Claude reviewer. CodeQL runs through GitHub's default setup.
