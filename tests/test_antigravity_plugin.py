"""Antigravity plugin package and fail-safe migration regression tests."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(filename, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load("build_antigravity_plugin.py", "orbit_plugin_builder")
migration = _load("preview_antigravity_plugin.py", "orbit_plugin_migration")


class PackageTests(unittest.TestCase):
    def test_inventory_and_roles(self):
        files = builder.build_files(ROOT)
        self.assertEqual(len([x for x in files if x.startswith("agents/")]), 13)
        self.assertIn("agents/orbit-lead-agent.md", files)
        self.assertIn("scripts/preview_antigravity_plugin.py", files)
        self.assertIn(b"mainAgent: true", files["agents/orbit-lead-agent.md"])
        self.assertIn(b"subagent: false", files["agents/orbit-lead-agent.md"])
        for filename, content in files.items():
            if filename.startswith("agents/") and filename != "agents/orbit-lead-agent.md":
                self.assertIn(b"mainAgent: false", content)
                self.assertIn(b"subagent: true", content)
        self.assertLess(len(files["skills/orbit-workflow-skill/SKILL.md"]), 24000)
        self.assertIn("skills/orbit-workflow-skill/references/FULL-LIFECYCLE-GUIDE.md", files)
        self.assertNotIn(b".agents/skills/orbit/", files["agents/orbit-lead-agent.md"])
        self.assertNotIn(b"`orbit-core-native`", files["agents/orbit-lead-agent.md"])
        self.assertIn(b"`orbit-core-mcp`", files["agents/orbit-lead-agent.md"])

    def test_manifest_and_local_stdio_db_continuity(self):
        files = builder.build_files(ROOT)
        manifest = json.loads(files["plugin.json"])
        mcp = json.loads(files["mcp_config.json"])
        self.assertEqual(manifest["name"], "orbit-core")
        self.assertEqual(manifest["version"], (ROOT / "VERSION").read_text().strip())
        server = mcp["mcpServers"]["orbit-core-mcp"]
        self.assertEqual(server["command"], "python")
        self.assertEqual(server["args"], ["${PLUGIN_ROOT}/runtime/orbit_mcp.py"])
        self.assertNotIn("ORBIT_LOCAL_DB", server.get("env", {}))
        self.assertNotIn("mcp.json", files)
        self.assertTrue(files["plugin.json"].startswith(b"{"))
        self.assertFalse(files["plugin.json"].startswith(b"\\xef\\xbb\\xbf"))

    def test_archive_is_deterministic_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            one, two = (Path(folder) / "one.zip", Path(folder) / "two.zip")
            a = builder.build(ROOT, one)
            b = builder.build(ROOT, two)
            self.assertEqual(a["sha256"], b["sha256"])
            self.assertEqual(one.read_bytes(), two.read_bytes())
            with zipfile.ZipFile(one) as archive:
                paths = archive.namelist()
                self.assertEqual(len(paths), len(set(paths)))
                self.assertTrue(all(p.startswith("orbit-core/") for p in paths))
                self.assertIn("orbit-core/mcp_config.json", paths)
            self.assertEqual(builder.verify_archive(ROOT, one)["sha256"], a["sha256"])
            with self.assertRaises(FileExistsError):
                builder.build(ROOT, one)
            # An altered entry is not accepted as an already-built package.
            with zipfile.ZipFile(one, "a") as archive:
                archive.writestr("orbit-core/unexpected.py", b"unreviewed")
            with self.assertRaisesRegex(ValueError, "inventory"):
                builder.verify_archive(ROOT, one)

    def test_extracted_mcp_starts_locally_with_real_tool_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "orbit.zip"
            builder.build(ROOT, archive)
            with zipfile.ZipFile(archive) as package:
                package.extractall(root / "extracted")
            script = root / "extracted" / "orbit-core" / "runtime" / "orbit_mcp.py"
            self.assertTrue(script.is_file())
            env = os.environ.copy()
            env["ORBIT_LOCAL_DB"] = str(root / "isolated-smoke.sqlite3")
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "plugin-regression", "version": "1"}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
            result = subprocess.run(
                [sys.executable, str(script)], input="\n".join(json.dumps(req) for req in requests) + "\n",
                text=True, capture_output=True, env=env, timeout=20
            )
            self.assertEqual(result.returncode, 0, result.stderr[-1500:])
            frames = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            responses = {frame.get("id"): frame for frame in frames}
            self.assertEqual(responses[1]["result"]["serverInfo"]["version"],
                             (ROOT / "VERSION").read_text().strip())
            tools = {item["name"] for item in responses[2]["result"]["tools"]}
            self.assertEqual(len(tools), 47)
            self.assertIn("orbit_practice_suggest", tools)
            self.assertIn("orbit_practice_review", tools)

    def test_unknown_agent_role_metadata_is_rejected(self):
        agents = sorted((ROOT / "source" / "agents").glob("orbit*.md"))
        with tempfile.TemporaryDirectory() as folder:
            copies = []
            for p in agents:
                clone = Path(folder) / p.name
                text = p.read_text(encoding="utf-8")
                if p.name == "orbit.md":
                    text = text.replace("mainAgent: true", "mainAgent: false")
                clone.write_text(text, encoding="utf-8")
                copies.append(clone)
            with self.assertRaises(ValueError):
                builder.validate_agents(copies)


class MigrationTests(unittest.TestCase):
    def _legacy(self, home: Path):
        config = home / ".gemini" / "config"
        (config / "agents").mkdir(parents=True)
        (config / "skills" / "orbit").mkdir(parents=True)
        (config / "agents" / "orbit.md").write_text("user custom agent", encoding="utf-8")
        (config / "skills" / "orbit" / "SKILL.md").write_text("user custom skill", encoding="utf-8")
        original = {
            "mcpServers": {
                "orbit-core-native": {"command": "python", "args": ["/home/demo/.orbit-universal/0.25.1/orbit_mcp.py"]},
                "other-mcp": {"command": "node", "args": ["server.js"]}
            },
            "settings": {"custom": True},
        }
        (config / "mcp_config.json").write_text(json.dumps(original), encoding="utf-8")
        return config, original

    def test_read_only_preview_never_modifies_config(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            config, old = self._legacy(home)
            before = (config / "mcp_config.json").read_bytes()
            result = migration.inspect(home)
            self.assertFalse(result["safe_to_install_now"])
            self.assertTrue(result["legacy_mcp"])
            self.assertEqual(len(result["global_agents"]), 1)
            self.assertEqual(before, (config / "mcp_config.json").read_bytes())
            self.assertTrue((config / "agents" / "orbit.md").exists())
            self.assertEqual(old, json.loads(before))

    def test_apply_requires_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            config, _ = self._legacy(home)
            with self.assertRaises(ValueError):
                migration.stage_migration(home, "yes")
            self.assertTrue((config / "agents" / "orbit.md").exists())

    def test_explicit_migration_archives_unknown_customizations_and_preserves_others(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            config, _ = self._legacy(home)
            result = migration.stage_migration(home, "ARCHIVE_LEGACY_ORBIT_AND_KEEP_BACKUPS")
            self.assertEqual(result["status"], "LEGACY_ARCHIVED_PLUGIN_NOT_INSTALLED")
            new = json.loads((config / "mcp_config.json").read_text(encoding="utf-8"))
            self.assertNotIn("orbit-core-native", new["mcpServers"])
            self.assertIn("other-mcp", new["mcpServers"])
            self.assertEqual(new["settings"], {"custom": True})
            self.assertFalse((config / "agents" / "orbit.md").exists())
            self.assertFalse((config / "skills" / "orbit").exists())
            backup = Path(result["backup"])
            self.assertEqual((backup / "agents" / "orbit.md").read_text(), "user custom agent")
            self.assertEqual((backup / "skill" / "SKILL.md").read_text(), "user custom skill")
            self.assertEqual(json.loads((backup / "mcp_config.json").read_text())["mcpServers"]["orbit-core-native"]["command"], "python")
            self.assertTrue(migration.inspect(home)["safe_to_install_now"])

    def test_other_orbit_servers_block_apply(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            config, old = self._legacy(home)
            old["mcpServers"]["orbit-m5-test"] = {"command": "python", "args": ["test_mcp.py"]}
            (config / "mcp_config.json").write_text(json.dumps(old), encoding="utf-8")
            self.assertEqual(migration.inspect(home)["additional_orbit_mcp_servers"], ["orbit-m5-test"])
            with self.assertRaises(ValueError):
                migration.stage_migration(home, "ARCHIVE_LEGACY_ORBIT_AND_KEEP_BACKUPS")
            self.assertTrue((config / "agents" / "orbit.md").exists())

    def test_custom_legacy_sqlite_path_requires_explicit_data_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            config, old = self._legacy(home)
            old["mcpServers"]["orbit-core-native"]["env"] = {
                "ORBIT_LOCAL_DB": "C:/SomeUser/OrbitCustom/memory.sqlite3"
            }
            (config / "mcp_config.json").write_text(json.dumps(old), encoding="utf-8")
            self.assertTrue(migration.inspect(home)["legacy_custom_database_override"])
            with self.assertRaisesRegex(ValueError, "ORBIT_LOCAL_DB"):
                migration.stage_migration(home, "ARCHIVE_LEGACY_ORBIT_AND_KEEP_BACKUPS")
            self.assertTrue((config / "agents" / "orbit.md").exists())
            self.assertIn("orbit-core-native", json.loads((config / "mcp_config.json").read_text())["mcpServers"])

    def test_existing_plugin_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            plugin = home / ".gemini" / "config" / "plugins" / "orbit-core"
            plugin.mkdir(parents=True)
            (plugin / "plugin.json").write_text('{"name":"orbit-core"}', encoding="utf-8")
            plan = migration.inspect(home)
            self.assertFalse(plan["safe_to_install_now"])
            # Windows CI TEMP can contain an 8.3 alias (RUNNER~1) that
            # resolves to a long user-profile name; compare canonical paths.
            self.assertEqual(Path(plan["installed_orbit_plugin"]).resolve(), plugin.resolve())
            with self.assertRaises(ValueError):
                migration.stage_migration(home, "ARCHIVE_LEGACY_ORBIT_AND_KEEP_BACKUPS")
            self.assertTrue((plugin / "plugin.json").is_file())

    def test_unrecognized_server_config_blocks_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            config, old = self._legacy(home)
            old["mcpServers"]["orbit-core-native"]["args"] = ["a-custom-unrelated-script.py"]
            (config / "mcp_config.json").write_text(json.dumps(old), encoding="utf-8")
            with self.assertRaises(ValueError):
                migration.inspect(home)

    def test_fresh_host_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            self.assertTrue(migration.inspect(home)["safe_to_install_now"])
            self.assertEqual(list(home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
