#!/usr/bin/env python3
"""Install or remove collision-safe symlinks for rendered harness adapters."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from _toolkit import (
    PLANS_DIRECTORY_VALUE,
    TOOLKIT_VERSION,
    agents_root,
    create_symlink,
    generated_dir,
    harness_enabled,
    has_toolkit_generated_marker,
    home_dir,
    install_state_path,
    is_toolkit_hook_command,
    iter_roles,
    iter_skills,
    load_json,
    load_routing,
    preflight_symlink,
    remove_symlink,
    render_manifest_path,
    sha256_file,
    sha256_text,
    symlink_ok,
    write_json_atomic,
    write_text_atomic,
)


def require_current_render(root: Path) -> list[str]:
    """Ensure adapters/*/generated matches local/render-manifest.json (no render side effects)."""
    manifest_path = render_manifest_path(root)
    if not manifest_path.is_file():
        return ["render manifest missing; run render.py first"]
    try:
        manifest = load_json(manifest_path)
    except (json.JSONDecodeError, ValueError) as exc:
        return [f"render manifest invalid; run render.py first ({exc})"]
    errors: list[str] = []
    for rel, digest in manifest.get("files", {}).items():
        path = root / rel
        if not path.is_file():
            errors.append(f"rendered file missing: {rel}; run render.py first")
            continue
        if sha256_text(path.read_text(encoding="utf-8")) != digest:
            errors.append(f"render drift: {rel}; run render.py first")
    return errors


def run_render(root: Path) -> None:
    script = root / "scripts" / "render.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=root / "scripts",
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def planned_symlinks(root: Path, routing: dict[str, Any]) -> list[dict[str, str]]:
    home = home_dir()
    gen = {name: generated_dir(root, name) for name in ("cursor", "claude", "codex", "copilot")}
    links: list[dict[str, str]] = []

    if harness_enabled(routing, "cursor"):
        cursor_gen = gen["cursor"]
        links.extend(
            [
                {
                    "path": str(home / ".cursor" / "rules" / "agent-config.mdc"),
                    "source": str(cursor_gen / "rules" / "operating-contract.mdc"),
                    "kind": "symlink",
                    "harness": "cursor",
                },
                {
                    "path": str(home / ".cursor" / "hooks.json"),
                    "source": str(cursor_gen / "hooks" / "hooks.json"),
                    "kind": "symlink",
                    "harness": "cursor",
                },
            ]
        )
    if harness_enabled(routing, "claude"):
        links.append(
            {
                "path": str(home / ".claude" / "CLAUDE.md"),
                "source": str(gen["claude"] / "CLAUDE.md"),
                "kind": "symlink",
                "harness": "claude",
            }
        )
        for skill in iter_skills(root):
            links.append(
                {
                    "path": str(home / ".claude" / "skills" / skill),
                    "source": str(root / "skills" / skill),
                    "kind": "symlink",
                    "harness": "claude",
                }
            )
        for role in iter_roles(root):
            adapter = role["adapterName"]
            links.append(
                {
                    "path": str(home / ".claude" / "agents" / f"{adapter}.md"),
                    "source": str(gen["claude"] / "agents" / f"{adapter}.md"),
                    "kind": "symlink",
                    "harness": "claude",
                }
            )

    if harness_enabled(routing, "codex"):
        links.extend(
            [
                {
                    "path": str(home / ".codex" / "AGENTS.md"),
                    "source": str(gen["codex"] / "AGENTS.md"),
                    "kind": "symlink",
                    "harness": "codex",
                },
                {
                    "path": str(home / ".codex" / "hooks.json"),
                    "source": str(gen["codex"] / "hooks.json"),
                    "kind": "symlink",
                    "harness": "codex",
                },
            ]
        )
        for role in iter_roles(root):
            adapter = role["adapterName"]
            links.append(
                {
                    "path": str(home / ".codex" / "agents" / f"{adapter}.toml"),
                    "source": str(gen["codex"] / "agents" / f"{adapter}.toml"),
                    "kind": "symlink",
                    "harness": "codex",
                }
            )

    if harness_enabled(routing, "copilot"):
        links.extend(
            [
                {
                    "path": str(home / ".copilot" / "copilot-instructions.md"),
                    "source": str(gen["copilot"] / "copilot-instructions.md"),
                    "kind": "symlink",
                    "harness": "copilot",
                },
                {
                    "path": str(home / ".copilot" / "hooks" / "toolkit-continuity.json"),
                    "source": str(gen["copilot"] / "hooks" / "toolkit-continuity.json"),
                    "kind": "symlink",
                    "harness": "copilot",
                },
            ]
        )
        for role in iter_roles(root):
            adapter = role["adapterName"]
            links.append(
                {
                    "path": str(home / ".copilot" / "agents" / f"{adapter}.agent.md"),
                    "source": str(gen["copilot"] / "agents" / f"{adapter}.agent.md"),
                    "kind": "symlink",
                    "harness": "copilot",
                }
            )

    return links


def planned_managed_copies(root: Path, routing: dict[str, Any]) -> list[dict[str, str]]:
    if not harness_enabled(routing, "cursor"):
        return []
    home = home_dir()
    cursor_gen = generated_dir(root, "cursor")
    copies: list[dict[str, str]] = []
    for role in iter_roles(root):
        adapter = role["adapterName"]
        copies.append(
            {
                "path": str(home / ".cursor" / "agents" / f"{adapter}.md"),
                "source": str(cursor_gen / "agents" / f"{adapter}.md"),
                "kind": "managed_copy",
                "harness": "cursor",
            }
        )
    return copies


def prior_managed_copy(prior: dict[str, Any] | None, dest_path: str) -> dict[str, Any] | None:
    if not prior:
        return None
    for entry in prior.get("managed_copies", []):
        if isinstance(entry, dict) and entry.get("path") == dest_path:
            return entry
    return None


def preflight_managed_copy(
    dest: Path,
    source: Path,
    prior: dict[str, Any] | None,
) -> str | None:
    if not source.is_file():
        return f"missing source: {source}"
    if not dest.exists() and not dest.is_symlink():
        return None
    if dest.is_symlink():
        if symlink_ok(dest, source):
            return None
        return f"foreign symlink: {dest}"
    if not dest.is_file():
        return f"blocked path: {dest}"
    prior_entry = prior_managed_copy(prior, str(dest))
    if not prior_entry:
        return f"regular file exists: {dest}"
    content = dest.read_text(encoding="utf-8")
    installed_hash = sha256_text(content)
    if installed_hash == prior_entry.get("installed_sha256"):
        return None
    if has_toolkit_generated_marker(content):
        return None
    return f"user-modified managed copy: {dest}"


def managed_copy_record(entry: dict[str, str], source_hash: str, installed_hash: str) -> dict[str, str]:
    return {
        **entry,
        "kind": "managed_copy",
        "source_sha256": source_hash,
        "installed_sha256": installed_hash,
    }


def apply_managed_copy(
    entry: dict[str, str],
    prior: dict[str, Any] | None,
) -> tuple[dict[str, str], dict[str, Any], bool]:
    """Install or update one managed copy. Returns (state record, rollback spec, changed)."""
    dest = Path(entry["path"])
    source = Path(entry["source"])
    content = source.read_text(encoding="utf-8")
    source_hash = sha256_text(content)

    rollback: dict[str, Any] = {"path": str(dest)}
    changed = True

    if dest.is_symlink():
        rollback["was"] = "symlink"
        rollback["target"] = str(dest.resolve())
        dest.unlink()
    elif dest.is_file():
        if sha256_file(dest) == source_hash:
            changed = False
            record = managed_copy_record(entry, source_hash, source_hash)
            return record, {"path": str(dest), "was": "unchanged"}, False
        rollback["was"] = "file"
        rollback["content"] = dest.read_text(encoding="utf-8")
    else:
        rollback["was"] = "absent"

    dest.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(dest, content)
    record = managed_copy_record(entry, source_hash, source_hash)
    return record, rollback, changed


def rollback_managed_copies(rollbacks: list[dict[str, Any]]) -> None:
    for spec in reversed(rollbacks):
        if spec.get("was") == "unchanged":
            continue
        path = Path(spec["path"])
        mode = spec.get("was")
        if mode == "absent":
            if path.is_file() and not path.is_symlink():
                path.unlink()
            continue
        if mode == "file":
            write_text_atomic(path, spec["content"])
            continue
        if mode == "symlink":
            if path.exists() or path.is_symlink():
                path.unlink()
            create_symlink(path, Path(spec["target"]))


def remove_managed_copy(entry: dict[str, Any], *, dry_run: bool) -> tuple[str, str | None]:
    dest = Path(entry["path"])
    if dest.is_symlink() or not dest.is_file():
        return "missing", None
    current_hash = sha256_file(dest)
    expected = str(entry.get("installed_sha256", ""))
    if current_hash != expected:
        return "preserved", f"user-modified managed copy: {dest}"
    if dry_run:
        return "would_remove", None
    dest.unlink()
    return "removed", None


def _strip_toolkit_hooks(data: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(data)
    hooks = merged.get("hooks")
    if not isinstance(hooks, dict):
        return merged
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        kept_groups: list[Any] = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            hook_items = group.get("hooks", [])
            if not isinstance(hook_items, list):
                kept_groups.append(group)
                continue
            kept_items = [
                item
                for item in hook_items
                if not (
                    isinstance(item, dict)
                    and is_toolkit_hook_command(str(item.get("command", "")))
                )
            ]
            if kept_items:
                clone = copy.deepcopy(group)
                clone["hooks"] = kept_items
                kept_groups.append(clone)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    return merged


def preflight_claude_settings(root: Path) -> tuple[dict[str, Any] | None, bool, list[str], list[str]]:
    """Return merged settings dict, plans_added flag, actions, errors."""
    home = home_dir()
    settings_path = home / ".claude" / "settings.json"
    fragment_path = generated_dir(root, "claude") / "settings-hooks-fragment.json"
    actions: list[str] = []
    errors: list[str] = []

    if not fragment_path.is_file():
        return None, False, actions, ["missing claude hook fragment; run render first"]

    fragment = load_json(fragment_path)
    toolkit_hooks = fragment.get("hooks", {})
    if not isinstance(toolkit_hooks, dict):
        return None, False, actions, ["invalid claude hook fragment shape"]

    existing: dict[str, Any] = {}
    if settings_path.is_file():
        try:
            existing = load_json(settings_path)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, False, actions, [f"invalid JSON: {settings_path} ({exc})"]
        if not isinstance(existing, dict):
            return None, False, actions, [f"settings root must be object: {settings_path}"]

    merged = _strip_toolkit_hooks(existing)
    merged_hooks = merged.setdefault("hooks", {})
    if not isinstance(merged_hooks, dict):
        return None, False, actions, ["settings hooks must be an object"]

    for event, entries in toolkit_hooks.items():
        current = merged_hooks.setdefault(event, [])
        if not isinstance(current, list):
            return None, False, actions, [f"cannot merge hooks: {event} is not a list"]
        for entry in entries:
            if not isinstance(entry, dict):
                return None, False, actions, [f"invalid hook group for {event}"]
            current.append(copy.deepcopy(entry))

    plans_added = False
    if merged.get("plansDirectory"):
        actions.append("plansDirectory already set; leaving unchanged")
    else:
        merged["plansDirectory"] = PLANS_DIRECTORY_VALUE
        plans_added = True
        actions.append(f"set plansDirectory -> {PLANS_DIRECTORY_VALUE}")

    actions.append(f"merge toolkit hooks into {settings_path}")
    return merged, plans_added, actions, errors


def format_claude_actions_for_output(actions: list[str], *, dry_run: bool) -> list[str]:
    formatted: list[str] = []
    for line in actions:
        if line.startswith("set plansDirectory"):
            formatted.append(f"would {line}" if dry_run else line)
        elif line.startswith("merge toolkit hooks into "):
            path = line.removeprefix("merge toolkit hooks into ")
            if dry_run:
                formatted.append(f"would merge toolkit hooks into {path}")
            else:
                formatted.append(f"merged toolkit hooks into {path}")
        else:
            formatted.append(line)
    return formatted


def read_claude_settings_snapshot() -> tuple[bool, str | None]:
    settings_path = home_dir() / ".claude" / "settings.json"
    if settings_path.is_file():
        return True, settings_path.read_text(encoding="utf-8")
    return False, None


def restore_claude_settings_snapshot(existed_before: bool, original_content: str | None) -> None:
    settings_path = home_dir() / ".claude" / "settings.json"
    if existed_before:
        if original_content is not None:
            write_text_atomic(settings_path, original_content)
        return
    if settings_path.is_file():
        settings_path.unlink()


def write_install_state(root: Path, state: dict[str, Any]) -> None:
    if os.environ.get("TOOLKIT_TEST_FAIL_INSTALL_STATE") == "1":
        raise RuntimeError("install state commit failed (test injection)")
    write_json_atomic(install_state_path(root), state)


def apply_claude_settings(merged: dict[str, Any]) -> None:
    settings_path = home_dir() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(settings_path, json.dumps(merged, indent=2, sort_keys=True) + "\n")


def rollback_symlinks(created: list[tuple[Path, Path]]) -> None:
    for link_path, _target in reversed(created):
        if link_path.is_symlink():
            link_path.unlink()


def load_prior_install_state(root: Path) -> dict[str, Any] | None:
    state_path = install_state_path(root)
    if not state_path.is_file():
        return None
    try:
        data = load_json(state_path)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def planned_path_set(links: list[dict[str, str]], copies: list[dict[str, str]]) -> set[str]:
    return {entry["path"] for entry in links} | {entry["path"] for entry in copies}


def obsolete_symlinks_from_prior(
    prior: dict[str, Any] | None,
    planned_paths: set[str],
) -> list[dict[str, str]]:
    if not prior:
        return []
    obsolete: list[dict[str, str]] = []
    for entry in prior.get("symlinks", []):
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if path and path not in planned_paths:
            obsolete.append(entry)
    return obsolete


def preflight_obsolete_symlinks(obsolete: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for entry in obsolete:
        link_path = Path(entry["path"])
        target = Path(entry["source"])
        if not link_path.exists() and not link_path.is_symlink():
            continue
        if link_path.is_symlink() and symlink_ok(link_path, target):
            continue
        if link_path.is_symlink():
            errors.append(f"obsolete link not toolkit-managed: {link_path}")
        else:
            errors.append(f"obsolete path blocked by regular file: {link_path}")
    return errors


def remove_obsolete_symlinks(
    obsolete: list[dict[str, str]],
    *,
    dry_run: bool,
) -> tuple[list[str], list[tuple[Path, Path]]]:
    actions: list[str] = []
    removed: list[tuple[Path, Path]] = []
    for entry in obsolete:
        link_path = Path(entry["path"])
        target = Path(entry["source"])
        if not link_path.is_symlink() or not symlink_ok(link_path, target):
            continue
        if dry_run:
            actions.append(f"would_remove_legacy: {link_path}")
            continue
        link_path.unlink()
        removed.append((link_path, target))
        actions.append(f"removed_legacy: {link_path}")
    return actions, removed


def preflight_install(
    root: Path,
    routing: dict[str, Any],
    *,
    prior: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[str]]:
    if prior is None:
        prior = load_prior_install_state(root)
    errors: list[str] = []
    links = planned_symlinks(root, routing)
    copies = planned_managed_copies(root, routing)
    planned_paths = planned_path_set(links, copies)
    obsolete = obsolete_symlinks_from_prior(prior, planned_paths)
    for entry in links:
        err = preflight_symlink(Path(entry["path"]), Path(entry["source"]))
        if err:
            errors.append(err)
    for entry in copies:
        err = preflight_managed_copy(Path(entry["path"]), Path(entry["source"]), prior)
        if err:
            errors.append(err)
    errors.extend(preflight_obsolete_symlinks(obsolete))
    if harness_enabled(routing, "claude"):
        _merged, _plans, _actions, merge_errors = preflight_claude_settings(root)
        errors.extend(merge_errors)
    return links, copies, obsolete, errors


def apply_install(root: Path, routing: dict[str, Any], dry_run: bool) -> int:
    prior_state = load_prior_install_state(root)
    links, copies, obsolete, preflight_errors = preflight_install(root, routing, prior=prior_state)
    if preflight_errors:
        for line in preflight_errors:
            print(f"error: {line}", file=sys.stderr)
        return 1

    actions: list[str] = []
    warnings: list[str] = []
    created: list[tuple[Path, Path]] = []
    managed: list[dict[str, str]] = []
    managed_copies: list[dict[str, str]] = []

    if dry_run:
        for entry in links:
            link_path = Path(entry["path"])
            target = Path(entry["source"])
            if symlink_ok(link_path, target):
                actions.append(f"unchanged: {link_path} -> {target}")
            else:
                actions.append(f"would_create: {link_path} -> {target}")
        for entry in copies:
            dest = Path(entry["path"])
            source = Path(entry["source"])
            source_hash = sha256_file(source)
            if dest.is_file() and not dest.is_symlink():
                if sha256_file(dest) == source_hash:
                    actions.append(f"unchanged_copy: {dest}")
                else:
                    actions.append(f"would_update_copy: {dest}")
            elif dest.is_symlink() and symlink_ok(dest, source):
                actions.append(f"would_replace_symlink_with_copy: {dest}")
            else:
                actions.append(f"would_create_copy: {dest}")
        if harness_enabled(routing, "claude"):
            _merged, _plans, merge_actions, merge_errors = preflight_claude_settings(root)
            actions.extend(format_claude_actions_for_output(merge_actions, dry_run=True))
            if merge_errors:
                for line in merge_errors:
                    print(f"error: {line}", file=sys.stderr)
                return 1
        legacy_actions, _ = remove_obsolete_symlinks(obsolete, dry_run=True)
        actions.extend(legacy_actions)
        for line in actions:
            print(line)
        return 0

    settings_existed_before = False
    settings_original_content: str | None = None
    claude_settings_applied = False
    removed_legacy: list[tuple[Path, Path]] = []
    copy_rollbacks: list[dict[str, Any]] = []

    try:
        for entry in links:
            link_path = Path(entry["path"])
            target = Path(entry["source"])
            if symlink_ok(link_path, target):
                actions.append(f"unchanged: {link_path} -> {target}")
                managed.append(entry)
                continue
            create_symlink(link_path, target)
            created.append((link_path, target))
            actions.append(f"created: {link_path} -> {target}")
            managed.append(entry)

        for entry in copies:
            record, rollback, changed = apply_managed_copy(entry, prior_state)
            managed_copies.append(record)
            if rollback.get("was") != "unchanged":
                copy_rollbacks.append(rollback)
            if changed:
                actions.append(f"copied: {entry['path']}")
            else:
                actions.append(f"unchanged_copy: {entry['path']}")

        claude_meta: dict[str, Any] = {"hooks_merged": False, "plans_directory_added": False}
        if harness_enabled(routing, "claude"):
            settings_existed_before, settings_original_content = read_claude_settings_snapshot()
            merged, plans_added, merge_actions, merge_errors = preflight_claude_settings(root)
            if merge_errors or merged is None:
                raise RuntimeError("; ".join(merge_errors) or "claude settings preflight failed")
            apply_claude_settings(merged)
            claude_settings_applied = True
            actions.extend(format_claude_actions_for_output(merge_actions, dry_run=False))
            claude_meta = {
                "hooks_merged": True,
                "plans_directory_added": plans_added,
            }

        legacy_actions, removed_legacy = remove_obsolete_symlinks(obsolete, dry_run=False)
        actions.extend(legacy_actions)

        state = {
            "version": TOOLKIT_VERSION,
            "symlinks": managed,
            "managed_copies": managed_copies,
            "legacy_symlinks": obsolete,
            "claude": claude_meta,
        }
        write_install_state(root, state)
    except Exception as exc:
        rollback_symlinks(created)
        rollback_managed_copies(copy_rollbacks)
        for link_path, target in removed_legacy:
            create_symlink(link_path, target)
        if claude_settings_applied:
            restore_claude_settings_snapshot(settings_existed_before, settings_original_content)
        print(f"error: install rolled back ({exc})", file=sys.stderr)
        return 1

    for line in actions:
        print(line)
    for line in warnings:
        print(f"warning: {line}", file=sys.stderr)
    return 0


def strip_claude_hooks_and_plans(root: Path, dry_run: bool) -> list[str]:
    home = home_dir()
    settings_path = home / ".claude" / "settings.json"
    actions: list[str] = []
    if not settings_path.is_file():
        return actions

    state_path = install_state_path(root)
    claude_state: dict[str, Any] = {}
    if state_path.is_file():
        try:
            claude_state = load_json(state_path).get("claude", {})
        except (json.JSONDecodeError, ValueError):
            claude_state = {}

    try:
        data = load_json(settings_path)
    except (json.JSONDecodeError, ValueError):
        return [f"invalid JSON: {settings_path}"]

    if not isinstance(data, dict):
        return actions

    original = json.dumps(data, indent=2, sort_keys=True) + "\n"
    updated = _strip_toolkit_hooks(data)
    changed = json.dumps(updated, indent=2, sort_keys=True) + "\n" != original

    if claude_state.get("plans_directory_added") and updated.get("plansDirectory") == PLANS_DIRECTORY_VALUE:
        del updated["plansDirectory"]
        changed = True
        actions.append(f"removed plansDirectory from {settings_path}")

    if changed:
        if dry_run:
            actions.append(f"would remove toolkit hooks from {settings_path}")
        else:
            write_text_atomic(settings_path, json.dumps(updated, indent=2, sort_keys=True) + "\n")
            actions.append(f"removed toolkit hooks from {settings_path}")

    return actions


def apply_uninstall(root: Path, dry_run: bool) -> int:
    routing = load_routing(root)
    state_path = install_state_path(root)
    actions: list[str] = []

    entries: list[dict[str, str]] = []
    managed_copy_entries: list[dict[str, Any]] = []
    if state_path.is_file():
        try:
            state = load_json(state_path)
            entries = list(state.get("symlinks", []))
            seen = {entry.get("path") for entry in entries}
            for entry in state.get("legacy_symlinks", []):
                if isinstance(entry, dict) and entry.get("path") not in seen:
                    entries.append(entry)
                    seen.add(entry.get("path"))
            managed_copy_entries = list(state.get("managed_copies", []))
        except (json.JSONDecodeError, ValueError):
            entries = []
            managed_copy_entries = []
    else:
        entries = planned_symlinks(root, routing)
        managed_copy_entries = planned_managed_copies(root, routing)

    for entry in entries:
        if entry.get("kind") == "managed_copy":
            continue
        link_path = Path(entry["path"])
        target = Path(entry["source"])
        status, err = remove_symlink(link_path, target, dry_run=dry_run)
        actions.append(f"{status}: {link_path}")
        if err:
            print(f"warning: {err}", file=sys.stderr)

    for entry in managed_copy_entries:
        status, err = remove_managed_copy(entry, dry_run=dry_run)
        actions.append(f"{status}: {entry.get('path')}")
        if err:
            print(f"warning: {err}", file=sys.stderr)

    actions.extend(strip_claude_hooks_and_plans(root, dry_run=dry_run))
    if not dry_run and state_path.is_file():
        state_path.unlink()

    for line in actions:
        print(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install toolkit harness adapters.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show actions without writing.")
    group.add_argument("--apply", action="store_true", help="Apply install actions.")
    group.add_argument("--uninstall", action="store_true", help="Remove managed symlinks/hooks.")
    args = parser.parse_args()

    root = agents_root()
    routing = load_routing(root)

    if args.uninstall:
        return apply_uninstall(root, dry_run=False)

    if args.dry_run:
        render_errors = require_current_render(root)
        if render_errors:
            for line in render_errors:
                print(f"error: {line}", file=sys.stderr)
            return 1
        return apply_install(root, routing, dry_run=True)

    run_render(root)
    return apply_install(root, routing, dry_run=False)


if __name__ == "__main__":
    sys.exit(main())
