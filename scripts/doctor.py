#!/usr/bin/env python3
"""Validate toolkit sources, rendered adapters, and install state."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from _toolkit import (
    CLAUDE_MODEL_ALIASES,
    CURSOR_ROLE_FALLBACKS,
    HARNESS_NAMES,
    HOOK_EVENTS,
    PLACEHOLDER_MODEL,
    PLANS_DIRECTORY_VALUE,
    agents_root,
    fetch_cursor_available_models,
    find_cursor_cli,
    generated_dir,
    harness_enabled,
    home_dir,
    install_state_path,
    iter_roles,
    iter_skills,
    load_json,
    load_routing,
    load_roles_manifest,
    missing_claude_toolkit_hook_groups,
    parse_codex_features_output,
    parse_skill_frontmatter,
    parse_toml,
    render_manifest_path,
    scan_secret_like,
    sha256_file,
    sha256_skill_directory,
    sha256_text,
    starts_with_yaml_frontmatter,
    symlink_ok,
    tomllib,
)

# planned_symlinks lives in install.py; import lazily to avoid circular import at module level
def _planned_symlinks(root: Path, routing: dict[str, Any]) -> list[dict[str, str]]:
    from install import planned_symlinks

    return planned_symlinks(root, routing)


def _planned_symlinks_when_enabled(
    root: Path,
    routing: dict[str, Any],
    harness: str,
) -> list[dict[str, str]]:
    enabled_routing = copy.deepcopy(routing)
    enabled_routing.setdefault("harnesses", {}).setdefault(harness, {})["enabled"] = True
    return [
        entry
        for entry in _planned_symlinks(root, enabled_routing)
        if entry.get("harness") == harness
    ]


def _failures_and_warnings(as_json: bool, failures: list[str], warnings: list[str]) -> int:
    payload = {"failures": failures, "warnings": warnings, "ok": not failures}
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for item in warnings:
            print(f"warning: {item}")
        for item in failures:
            print(f"failure: {item}")
        if not failures and not warnings:
            print("ok")
    return 1 if failures else 0


def validate_required_files(root: Path, failures: list[str]) -> None:
    required = [
        root / "AGENTS.md",
        root / "roles" / "manifest.json",
        root / "routing" / "routing.example.json",
        root / "sources.lock.json",
        root / "THIRD_PARTY_NOTICES.md",
    ]
    for path in required:
        if not path.is_file():
            failures.append(f"missing required file: {path.relative_to(root)}")


def validate_skills(root: Path, failures: list[str]) -> None:
    names = iter_skills(root)
    if len(names) != len(set(names)):
        failures.append("duplicate skill directory names")
    for name in names:
        skill_md = root / "skills" / name / "SKILL.md"
        try:
            meta = parse_skill_frontmatter(skill_md)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        if meta.get("name") != name:
            failures.append(f"skill name mismatch: {name}")


def validate_roles_manifest(root: Path, failures: list[str]) -> None:
    manifest = load_roles_manifest(root)
    roles = manifest.get("roles", [])
    if not isinstance(roles, list):
        failures.append("roles manifest roles must be a list")
        return

    seen_ids: set[str] = set()
    seen_adapters: set[str] = set()
    for role in roles:
        if not isinstance(role, dict):
            failures.append("roles manifest entry must be an object")
            continue
        role_id = str(role.get("id", "")).strip()
        adapter = str(role.get("adapterName", "")).strip()
        if not role_id:
            failures.append("role missing id")
            continue
        if role_id in seen_ids:
            failures.append(f"duplicate role id: {role_id}")
        seen_ids.add(role_id)
        if not adapter:
            failures.append(f"role missing adapterName: {role_id}")
            continue
        if adapter in seen_adapters:
            failures.append(f"duplicate adapterName: {adapter}")
        seen_adapters.add(adapter)

        prompt_file = role.get("promptFile")
        if not isinstance(prompt_file, str) or not prompt_file.strip():
            failures.append(f"role missing promptFile: {role_id}")
            continue
        prompt_path = root / "roles" / prompt_file
        if not prompt_path.is_file():
            failures.append(f"role prompt missing: {prompt_file}")

        fallbacks = role.get("fallbacks")
        cursor_fallback = ""
        if isinstance(fallbacks, dict):
            cursor_fallback = str(fallbacks.get("cursor", "")).strip()
        if not cursor_fallback:
            failures.append(f"role missing fallbacks.cursor: {role_id}")
            continue

        expected = CURSOR_ROLE_FALLBACKS.get(role_id)
        if expected is None:
            failures.append(f"cursor fallback map missing role id: {role_id}")
        elif cursor_fallback != expected:
            failures.append(
                f"cursor fallback drift: {role_id} -> {cursor_fallback} (expected {expected})"
            )

    for role_id in CURSOR_ROLE_FALLBACKS:
        if role_id not in seen_ids:
            failures.append(f"manifest missing required role id: {role_id}")


def validate_orchestration_fallback_contract(root: Path, failures: list[str]) -> None:
    agents_path = root / "AGENTS.md"
    if agents_path.is_file():
        agents_text = agents_path.read_text(encoding="utf-8")
        if "roles/manifest.json" not in agents_text:
            failures.append("AGENTS.md must reference roles/manifest.json for runtime fallback")
        if "fallback" not in agents_text.lower():
            failures.append("AGENTS.md must document harness runtime fallback delegation")

    skill_path = root / "skills" / "orchestrate-work" / "SKILL.md"
    if not skill_path.is_file():
        failures.append("orchestrate-work skill missing for fallback contract")
        return
    skill_text = skill_path.read_text(encoding="utf-8")
    if "roles/manifest.json" not in skill_text:
        failures.append("orchestrate-work skill must reference roles/manifest.json")
    if "runtime role fallback" not in skill_text.lower():
        failures.append("orchestrate-work skill must document runtime role fallback")
    for role_id, fallback_type in CURSOR_ROLE_FALLBACKS.items():
        if fallback_type not in skill_text:
            failures.append(
                f"orchestrate-work skill missing cursor fallback type for {role_id}: {fallback_type}"
            )


def validate_enabled_model_mappings(routing: dict[str, Any], failures: list[str], warnings: list[str]) -> None:
    if harness_enabled(routing, "claude"):
        roles_cfg = routing.get("harnesses", {}).get("claude", {}).get("roles", {})
        for adapter, entry in roles_cfg.items():
            model = str(entry.get("model", ""))
            if not model or model == "inherit":
                continue
            if PLACEHOLDER_MODEL.match(model):
                continue
            if model not in CLAUDE_MODEL_ALIASES:
                failures.append(f"claude invalid model alias: {adapter} -> {model}")

    if harness_enabled(routing, "cursor"):
        roles_cfg = routing.get("harnesses", {}).get("cursor", {}).get("roles", {})
        configured = [
            (adapter, str(entry.get("model", "")))
            for adapter, entry in roles_cfg.items()
            if entry.get("model") and entry.get("model") != "inherit"
            and not PLACEHOLDER_MODEL.match(str(entry.get("model", "")))
        ]
        if not configured:
            return
        cli = find_cursor_cli()
        if not cli:
            warnings.append("cursor model validation skipped: CLI not found")
            return
        available = fetch_cursor_available_models(cli)
        if available is None:
            warnings.append("cursor model validation skipped: --list-models unavailable")
            return
        for adapter, model in configured:
            if model not in available:
                failures.append(f"cursor unavailable model: {adapter} -> {model}")


def validate_roles_routing(root: Path, failures: list[str], warnings: list[str]) -> None:
    manifest = load_roles_manifest(root)
    routing = load_routing(root)
    adapter_names = {role["adapterName"] for role in manifest.get("roles", [])}
    tiers = routing.get("capabilityTiers", {})

    for harness in HARNESS_NAMES:
        cfg = routing.get("harnesses", {}).get(harness, {})
        if not cfg.get("enabled", False):
            warnings.append(f"harness disabled: {harness}")
            continue
        roles_cfg = cfg.get("roles", {})
        for adapter in adapter_names:
            if adapter not in roles_cfg:
                failures.append(f"routing missing role mapping: {harness}/{adapter}")
                continue
            entry = roles_cfg[adapter]
            tier = entry.get("capabilityTier")
            if tier not in tiers:
                failures.append(f"unknown capability tier: {harness}/{adapter}")
            model = entry.get("model", "")
            if PLACEHOLDER_MODEL.match(str(model)):
                failures.append(f"placeholder model id: {harness}/{adapter}")


def validate_sources_lock(root: Path, failures: list[str]) -> None:
    lock = load_json(root / "sources.lock.json")
    for repo in lock.get("licenses", []):
        for file_entry in repo.get("files", []):
            local = root / file_entry["local_path"]
            if not local.is_file():
                failures.append(f"license file missing: {file_entry['local_path']}")
                continue
            digest = file_entry.get("content_sha256")
            if digest and sha256_file(local) != digest:
                failures.append(f"license hash mismatch: {file_entry['local_path']}")

    for entry in lock.get("entries", []):
        skill_dir = root / entry["path_in_repo"]
        if not skill_dir.is_dir():
            failures.append(f"locked skill missing: {entry['path_in_repo']}")
            continue
        expected = entry.get("content_sha256")
        if expected:
            actual = sha256_skill_directory(skill_dir)
            if actual != expected:
                failures.append(f"skill hash mismatch: {entry['skill']}")


def validate_render_drift(root: Path, failures: list[str]) -> None:
    manifest_path = render_manifest_path(root)
    if not manifest_path.is_file():
        failures.append("render manifest missing; run render.py")
        return
    manifest = load_json(manifest_path)
    for rel, digest in manifest.get("files", {}).items():
        path = root / rel
        if not path.is_file():
            failures.append(f"rendered file missing: {rel}")
            continue
        if sha256_text(path.read_text(encoding="utf-8")) != digest:
            failures.append(f"render drift: {rel}")


def validate_generated_artifacts(root: Path, failures: list[str]) -> None:
    if tomllib is None:
        failures.append("Python 3.11+ required for TOML validation (tomllib)")
        return

    cursor_gen = generated_dir(root, "cursor")
    plugin_path = cursor_gen / ".cursor-plugin" / "plugin.json"
    if plugin_path.is_file():
        plugin = load_json(plugin_path)
        for key in ("rules", "agents", "hooks"):
            if key not in plugin:
                failures.append(f"cursor plugin.json missing key: {key}")
            else:
                ref = cursor_gen / str(plugin[key])
                if not ref.exists():
                    failures.append(f"cursor plugin reference missing: {plugin[key]}")
        if plugin.get("hooks") != "hooks/hooks.json":
            failures.append("cursor plugin hooks path must be hooks/hooks.json")
        hooks_file = cursor_gen / "hooks" / "hooks.json"
        if not hooks_file.is_file():
            failures.append("cursor plugin hooks/hooks.json missing")
        elif (cursor_gen / "user-hooks.json").exists():
            failures.append("cursor user-hooks.json must not be generated")

    for harness in HARNESS_NAMES:
        gen = generated_dir(root, harness)
        if not gen.is_dir():
            failures.append(f"generated adapter missing: adapters/{harness}/generated")
            continue
        for path in sorted(gen.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix == ".json":
                try:
                    load_json(path)
                except (json.JSONDecodeError, ValueError) as exc:
                    failures.append(f"invalid JSON: {path.relative_to(root)} ({exc})")
            if path.suffix == ".toml":
                try:
                    parse_toml(path)
                except Exception as exc:
                    failures.append(f"invalid TOML: {path.relative_to(root)} ({exc})")
            if path.suffix in {".md", ".mdc"} and path.name.endswith((".md", ".mdc")):
                text = path.read_text(encoding="utf-8")
                if path.suffix == ".mdc" or "agents" in path.parts or path.name.endswith(".agent.md"):
                    if not starts_with_yaml_frontmatter(text):
                        failures.append(f"frontmatter must start file: {path.relative_to(root)}")
                    elif "<!-- toolkit-generated" in text.split("---", 2)[0]:
                        failures.append(
                            f"generated marker before frontmatter: {path.relative_to(root)}"
                        )

    claude_gen = generated_dir(root, "claude")
    for role in iter_roles(root):
        if not role.get("readOnly"):
            continue
        claude_agent = claude_gen / "agents" / f"{role['adapterName']}.md"
        if claude_agent.is_file() and "Bash" in claude_agent.read_text(encoding="utf-8"):
            failures.append(f"readonly claude agent includes Bash: {role['adapterName']}")

    validate_codex_generated_artifacts(root, failures)


def validate_codex_generated_artifacts(root: Path, failures: list[str]) -> None:
    codex_gen = generated_dir(root, "codex")
    hooks_path = codex_gen / "hooks.json"
    if hooks_path.is_file():
        try:
            hook_document = load_json(hooks_path)
        except (json.JSONDecodeError, ValueError):
            hook_document = {}
        if isinstance(hook_document, dict):
            unsupported_fields = set(hook_document) - {"description", "hooks"}
            for field in sorted(unsupported_fields):
                failures.append(f"codex hooks.json unsupported field: {field}")
        hooks = hook_document.get("hooks", {}) if isinstance(hook_document, dict) else {}
        if not isinstance(hooks, dict):
            failures.append("codex hooks.json hooks must be an object")
        else:
            for event, meta in HOOK_EVENTS["codex"].items():
                groups = hooks.get(event)
                if not isinstance(groups, list) or not groups:
                    failures.append(f"codex hook event missing groups: {event}")
                    continue
                for group in groups:
                    if not isinstance(group, dict):
                        failures.append(f"codex hook group invalid: {event}")
                        continue
                    expected_matcher = meta.get("matcher")
                    if expected_matcher and group.get("matcher") != expected_matcher:
                        failures.append(f"codex hook matcher invalid: {event}")
                    handlers = group.get("hooks")
                    if not isinstance(handlers, list) or not handlers:
                        failures.append(f"codex hook handlers missing: {event}")
                        continue
                    for handler in handlers:
                        if not isinstance(handler, dict):
                            failures.append(f"codex hook handler invalid: {event}")
                            continue
                        if handler.get("type") != "command" or not handler.get("command"):
                            failures.append(f"codex command hook invalid: {event}")

    for role in iter_roles(root):
        agent_path = codex_gen / "agents" / f"{role['adapterName']}.toml"
        if not agent_path.is_file():
            failures.append(f"codex agent missing: {role['adapterName']}")
            continue
        try:
            agent = parse_toml(agent_path)
        except Exception:
            continue
        for field in ("name", "description", "developer_instructions"):
            if not isinstance(agent.get(field), str) or not agent[field].strip():
                failures.append(f"codex agent missing {field}: {role['adapterName']}")
        if role.get("readOnly") and agent.get("sandbox_mode") != "read-only":
            failures.append(f"readonly codex agent lacks sandbox: {role['adapterName']}")


def validate_disabled_harness_activation(root: Path, routing: dict[str, Any], failures: list[str]) -> None:
    for harness in HARNESS_NAMES:
        if harness_enabled(routing, harness):
            continue
        for entry in _planned_symlinks_when_enabled(root, routing, harness):
            link = Path(entry["path"])
            target = Path(entry["source"])
            if link.is_symlink() and symlink_ok(link, target):
                failures.append(f"disabled harness has active link: {harness} -> {link}")


def validate_installed_cursor_activation(
    root: Path,
    routing: dict[str, Any],
    failures: list[str],
    warnings: list[str],
) -> None:
    if not harness_enabled(routing, "cursor"):
        return
    state_path = install_state_path(root)
    if not state_path.is_file():
        return
    try:
        state = load_json(state_path)
    except (json.JSONDecodeError, ValueError):
        return
    home = home_dir()
    home_prefix = str(home)
    cursor_installed = any(
        isinstance(entry, dict)
        and entry.get("harness") == "cursor"
        and str(entry.get("path", "")).startswith(home_prefix)
        for entry in state.get("symlinks", [])
    ) or any(
        isinstance(entry, dict)
        and entry.get("harness") == "cursor"
        and str(entry.get("path", "")).startswith(home_prefix)
        for entry in state.get("managed_copies", [])
    )
    if not cursor_installed:
        return

    from install import planned_managed_copies, planned_symlinks

    for entry in planned_symlinks(root, routing):
        if entry.get("harness") != "cursor":
            continue
        link = Path(entry["path"])
        target = Path(entry["source"])
        if not link.is_symlink():
            failures.append(f"cursor activation missing: {link}")
            continue
        if not symlink_ok(link, target):
            failures.append(f"cursor activation drift: {link}")

    for entry in planned_managed_copies(root, routing):
        dest = Path(entry["path"])
        source = Path(entry["source"])
        if not dest.is_file() or dest.is_symlink():
            failures.append(f"cursor managed copy missing: {dest}")
            continue
        if not source.is_file():
            failures.append(f"cursor managed copy source missing: {source}")
            continue
        if sha256_file(dest) != sha256_file(source):
            failures.append(f"cursor managed copy drift: {dest}")

    legacy_plugin = home_dir() / ".cursor" / "plugins" / "local" / "agent-config"
    if legacy_plugin.is_symlink():
        warnings.append(
            "legacy cursor plugin symlink still present; re-run install --apply to migrate"
        )


def validate_installed_codex_activation(
    root: Path,
    routing: dict[str, Any],
    failures: list[str],
) -> None:
    if not harness_enabled(routing, "codex"):
        return
    for entry in _planned_symlinks(root, routing):
        if entry.get("harness") != "codex":
            continue
        link = Path(entry["path"])
        target = Path(entry["source"])
        if not link.is_symlink():
            failures.append(f"codex activation missing: {link}")
            continue
        if not symlink_ok(link, target):
            failures.append(f"codex activation drift: {link}")


def validate_installed_claude_settings(root: Path, failures: list[str]) -> None:
    state_path = install_state_path(root)
    if not state_path.is_file():
        return
    try:
        state = load_json(state_path)
    except (json.JSONDecodeError, ValueError):
        return
    claude_state = state.get("claude", {})
    if not claude_state.get("hooks_merged"):
        return

    settings_path = home_dir() / ".claude" / "settings.json"
    claude_md = home_dir() / ".claude" / "CLAUDE.md"
    claude_md_target = generated_dir(root, "claude") / "CLAUDE.md"
    claude_active_in_home = claude_md.is_symlink() and symlink_ok(claude_md, claude_md_target)
    if not claude_active_in_home and not settings_path.is_file():
        return
    if not settings_path.is_file():
        failures.append("claude settings.json missing despite hooks_merged in install-state")
        return
    try:
        settings = load_json(settings_path)
    except (json.JSONDecodeError, ValueError) as exc:
        failures.append(f"claude settings.json invalid JSON ({exc})")
        return
    if not isinstance(settings, dict):
        failures.append("claude settings.json root must be an object")
        return

    fragment_path = generated_dir(root, "claude") / "settings-hooks-fragment.json"
    if not fragment_path.is_file():
        failures.append("claude hook fragment missing; run render.py")
        return
    try:
        fragment = load_json(fragment_path)
    except (json.JSONDecodeError, ValueError) as exc:
        failures.append(f"claude hook fragment invalid JSON ({exc})")
        return
    expected_hooks = fragment.get("hooks", {})
    if not isinstance(expected_hooks, dict):
        failures.append("claude hook fragment hooks must be an object")
        return

    failures.extend(
        missing_claude_toolkit_hook_groups(settings.get("hooks"), expected_hooks)
    )

    if claude_state.get("plans_directory_added"):
        if settings.get("plansDirectory") != PLANS_DIRECTORY_VALUE:
            failures.append(
                "claude settings plansDirectory missing or incorrect (install-state says toolkit added it)"
            )


def validate_installed_links(root: Path, warnings: list[str]) -> None:
    state_path = install_state_path(root)
    if not state_path.is_file():
        warnings.append("install-state.json missing (not installed)")
        return
    state = load_json(state_path)
    for entry in state.get("symlinks", []):
        link = Path(entry["path"])
        target = Path(entry["source"])
        if not link.is_symlink():
            warnings.append(f"installed link missing: {link}")
            continue
        if not symlink_ok(link, target):
            warnings.append(f"installed link drift: {link}")


def validate_harness_availability(routing: dict[str, Any], warnings: list[str]) -> None:
    checks = [
        ("cursor", find_cursor_cli()),
        ("claude", shutil.which("claude")),
        ("codex", shutil.which("codex")),
        ("copilot", shutil.which("copilot")),
    ]
    for name, path in checks:
        if not harness_enabled(routing, name):
            continue
        if not path:
            warnings.append(f"harness CLI not found: {name}")
            continue
        if name == "cursor" and Path(path).name == "cursor":
            warnings.append("cursor-agent CLI not found; using cursor fallback")
        try:
            proc = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=3,
            )
        except subprocess.TimeoutExpired:
            warnings.append(f"harness version check timed out: {name}")
            continue
        if proc.returncode != 0:
            warnings.append(f"harness version check failed: {name}")


def validate_codex_features(
    routing: dict[str, Any],
    failures: list[str],
    warnings: list[str],
) -> None:
    if not harness_enabled(routing, "codex"):
        return
    cli = shutil.which("codex")
    if not cli:
        return
    try:
        proc = subprocess.run(
            [cli, "features", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        warnings.append("codex feature check timed out")
        return
    if proc.returncode != 0:
        warnings.append("codex feature check failed")
        return
    features = parse_codex_features_output(proc.stdout)
    for feature in ("hooks", "multi_agent", "skill_search"):
        if not features.get(feature, False):
            failures.append(f"codex required feature unavailable: {feature}")


def validate_cursor_safety(warnings: list[str]) -> None:
    cfg_path = home_dir() / ".cursor" / "cli-config.json"
    if not cfg_path.is_file():
        warnings.append("cursor cli-config.json not found")
        return
    try:
        data = load_json(cfg_path)
    except (json.JSONDecodeError, ValueError):
        warnings.append("cursor cli-config.json invalid JSON")
        return

    def read_bool(path_keys: list[str]) -> bool | None:
        node: Any = data
        for key in path_keys:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
        if isinstance(node, bool):
            return node
        return None

    sandbox_node = data.get("sandbox")
    sandbox_disabled = False
    if isinstance(sandbox_node, dict):
        if read_bool(["sandbox", "enabled"]) is False:
            sandbox_disabled = True
        mode = sandbox_node.get("mode")
        if isinstance(mode, str) and mode.strip().lower() == "disabled":
            sandbox_disabled = True
    if sandbox_disabled:
        warnings.append(
            "cursor sandbox is disabled in cli-config.json (sandbox.mode=disabled or sandbox.enabled=false)"
        )

    approval_unrestricted = False
    approval_mode = data.get("approvalMode")
    if isinstance(approval_mode, str) and approval_mode.strip().lower() == "unrestricted":
        approval_unrestricted = True
    if read_bool(["yolo"]) or read_bool(["yoloMode"]):
        approval_unrestricted = True
    permissions = data.get("permissions")
    if isinstance(permissions, dict) and permissions.get("allow") == ["*"]:
        approval_unrestricted = True
    if approval_unrestricted:
        warnings.append(
            "cursor approval is unrestricted in cli-config.json "
            "(approvalMode=unrestricted, yolo/yoloMode, or permissions.allow=*)"
        )


def validate_authored_secrets(root: Path, failures: list[str]) -> None:
    paths: list[Path] = [
        root / "AGENTS.md",
        root / "sources.lock.json",
        root / "routing" / "routing.example.json",
    ]
    paths.extend((root / "roles" / "prompts").glob("*.md"))
    for name in iter_skills(root):
        paths.append(root / "skills" / name / "SKILL.md")
    for path in paths:
        if not path.is_file():
            continue
        if scan_secret_like(path.read_text(encoding="utf-8")):
            failures.append(f"secret-like pattern in {path.relative_to(root)}")


def validate_hook_guarantees(warnings: list[str]) -> None:
    for harness, events in HOOK_EVENTS.items():
        for event, meta in events.items():
            if not meta.get("can_block"):
                warnings.append(f"hook warn-only: {harness}/{event}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate agent toolkit health.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = agents_root()
    routing = load_routing(root)
    failures: list[str] = []
    warnings: list[str] = []

    validate_required_files(root, failures)
    validate_skills(root, failures)
    validate_roles_manifest(root, failures)
    validate_orchestration_fallback_contract(root, failures)
    validate_roles_routing(root, failures, warnings)
    validate_enabled_model_mappings(routing, failures, warnings)
    validate_sources_lock(root, failures)
    validate_render_drift(root, failures)
    validate_generated_artifacts(root, failures)
    validate_disabled_harness_activation(root, routing, failures)
    validate_installed_cursor_activation(root, routing, failures, warnings)
    validate_installed_codex_activation(root, routing, failures)
    validate_installed_claude_settings(root, failures)
    validate_installed_links(root, warnings)
    validate_harness_availability(routing, warnings)
    validate_codex_features(routing, failures, warnings)
    validate_cursor_safety(warnings)
    validate_authored_secrets(root, failures)
    validate_hook_guarantees(warnings)

    return _failures_and_warnings(args.json, failures, warnings)


if __name__ == "__main__":
    sys.exit(main())
