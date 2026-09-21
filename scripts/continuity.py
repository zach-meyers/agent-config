#!/usr/bin/env python3
"""Portable continuity checks and harness hook adapter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _toolkit import (
    HOOK_EVENTS,
    continuity_status,
    git_head,
    git_worktree_root,
    resolve_active_task,
    write_dirty_marker,
)


def _tracks_dirty(harness: str, event: str) -> bool:
    return bool(HOOK_EVENTS.get(harness, {}).get(event, {}).get("tracks_dirty"))


def cmd_status(args: argparse.Namespace) -> int:
    worktree = git_worktree_root(Path.cwd())
    if not worktree:
        print("no git worktree")
        return 1
    status = continuity_status(worktree)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0
    task_id = status.get("active_task_id") or "(none)"
    print(f"worktree: {status['worktree']}")
    print(f"active_task_id: {task_id}")
    print(f"handoff_state: {status['handoff_state']}")
    print(f"head: {status.get('head')}")
    if status.get("error"):
        print(f"error: {status['error']}")
    return 0


def cmd_mark_dirty(args: argparse.Namespace) -> int:
    worktree = git_worktree_root(Path.cwd())
    if not worktree:
        print("no git worktree", file=sys.stderr)
        return 1
    task_id, task_dir, error = resolve_active_task(worktree)
    if error or not task_id or not task_dir:
        print(error or "no active task", file=sys.stderr)
        return 1
    write_dirty_marker(task_dir, git_head(worktree))
    print(f"marked dirty for task {task_id}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    worktree = git_worktree_root(Path.cwd())
    if not worktree:
        print("no git worktree", file=sys.stderr)
        return 1
    status = continuity_status(worktree)
    if status.get("error"):
        if args.json:
            print(json.dumps(status, indent=2, sort_keys=True))
        else:
            print(f"continuity error: {status['error']}", file=sys.stderr)
        return 2
    if not status.get("active_task_id"):
        if args.json:
            print(json.dumps(status, indent=2, sort_keys=True))
        else:
            print("no active task; continuity check skipped")
        return 0
    stale = status.get("stale") or status.get("handoff_state") == "missing"
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
        return 2 if stale else 0
    if stale:
        print(f"handoff {status['handoff_state']}")
        return 2
    print("handoff current")
    return 0


def _message_for_status(status: dict, event: str) -> str:
    task_id = status.get("active_task_id")
    if not task_id:
        return ""
    if event in {"sessionStart", "SessionStart"}:
        return (
            f"Active task `{task_id}` is bound in this worktree. "
            "If the user asked to continue, invoke the handoff-resume skill before editing."
        )
    if status.get("handoff_state") == "missing":
        return (
            f"Task `{task_id}` has no HANDOFF.md checkpoint. "
            "Run handoff-resume checkpoint before compaction or stopping."
        )
    if status.get("stale"):
        return (
            f"Task `{task_id}` checkpoint looks stale relative to git activity. "
            "Refresh HANDOFF.md via handoff-resume checkpoint."
        )
    return ""


def _mark_dirty_from_hook(worktree: Path) -> None:
    _task_id, task_dir, _error = resolve_active_task(worktree)
    if task_dir and task_dir.is_dir():
        write_dirty_marker(task_dir, git_head(worktree))


def cmd_hook(args: argparse.Namespace) -> int:
    harness = args.harness
    event = args.event
    if harness not in HOOK_EVENTS:
        print(f"unknown harness: {harness}", file=sys.stderr)
        return 1
    if event not in HOOK_EVENTS[harness]:
        print(f"unknown event {event} for harness {harness}", file=sys.stderr)
        return 1

    worktree = git_worktree_root(Path.cwd())
    if not worktree:
        print("warning: no git worktree; hook no-op", file=sys.stderr)
        print("{}")
        return 0

    if _tracks_dirty(harness, event):
        _mark_dirty_from_hook(worktree)
        print("{}")
        return 0

    status = continuity_status(worktree)
    message = _message_for_status(status, event)
    can_block = HOOK_EVENTS[harness][event]["can_block"]
    needs_action = bool(message) and status.get("handoff_state") in {"missing", "stale"}

    if harness == "cursor":
        if not message:
            print("{}")
            return 0
        if event == "stop" and needs_action and can_block:
            print(json.dumps({"followup_message": message}))
            return 2
        print(json.dumps({"user_message": message}))
        return 0

    if harness == "claude":
        if not message:
            print("{}")
            return 0
        if event in {"PreCompact", "Stop"} and needs_action and can_block:
            print(json.dumps({"decision": "block", "reason": message}))
            return 0
        print(json.dumps({"hookSpecificOutput": {"additionalContext": message}}))
        return 0

    if harness == "codex":
        if not message:
            print("{}")
            return 0
        if event in {"PreCompact", "Stop"} and needs_action and can_block:
            print(json.dumps({"decision": "block", "reason": message}))
            return 0
        print(json.dumps({"additionalContext": message}))
        return 0

    if harness == "copilot":
        if not message:
            print("{}")
            return 0
        if needs_action and not can_block:
            print(f"warning: {message}", file=sys.stderr)
        if event in {"agentStop", "subagentStop"} and needs_action and can_block:
            print(json.dumps({"decision": "block", "reason": message}))
            return 0
        print(json.dumps({"additionalContext": message}))
        return 0

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuity status and harness hooks.")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show continuity status.")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    mark = sub.add_parser("mark-dirty", help="Record non-sensitive dirty marker for active task.")
    mark.set_defaults(func=cmd_mark_dirty)

    check = sub.add_parser("check", help="Exit nonzero when checkpoint missing/stale.")
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_check)

    hook = sub.add_parser("hook", help="Harness lifecycle hook entrypoint.")
    hook.add_argument("--harness", required=True)
    hook.add_argument("--event", required=True)
    hook.set_defaults(func=cmd_hook)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
