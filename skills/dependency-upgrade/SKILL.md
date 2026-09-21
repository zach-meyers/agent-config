---
name: dependency-upgrade
description: >-
  Plans and executes dependency upgrades with release-note review, lockfile
  updates, central NuGet management (Directory.Packages.props), supply-chain
  checks, rollback boundaries, and verification. Enforces no package install
  scripts without explicit opt-in. Use when bumping npm, NuGet, or other
  pinned dependencies.
---

# Dependency upgrade

## Preconditions

- Read release notes and changelogs for **every** direct dependency being bumped; note breaking changes and security advisories.
- Identify the repo's package manager conventions before editing (central NuGet props, lockfiles, workspace roots).

## Rules

1. **Central NuGet** — change versions in shared `Directory.Packages.props` (or documented central file), not scattered `.csproj` pins, unless the repo explicitly diverges.
2. **Lockfiles** — regenerate and commit `packages.lock.json` / npm lock where the repo uses them; do not hand-edit lock entries.
3. **Install scripts** — never run install-time scripts by default; require explicit user opt-in (e.g. `--ignore-scripts` default per workspace policy).
4. **Scope** — one coherent upgrade wave; avoid unrelated version bumps.
5. **Rollback** — define revert boundary (git commit or single PR) before applying; keep upgrade commits isolated when possible.

## Workflow

1. Inventory current and target versions; list transitive risk hotspots.
2. Review release notes; document required code or config reactions in the task handoff if multi-step.
3. Apply version changes at the authoritative pin location.
4. Restore/build with lockfile regeneration as required by the repo.
5. Run targeted tests first, then broader build/lint/typecheck proportional to blast radius.
6. Report what changed, advisories addressed, skipped checks, and rollback command (e.g. revert commit hash).

## Supply chain

- Prefer official registries and pinned versions; note any new transitive packages with unusual publishers or install scripts.
- Do not add dependencies solely to silence warnings without user approval.

See [upgrade-checklist.md](./upgrade-checklist.md) for a copy-ready gate list.
