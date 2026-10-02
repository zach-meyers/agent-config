#!/usr/bin/env python3
"""Unit tests for ~/.agents render/install/continuity/doctor tooling."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"

SAMPLE_CURSOR_MODELS = """Available models

auto - Auto (default)
composer-2.5-fast - Composer 2.5 Fast
claude-opus-5-thinking-high - Claude Opus 5 1M Thinking
"""

ADAPTER_HARNESSES = frozenset({"cursor", "claude", "codex", "copilot"})
FIXTURE_SKIP_TOP_LEVEL = frozenset({"local", "plans", "tests"})


def copy_toolkit_fixture(source: Path, destination: Path) -> None:
    """Copy toolkit sources into an isolated AGENTS_ROOT (no local/, plans/, or generated/)."""

    def ignore(directory: str, entries: list[str]) -> set[str]:
        ignored: set[str] = set()
        dir_path = Path(directory)
        try:
            rel = dir_path.relative_to(source)
        except ValueError:
            return ignored
        parts = rel.parts
        for name in entries:
            if name in ("__pycache__", ".pytest_cache", ".git"):
                ignored.add(name)
            if not parts and name in FIXTURE_SKIP_TOP_LEVEL:
                ignored.add(name)
            if (
                len(parts) == 2
                and parts[0] == "adapters"
                and parts[1] in ADAPTER_HARNESSES
                and name == "generated"
            ):
                ignored.add(name)
        return ignored

    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=ignore)
    (destination / "local").mkdir(exist_ok=True)


def run_script(
    script: str,
    *args: str,
    env: dict[str, str] | None = None,
    agents_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged["AGENTS_ROOT"] = str(agents_root or REPO_ROOT)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=SCRIPTS,
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_generated_json(relative: str, agents_root: Path) -> dict:
    path = agents_root / relative
    return json.loads(path.read_text(encoding="utf-8"))


def assert_frontmatter_first(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"frontmatter must start at byte 0: {path}"
    parts = text.split("---", 2)
    assert len(parts) >= 3
    assert "toolkit-generated" not in parts[0]


def real_local_sentinel_snapshot() -> dict[Path, tuple[int | None, bytes | None]]:
    paths = [
        REPO_ROOT / "local" / "install-state.json",
        REPO_ROOT / "local" / "render-manifest.json",
    ]
    snapshot: dict[Path, tuple[int | None, bytes | None]] = {}
    for path in paths:
        if path.is_file():
            snapshot[path] = (path.stat().st_mtime_ns, path.read_bytes())
        else:
            snapshot[path] = (None, None)
    return snapshot


CURSOR_TOOLKIT_AGENT_FILES = (
    "toolkit-architect.md",
    "toolkit-researcher.md",
    "toolkit-implementer.md",
    "toolkit-reviewer.md",
)


def assert_cursor_direct_activation(home: Path, agents_root: Path) -> None:
    cursor_gen = agents_root / "adapters" / "cursor" / "generated"
    rule = home / ".cursor" / "rules" / "agent-config.mdc"
    hooks = home / ".cursor" / "hooks.json"
    assert rule.is_symlink()
    assert rule.resolve() == (cursor_gen / "rules" / "operating-contract.mdc").resolve()
    assert hooks.is_symlink()
    assert hooks.resolve() == (cursor_gen / "hooks" / "hooks.json").resolve()
    for name in CURSOR_TOOLKIT_AGENT_FILES:
        dest = home / ".cursor" / "agents" / name
        source = cursor_gen / "agents" / name
        assert dest.is_file() and not dest.is_symlink(), name
        assert dest.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def assert_no_cursor_plugin_symlink(home: Path) -> None:
    plugin = home / ".cursor" / "plugins" / "local" / "agent-config"
    assert not plugin.exists()


def assert_real_local_sentinel_unchanged(
    before: dict[Path, tuple[int | None, bytes | None]],
) -> None:
    for path, (mtime_ns, content) in before.items():
        if content is None:
            if path.exists():
                raise AssertionError(f"real path created during tests: {path}")
            continue
        if not path.is_file():
            raise AssertionError(f"real path removed during tests: {path}")
        if path.read_bytes() != content:
            raise AssertionError(f"real path content changed during tests: {path}")
        if path.stat().st_mtime_ns != mtime_ns:
            raise AssertionError(f"real path mtime changed during tests: {path}")


class ToolkitFixtureTestCase(unittest.TestCase):
    agents_root: Path
    _fixture_holder: tempfile.TemporaryDirectory[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls._fixture_holder = tempfile.TemporaryDirectory()
        cls.agents_root = Path(cls._fixture_holder.name)
        copy_toolkit_fixture(REPO_ROOT, cls.agents_root)
        render_proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "render.py")],
            cwd=SCRIPTS,
            env={**os.environ, "AGENTS_ROOT": str(cls.agents_root)},
            capture_output=True,
            text=True,
            check=False,
        )
        if render_proc.returncode != 0:
            raise RuntimeError(render_proc.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._fixture_holder.cleanup()

    def run_in_fixture(
        self,
        script: str,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return run_script(script, *args, env=env, agents_root=self.agents_root)


class RenderTests(ToolkitFixtureTestCase):
    def test_render_is_deterministic(self) -> None:
        first = self.run_in_fixture("render.py")
        second = self.run_in_fixture("render.py")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        manifest = json.loads((self.agents_root / "local" / "render-manifest.json").read_text())
        manifest2 = json.loads((self.agents_root / "local" / "render-manifest.json").read_text())
        self.assertEqual(manifest["files"], manifest2["files"])

    def test_generated_json_strict_and_plugin_paths(self) -> None:
        self.run_in_fixture("render.py")
        plugin = parse_generated_json(
            "adapters/cursor/generated/.cursor-plugin/plugin.json",
            self.agents_root,
        )
        self.assertEqual(plugin["hooks"], "hooks/hooks.json")
        hooks = parse_generated_json("adapters/cursor/generated/hooks/hooks.json", self.agents_root)
        self.assertIn("afterFileEdit", hooks["hooks"])
        self.assertFalse((self.agents_root / "adapters/cursor/generated/user-hooks.json").exists())
        manifest = json.loads((self.agents_root / "local" / "render-manifest.json").read_text())
        self.assertNotIn("adapters/cursor/generated/user-hooks.json", manifest.get("files", {}))
        assert_frontmatter_first(
            self.agents_root / "adapters/cursor/generated/agents/toolkit-researcher.md"
        )

    def test_codex_hooks_use_matcher_groups_and_command_handlers(self) -> None:
        self.run_in_fixture("render.py")
        hooks = parse_generated_json(
            "adapters/codex/generated/hooks.json",
            self.agents_root,
        )["hooks"]

        for event, groups in hooks.items():
            self.assertIsInstance(groups, list, event)
            self.assertTrue(groups, event)
            for group in groups:
                self.assertIn("hooks", group, event)
                for handler in group["hooks"]:
                    self.assertEqual(handler.get("type"), "command", event)
                    self.assertTrue(handler.get("command"), event)

        self.assertEqual(hooks["PostToolUse"][0].get("matcher"), "Edit|Write")

    @unittest.skipIf(tomllib is None, "tomllib requires Python 3.11+")
    def test_generated_toml_parses(self) -> None:
        self.run_in_fixture("render.py")
        toml_path = self.agents_root / "adapters/codex/generated/agents/toolkit-researcher.toml"
        body = toml_path.read_text(encoding="utf-8")
        if body.startswith("# toolkit-generated"):
            body = "\n".join(body.splitlines()[1:])
        parsed = tomllib.loads(body)
        self.assertIn("name", parsed)


class InstallTests(ToolkitFixtureTestCase):
    def setUp(self) -> None:
        self.temp_home = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_home.name)
        self.env = {"HOME": str(self.home), "AGENTS_ROOT": str(self.agents_root)}

    def tearDown(self) -> None:
        self.temp_home.cleanup()

    def test_dry_run_does_not_create_symlinks(self) -> None:
        proc = self.run_in_fixture("install.py", "--dry-run", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert_no_cursor_plugin_symlink(self.home)
        self.assertFalse((self.home / ".cursor" / "hooks.json").exists())

    def test_dry_run_does_not_mutate_render_manifest(self) -> None:
        manifest = self.agents_root / "local" / "render-manifest.json"
        before = manifest.read_bytes()
        before_mtime = manifest.stat().st_mtime_ns
        sample = self.agents_root / "adapters/cursor/generated/hooks/hooks.json"
        sample_before = sample.read_bytes()
        proc = self.run_in_fixture("install.py", "--dry-run", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual(manifest.stat().st_mtime_ns, before_mtime)
        self.assertEqual(sample.read_bytes(), sample_before)

    def test_dry_run_rejects_stale_render_output(self) -> None:
        hooks = self.agents_root / "adapters/cursor/generated/hooks/hooks.json"
        hooks.write_text(hooks.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        proc = self.run_in_fixture("install.py", "--dry-run", env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("run render.py first", proc.stderr)

    def test_cursor_direct_activation_no_plugin(self) -> None:
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert_cursor_direct_activation(self.home, self.agents_root)
        assert_no_cursor_plugin_symlink(self.home)

    def test_disabled_harness_links_absent(self) -> None:
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((self.home / ".codex" / "AGENTS.md").exists())
        self.assertFalse((self.home / ".copilot" / "copilot-instructions.md").exists())

    def test_collision_preflight_creates_zero_links(self) -> None:
        target = self.home / ".claude" / "CLAUDE.md"
        target.parent.mkdir(parents=True)
        target.write_text("foreign", encoding="utf-8")
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse((self.home / ".cursor" / "hooks.json").exists())
        assert_no_cursor_plugin_symlink(self.home)

    def test_cursor_collision_preflight_skips_cursor_links(self) -> None:
        hooks = self.home / ".cursor" / "hooks.json"
        hooks.parent.mkdir(parents=True)
        hooks.write_text("{}", encoding="utf-8")
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse((self.home / ".cursor" / "rules" / "agent-config.mdc").exists())
        assert_no_cursor_plugin_symlink(self.home)

    def test_migration_removes_legacy_plugin_symlink(self) -> None:
        self.run_in_fixture("render.py")
        cursor_gen = self.agents_root / "adapters" / "cursor" / "generated"
        plugin = self.home / ".cursor" / "plugins" / "local" / "agent-config"
        plugin.parent.mkdir(parents=True, exist_ok=True)
        plugin.symlink_to(cursor_gen, target_is_directory=True)
        prior = {
            "version": 2,
            "symlinks": [
                {
                    "path": str(plugin),
                    "source": str(cursor_gen),
                    "kind": "symlink",
                    "harness": "cursor",
                }
            ],
            "claude": {"hooks_merged": False, "plans_directory_added": False},
        }
        (self.agents_root / "local" / "install-state.json").write_text(
            json.dumps(prior),
            encoding="utf-8",
        )
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        assert_no_cursor_plugin_symlink(self.home)
        assert_cursor_direct_activation(self.home, self.agents_root)
        state = json.loads((self.agents_root / "local" / "install-state.json").read_text())
        legacy_paths = {entry["path"] for entry in state.get("legacy_symlinks", [])}
        self.assertIn(str(plugin), legacy_paths)

    def test_migration_apply_failure_restores_legacy_plugin(self) -> None:
        self.run_in_fixture("render.py")
        cursor_gen = self.agents_root / "adapters" / "cursor" / "generated"
        plugin = self.home / ".cursor" / "plugins" / "local" / "agent-config"
        plugin.parent.mkdir(parents=True, exist_ok=True)
        plugin.symlink_to(cursor_gen, target_is_directory=True)
        prior = {
            "version": 2,
            "symlinks": [
                {
                    "path": str(plugin),
                    "source": str(cursor_gen),
                    "kind": "symlink",
                    "harness": "cursor",
                }
            ],
        }
        (self.agents_root / "local" / "install-state.json").write_text(
            json.dumps(prior),
            encoding="utf-8",
        )
        env = {**self.env, "TOOLKIT_TEST_FAIL_INSTALL_STATE": "1"}
        proc = self.run_in_fixture("install.py", "--apply", env=env)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(plugin.is_symlink())
        self.assertTrue(plugin.resolve() == cursor_gen.resolve())

    def test_transactional_rollback_on_settings_failure(self) -> None:
        (self.home / ".claude").write_text("blocking-file", encoding="utf-8")
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse((self.home / ".cursor" / "hooks.json").exists())

    def test_apply_log_uses_past_tense_for_claude_hooks(self) -> None:
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("merged toolkit hooks into", proc.stdout)
        self.assertNotIn("would merge toolkit hooks", proc.stdout)
        self.assertIn("set plansDirectory", proc.stdout)
        self.assertNotIn("would set plansDirectory", proc.stdout)

    def test_dry_run_log_prefixes_would_for_claude(self) -> None:
        proc = self.run_in_fixture("install.py", "--dry-run", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("would merge toolkit hooks into", proc.stdout)
        self.assertIn("would set plansDirectory", proc.stdout)
        self.assertNotIn("merged toolkit hooks into", proc.stdout)

    def test_settings_rollback_after_install_state_failure(self) -> None:
        settings_dir = self.home / ".claude"
        settings_dir.mkdir(parents=True)
        original = {"custom": True, "hooks": {}}
        (settings_dir / "settings.json").write_text(json.dumps(original), encoding="utf-8")
        env = {**self.env, "TOOLKIT_TEST_FAIL_INSTALL_STATE": "1"}
        proc = self.run_in_fixture("install.py", "--apply", env=env)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        restored = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(restored, original)
        self.assertFalse((self.home / ".cursor" / "hooks.json").exists())
        self.assertFalse((self.agents_root / "local" / "install-state.json").exists())

    def test_settings_rollback_removes_new_file_when_state_commit_fails(self) -> None:
        env = {**self.env, "TOOLKIT_TEST_FAIL_INSTALL_STATE": "1"}
        proc = self.run_in_fixture("install.py", "--apply", env=env)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse((self.home / ".claude" / "settings.json").exists())

    def test_claude_settings_merge_preserves_unrelated(self) -> None:
        settings_dir = self.home / ".claude"
        settings_dir.mkdir(parents=True)
        original = {
            "foo": "bar",
            "hooks": {
                "UserPromptSubmit": [
                    {"hooks": [{"type": "command", "command": "echo preserve-me"}]}
                ]
            },
        }
        (settings_dir / "settings.json").write_text(json.dumps(original), encoding="utf-8")
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        merged = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(merged.get("foo"), "bar")
        commands = [
            item.get("command")
            for group in merged.get("hooks", {}).get("UserPromptSubmit", [])
            for item in group.get("hooks", [])
            if isinstance(item, dict)
        ]
        self.assertIn("echo preserve-me", commands)

    def test_plans_directory_add_and_uninstall_remove(self) -> None:
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        settings = json.loads((self.home / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings.get("plansDirectory"), ".agents/plans")
        uninstall = self.run_in_fixture("install.py", "--uninstall", env=self.env)
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        settings_after = json.loads((self.home / ".claude" / "settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("plansDirectory", settings_after)
        self.assertFalse((self.agents_root / "local" / "install-state.json").exists())

    def test_uninstall_does_not_render(self) -> None:
        self.run_in_fixture("install.py", "--apply", env=self.env)
        before = (self.agents_root / "local" / "render-manifest.json").read_text(encoding="utf-8")
        uninstall = self.run_in_fixture("install.py", "--uninstall", env=self.env)
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        after = (self.agents_root / "local" / "render-manifest.json").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_uninstall_removes_cursor_direct_paths(self) -> None:
        self.run_in_fixture("install.py", "--apply", env=self.env)
        assert_cursor_direct_activation(self.home, self.agents_root)
        uninstall = self.run_in_fixture("install.py", "--uninstall", env=self.env)
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertFalse((self.home / ".cursor" / "hooks.json").exists())
        self.assertFalse((self.home / ".cursor" / "rules" / "agent-config.mdc").exists())
        for name in CURSOR_TOOLKIT_AGENT_FILES:
            self.assertFalse((self.home / ".cursor" / "agents" / name).exists())

    def test_cursor_agent_copy_records_hashes_in_state(self) -> None:
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = json.loads((self.agents_root / "local" / "install-state.json").read_text())
        copies = state.get("managed_copies", [])
        self.assertEqual(len(copies), len(CURSOR_TOOLKIT_AGENT_FILES))
        researcher = (self.home / ".cursor" / "agents" / "toolkit-researcher.md").resolve()
        entry = next(
            item for item in copies if Path(item["path"]).resolve() == researcher
        )
        self.assertEqual(entry.get("kind"), "managed_copy")
        self.assertTrue(entry.get("source_sha256"))
        self.assertEqual(entry.get("installed_sha256"), entry.get("source_sha256"))

    def test_cursor_agent_collision_blocks_install(self) -> None:
        agent = self.home / ".cursor" / "agents" / "toolkit-researcher.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("# foreign agent\n", encoding="utf-8")
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("regular file exists", proc.stderr)

    def test_cursor_agent_copy_updates_when_source_changes(self) -> None:
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        dest = self.home / ".cursor" / "agents" / "toolkit-researcher.md"
        prompt = self.agents_root / "roles" / "prompts" / "researcher.md"
        prompt.write_text(
            prompt.read_text(encoding="utf-8") + "\nUNIQUE_TOOLKIT_UPDATE_PROBE\n",
            encoding="utf-8",
        )
        again = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("UNIQUE_TOOLKIT_UPDATE_PROBE", dest.read_text(encoding="utf-8"))

    def test_cursor_agent_user_modified_uninstall_preserves(self) -> None:
        proc = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        dest = self.home / ".cursor" / "agents" / "toolkit-researcher.md"
        dest.write_text(dest.read_text(encoding="utf-8") + "\n# user edit\n", encoding="utf-8")
        uninstall = self.run_in_fixture("install.py", "--uninstall", env=self.env)
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertTrue(dest.is_file())
        self.assertIn("user-modified managed copy", uninstall.stderr)
        self.assertIn("# user edit", dest.read_text(encoding="utf-8"))

    def test_cursor_managed_copy_rollback_on_state_failure(self) -> None:
        env = {**self.env, "TOOLKIT_TEST_FAIL_INSTALL_STATE": "1"}
        proc = self.run_in_fixture("install.py", "--apply", env=env)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        dest = self.home / ".cursor" / "agents" / "toolkit-researcher.md"
        self.assertFalse(dest.exists())


class RealRootIsolationTests(unittest.TestCase):
    def test_install_apply_uninstall_leaves_real_local_untouched(self) -> None:
        before = real_local_sentinel_snapshot()
        fixture_home = tempfile.TemporaryDirectory()
        fixture_root = tempfile.TemporaryDirectory()
        try:
            home = Path(fixture_home.name)
            agents_root = Path(fixture_root.name)
            copy_toolkit_fixture(REPO_ROOT, agents_root)
            env = {"HOME": str(home), "AGENTS_ROOT": str(agents_root)}
            apply_proc = run_script("install.py", "--apply", env=env, agents_root=agents_root)
            self.assertEqual(apply_proc.returncode, 0, apply_proc.stderr)
            self.assertTrue((agents_root / "local" / "install-state.json").is_file())
            uninstall_proc = run_script("install.py", "--uninstall", env=env, agents_root=agents_root)
            self.assertEqual(uninstall_proc.returncode, 0, uninstall_proc.stderr)
            self.assertFalse((agents_root / "local" / "install-state.json").exists())
        finally:
            fixture_home.cleanup()
            fixture_root.cleanup()
        assert_real_local_sentinel_unchanged(before)


class ContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=self.root, check=True)
        (self.root / "file.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.root, check=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_rejects_path_traversal_active_task(self) -> None:
        agents = self.root / ".agents"
        agents.mkdir()
        (agents / "active-task").write_text("../outside", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "continuity.py"), "status"],
            cwd=self.root,
            env={**os.environ, "AGENTS_ROOT": str(REPO_ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("invalid task id", proc.stdout + proc.stderr)

    def test_check_rejects_invalid_active_task(self) -> None:
        agents = self.root / ".agents"
        agents.mkdir()
        (agents / "active-task").write_text("../outside", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "continuity.py"), "check"],
            cwd=self.root,
            env={**os.environ, "AGENTS_ROOT": str(REPO_ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid task id", proc.stdout + proc.stderr)

    def test_check_skips_when_no_task_is_active(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "continuity.py"), "check"],
            cwd=self.root,
            env={**os.environ, "AGENTS_ROOT": str(REPO_ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no active task", proc.stdout)

    def test_stale_after_mark_dirty(self) -> None:
        task_id = "task-1"
        task_dir = self.root / ".agents" / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (self.root / ".agents" / "active-task").write_text(task_id, encoding="utf-8")
        (task_dir / "HANDOFF.md").write_text("# handoff\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(SCRIPTS / "continuity.py"), "mark-dirty"],
            cwd=self.root,
            env={**os.environ, "AGENTS_ROOT": str(REPO_ROOT)},
            check=True,
        )
        (self.root / "file.txt").write_text("changed", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=self.root, check=True)
        check = subprocess.run(
            [sys.executable, str(SCRIPTS / "continuity.py"), "check"],
            cwd=self.root,
            env={**os.environ, "AGENTS_ROOT": str(REPO_ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(check.returncode, 2)

    def test_edit_hook_marks_dirty(self) -> None:
        task_id = "task-edit"
        task_dir = self.root / ".agents" / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (self.root / ".agents" / "active-task").write_text(task_id, encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "continuity.py"),
                "hook",
                "--harness",
                "cursor",
                "--event",
                "afterFileEdit",
            ],
            cwd=self.root,
            env={**os.environ, "AGENTS_ROOT": str(REPO_ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((task_dir / ".toolkit-dirty.json").is_file())

    def test_hook_does_not_print_task_content(self) -> None:
        secret = "SUPERSECRETTASKCONTENT"
        task_id = "task-2"
        task_dir = self.root / ".agents" / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (self.root / ".agents" / "active-task").write_text(task_id, encoding="utf-8")
        (task_dir / "HANDOFF.md").write_text(secret, encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "continuity.py"),
                "hook",
                "--harness",
                "cursor",
                "--event",
                "sessionStart",
            ],
            cwd=self.root,
            env={**os.environ, "AGENTS_ROOT": str(REPO_ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotIn(secret, proc.stdout + proc.stderr)

    def test_codex_session_start_adds_developer_context(self) -> None:
        task_id = "task-codex-start"
        task_dir = self.root / ".agents" / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (self.root / ".agents" / "active-task").write_text(task_id, encoding="utf-8")

        proc = self._run_codex_hook("SessionStart")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        output = payload["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        self.assertIn(task_id, output["additionalContext"])

    def test_codex_precompact_stops_for_missing_checkpoint(self) -> None:
        task_id = "task-codex-compact"
        task_dir = self.root / ".agents" / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (self.root / ".agents" / "active-task").write_text(task_id, encoding="utf-8")

        proc = self._run_codex_hook("PreCompact")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["continue"])
        self.assertIn(task_id, payload["stopReason"])
        self.assertEqual(payload["systemMessage"], payload["stopReason"])

    def test_codex_stop_continues_for_missing_checkpoint(self) -> None:
        task_id = "task-codex-stop"
        task_dir = self.root / ".agents" / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (self.root / ".agents" / "active-task").write_text(task_id, encoding="utf-8")

        proc = self._run_codex_hook("Stop")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["decision"], "block")
        self.assertIn(task_id, payload["reason"])

    def _run_codex_hook(self, event: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "continuity.py"),
                "hook",
                "--harness",
                "codex",
                "--event",
                event,
            ],
            cwd=self.root,
            env={**os.environ, "AGENTS_ROOT": str(REPO_ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )


class ModelValidationTests(unittest.TestCase):
    def test_parse_cursor_list_models_output(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            from _toolkit import parse_cursor_list_models_output

            models = parse_cursor_list_models_output(SAMPLE_CURSOR_MODELS)
            self.assertIn("composer-2.5-fast", models)
            self.assertIn("auto", models)
            self.assertNotIn("Available", models)
        finally:
            if str(SCRIPTS) in sys.path:
                sys.path.remove(str(SCRIPTS))

    def test_claude_alias_validation_logic(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        try:
            from _toolkit import CLAUDE_MODEL_ALIASES

            self.assertIn("sonnet", CLAUDE_MODEL_ALIASES)
            self.assertNotIn("gpt-4", CLAUDE_MODEL_ALIASES)
        finally:
            if str(SCRIPTS) in sys.path:
                sys.path.remove(str(SCRIPTS))


class DoctorTests(ToolkitFixtureTestCase):
    def setUp(self) -> None:
        self.temp_home = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_home.name)
        self.env = {"HOME": str(self.home), "AGENTS_ROOT": str(self.agents_root)}

    def tearDown(self) -> None:
        self.temp_home.cleanup()

    def test_doctor_ok_after_render(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib requires Python 3.11+")
        self.run_in_fixture("render.py")
        proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"], data.get("failures"))
        self.assertEqual(proc.returncode, 0)

    def test_doctor_fails_when_cursor_managed_copy_drifted(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib requires Python 3.11+")
        install = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(install.returncode, 0, install.stderr)
        dest = self.home / ".cursor" / "agents" / "toolkit-researcher.md"
        dest.write_text(dest.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
        proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
        data = json.loads(proc.stdout)
        self.assertFalse(data["ok"])
        self.assertTrue(
            any("cursor managed copy drift" in item for item in data["failures"]),
            data.get("failures"),
        )

    def test_doctor_fails_when_cursor_activation_missing(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib requires Python 3.11+")
        install = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(install.returncode, 0, install.stderr)
        (self.home / ".cursor" / "hooks.json").unlink()
        proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
        data = json.loads(proc.stdout)
        self.assertFalse(data["ok"])
        self.assertTrue(
            any("cursor activation missing" in item for item in data["failures"]),
            data.get("failures"),
        )

    def test_doctor_fails_when_installed_claude_hook_missing(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib requires Python 3.11+")
        install = self.run_in_fixture("install.py", "--apply", env=self.env)
        self.assertEqual(install.returncode, 0, install.stderr)
        settings_path = self.home / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks = settings.get("hooks", {})
        stop_groups = hooks.get("Stop", [])
        self.assertTrue(stop_groups)
        hooks["Stop"] = stop_groups[1:]
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
        data = json.loads(proc.stdout)
        self.assertFalse(data["ok"])
        self.assertTrue(
            any("claude installed hook missing" in item for item in data["failures"]),
            data.get("failures"),
        )
        combined = proc.stdout + proc.stderr
        self.assertNotIn("custom", combined)
        self.assertNotIn("preserve-me", combined)

    def test_doctor_does_not_print_auth_values(self) -> None:
        self.run_in_fixture("render.py")
        cursor_dir = self.home / ".cursor"
        cursor_dir.mkdir(parents=True)
        token = "sk-test-do-not-leak-1234567890"
        (cursor_dir / "cli-config.json").write_text(
            json.dumps({"apiKey": token, "sandbox": {"enabled": False}}),
            encoding="utf-8",
        )
        proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
        self.assertNotIn(token, proc.stdout + proc.stderr)

    def test_doctor_roles_manifest_cursor_fallbacks_valid(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib requires Python 3.11+")
        proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
        data = json.loads(proc.stdout)
        manifest_failures = [
            item
            for item in data.get("failures", [])
            if "fallback" in item or "prompt missing" in item or "duplicate role" in item
        ]
        self.assertEqual(manifest_failures, [], data.get("failures"))

    def test_doctor_fails_missing_cursor_fallback_in_manifest(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib requires Python 3.11+")
        manifest_path = self.agents_root / "roles" / "manifest.json"
        original = manifest_path.read_text(encoding="utf-8")
        try:
            manifest = json.loads(original)
            manifest["roles"][0].pop("fallbacks", None)
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
            data = json.loads(proc.stdout)
            self.assertFalse(data["ok"])
            self.assertTrue(
                any("fallbacks.cursor" in item for item in data.get("failures", [])),
                data.get("failures"),
            )
        finally:
            manifest_path.write_text(original, encoding="utf-8")

    def test_doctor_fails_cursor_fallback_drift(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib requires Python 3.11+")
        manifest_path = self.agents_root / "roles" / "manifest.json"
        original = manifest_path.read_text(encoding="utf-8")
        try:
            manifest = json.loads(original)
            for role in manifest["roles"]:
                if role.get("id") == "researcher":
                    role["fallbacks"]["cursor"] = "generalPurpose"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
            data = json.loads(proc.stdout)
            self.assertFalse(data["ok"])
            self.assertTrue(
                any("cursor fallback drift" in item and "researcher" in item for item in data.get("failures", [])),
                data.get("failures"),
            )
        finally:
            manifest_path.write_text(original, encoding="utf-8")

    def test_doctor_fails_placeholder_model_when_harness_enabled(self) -> None:
        if tomllib is None:
            self.skipTest("tomllib requires Python 3.11+")
        routing_path = self.agents_root / "routing" / "routing.local.json"
        original_routing = routing_path.read_text(encoding="utf-8")
        try:
            routing = json.loads(original_routing)
            routing["harnesses"]["cursor"]["roles"]["toolkit-researcher"]["model"] = "<cursor-model-id>"
            routing_path.write_text(json.dumps(routing), encoding="utf-8")
            proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
            data = json.loads(proc.stdout)
            self.assertFalse(data["ok"])
            self.assertTrue(
                any("placeholder model id" in item for item in data.get("failures", [])),
                data.get("failures"),
            )
        finally:
            routing_path.write_text(original_routing, encoding="utf-8")

    def test_doctor_warns_cursor_safety_mode_and_approval_schema(self) -> None:
        self.run_in_fixture("render.py")
        cursor_dir = self.home / ".cursor"
        cursor_dir.mkdir(parents=True)
        token = "sk-test-do-not-leak-mode-schema-999"
        (cursor_dir / "cli-config.json").write_text(
            json.dumps(
                {
                    "apiKey": token,
                    "authToken": "Bearer also-secret-value",
                    "sandbox": {"mode": "disabled"},
                    "approvalMode": "unrestricted",
                }
            ),
            encoding="utf-8",
        )
        proc = self.run_in_fixture("doctor.py", "--json", env=self.env)
        data = json.loads(proc.stdout)
        warnings = data.get("warnings", [])
        self.assertTrue(
            any("sandbox is disabled" in item and "sandbox.mode=disabled" in item for item in warnings),
            warnings,
        )
        self.assertTrue(
            any("approval is unrestricted" in item and "approvalMode=unrestricted" in item for item in warnings),
            warnings,
        )
        combined = proc.stdout + proc.stderr
        self.assertNotIn(token, combined)
        self.assertNotIn("also-secret-value", combined)


if __name__ == "__main__":
    unittest.main()
