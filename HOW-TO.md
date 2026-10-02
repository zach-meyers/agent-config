# HOW-TO

Command-oriented guide for the personal toolkit at `~/.agents`. Use `/opt/homebrew/bin/python3` (Python 3.11+).

## Quick start

```bash
PY=/opt/homebrew/bin/python3
AGENTS=~/.agents

$PY $AGENTS/scripts/render.py
$PY $AGENTS/scripts/install.py --dry-run   # preview only; does not run render
$PY $AGENTS/scripts/install.py --apply     # runs render, then installs
$PY $AGENTS/scripts/doctor.py
$PY -m unittest discover -s $AGENTS/tests
```

| Goal | Command |
| ---- | ------- |
| Regenerate adapters | `$PY ~/.agents/scripts/render.py` |
| Preview install | `$PY ~/.agents/scripts/install.py --dry-run` |
| Apply install | `$PY ~/.agents/scripts/install.py --apply` |
| Health check (text) | `$PY ~/.agents/scripts/doctor.py` |
| Health check (JSON) | `$PY ~/.agents/scripts/doctor.py --json` |
| Unit tests | `$PY -m unittest discover -s ~/.agents/tests` |
| Roll back managed links/hooks | `$PY ~/.agents/scripts/install.py --uninstall` |

Run `render.py` before `--dry-run` or whenever sources or routing change. `--dry-run` validates that generated adapters match `local/render-manifest.json` and **does not** invoke `render.py` or write under `adapters/` or `local/`. `--apply` runs `render.py` automatically, then installs. Install is idempotent; collisions with non-toolkit paths are refused.

### Which command?

- **Changed routing or role prompts** → `render.py` then `install.py --apply` then `doctor.py`
- **Drift or broken symlinks** → `doctor.py`, then re-apply or `--uninstall` + `--apply`
- **Before push** → `doctor.py`, unittest, scan staged files for secrets and gitignored paths
- **In a project repo (handoff)** → `continuity.py status` / `check` from that worktree (see below)

## Shipped components (review)

| Component | Location | Notes |
| --------- | -------- | ----- |
| Operating contract | [AGENTS.md](./AGENTS.md) | Rendered to Cursor rule + Claude/Codex/Copilot adapters |
| Skills (11) | [skills/](./skills/) | **Pinned (5):** `writing-mstest-tests`, `test-anti-patterns`, `analyzing-dotnet-performance`, `azure-diagnostics`, `azure-well-architected`. **Local (6):** `change-review`, `cross-stack-debugging`, `dependency-upgrade`, `application-security-review`, `orchestrate-work`, `handoff-resume` |
| Roles (4) | [roles/prompts/](./roles/prompts/), [manifest.json](./roles/manifest.json) | `architect`, `researcher`, `implementer`, `reviewer` → `toolkit-*` adapters |
| Routing | [routing/routing.example.json](./routing/routing.example.json) + gitignored `routing.local.json` | Capability tiers; per-harness model IDs; doctor refuses silent substitution |
| Adapters | `adapters/*/generated/` | Cursor, Claude, Codex, Copilot formats from `render.py` |
| Scripts | [scripts/](./scripts/) | `render.py`, `install.py`, `doctor.py`, `continuity.py` |
| Handoff templates | [templates/handoff/](./templates/handoff/) | Seed `<worktree>/.agents/tasks/<task-id>/` |
| Provenance | [sources.lock.json](./sources.lock.json), [licenses/](./licenses/), [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) | Pinned commits, hashes, omitted upstream scripts |
| Hooks | Installed via Cursor `hooks.json`, Claude settings merge, generated Codex/Copilot hook files | **Warn-only** on this machine (doctor lists each); hooks do not write summaries into `~/.agents` |

## Activation matrix

| Harness | Routing | Install | Runtime notes |
| ------- | ------- | ------- | ------------- |
| **Cursor** | Set `enabled: true` in `routing.local.json` after real model IDs | Symlinks: `~/.cursor/rules/agent-config.mdc`, `~/.cursor/hooks.json`. Managed **copies**: `~/.cursor/agents/toolkit-*.md` | Operating contract + **native** `~/.agents/skills` verified. Role files on disk; **not** listed as custom Task subagent types in current CLI—orchestrate with built-in worker types + brief (below). |
| **Claude** | Set `enabled: true` in `routing.local.json` after aliases/IDs | Symlinks: `~/.claude/CLAUDE.md`, `~/.claude/skills/*`, `~/.claude/agents/toolkit-*.md`; hooks merged into `settings.json` | `claude doctor` reports no install issues; **not** live model-smoke verified until `claude auth login`. |
| **Codex** | Set `enabled: true`; start each role with `model: "inherit"` | Symlinks: `~/.codex/AGENTS.md`, `~/.codex/hooks.json`, `~/.codex/agents/toolkit-*.toml` | Skills load natively from `~/.agents/skills`. After install, use `/hooks`, `/skills`, and `/agent` to verify and trust the installed components. |
| **Copilot** | `enabled: false` | Not linked when disabled | Adapters under `adapters/copilot/generated/`; doctor warns `harness disabled: copilot`. |

