---
name: application-security-review
description: >-
  Security-focused review of changes and designs covering authorization, sensitive
  data handling, ASP.NET Core and Vue attack surfaces, supply chain, secrets, and
  trust boundaries with mitigations and residual risk. Use for security review,
  threat modeling of a feature, or pre-release hardening—not for generic code style.
---

# Application security review

## Mode

Read-only unless the user explicitly requests remediations. Do not exfiltrate secrets or paste live credentials into reports.

## Trust boundaries

Map data and control flow across:

- Browser / Vue (XSS, CSRF, token storage, route guards)
- Public and authenticated APIs (JWT policies, roles, multi-surface authorization across distinct client surfaces or audiences)
- Service-to-service and background workers
- Data stores, queues, and third-party webhooks
- Operator and deployment paths (config, feature flags, admin tools)

## Review areas

| Area | Questions |
| ---- | ----------- |
| **Authz** | Least privilege, policy coverage, IDOR, impersonation boundaries |
| **Data** | PII/PHI classification, logging redaction, retention, encryption at rest/transit |
| **ASP.NET** | Input validation, mass assignment, SSRF, deserialization, error leakage |
| **Vue** | DOM sinks, unsafe HTML, dependency on client-side-only checks |
| **Supply chain** | New packages, install scripts, pinned versions, known CVEs |
| **Secrets** | Hardcoded values, config drift, vault usage vs cleartext on disk |

## Workflow

1. Clarify assets, actors, and abuse scenarios relevant to the change.
2. Walk the diff and entry points; flag missing controls on new paths.
3. Classify findings: critical / high / medium / low / informational.
4. Recommend mitigations with proportionate effort; call out accepted risk explicitly.

## Output

1. **Scope and boundaries** — what was reviewed.
2. **Findings** — severity, location, exploit scenario, mitigation.
3. **Residual risk** — unreviewed areas, assumptions, follow-up tests.
4. **Verification** — SAST/DAST, dependency scan, or manual tests to run.

See [threat-boundaries.md](./threat-boundaries.md) for a lightweight boundary worksheet.
