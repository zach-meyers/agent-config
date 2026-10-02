# Personal agent toolkit

`~/.agents` is the **source of truth** for a portable operating contract, skills, role prompts, routing, generated harness adapters, scripts, and tests. Harness install targets are symlinks, managed copies, or merged hook fragments produced by `render.py` and `install.py`—edit sources here, not the generated files under `~/.cursor` or `~/.claude`.

| Location | Role |
| -------- | ---- |
| `~/.agents/` | Reusable prompts, skills, routing example, adapters, tooling |
| `<worktree>/.agents/` | Task handoff (`tasks/<id>/`, `active-task`, `archive/`) |
| Harness home dirs | Installed consumers only; native plan/session state is **not** portable |

**Authority:** system → user → nearest project instructions → personal [AGENTS.md](./AGENTS.md). Project policy wins.

**Shipped:** see [HOW-TO.md](./HOW-TO.md) for commands, activation matrix, and flows. Summary: [AGENTS.md](./AGENTS.md); 11 skills (5 pinned upstream + 6 local, including `application-security-review`); four roles in `roles/prompts/` with `routing/routing.example.json`; `render` / `install` / `doctor` / `continuity`; handoff templates; `sources.lock.json` and `licenses/`; continuity hooks (warn-only where the harness cannot block).

**Safe bootstrap:** [routing/routing.example.json](./routing/routing.example.json) ships with all harnesses **`enabled: false`** and placeholder model IDs. Copy to gitignored `routing/routing.local.json`, set real Cursor IDs and Claude aliases (`inherit|haiku|sonnet|opus`), then explicitly enable each harness before `install.py --apply`.

**Typical activation:** a local `routing.local.json` may enable Cursor, Claude, and Codex; Copilot adapters are still **rendered** under `adapters/*/generated/` but stay off until enabled. Cursor operating contract and skills are runtime-verified; toolkit role files install as managed copies under `~/.cursor/agents/` but are **not** Task subagent types in the current CLI—use worker types with portable role text until that gap closes. Claude install is validated by toolkit `doctor.py`; live model smoke requires `claude auth login` (not verified here). Codex installs the contract, hooks, and custom agents under `~/.codex`; it discovers `~/.agents/skills` natively. Review the installed hooks with `/hooks`, then verify `/skills` and `/agent` in a new session.

**Install commands:** `install.py --dry-run` previews against the current render manifest without running `render.py`. `install.py --apply` renders, then installs. `--uninstall` does not render.

## Gitignored / local-only

Never commit: `plans/`, `backups/`, `local/` (e.g. `install-state.json`), `routing/routing.local.json`, macOS/editor noise, Python caches, generated adapter scratch. Inspect [.gitignore](./.gitignore) before push.

## Safety

No secrets or employer/client task state in the personal remote. Doctor **warns** if Cursor CLI has sandbox disabled or unrestricted approval—it does not change those settings; review `~/.cursor/cli-config.json` yourself. Prompts and warn-only hooks are not a substitute for sandboxing and approvals.

**Start:** [HOW-TO.md](./HOW-TO.md) quick start.