Disabled harnesses must not have active install links; doctor fails if they do.

### Codex activation

1. In `routing/routing.local.json`, set `harnesses.codex.enabled` to `true`.
2. Set each Codex role model to `inherit` for the first activation. Use `/model` later to select and verify account-available model IDs before you pin them.
3. Run `render.py`, `install.py --dry-run`, `install.py --apply`, `doctor.py`, and the unit tests.
4. Run `codex doctor`. If it reports missing credentials, run `codex login`.
5. Start a new Codex session. Codex loads `AGENTS.md` once when the session starts.
6. Run `/hooks` and trust the toolkit hooks, then confirm the personal skills with `/skills` and the four custom roles with `/agent`.
7. Ask: `Without reading files or using tools, summarize my request modes, delegation rules, and artifact locations.`

## Directory model

- **`~/.agents`:** portable config (this repo). Task content and employer-specific plans do **not** belong here.
- **`<worktree>/.agents`:** project artifacts—`tasks/<task-id>/` for plans/checkpoints, `reviews/` for saved reviews, `research/` for substantial research, and optional `archive/`. **Git + tests** override narrative files.
- **Harness dirs:** `~/.cursor`, `~/.claude`, etc.—installed artifacts only. Native plan files, checkpoints, and session resume are **convenience**, not portable handoff.

**Gitignored:** `plans/`, `backups/`, `local/`, `routing/routing.local.json`, caches, local generated scratch ([.gitignore](./.gitignore)).

## Everyday task flow

1. Project instructions + user request (personal [AGENTS.md](./AGENTS.md) fills gaps only).
2. Read-only modes (review, status, answer) stay read-only; implement only when asked.
3. Use skills when they match (`change-review`, `writing-mstest-tests`, etc.).
4. Verify in proportion to risk; report evidence, not narrative alone.

When an output must be reusable across sessions or harnesses, save it under the worktree `.agents` tree: plans/checkpoints in `tasks/<task-id>/`, review reports in `reviews/`, research reports in `research/`, and repository-specific skills in `.agents/skills/`. Keep personal reusable skills in `~/.agents/skills/`.

## Orchestration flow

Trigger for nontrivial work: [orchestrate-work](./skills/orchestrate-work/SKILL.md) + [AGENTS.md](./AGENTS.md) orchestration section.

1. Decompose; default **one** worker, **two–four** only for independent subtasks.
2. **Disjoint file ownership**; parallel writers → separate worktrees.
3. Map work to a role (`researcher` / `implementer` / `architect` / `reviewer`) and tier in `routing.local.json`.
4. **Cursor gap:** inspect the Task types currently exposed, then use the fallback in `roles/manifest.json`: `architect → deep-reasoner`, `researcher → explore`, `implementer → fast-worker`, `reviewer → deep-reasoner`. Paste the matching portable prompt from `roles/prompts/<role>.md` and a filled [worker-brief-template.md](./skills/orchestrate-work/worker-brief-template.md). Use `security-review` only when the user explicitly requests that review.
5. **Claude:** use `~/.claude/agents/toolkit-*.md` symlinks when the product exposes them; same brief either way.
6. **Codex:** use `/agent` to inspect or select the `toolkit-*` roles. The generated TOML files enforce read-only sandboxing for researcher and reviewer.
7. Synthesize worker returns; replay checks; only the lead declares done/blocked.

**Worker brief sections (required):** Outcome; Context; Scope and ownership; Instructions and skills; Tools and mutation boundary; Commands and sources; Verification required; Return schema; Trust boundary; Stop and escalate.

## Security and independent review

- **Security-focused pass:** invoke skill `application-security-review` (read-only unless user authorizes fixes).
- **Independent review:** route to `reviewer` tier (`review-independent`); prefer a **different model family** from implementers when `routing.local.json` allows. Use `change-review` for general PR-style review. Treat all worker output as claims—inspect diffs and rerun checks.

## Handoff and resume

Portable state lives in the **project worktree**, not `~/.agents`.

```text
<worktree>/.agents/
├── active-task                 # single line: <task-id>
└── tasks/<task-id>/
    ├── TASK.md
    ├── PLAN.md
    ├── HANDOFF.md              # hot checkpoint (rewrite atomically)
    └── DECISIONS.md            # optional append-only
```

**Create:** copy [templates/handoff/](./templates/handoff/) into `tasks/<task-id>/`; write `TASK.md` and `PLAN.md`; set `active-task` to `<task-id>`.

**Checkpoint:** use skill `handoff-resume` (checkpoint)—rewrite `HANDOFF.md`, update `PLAN.md`, append durable items to `DECISIONS.md`. Before compaction, harness switch, or milestone.

**Continuity (machine, from project repo root):**

