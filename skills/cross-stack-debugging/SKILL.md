---
name: cross-stack-debugging
description: >-
  Reproduces and traces defects across Vue/TypeScript frontends, .NET/Aspire
  services, and Azure-hosted dependencies. Distinguishes diagnosis (explain cause)
  from fix (implement change). Use when symptoms span UI, API, background jobs,
  or cloud resources,   or when the user asks to debug without authorizing a fix.
---

# Cross-stack debugging

## Request mode

| Mode | Authorized actions |
| ---- | ------------------ |
| **Diagnose** | Read code and config, reproduce, trace requests, query read-only telemetry, explain root cause and blast radius |
| **Fix** | Edits and mutating commands only when the user explicitly requests implementation |

Do not expand diagnosis into unrequested fixes or refactors.

## Trace map

Follow the symptom outward and inward:

1. **Browser / Vue** — route, component, store, API client, error surfaces, network tab equivalents.
2. **API boundary** — auth policy, validation, status codes, correlation IDs, multi-surface authorization (e.g. distinct client surfaces or audiences).
3. **.NET service** — handler, domain logic, EF/data access, messaging, background workers.
4. **Aspire / local** — service references, connection strings, health, resource startup order.
5. **Azure** — App Service, Functions, Service Bus, storage, Key Vault references (read-first).

At each hop, record: expected vs actual, last known good layer, and the narrowest failing boundary.

## Workflow

1. Restate the symptom and reproduction steps; confirm environment (local Aspire vs deployed).
2. Gather evidence: logs, traces, failing test, minimal repro—before proposing theory.
3. Bisect the stack: frontend-only → contract → backend → infrastructure.
4. Form a root-cause hypothesis tied to evidence; list disconfirming checks.
5. **Diagnose:** deliver cause chain, contributing factors, and verification that would prove the fix.
6. **Fix (if authorized):** smallest change at the correct layer; add or adjust a test that fails without the fix.

## Output

- **Reproduction** — steps and prerequisites.
- **Evidence** — commands, log excerpts, file/line references (no secrets).
- **Cause chain** — ordered hops across layers.
- **Next action** — one concrete step (diagnostic or fix per mode).

For Aspire-oriented checks, see [aspire-trace-checklist.md](./aspire-trace-checklist.md).
