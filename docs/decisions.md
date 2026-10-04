# Decisions log

Newest first. One entry per decision that changes the plan: date, decision, reason, and who made it.

| Date | Decision | Reason | By |
|---|---|---|---|
| 2026-10-04 | Keep id-token: write on the review workflow | claude-code-action needs it for its GitHub App token; --allowedTools keeps the reviewer to inline comments | Dusten |
| 2026-09-30 | Add five free MCP servers, each when its build group needs it: Context7 and Semgrep (all groups, in `.mcp.json`), Playwright (group 2), HashiCorp Terraform with read-only registry tools and AWS Pricing (group 3). | Current library docs, security scanning before each PR, UI checks, accurate Terraform, and a cost check on the $0 claim. | Dusten |
| 2026-09-30 | Build with Claude Code plan mode; review with CodeRabbit and GitHub Actions; red-team the spec with ChatGPT (free); fact-check content with Perplexity (free). Kiro, Cursor and Codex dropped. | $0 beyond the Claude subscription; less setup; the reviewer comes from a different vendor than the author. | Dusten (confirmed 2026-09-30) |
| 2026-09-30 | The app makes no LLM calls. AI coaching moves to a public read-only MCP endpoint that learners use from their own Claude (group 5.5, stretch). Scenario drafting moves to a local authoring MCP server. | Removes Bedrock cost; adds MCP on both the build side and the product side. | Dusten (confirmed 2026-09-30) |
| 2026-09-30 | Edge protection comes from CloudFront's Free flat-rate plan (WAF included) if the account is eligible; no paid standalone WAF. | $0 target. | Dusten (confirmed 2026-09-30) |
| 2026-09-29 | Hosted demo, no logins; curated scenario bank the owner approves; CISSP terms with lesson aliases. | Shareable in applications; accuracy control; exam alignment. | Dusten |

## Spec reviews

| Date | Reviewer | Findings | Accepted | Rejected | Notes |
|---|---|---|---|---|---|
| | ChatGPT (free) | | | | |
