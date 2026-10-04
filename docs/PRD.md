# Risk Trainer — Product Requirements Document

| Field | Value |
|---|---|
| Working name | Risk Trainer ("Fix Two of Five") |
| Owner | Dusten Harrison, CISSP |
| Version | 1.1 — 30 Sep 2026 (revised 4 Oct 2026: pull-request reviewer) |
| Status | Draft for owner review |
| Build path | Claude Code (plan mode) builds; a read-only Claude review agent, CodeQL and Semgrep review each pull request in GitHub Actions; the owner approves. See the Risk Trainer Build Guide. |
| Cost constraint | $0 beyond the owner's Claude subscription |

Claude Code reads this document at the start of each build group (see `AGENTS.md`). Section 5 is split into five groups (5.1–5.5), built in that order; group 5.5 is a stretch goal. Anything not written here is out of scope until the owner adds it.

---

## 1. Summary

Risk Trainer is a hosted, no-login web app that teaches security risk prioritization the way a manager has to do it. The learner reads a short organizational scenario with five security findings and a fixed remediation capacity (typically two). They pick a risk treatment for each finding, write a one-line rationale and submit. They then get:

1. a deterministic score against an answer key the owner has approved,
2. the expert debrief (rationale, traps, exam tip),
3. once enough attempts exist, how other learners answered, and
4. optionally, AI coaching in their own Claude through the Risk Trainer MCP connector, grounded in that scenario's debrief (stretch goal, group 5.5).

The app itself makes no LLM calls. The owner drafts scenarios with Claude through a local authoring MCP server (group 5.4) and approves every one by hand.

It is the interactive companion to the owner's recorded lesson "Why We Don't Fix Everything: How Security Teams Prioritize Risk." It is aligned to CISSP Domain 1 (Security and Risk Management) concepts.

## 2. Goals and non-goals

### Goals
- G1. Teach the four risk responses (avoid, mitigate, transfer, accept) and the manager mindset: risk is likelihood × impact, and CVSS is not the same thing as risk.
- G2. Be shareable: one public URL usable in instructor applications, YouTube videos and live classes.
- G3. Stay accurate: no learner ever sees scenario content that the owner has not approved.
- G4. No AI dependency at runtime: the web exercise needs no LLM. AI coaching is optional and runs on the learner's own Claude.
- G5. Be production-grade at $0: least-privilege IAM, edge protection, cost caps, observability and CI/CD with a human approval gate, all within AWS always-free limits and with no paid AI API.

### Non-goals (v1)
- User accounts, logins, progress tracking or certificates.
- An instructor dashboard, classes or rosters.
- Live AI-generated scenarios shown to learners.
- Any official ISC2 content, practice questions or branding.
- Mobile apps, payments or multi-language support.
- Any paid LLM API called by the app (Bedrock or others). That's a v2 option only if a budget ever exists.

## 3. Users and primary use cases

| User | Use case |
|---|---|
| Self-study learner (CISSP / Security+ candidate) | Works through scenarios and learns from the debrief |
| Owner as instructor | Uses a scenario live in a class or on a recording, then shows the peer distribution |
| Hiring manager / reviewer | Opens the link from an application and completes one scenario in under 10 minutes |
| Owner as author | Drafts scenarios with Claude through the authoring MCP server, fact-checks and edits them, then approves them for publication |
| Learner using Claude (stretch) | Adds the Risk Trainer connector to Claude and works scenarios in chat, coached by their own Claude |

## 4. Core concepts

### 4.1 Risk treatments
The treatment set uses CISSP exam terminology, with the owner's lesson vocabulary shown as aliases:

