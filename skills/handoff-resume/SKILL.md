---
name: handoff-resume
description: >-
  Creates and resumes portable task state under <worktree>/.agents/tasks/<task-id>
  using TASK, PLAN, HANDOFF, and DECISIONS artifacts. Checkpoint rewrites current
  state (not a transcript); resume verifies git and tests before continuing.
  Use before compaction, harness switches, or when the user asks to resume an
  active task.
---

# Handoff and resume

## Location

Task state lives in the **project worktree**, not `~/.agents`:

```text
<worktree>/.agents/
├── active-task          # contains <task-id> when resume should bind here
└── tasks/<task-id>/
    ├── TASK.md
    ├── PLAN.md
    ├── HANDOFF.md
    └── DECISIONS.md     # optional, append-only durable decisions
```

Seed files from `~/.agents/templates/handoff/` when creating a new task.

## Operations

### Checkpoint (`checkpoint`)

Run before compaction, context reset, model/harness switch, milestone, blocker, or explicit handoff.

1. Resolve `<worktree>` and `<task-id>` from `.agents/active-task` or user-provided id.
2. Inspect live **git** state (branch/worktree, HEAD, dirty files) and recent verification results.
3. **Atomically rewrite** `HANDOFF.md`—current state only, concise; not an append-only log.
4. Update `PLAN.md` milestones and current focus; adjust `TASK.md` only if scope changed materially.
5. Append durable choices to `DECISIONS.md`; do not duplicate long rationale in `HANDOFF.md`.
6. Never store secrets, regulated data, raw logs, or untrusted issue/web paste in artifacts.

### Resume (`resume`)

Run at session start when the user continues work or `.agents/active-task` points at a task.

1. Read applicable project instructions first.
2. Load **in order:** `TASK.md` → `PLAN.md` → `HANDOFF.md` → relevant `DECISIONS.md`.
3. Verify claims: `git status`, recent commits, diff vs narrative; replay critical checks from `HANDOFF.md`.
4. Mark stale assumptions; refresh checkpoint if git or checks disagree with files.
5. Execute the **exact next action** recorded in `HANDOFF.md` unless the user redirects.

Do not load an unrelated active task when the user's request targets different work.

## Archive

On completion, move `<task-id>` to `<worktree>/.agents/archive/` (e.g. `YYYY-MM/`) or remove per local policy. Promote only durable architecture or ops decisions into normal repo documentation.

See [checkpoint-guide.md](./checkpoint-guide.md) for field-level guidance on `HANDOFF.md`.