```bash
PY=/opt/homebrew/bin/python3
$PY ~/.agents/scripts/continuity.py status
$PY ~/.agents/scripts/continuity.py status --json
$PY ~/.agents/scripts/continuity.py mark-dirty    # after edits; needs active-task
$PY ~/.agents/scripts/continuity.py check         # exit 2 if missing/stale handoff
$PY ~/.agents/scripts/continuity.py check --json
```

Hooks call `continuity.py hook --harness <name> --event <Event>`; they detect stale/missing checkpoints, not semantic content.

**Resume:** new session → user says **resume active task** (or invoke `handoff-resume` resume). Order: project instructions → `TASK.md` → `PLAN.md` → `HANDOFF.md` → `DECISIONS.md` → `git status`, log, diff → replay checks in `HANDOFF.md` → continue **exact next action** in `HANDOFF.md`.

**Archive:** move `tasks/<task-id>/` to `.agents/archive/YYYY-MM/` or delete per policy; promote only durable decisions into normal repo docs.

## Model routing customization

1. Copy [routing/routing.example.json](./routing/routing.example.json) to `routing/routing.local.json` (gitignored). The example keeps **every harness `enabled: false`** with placeholder model IDs—safe to commit as a template only.
2. Replace placeholder IDs with harness-specific values for each role you use. Set `enabled: true` only for harnesses you intend to activate.
3. **Claude** mappings in this toolkit accept stable aliases: `inherit`, `haiku`, `sonnet`, `opus` (doctor rejects unknown aliases when Claude is enabled).
4. **Cursor** mappings use concrete model IDs from `cursor-agent --list-models` (or `cursor --list-models`); doctor fails if an enabled role references an ID not returned by that command when the CLI is available.
5. **Codex** mappings should use `inherit` until you verify account-available models with `/model`. After you pin a model, smoke-test that role through `/agent`; Codex does not expose a noninteractive model-list command for doctor.
6. `render.py`, then `install.py --apply`; `doctor.py` fails on placeholder IDs for **enabled** harnesses and on invalid/unavailable models where the harness exposes machine-readable discovery—**no silent substitution**.

Edit portable text in `roles/prompts/`, not model IDs in role files.

## Skill provenance and updates

1. Preview upstream at a **fixed commit**; diff against `skills/<name>/`.
2. Update skill tree; refresh [sources.lock.json](./sources.lock.json) entry (path, `content_sha256`, `omitted_files`).
3. Update [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) and `licenses/` as needed.
4. Do **not** import upstream install scripts, hooks, or MCP config without separate review. Upstream scripts omitted from `azure-diagnostics` stay omitted.
5. `render.py`, unittest, `doctor.py`, commit.

Local-only skills: record in lock only if you add a local provenance convention; no auto-update.

## Safety and limits

- **Doctor warnings (informational):** Cursor sandbox disabled and/or unrestricted approval in `~/.cursor/cli-config.json`. Toolkit does **not** change them—review and tighten in Cursor settings/CLI config if you want enforcement.
- **No secrets** or client task/ticket content in the personal remote; handoff dirs in worktrees stay out of `~/.agents` pushes.
- **Hooks:** warn-only here; blocking varies by harness (doctor lists `can_block`).
- **Package installs:** default `--ignore-scripts` / explicit opt-in per [AGENTS.md](./AGENTS.md).
- Cloud agents do not automatically receive `routing.local.json` or gitignored overlays.

## Troubleshooting

| Symptom | Action |
| ------- | ------ |
| Symlink vs managed-copy drift | `doctor.py`; `install.py --apply`; Cursor roles are **copies**—re-apply after `render.py` |
| Missing / invalid model ID | Fix `routing/routing.local.json`; `doctor.py --json` |
| Cursor skills missing | Skills live in `~/.agents/skills` (Cursor native path); confirm directory and skill frontmatter |
| Cursor `toolkit-*` not in Task menu | Known limitation—use worker types + `roles/prompts/*.md` + worker brief |
| Claude auth / policy | `claude auth login`; `claude doctor` (install only, not model smoke) |
| Codex auth missing | Run `codex doctor`, then `codex login` |
| Codex contract missing | Confirm `~/.codex/AGENTS.md` is a toolkit symlink, then restart Codex |
| Codex hooks inactive | Run `/hooks`, inspect the source, and trust the toolkit hooks |
| Codex role missing | Run `doctor.py`, restart Codex, then inspect `/agent` |
| Stale checkpoint | `continuity.py check`; compare `HANDOFF.md` to git; run `handoff-resume` checkpoint |
| Disabled harness still linked | Set `enabled: false`; `install.py --uninstall`; `doctor.py` |
| Rollback toolkit install | `install.py --uninstall` (removes **managed** symlinks/hooks only—review dry-run first) |
| Legacy Cursor plugin symlink | Doctor may warn; `install.py --apply` migrates off `~/.cursor/plugins/local/agent-config` |

Details: [AGENTS.md](./AGENTS.md), [README.md](./README.md), skill bodies under [skills/](./skills/).
