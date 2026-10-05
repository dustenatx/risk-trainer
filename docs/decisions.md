# Decisions log

Newest first. One entry per decision that changes the plan: date, decision, reason, and who made it.

| Date | Decision | Reason | By |
|---|---|---|---|
| 2026-10-05 | Python 3.14 (`requires-python >=3.14`). | Newest GA Lambda managed runtime (deprecation Jun 2029, per the AWS Lambda runtimes page via aws-knowledge); 3.15 is preview only. | Dusten |
| 2026-10-05 | `rt approve`/`rt retire` edit only the top-level `status`, `reviewed_by`, `reviewed_on` lines, then re-validate; no round-trip YAML library. | Keeps comments and folded text intact with no new dependency. | Dusten |
| 2026-10-05 | File name must be `<id>.yaml`; `content/drafts/` holds only drafts with null review fields; `content/scenarios/` holds only approved or retired. | Catches hand edits that bypass `rt approve`; R17 later builds file names from the ID. | Dusten |
| 2026-10-05 | `rt retire` accepts approved scenarios only; the file stays in `content/scenarios/`. | Keeps the AGENTS.md layout; the publishable loader excludes retired. | Dusten |
| 2026-10-05 | Extra content rules: approvers only when accept is allowed and no correct/acceptable overlap; rationale ≤ 120 words; 2–4 key considerations; CVSS 0–10; CISSP domains 1–8 unique; no CVE IDs; duplicate YAML keys rejected (SafeLoader subclass). | Enforces AGENTS.md content rules mechanically instead of by review. | Dusten |
| 2026-10-05 | CodeQL via GitHub default setup (owner enables it in settings), not a workflow file. | Less code to maintain; free for public repos. | Dusten |
| 2026-10-05 | Dependencies for group 5.1: `pydantic` (scenario model), `pyyaml` (safe YAML loading), `typer` (`rt` CLI); dev: `ruff`, `mypy`, `pytest`, `pytest-cov`, `types-pyyaml` (mypy stubs), `pip-audit`. Build backend `hatchling`. CI tools pinned by SHA/digest/checksum: gitleaks 8.30.1 binary, semgrep 1.179.0 image, checkov 3.3.21. | Stack in AGENTS.md; nothing beyond what 5.1 uses. | Dusten |
| 2026-10-05 | v1 launch narrowed to groups 5.1-5.3; authoring MCP (5.4) becomes v1.1 after launch; learner MCP (5.5) becomes v1.2 stretch | Spec review finding #15: one-person scope; get the public link into applications sooner | Dusten |
| 2026-10-04 | PRD v1.2 after owner review: audience split by difficulty (foundational = new analysts with job_tip; intermediate/advanced = CISSP with exam_tip); rationale required only for accept; launch at 5 scenarios (2/2/1); PEER_MIN_SAMPLE 10; rt-001 F2 prefers a compensating control | Less friction for reviewers on a phone, an earlier launch link, and the owner's judgment on F2 | Dusten |
| 2026-10-04 | Keep id-token: write on the review workflow | claude-code-action needs it for its GitHub App token; --allowedTools keeps the reviewer to inline comments | Dusten |
| 2026-09-30 | Add five free MCP servers, each when its build group needs it: Context7 and Semgrep (all groups, in `.mcp.json`), Playwright (group 2), HashiCorp Terraform with read-only registry tools and AWS Pricing (group 3). | Current library docs, security scanning before each PR, UI checks, accurate Terraform, and a cost check on the $0 claim. | Dusten |
| 2026-09-30 | Build with Claude Code plan mode; review with CodeRabbit and GitHub Actions; red-team the spec with ChatGPT (free); fact-check content with Perplexity (free). Kiro, Cursor and Codex dropped. | $0 beyond the Claude subscription; less setup; the reviewer comes from a different vendor than the author. | Dusten (confirmed 2026-09-30) |
| 2026-09-30 | The app makes no LLM calls. AI coaching moves to a public read-only MCP endpoint that learners use from their own Claude (group 5.5, stretch). Scenario drafting moves to a local authoring MCP server. | Removes Bedrock cost; adds MCP on both the build side and the product side. | Dusten (confirmed 2026-09-30) |
| 2026-09-30 | Edge protection comes from CloudFront's Free flat-rate plan (WAF included) if the account is eligible; no paid standalone WAF. | $0 target. | Dusten (confirmed 2026-09-30) |
| 2026-09-29 | Hosted demo, no logins; curated scenario bank the owner approves; CISSP terms with lesson aliases. | Shareable in applications; accuracy control; exam alignment. | Dusten |

## Spec reviews

| Date | Reviewer | Findings | Accepted | Rejected | Notes |
|---|---|---|---|---|---|
| 2026-10-05 | ChatGPT (free) | 15 | 13 (2 with changes) | 1 in part (#6: id-token is required by claude-code-action) | 1 owner decision (#15); applied as PRD v1.3 |
