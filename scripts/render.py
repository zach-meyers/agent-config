#!/usr/bin/env python3
"""Deterministically render harness adapters under adapters/<harness>/generated/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from _toolkit import (
    CLAUDE_READONLY_TOOLS,
    COPILOT_READONLY_TOOLS,
    HOOK_EVENTS,
    agents_root,
    clean_generated_dir,
    compose_frontmatter_document,
    generated_dir,
    hook_command,
    iter_roles,
    load_routing,
    render_manifest_path,
    role_prompt_text,
    role_routing,
    sha256_text,
    source_marker,
    write_json_atomic,
    write_text_atomic,
)


def _cursor_hook_entries() -> dict[str, list[dict[str, str]]]:
    hooks: dict[str, list[dict[str, str]]] = {}
    for event, meta in HOOK_EVENTS["cursor"].items():
        hooks[event] = [{"command": hook_command("cursor", event)}]
    return hooks


def _claude_hook_fragment() -> dict[str, list[dict]]:
    hooks: dict[str, list[dict]] = {}
    for event, meta in HOOK_EVENTS["claude"].items():
        entry = {
            "hooks": [{"type": "command", "command": hook_command("claude", event)}],
        }
        matcher = meta.get("matcher")
        if matcher:
            entry["matcher"] = matcher
        hooks.setdefault(event, []).append(entry)
    return hooks


def _codex_hook_entries() -> dict[str, list[dict[str, Any]]]:
    hooks: dict[str, list[dict[str, Any]]] = {}
    for event, meta in HOOK_EVENTS["codex"].items():
        group: dict[str, Any] = {
            "hooks": [
                {
                    "type": "command",
                    "command": hook_command("codex", event),
                }
            ]
        }
        matcher = meta.get("matcher")
        if matcher:
            group["matcher"] = matcher
        hooks[event] = [group]
    return hooks


def _copilot_hook_entries() -> dict[str, list[dict[str, str]]]:
    hooks: dict[str, list[dict[str, str]]] = {}
    for event in HOOK_EVENTS["copilot"]:
        hooks[event] = [
            {
                "type": "command",
                "bash": hook_command("copilot", event),
            }
        ]
    return hooks


def render_cursor(root: Path, routing: dict) -> list[str]:
    out = generated_dir(root, "cursor")
    clean_generated_dir(out)
    sources: list[str] = []
    marker = source_marker(["AGENTS.md", "roles/manifest.json", "routing"])

    plugin = {
        "name": "agent-config",
        "version": "0.1.0",
        "description": "Personal agent toolkit: operating contract, routed toolkit roles, continuity hooks.",
        "author": {"name": "Personal toolkit"},
        "rules": "rules",
        "agents": "agents",
        "hooks": "hooks/hooks.json",
    }
    plugin_path = out / ".cursor-plugin" / "plugin.json"
    write_json_atomic(plugin_path, plugin)
    sources.append(str(plugin_path.relative_to(root)))

    agents_md = (root / "AGENTS.md").read_text(encoding="utf-8")
    rule = compose_frontmatter_document(
        [
            "description: Personal senior engineering operating contract (portable defaults).",
            "alwaysApply: true",
        ],
        agents_md,
        marker,
    )
    rule_path = out / "rules" / "operating-contract.mdc"
    write_text_atomic(rule_path, rule)
    sources.append(str(rule_path.relative_to(root)))

    for role in iter_roles(root):
        adapter_name = role["adapterName"]
        route = role_routing(routing, "cursor", adapter_name)
        prompt = role_prompt_text(root, role)
        fm = [
            f"name: {adapter_name}",
            f"description: Portable {role['id']} role from ~/.agents (toolkit-routed).",
        ]
        if route and route.get("model") and route["model"] != "inherit":
            fm.append(f"model: {route['model']}")
        if role.get("readOnly"):
            fm.append("readonly: true")
        agent_path = out / "agents" / f"{adapter_name}.md"
        write_text_atomic(agent_path, compose_frontmatter_document(fm, prompt, marker))
        sources.append(str(agent_path.relative_to(root)))

    hooks_path = out / "hooks" / "hooks.json"
    write_json_atomic(hooks_path, {"version": 1, "hooks": _cursor_hook_entries()})
    sources.append(str(hooks_path.relative_to(root)))

    return sources


def render_claude(root: Path, routing: dict) -> list[str]:
    out = generated_dir(root, "claude")
    clean_generated_dir(out)
    marker = source_marker(["AGENTS.md", "roles/manifest.json", "routing"])
    sources: list[str] = []

    claude_adapter = f"@{(root / 'AGENTS.md').as_posix()}\n"
    claude_path = out / "CLAUDE.md"
    write_text_atomic(claude_path, f"<!-- {marker} -->\n{claude_adapter}")
    sources.append(str(claude_path.relative_to(root)))

    for role in iter_roles(root):
        adapter_name = role["adapterName"]
        route = role_routing(routing, "claude", adapter_name)
        prompt = role_prompt_text(root, role)
        fm = [
            f"name: {adapter_name}",
            f"description: Portable {role['id']} role from ~/.agents.",
        ]
        if route and route.get("model") and route["model"] != "inherit":
            fm.append(f"model: {route['model']}")
        if role.get("readOnly"):
            fm.append(f"tools: {CLAUDE_READONLY_TOOLS}")
        agent_path = out / "agents" / f"{adapter_name}.md"
        write_text_atomic(agent_path, compose_frontmatter_document(fm, prompt, marker))
        sources.append(str(agent_path.relative_to(root)))

    fragment_path = out / "settings-hooks-fragment.json"
    write_json_atomic(fragment_path, {"hooks": _claude_hook_fragment()})
    sources.append(str(fragment_path.relative_to(root)))

    return sources


def render_codex(root: Path, routing: dict) -> list[str]:
    out = generated_dir(root, "codex")
    clean_generated_dir(out)
    marker = source_marker(["AGENTS.md", "roles/manifest.json", "routing"])
    sources: list[str] = []

    agents_md = (root / "AGENTS.md").read_text(encoding="utf-8")
    agents_path = out / "AGENTS.md"
    write_text_atomic(agents_path, f"<!-- {marker} -->\n{agents_md}")
    sources.append(str(agents_path.relative_to(root)))

    for role in iter_roles(root):
        adapter_name = role["adapterName"]
        route = role_routing(routing, "codex", adapter_name)
        prompt = role_prompt_text(root, role)
        lines = [
            f"# {marker}",
            f'name = "{adapter_name}"',
            f'description = "Portable {role["id"]} role from ~/.agents."',
        ]
        if route and route.get("model") and route["model"] != "inherit":
            lines.append(f'model = "{route["model"]}"')
        if role.get("readOnly"):
            lines.append('sandbox_mode = "read-only"')
        instructions = prompt.strip().replace('"""', '\\"\\"\\"')
        lines.append(f'developer_instructions = """\n{instructions}\n"""')
        toml_path = out / "agents" / f"{adapter_name}.toml"
        write_text_atomic(toml_path, "\n".join(lines) + "\n")
        sources.append(str(toml_path.relative_to(root)))

    hooks_path = out / "hooks.json"
    write_json_atomic(hooks_path, {"hooks": _codex_hook_entries()})
    sources.append(str(hooks_path.relative_to(root)))

    return sources