| Code | UI label | Meaning |
|---|---|---|
| `avoid` | Avoid — stop the activity | Eliminate the risk by discontinuing the activity or asset that creates it |
| `mitigate_remediate` | Mitigate: remediate ("fix") | Remove the vulnerability (patch, reconfigure, replace). **Consumes one remediation slot.** |
| `mitigate_compensate` | Mitigate: compensating control ("reduce") | Lower likelihood or impact without removing the vulnerability (segment, restrict, monitor) |
| `transfer` | Transfer / share | Shift financial impact to a third party (insurance, contract). Accountability stays with the organization. |
| `accept` | Accept | A documented, informed decision to retain the risk. **Requires choosing who approves the acceptance.** |

Ignoring or rejecting a risk is not an option. The debrief says so wherever it is relevant.

### 4.2 Acceptance approvers
When a learner picks `accept`, they must choose an approver:

| Code | UI label |
|---|---|
| `security_team` | Security team |
| `it_operations` | IT operations (runs the system) |
| `business_risk_owner` | Business owner of the affected asset or process |
| `senior_management` | Executive leadership / risk committee |

Each scenario's answer key lists the correct and acceptable approvers. The teaching point: the security team advises on risk but does not accept it, and whoever runs a system doesn't necessarily own its risk.

### 4.3 Remediation capacity
Every scenario sets `context.capacity.remediation_slots` (default 2). No more than that many findings can be assigned `mitigate_remediate`. Both the UI and the server enforce this.

### 4.4 Scenario lifecycle
`draft` → (owner review) → `approved` → optionally `retired`. Only `approved` scenarios are packaged into a deployment. Drafts are visible only in the local preview.

## 5. Functional requirements

Acceptance criteria use EARS-style phrasing. "The system" means the deployed web app unless the text says the CLI.

### 5.1 Group: `content-foundation`

**R1 — Scenario schema.** As the author, I want a strict schema so that invalid content cannot ship.
- The system SHALL define scenarios as YAML files validated by a Pydantic v2 model covering the fields in Appendix A.
- The system SHALL require exactly one answer-key entry for every finding, and no key entries without a finding.
- The system SHALL require each finding's `preferred` treatment to also appear in its `acceptable` list.
- IF the answer key's `preferred` treatments assign `mitigate_remediate` to more findings than `remediation_slots`, THEN validation SHALL fail.
- IF a finding's `preferred` or `acceptable` treatments include `accept`, THEN its key SHALL define `approvers.correct` with at least one value.
- IF `status` is `approved`, THEN `reviewed_by` and `reviewed_on` SHALL be present.
- Finding IDs SHALL be unique within a scenario, and scenario IDs SHALL be unique across the repository.
- `context.organization` SHALL end with "(fictional)".

**R2 — Validation CLI.** As the author, I want one command that tells me exactly what is wrong.
- WHEN the author runs `rt validate`, THEN the CLI SHALL validate every file under `content/` and print file, field path and message for each error.
- WHEN validation fails, THEN the CLI SHALL exit non-zero.

**R3 — Approval workflow.** As the author, I want approval to be an explicit human act.
- WHEN the author runs `rt approve <scenario-id> --reviewer "<name>"`, THEN the CLI SHALL validate the scenario, set `status: approved`, `reviewed_by` and `reviewed_on` (today, ISO date), and move the file from `content/drafts/` to `content/scenarios/`.
- IF validation fails, THEN the CLI SHALL refuse to approve and leave the file unchanged.
- WHEN the author runs `rt retire <scenario-id>`, THEN the CLI SHALL set `status: retired`, and the build SHALL exclude it.

**R4 — Repository foundation and CI.**
- The repository SHALL have the layout defined in `AGENTS.md`.
- WHEN a pull request is opened or updated, THEN CI SHALL run lint (ruff), type check (mypy), tests (pytest), `rt validate`, secret scanning (gitleaks), static analysis (Semgrep), dependency audit (pip-audit), and `terraform fmt -check` / `validate` plus an IaC security scan (checkov) once `infra/` exists. A separate Claude review agent with read-only permissions and GitHub CodeQL review the same pull request.
- IF any check fails, THEN the pull request SHALL be blocked from merging.

### 5.2 Group: `exercise-flow`

