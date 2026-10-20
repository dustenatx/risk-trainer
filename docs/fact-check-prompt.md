# Fact-check prompt (Perplexity)

Use this for every new scenario before you open its save pull request. Claude fills in the placeholders from the draft; you paste the result into Perplexity yourself. Claude never calls Perplexity. Then put the filled prompt, the key findings with their source links, and your triage (accepted and reworded, or rejected with a reason) in the save PR body. See "Authoring a new scenario" in [`README.md`](../README.md).

Copy everything below the line.

---

You are fact-checking a training scenario for security risk prioritization. A learner gets five findings, limited remediation capacity, and chooses a CISSP risk response (avoid, mitigate, transfer, accept) for each. The YAML below holds the findings and the answer key with the expert's reasoning.

Scenario: `{{SCENARIO_ID}}`
About AI systems: `{{AI_SCENARIO: yes/no}}`
Contains numbers: `{{HAS_NUMBERS: yes/no}}`

## Scope

- The scenario facts are given. Don't fact-check the organization (it's fictional), the remediation slots, timing, people, roles or the findings' details.
- Check only claims about standards, terms and practice. Examples: what "transfer" does and doesn't shift, who may accept risk, what CVSS measures, what a control does, how a framework defines a term.

## Sources

Check against these, in this order, and link the section you rely on:

- NIST SP 800-39, *Managing Information Security Risk*
- NIST SP 800-30 Rev. 1, *Guide for Conducting Risk Assessments*
- ISC2 CISSP exam outline, current edition

If "About AI systems" is yes, also use:

- NIST AI 100-1, *AI Risk Management Framework (AI RMF 1.0)*
- NIST AI 600-1, *AI RMF: Generative Artificial Intelligence Profile*
- OWASP Top 10 for LLM Applications 2025

Prefer these primary sources. If a claim has only secondary support, say so.

## Numbers

If "Contains numbers" is yes, recompute every calculation (for example SLE, ARO, ALE, cost against benefit) and say whether each figure is plausible for the context the scenario gives. Report any arithmetic error with the corrected value.

## Output

For each claim you flag, give:

1. **Quote:** the exact text, with its YAML path (for example `answer_key.findings.F2.expert_rationale`).
2. **Verdict:** supported, overstated or unsupported.
3. **Source:** document, section and link.
4. **Suggested rewording:** for overstated or unsupported claims, in the same plain voice and no longer than the original.

Then list the claims you checked and found supported, one line each, without detail. Don't rewrite the whole scenario.

## Scenario (findings through answer key)

```yaml
{{PASTE content/drafts/<id>.yaml FROM findings: THROUGH reviewed_by:}}
```
