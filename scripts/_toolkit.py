"""Shared helpers for ~/.agents render/install/continuity/doctor tooling."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None  # type: ignore[assignment]

TOOLKIT_VERSION = 2
GENERATED_MARKER_PREFIX = "toolkit-generated"
TOOLKIT_GENERATED_HTML_MARKER = "<!-- toolkit-generated"
PLANS_DIRECTORY_VALUE = ".agents/plans"
TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|token|private[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
]
PLACEHOLDER_MODEL = re.compile(r"^<[^>]+>$")
CLAUDE_MODEL_ALIASES = frozenset({"inherit", "haiku", "sonnet", "opus"})

HARNESS_NAMES = ("cursor", "claude", "codex", "copilot")

CURSOR_ROLE_FALLBACKS: dict[str, str] = {
    "architect": "deep-reasoner",
    "researcher": "explore",
    "implementer": "fast-worker",
    "reviewer": "deep-reasoner",
}

CLAUDE_READONLY_TOOLS = "Read, Grep, Glob, WebSearch, WebFetch"
COPILOT_READONLY_TOOLS = ["read", "search"]

HOOK_EVENTS: dict[str, dict[str, dict[str, Any]]] = {
    "cursor": {
        "sessionStart": {"can_block": False},
        "preCompact": {"can_block": False},
        "stop": {"can_block": True},
        "sessionEnd": {"can_block": False},
        "afterFileEdit": {"can_block": False, "tracks_dirty": True},
    },
    "claude": {
        "SessionStart": {"can_block": False},
        "PreCompact": {"can_block": True},
        "Stop": {"can_block": True},
        "SessionEnd": {"can_block": False},
        "PostToolUse": {"can_block": False, "tracks_dirty": True, "matcher": "Edit|Write"},
    },
    "codex": {
        "SessionStart": {"can_block": False},
        "PreCompact": {"can_block": True},
        "Stop": {"can_block": True},
        "PostToolUse": {"can_block": False, "tracks_dirty": True, "matcher": "Edit|Write"},
    },
    "copilot": {
        "sessionStart": {"can_block": False},
        "agentStop": {"can_block": False},
        "sessionEnd": {"can_block": False},
        "postToolUse": {"can_block": False, "tracks_dirty": True},
    },
}

INSTALL_TARGETS: dict[str, tuple[str, ...]] = {
    "cursor": (
        "plugin",
        "user_hooks",
    ),
    "claude": (
        "claude_md",
        "skills",
        "agents",
        "settings_hooks",
    ),
    "codex": (
        "agents_md",
        "agents",
        "hooks",
    ),
    "copilot": (
        "instructions",
        "agents",
        "hooks",
    ),
}


def agents_root() -> Path:
    override = os.environ.get("AGENTS_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def home_dir() -> Path:
    return Path(os.environ.get("HOME", str(Path.home()))).expanduser().resolve()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def has_toolkit_generated_marker(text: str) -> bool:
    return TOOLKIT_GENERATED_HTML_MARKER in text


def sha256_skill_directory(skill_dir: Path) -> str:
    """SHA-256 of sorted per-file SHA-256 lines (sources.lock documented algorithm)."""
    lines: list[str] = []
    files = sorted(
        (path for path in skill_dir.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(skill_dir).as_posix(),
    )
    for path in files:
        rel = path.relative_to(skill_dir).as_posix()
        digest = sha256_file(path)
        lines.append(f"{digest}  {rel}")
    payload = "\n".join(lines)
    if lines:
        payload += "\n"
    return sha256_text(payload)


def source_marker(sources: Iterable[str]) -> str:
    joined = "|".join(sorted(sources))
    digest = sha256_text(joined)[:16]
    return f"{GENERATED_MARKER_PREFIX} sources={joined} sha256={digest}"


def compose_frontmatter_document(
    frontmatter_lines: list[str],
    body: str,
    marker: str | None = None,
) -> str:
    front = "---\n" + "\n".join(frontmatter_lines) + "\n---"
    if marker:
        return f"{front}\n\n<!-- {marker} -->\n\n{body.strip()}\n"
    return f"{front}\n\n{body.strip()}\n"


def starts_with_yaml_frontmatter(text: str) -> bool:
    return text.startswith("---\n") or text.startswith("---\r\n")


def strict_json_loads(text: str, path: Path | None = None) -> Any:
    stripped = text.lstrip()
    if not stripped or stripped[0] not in "{[":
        label = str(path) if path else "JSON"
        raise ValueError(f"{label}: content does not start with JSON")
    return json.loads(stripped)


def load_json(path: Path) -> Any:
    return strict_json_loads(path.read_text(encoding="utf-8"), path)


def parse_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise RuntimeError("tomllib requires Python 3.11+")
    text = path.read_text(encoding="utf-8")
    body = text
    if body.startswith("# toolkit-generated"):
        body = "\n".join(body.splitlines()[1:]).lstrip("\n")
    return tomllib.loads(body)


def parse_codex_features_output(output: str) -> dict[str, bool]:
    features: dict[str, bool] = {}
    for line in output.splitlines():
        columns = line.split()
        if len(columns) < 3 or columns[-1] not in {"true", "false"}:
            continue
        features[columns[0]] = columns[-1] == "true"
    return features


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def write_json_atomic(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def clean_generated_dir(path: Path) -> None:
    if path.is_dir():
        for child in path.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    path.mkdir(parents=True, exist_ok=True)


def load_roles_manifest(root: Path) -> dict[str, Any]:
    return load_json(root / "roles" / "manifest.json")


def load_routing(root: Path) -> dict[str, Any]:
    local = root / "routing" / "routing.local.json"
    if local.is_file():
        return load_json(local)
    return load_json(root / "routing" / "routing.example.json")


def harness_enabled(routing: dict[str, Any], harness: str) -> bool:
    return bool(routing.get("harnesses", {}).get(harness, {}).get("enabled", False))


def iter_roles(root: Path) -> list[dict[str, Any]]:
    manifest = load_roles_manifest(root)
    roles = manifest.get("roles", [])
    return sorted(roles, key=lambda item: item["id"])


def iter_skills(root: Path) -> list[str]:
    skills_dir = root / "skills"
    names: list[str] = []
    if not skills_dir.is_dir():
        return names
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file():
            names.append(child.name)
    return names


def parse_skill_frontmatter(skill_path: Path) -> dict[str, str]:
    text = skill_path.read_text(encoding="utf-8")
    if not starts_with_yaml_frontmatter(text):
        raise ValueError(f"missing frontmatter: {skill_path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"invalid frontmatter: {skill_path}")
    block = parts[1]
    meta: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def role_prompt_text(root: Path, role: dict[str, Any]) -> str:
    prompt_file = root / "roles" / role["promptFile"]
    return prompt_file.read_text(encoding="utf-8")


def role_routing(
    routing: dict[str, Any], harness: str, adapter_name: str
) -> dict[str, Any] | None:
    harness_cfg = routing.get("harnesses", {}).get(harness, {})
    if not harness_cfg.get("enabled", False):
        return None
    return harness_cfg.get("roles", {}).get(adapter_name)


def toolkit_hook_command(harness: str, event: str) -> str:
    script = agents_root() / "scripts" / "continuity.py"
    return f"python3 {script} hook --harness {harness} --event {event}"


def all_toolkit_hook_commands() -> set[str]:
    commands: set[str] = set()
    for harness, events in HOOK_EVENTS.items():
        for event in events:
            commands.add(toolkit_hook_command(harness, event))
    return commands


def is_toolkit_hook_command(command: str) -> bool:
    return command.strip() in all_toolkit_hook_commands()


def hook_command(harness: str, event: str) -> str:
    return toolkit_hook_command(harness, event)


def git_worktree_root(start: Path | None = None) -> Path | None:
    cwd = start or Path.cwd()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    top = proc.stdout.strip()
    if not top:
        return None
    return Path(top).resolve()


def git_head(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def validate_task_id(task_id: str) -> bool:
    if not task_id or ".." in task_id or "/" in task_id or "\\" in task_id:
        return False
    return TASK_ID_PATTERN.fullmatch(task_id) is not None


def resolve_active_task(worktree: Path) -> tuple[str | None, Path | None, str | None]:
    pointer = worktree / ".agents" / "active-task"
    if not pointer.is_file():
        return None, None, None
    raw = pointer.read_text(encoding="utf-8").strip()
    if not raw:
        return None, None, "active-task is empty"
    if not validate_task_id(raw):
        return None, None, "active-task contains invalid task id"
    expected_root = (worktree / ".agents" / "tasks").resolve()
    task_dir = (expected_root / raw).resolve()
    try:
        task_dir.relative_to(expected_root)
    except ValueError:
        return None, None, "active-task path traversal rejected"
    if not task_dir.is_dir():
        return raw, task_dir, "task directory missing"
    return raw, task_dir, None


def dirty_marker_path(task_dir: Path) -> Path:
    return task_dir / ".toolkit-dirty.json"


def read_dirty_marker(task_dir: Path) -> dict[str, Any] | None:
    path = dirty_marker_path(task_dir)
    if not path.is_file():
        return None
    try:
        return load_json(path)
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def write_dirty_marker(task_dir: Path, head: str | None) -> None:
    payload = {
        "head": head,
        "marked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_json_atomic(dirty_marker_path(task_dir), payload)


def handoff_path(task_dir: Path) -> Path:
    return task_dir / "HANDOFF.md"


def continuity_status(worktree: Path) -> dict[str, Any]:
    task_id, task_dir, error = resolve_active_task(worktree)
    result: dict[str, Any] = {
        "worktree": str(worktree),
        "active_task_id": task_id,
        "error": error,
        "head": git_head(worktree),
        "handoff_state": "none",
        "dirty": False,
        "stale": False,
    }
    if error or not task_id or not task_dir:
        return result

    marker = read_dirty_marker(task_dir)
    handoff = handoff_path(task_dir)
    if not handoff.is_file():
        result["handoff_state"] = "missing"
        result["stale"] = True
        return result

    handoff_mtime = handoff.stat().st_mtime
    head = result["head"]
    if marker:
        result["dirty"] = True
        marker_head = marker.get("head")
        if marker_head and head and marker_head != head:
            result["stale"] = True
            result["handoff_state"] = "stale"
            return result
        marked_at = marker.get("marked_at_utc")
        if marked_at:
            try:
                marked_dt = datetime.strptime(marked_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
                if handoff_mtime < marked_dt.timestamp():
                    result["stale"] = True
                    result["handoff_state"] = "stale"
                    return result
            except ValueError:
                result["stale"] = True
                result["handoff_state"] = "stale"
                return result

    result["handoff_state"] = "current"
    return result


def install_state_path(root: Path | None = None) -> Path:
    root = root or agents_root()
    return root / "local" / "install-state.json"


def render_manifest_path(root: Path | None = None) -> Path:
    root = root or agents_root()
    return root / "local" / "render-manifest.json"


def generated_dir(root: Path, harness: str) -> Path:
    return root / "adapters" / harness / "generated"


def symlink_ok(link_path: Path, expected_target: Path) -> bool:
    if not link_path.is_symlink():
        return False
    try:
        return link_path.resolve() == expected_target.resolve()
    except OSError:
        return False


def preflight_symlink(link_path: Path, target: Path) -> str | None:
    target = target.resolve()
    if not target.is_file() and not target.is_dir():
        return f"missing source: {target}"
    if link_path.exists() or link_path.is_symlink():
        if symlink_ok(link_path, target):
            return None
        if link_path.is_symlink():
            return f"foreign symlink: {link_path}"
        return f"regular file exists: {link_path}"
    return None


def create_symlink(link_path: Path, target: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(target.resolve())


def remove_symlink(link_path: Path, expected_target: Path, dry_run: bool) -> tuple[str, str | None]:
    if not link_path.is_symlink():
        if link_path.exists():
            return "skipped", f"not a symlink: {link_path}"
        return "missing", None
    if not symlink_ok(link_path, expected_target):
        return "skipped", f"not managed: {link_path}"
    if dry_run:
        return "would_remove", None
    link_path.unlink()
    return "removed", None


def scan_secret_like(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def find_cursor_cli() -> str | None:
    for candidate in ("cursor-agent", "cursor"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def parse_cursor_list_models_output(text: str) -> set[str]:
    """Parse `cursor-agent --list-models` stdout; model id is the token before ' - '."""
    models: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered.startswith("available"):
            continue
        if " - " in stripped:
            model_id = stripped.split(" - ", 1)[0].strip()
        else:
            parts = stripped.split()
            model_id = parts[0] if parts else ""
        if model_id:
            models.add(model_id)
    return models


def fetch_cursor_available_models(cli_path: str, timeout_sec: float = 5.0) -> set[str] | None:
    try:
        proc = subprocess.run(
            [cli_path, "--list-models"],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return parse_cursor_list_models_output(proc.stdout)


def normalize_json_for_compare(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def hook_group_present(groups: list[Any], expected_group: dict[str, Any]) -> bool:
    needle = normalize_json_for_compare(expected_group)
    for group in groups:
        if isinstance(group, dict) and normalize_json_for_compare(group) == needle:
            return True
    return False


def claude_hook_group_label(event: str, group: dict[str, Any]) -> str:
    matcher = group.get("matcher")
    if matcher:
        return f"{event} (matcher={matcher})"
    return event


def missing_claude_toolkit_hook_groups(
    installed_hooks: Any,
    expected_hooks: dict[str, Any],
) -> list[str]:
    """Return failure messages for expected toolkit hook groups absent from installed settings."""
    missing: list[str] = []
    if not isinstance(installed_hooks, dict):
        return ["claude settings hooks must be an object"]
    for event, expected_groups in expected_hooks.items():
        if not isinstance(expected_groups, list):
            continue
        actual = installed_hooks.get(event, [])
        if not isinstance(actual, list):
            missing.append(f"claude settings hooks.{event} must be a list")
            continue
        for group in expected_groups:
            if not isinstance(group, dict):
                continue
            if not hook_group_present(actual, group):
                missing.append(f"claude installed hook missing: {claude_hook_group_label(event, group)}")
    return missing