**R5 — Home and scenario list.**
- The home page SHALL explain the exercise in no more than 120 words and link to a reference page describing the four treatments.
- The scenario list SHALL show each approved scenario's title, difficulty, estimated minutes and CISSP domain tags.

**R6 — Exercise page.**
- WHEN a learner opens a scenario, THEN the system SHALL show the organizational context, the remediation capacity and all five findings with their signals.
- The system SHALL require one treatment per finding and one rationale per finding (10–600 characters). An overall note (0–1,200 characters) is optional.
- WHEN a learner selects `accept`, THEN the system SHALL require an approver selection for that finding.
- WHILE the number of findings set to `mitigate_remediate` equals `remediation_slots`, the system SHALL disable further remediate selections and say why.
- The form SHALL be fully usable by keyboard and at 360 px viewport width.

**R7 — Submission and scoring.**
- WHEN a learner submits, THEN the server SHALL re-validate every constraint in R6 and reject violations with HTTP 422 and a message the learner can understand.
- The system SHALL score each finding deterministically per Section 7 and show the total as points and as a percentage.
- The score SHALL NOT depend on the rationale text or on any AI output.

**R8 — Debrief.**
- WHEN scoring completes, THEN the system SHALL show a per-finding table (learner's choice, expert choice, points), the expert rationale, key considerations, common traps and the exam tip from the answer key.
- WHERE a learner chose `accept` with an approver that is not correct, the debrief SHALL state who should approve and why.

**R9 — Peer distribution.**
- WHEN a submission is scored, THEN the system SHALL record the structured choices (scenario ID and version, per-finding treatment and approver, score, timestamp). It SHALL NOT record rationale text, overall notes, IP address or user agent.
- WHILE a scenario version has at least `PEER_MIN_SAMPLE` (default 20) recorded attempts, the debrief SHALL show the percentage of learners choosing each treatment for each finding.
- Raw attempt records SHALL expire after 180 days. Aggregate counters SHALL persist.

**R10 — Static pages.** The system SHALL include About, Privacy and "The four responses" reference pages. About SHALL state that scenarios are AI-drafted, fact-checked and human-approved; that any coaching through the MCP connector is generated by the learner's own AI assistant; and that the site is not affiliated with or endorsed by ISC2.

### 5.3 Group: `aws-deployment`

**R11 — Infrastructure as code.** All AWS resources SHALL be defined in Terraform under `infra/`, with remote state in S3 using native state locking (`use_lockfile = true`) and no DynamoDB lock table.

**R12 — Edge and security.**
- The system SHALL be served only over HTTPS through CloudFront.
- WHERE the AWS account is eligible, the distribution SHALL be subscribed to CloudFront's Free flat-rate plan and SHALL use its included WAF, with a rate-based rule per client IP.
- IF the account is not eligible, THEN the system SHALL NOT add a paid standalone WAF; it SHALL rely on application rate limits (R13) and Lambda reserved concurrency.
- CloudFront SHALL attach a response-headers policy enforcing HSTS, a strict Content-Security-Policy (no inline scripts, no third-party script origins), X-Content-Type-Options, Referrer-Policy and frame-ancestors 'none'.
- The application origin SHALL NOT be publicly reachable except through CloudFront.

**R13 — Compute, data and cost ceilings.**
- The app SHALL run on AWS Lambda (Python) behind CloudFront, with reserved concurrency set by `LAMBDA_RESERVED_CONCURRENCY` (default 5).
- Session and attempt data SHALL live in DynamoDB in provisioned-capacity mode, within the always-free allowance, with TTL enabled.
- The application SHALL rate-limit each session to `REQUESTS_PER_SESSION_PER_MINUTE` (default 60) and return HTTP 429 above it.
- Secrets SHALL live in SSM Parameter Store SecureString (standard tier) and SHALL NOT be in the repository or in Lambda environment variables in plaintext.
- CloudWatch log groups SHALL keep logs for 14 days.

**R14 — CI/CD.**
- Deployments SHALL use GitHub Actions with OIDC federation to AWS; no long-lived AWS keys.
- WHEN a change merges to `main`, THEN CI SHALL produce a Terraform plan, and apply SHALL wait for manual approval through a protected GitHub environment.
- The build SHALL package only `approved` scenarios. IF any approved scenario fails validation, THEN the build SHALL fail.

**R15 — Observability and cost.**
- Logs SHALL be structured JSON with a request ID. Rationale text SHALL never be logged.
- The system SHALL emit metrics for attempts, 429 responses and, once group 5.5 ships, MCP tool calls. Custom metrics SHALL stay within the always-free allowance.
- Alarms SHALL notify the owner by email (SNS) on sustained 5xx errors, Lambda errors and Lambda throttles.
- An AWS Budgets monthly budget SHALL alert at any spend above `MONTHLY_BUDGET_USD` (default 1).

### 5.4 Group: `authoring-mcp`

**R16 — Authoring MCP server.** As the author, I want Claude to draft and check scenarios through tools I control.
- WHEN the author runs `rt mcp`, THEN the CLI SHALL start a local MCP server over stdio, built with the official MCP Python SDK.
- The server SHALL expose exactly these tools: `get_schema`, `list_scenarios`, `validate_scenario`, `score_answers`, `save_draft` (contracts in Section 8.1).
- The server SHALL NOT expose any tool that approves, retires or deletes a scenario, or that edits `status`, `reviewed_by` or `reviewed_on`.
- Every tool SHALL validate its input and return a structured error, never a stack trace.

**R17 — Draft safety.**
- WHEN `save_draft` is called, THEN the server SHALL validate the scenario (R1) and write it only if validation passes.
- The server SHALL write only under `content/drafts/`, SHALL reject any path that resolves outside it, and SHALL force `status: draft`, `reviewed_by: null` and `reviewed_on: null`.
- IF a scenario ID already exists in `content/scenarios/`, THEN `save_draft` SHALL refuse and name the conflict.
- Tests SHALL call every tool in-process, and the owner SHALL verify the server in MCP Inspector before first use with Claude.

**R18 — Local preview.**
- WHEN the author runs `rt preview`, THEN the CLI SHALL start the app locally with drafts visible and clearly labeled "DRAFT — not published."
- Preview mode SHALL NOT be available in the deployed environment.

### 5.5 Group: `learner-mcp` (stretch, v1.1)

**R19 — Public learner MCP endpoint.**
- The deployed app SHALL serve an MCP endpoint at `/mcp` using stateless streamable HTTP with JSON responses, from the same Lambda as the web app.
- The endpoint SHALL expose the tools `list_scenarios`, `get_scenario` and `submit_answers`, and the prompt `coach_me` (contracts in Section 8.2).
- The endpoint SHALL require no login and SHALL be read-only apart from recording attempts as in R9.

**R20 — Learner MCP safety.**
- `get_scenario` SHALL NEVER return answer-key content. Only `submit_answers` returns it, after scoring.
- Only approved scenarios SHALL be reachable. Inputs SHALL be validated with the same rules as R7, and the same rate limits as R13 SHALL apply.
- Tool and prompt descriptions SHALL be static strings in code, never built from stored content.
- Rationale text submitted through MCP SHALL NOT be stored or logged (same as R9).

**R21 — Connector compatibility.**
- Before building R19–R20 in full, a one-tool spike SHALL confirm that Claude accepts the deployed endpoint as a custom connector with no authentication.
- WHEN a learner adds the endpoint as a Claude custom connector, THEN they SHALL be able to list scenarios, fetch one, submit answers and receive the debrief in chat.

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Security | OWASP ASVS Level 1 baseline. Signed session cookie (HttpOnly, Secure, SameSite=Lax); CSRF token on every state-changing request; server-side input length limits; Jinja autoescape on; htmx vendored and served from the app's own origin. MCP servers follow the least-privilege tool sets in R16 and R19. |
| Privacy | No accounts and no PII collected. Free text is not persisted and not logged, whether it arrives through the web or MCP. Privacy page states exactly what is stored and for how long. |
| Reliability | No runtime dependency on any LLM. The web exercise works whether or not the MCP endpoint exists. |
| Performance | p95 server time under 500 ms for web routes at demo load (warm). Cold starts of up to about 5 s are acceptable for v1. |
| Cost | $0 target: AWS always-free limits, CloudFront Free flat-rate plan where eligible, no paid APIs, no custom domain in v1. A $1 budget alert catches any drift. |
| Accessibility | WCAG 2.2 AA target: labels on all inputs, visible focus, color never the only signal, usable at 360 px. |
| Maintainability | Python ≥ 3.12, fully typed; mypy strict on `risk_trainer/domain` and `risk_trainer/content`; test coverage ≥ 85% on the domain and content packages. |
| Error handling | Typed domain exceptions; no stack traces shown to users; error pages show a correlation ID that matches the logs. |

## 7. Scoring model

For each finding:

| Learner treatment | Points |
|---|---|
| Equals the key's `preferred` | 2 |
| In the key's `acceptable` list (not preferred) | 1 |
| Anything else | 0 |

The acceptance approver adjusts points whenever the learner chose `accept` and `accept` scored above zero:
- approver in `approvers.correct` → no change
- approver in `approvers.acceptable` → −1 (floor 0)
- any other approver → 0 for that finding

Total = sum of points; maximum = 2 × number of findings. The same inputs always produce the same score.

## 8. MCP tool contracts

All tools take and return JSON validated with Pydantic. Errors return `{"error": {"code": "<code>", "message": "<plain words>"}}`.

### 8.1 Authoring server (local, R16–R17)

| Tool | Input | Output |
|---|---|---|
| `get_schema` | none | JSON Schema of the scenario model, plus the treatment and approver codes with their labels |
| `list_scenarios` | `status` (optional: draft, approved, retired) | `[{id, version, status, title, difficulty}]` |
| `validate_scenario` | `yaml_text` (≤ 30,000 characters) | `{valid: bool, errors: [{path, message}]}` |
| `score_answers` | `scenario_id` or `yaml_text`; `answers: [{finding_id, treatment, approver?}]` | `{points, max_points, per_finding: [{finding_id, points, preferred}]}` |
| `save_draft` | `yaml_text` | `{saved: bool, path, errors: [...]}` (writes only under `content/drafts/`) |

### 8.2 Learner server (remote, R19–R20)

| Tool or prompt | Input | Output |
|---|---|---|
| `list_scenarios` | none | Approved scenarios: `[{id, title, difficulty, estimated_minutes}]` |
| `get_scenario` | `scenario_id` | Context, capacity and findings. No answer-key fields. |
| `submit_answers` | `scenario_id`; `answers: [{finding_id, treatment, approver?, rationale (10–600 chars)}]` | Score (Section 7), per-finding comparison, expert rationale, key considerations, common traps, exam tip |
| `coach_me` (prompt) | `scenario_id` | The coaching instructions in Appendix B, to be used with the `submit_answers` result |

## 9. Definition of done for v1 launch

1. At least 8 approved scenarios covering all four treatments and all four approver roles, each fact-checked with sources listed in its approval pull request.
2. All CI checks green; coverage targets met; every review conversation resolved on every merged pull request (the branch ruleset enforces this).
3. Deployed through the approved pipeline; edge protection, headers, alarms and the budget have been checked by hand.
4. The authoring MCP server has been verified in MCP Inspector and used from Claude to draft at least 3 of the 8 scenarios.
5. Playwright smoke test passes against the deployed URL: complete a scenario, see the score and the debrief.
6. The owner has completed every scenario on a phone.

Group 5.5 (learner MCP) is not required for the v1 launch.

## 10. Deferred decisions (resolve in the Claude Code plan for the group that needs them)

- Lambda adapter: Mangum or AWS Lambda Web Adapter. Pick one actively maintained option and justify it.
- Origin pattern: CloudFront → API Gateway HTTP API → Lambda, or CloudFront → Lambda Function URL. A Function URL behind OAC requires clients to send an `x-amz-content-sha256` header on POST, which plain HTML form and htmx POSTs do not do. Also weigh which pattern stays free: API Gateway requests are not always-free.
- Whether the chosen origin works with CloudFront's Free flat-rate plan on this account.
- Group 5.5 transport details on Lambda: stateless streamable HTTP with JSON responses; how cold starts affect the connector.
- Custom domain (Route 53 + ACM) or the default CloudFront domain. Default for v1, because a domain costs money.

## 11. Out of scope for v1 (v2 candidates)

Instructor mode with class codes; learner progress with accounts; timed "exam mode"; additional exercise types (quantitative ALE/SLE/ARO calculations, BIA/RTO prioritization); scenario import from vulnerability scanner output; in-app AI critique through a paid LLM API.

---

## Appendix A — Scenario schema (reference)

The authoritative model is the Pydantic class built in group `content-foundation`. A complete example is in `content/drafts/rt-001-five-findings.yaml`.

```yaml
id: string                 # kebab-case, unique, e.g. rt-001-five-findings
version: int               # bump on any learner-visible change
status: draft | approved | retired
title: string
difficulty: foundational | intermediate | advanced
estimated_minutes: int
cissp_domains: [int]       # 1-8
learning_objectives: [string]
context:
  organization: string     # fictional
  industry: string
  size: string
  risk_appetite: string
  constraints: [string]
  capacity:
    remediation_slots: int # default 2
findings:                  # exactly 5 in v1
  - id: F1..F5
    title: string
    description: string
    asset: string
    exposure: internet_facing | internal | segmented | third_party | process
    signals:
      cvss_base: float | null       # null for misconfigurations or non-CVE risks
      known_exploited: bool
      data_involved: string | null
      compensating_controls_available: [string]
      remediation_effort: low | medium | high
      business_owner: string
answer_key:
  findings:
    F1:
      preferred: <treatment>
      acceptable: [<treatment>]      # must include preferred
      approvers:                     # required if accept is preferred or acceptable
        correct: [<approver>]
        acceptable: [<approver>]
      key_considerations: [string]   # 2-4, used by the debrief and MCP coaching
      expert_rationale: string       # owner's voice, <= 120 words
      why_not: {<treatment>: string} # optional, explains tempting wrong answers
  overall_debrief: string
  common_traps: [string]
  exam_tip: string
reviewed_by: string | null
reviewed_on: date | null
```

## Appendix B — `coach_me` prompt (learner MCP server)

Returned by the learner server's `coach_me` prompt. It lives in `prompts/coach_me.md` and is versioned with the code.

```
You are coaching a learner through a Risk Trainer scenario, the way a
security manager coaches a new analyst.

Flow: call get_scenario and present the context and the five findings.
Ask the learner for a treatment (avoid, mitigate by remediating, mitigate
with a compensating control, transfer, accept) and a one-line reason for
each finding. If they choose accept, ask who approves it. Respect the
remediation capacity. Then call submit_answers with their answers.

After scoring:
- Do not re-score and do not argue with the answer key.
- Coach the reasoning: compare each reason with the key considerations
  that submit_answers returned.
- Use only facts from the scenario and the submit_answers result. Add no
  outside facts, CVE identifiers, statistics or product names.
- Use CISSP risk-response terms. "Fix" and "reduce" are forms of
  mitigation.
- Reinforce the manager mindset: risk is likelihood x impact, CVSS is not
  risk, capacity is finite, and the risk owner accepts risk, not security.
- Be direct and brief: a few sentences per finding, then one overall tip.
```
