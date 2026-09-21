# Checkpoint guide

`HANDOFF.md` fields (rewrite wholesale each checkpoint):

| Section | Content |
| ------- | ------- |
| Goal | One-line unchanged summary from `TASK.md` |
| Completed | Done work with evidence (commits, files, check results) |
| Next action | Single exact step for the next instance |
| Git state | Branch/worktree, HEAD, notable dirty paths |
| Verification | Commands and pass/fail/not-run |
| Blockers and risks | Or "none" |
| Decisions pointer | Reference `DECISIONS.md`; no long essays |

**Stale detection:** if HEAD, diff, or check results disagree with the checkpoint, treat narrative as suspect and refresh before continuing.
