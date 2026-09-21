---
name: change-review
description: >-
  Reviews diffs and change sets for correctness, API compatibility, architecture
  fit, test quality, observability, and operational risk with actionable evidence.
  Use for PR review, pre-merge audit, or post-implementation review. Report-only
  unless the user explicitly requests fixes.
---

# Change review

## Mode

- **Default:** read-only. Produce findings and recommendations; do not edit files, run mutating commands, or open fix PRs unless the user explicitly asks to implement fixes.
- **Scope:** the requested diff, branch, or files—not opportunistic cleanup.

## Workflow

1. Identify the change surface: intent, touched areas, public contracts, data paths, and deployment touchpoints.
2. Read the diff and surrounding code; trace call sites and failure paths.
3. Check tests and verification evidence already present; note gaps proportionally to risk.
4. Record each finding with severity, location (file and line or symbol), impact, and a concrete suggestion.

## Review dimensions

| Area | Look for |
| ---- | -------- |
| Correctness | Logic errors, race conditions, null/edge cases, error handling |
| API compatibility | Breaking changes, versioning, dual-surface auth policies |
| Architecture | Layering, duplication, coupling, feature-flag boundaries |
| Tests | Meaningful assertions, missing cases, flaky patterns |
| Observability | Logging, metrics, correlation, sensitive data in logs |
| Operations | Migrations, rollbacks, config, feature toggles, backpressure |

## Output format

Use a compact report:

1. **Summary** — one paragraph: intent vs what the diff actually does.
2. **Findings** — ordered by severity (blocker → major → minor → nit).
3. **Verification** — what was run or what should be run before merge.
4. **Residual risk** — what remains untested or ambiguous.

For a structured template, see [review-report.md](./review-report.md).