def render_copilot(root: Path, routing: dict) -> list[str]:
    out = generated_dir(root, "copilot")
    clean_generated_dir(out)
    marker = source_marker(["AGENTS.md", "roles/manifest.json", "routing"])
    sources: list[str] = []

    instructions = (root / "AGENTS.md").read_text(encoding="utf-8")
    instructions_path = out / "copilot-instructions.md"
    write_text_atomic(instructions_path, f"<!-- {marker} -->\n{instructions}")
    sources.append(str(instructions_path.relative_to(root)))

    for role in iter_roles(root):
        adapter_name = role["adapterName"]
        route = role_routing(routing, "copilot", adapter_name)
        prompt = role_prompt_text(root, role)
        fm = [
            f"name: {adapter_name}",
            f"description: Portable {role['id']} role from ~/.agents.",
        ]
        if route and route.get("model") and route["model"] != "inherit":
            fm.append(f"model: {route['model']}")
        if role.get("readOnly"):
            fm.append("tools:")
            for tool in COPILOT_READONLY_TOOLS:
                fm.append(f"  - {tool}")
        agent_path = out / "agents" / f"{adapter_name}.agent.md"
        write_text_atomic(agent_path, compose_frontmatter_document(fm, prompt, marker))
        sources.append(str(agent_path.relative_to(root)))

    hooks_path = out / "hooks" / "toolkit-continuity.json"
    write_json_atomic(hooks_path, {"version": 1, "hooks": _copilot_hook_entries()})
    sources.append(str(hooks_path.relative_to(root)))

    return sources


def collect_file_hashes(root: Path, rel_paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for rel in sorted(rel_paths):
        path = root / rel
        if path.is_file():
            hashes[rel] = sha256_text(path.read_text(encoding="utf-8"))
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description="Render harness adapters.")
    parser.parse_args()

    root = agents_root()
    routing = load_routing(root)

    all_sources: list[str] = []
    all_sources.extend(render_cursor(root, routing))
    all_sources.extend(render_claude(root, routing))
    all_sources.extend(render_codex(root, routing))
    all_sources.extend(render_copilot(root, routing))

    manifest = {
        "version": 1,
        "files": collect_file_hashes(root, all_sources),
    }
    write_json_atomic(render_manifest_path(root), manifest)
    print(f"Rendered {len(all_sources)} files under adapters/*/generated/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
