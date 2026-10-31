"""v0.27 swarm preview: DAG, safe concurrency, host permissions and isolation."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source" / "runtime"))
import orbit_mcp
import orbit_tasks


class SwarmPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name, "a").resolve()
        self.other_root = Path(self.tmp.name, "b").resolve()
        self.root.mkdir()
        self.other_root.mkdir()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        orbit_tasks.setup(self.conn)
        self.project = "swarm-lab"
        self.base = {"project_root": str(self.root), "project": self.project,
                     "host": "antigravity",
                     "available_host_tools": ["invoke_subagent"]}

    def task(self, key, *, deps=(), paths=(), status="PLANNED",
             project=None, root=None):
        project = project or self.project
        root = root or self.root
        self.conn.execute(
            """INSERT INTO orbit_agent_tasks
               (project,project_root,task_key,step,role,goal,reason,
                write_paths,depends_on,status,revision,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (project, str(root), key, "Implementation", "backend",
             "Implement bounded specialist functionality", "Necessary for tested scope",
             json.dumps(list(paths)), json.dumps(list(deps)), status, 1,
             "2026-10-30", "2026-10-30"))
        self.conn.commit()

    def preview(self, **extra):
        return orbit_mcp.execute(self.conn, "orbit_swarm_preview",
                                 {**self.base, **extra})

    def test_empty_and_read_only_and_tool_annotations(self):
        before = self.conn.total_changes
        result = self.preview()
        self.assertEqual(result["status"], "NO_READY_TASKS")
        self.assertEqual(result["ready_now"], [])
        self.assertFalse(result["agent_spawned"])
        self.assertFalse(result["state_written"])
        self.assertFalse(result["approval_verified"])
        self.assertEqual(self.conn.total_changes, before)
        tool = next(t for t in orbit_mcp.TOOLS if t["name"] == "orbit_swarm_preview")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertTrue(tool["annotations"]["idempotentHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])
        self.assertEqual(len(orbit_mcp.TOOLS), 47)

    def test_different_paths_parallel_and_strict_cap(self):
        self.task("backend", paths=["src/backend/"])
        self.task("frontend", paths=["src/frontend/"])
        self.task("qa", paths=["tests/test_app.py"])
        before = self.conn.total_changes
        result = self.preview()
        self.assertEqual(result["status"], "READY_FOR_HOST_REVIEW")
        self.assertEqual([t["task_key"] for t in result["ready_now"]],
                         ["backend", "frontend"])
        self.assertEqual(result["deferred"], [
            {"task_key": "qa", "reason": "PARALLEL_CAP_REACHED"}])
        self.assertEqual(self.conn.total_changes, before)
        one = self.preview(max_parallel=1)
        self.assertEqual(len(one["ready_now"]), 1)

    def test_read_only_workspace_defers_writable_tasks_before_reservation(self):
        self.task("api", paths=["src/api/"])
        self.task("audit", paths=[])
        before = self.conn.total_changes
        result = self.preview(host_workspace_mode="read-only")
        self.assertEqual(result["status"], "READY_FOR_HOST_REVIEW")
        self.assertEqual([t["task_key"] for t in result["ready_now"]], ["audit"])
        self.assertIn(
            {"task_key": "api", "reason": "HOST_WORKSPACE_READ_ONLY",
             "next": ("Do not reserve a writable specialist in this host "
                      "session. Obtain legitimate host permissions first "
                      "or select a read-only task.")},
            result["deferred"])
        self.assertEqual(result["host_workspace_mode_reported"], "read-only")
        self.assertFalse(result["host_workspace_writes_verified"])
        self.assertFalse(result["state_written"])
        self.assertEqual(self.conn.total_changes, before)
        self.conn.execute(
            "UPDATE orbit_agent_tasks SET status='REVIEW_ACCEPTED' "
            "WHERE task_key='audit'")
        self.conn.commit()
        blocked = self.preview(host_workspace_mode="read-only")
        self.assertEqual(blocked["status"], "HOLD_HOST_WORKSPACE_READ_ONLY")
        self.assertEqual(blocked["ready_now"], [])
        self.assertEqual(blocked["candidate_count"], 0)
        self.assertIsNone(blocked["serial_fallback"])

    def test_host_workspace_mode_is_bounded_and_optional(self):
        self.task("api", paths=["src/api/"])
        self.assertEqual(
            self.preview(host_workspace_mode="workspace-write")["status"],
            "READY_FOR_HOST_REVIEW")
        self.assertEqual(self.preview()["host_workspace_mode_reported"], "unknown")
        for mode in ("unrestricted", "admin", True, None, [], {}):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.preview(host_workspace_mode=mode)

    def test_directory_and_file_overlap_are_serialized(self):
        self.task("a", paths=["src/App/"])
        self.task("b", paths=["src/app/main.py"])
        result = self.preview()
        self.assertEqual([x["task_key"] for x in result["ready_now"]], ["a"])
        self.assertEqual(result["deferred"][0]["reason"], "OVERLAPPING_WRITE_SCOPE")

    def test_dependency_requires_review_acceptance_not_reported_done(self):
        self.task("a", status="REPORTED_DONE")
        self.task("b", deps=["a"])
        result = self.preview()
        self.assertEqual(result["status"], "NO_READY_TASKS")
        self.assertIn({"task_key": "b", "reason": "DEPENDENCY_REVIEW_REQUIRED",
                       "unaccepted_dependencies": ["a"]}, result["deferred"])
        self.conn.execute(
            "UPDATE orbit_agent_tasks SET status='REVIEW_ACCEPTED' WHERE task_key='a'")
        self.conn.commit()
        result = self.preview()
        self.assertEqual([t["task_key"] for t in result["ready_now"]], ["b"])

    def test_missing_dependency_is_fail_closed(self):
        self.task("a", deps=["never-created"])
        result = self.preview()
        self.assertEqual(result["status"], "HOLD_MISSING_DEPENDENCIES")
        self.assertEqual(result["ready_now"], [])
        self.assertEqual(result["missing_dependency_keys"], ["never-created"])

    def test_cycle_is_fail_closed(self):
        self.task("a", deps=["b"])
        self.task("b", deps=["a"])
        result = self.preview()
        self.assertEqual(result["status"], "HOLD_DEPENDENCY_CYCLE")
        self.assertEqual(result["cycle"][0], result["cycle"][-1])
        self.assertEqual(result["ready_now"], [])

    def test_preexisting_active_session_requires_reconciliation(self):
        self.task("a", status="RUNNING")
        self.task("b")
        result = self.preview()
        self.assertEqual(result["status"], "HOLD_HOST_RECONCILIATION")
        self.assertEqual(result["ready_now"], [])
        self.assertFalse(result["host_liveness_verified"])

    def test_root_wide_active_is_safe_without_exposing_other_project(self):
        self.task("other", project="different-project", status="RESERVED")
        self.task("mine")
        result = self.preview()
        self.assertEqual(result["status"], "HOLD_HOST_RECONCILIATION")
        self.assertEqual(result["registered_tasks"], 1)
        self.assertNotIn("other", json.dumps(result))
        self.assertEqual(result["active_records_same_root"], 1)

    def test_project_and_folder_isolation(self):
        self.task("other", project="different-project")
        self.task("elsewhere", root=self.other_root)
        result = self.preview()
        self.assertEqual(result["registered_tasks"], 0)
        self.assertEqual(result["ready_now"], [])

    def test_no_native_host_tool_does_not_fabricate_swarm(self):
        self.task("a")
        result = self.preview(host="codex", available_host_tools=[])
        self.assertEqual(result["status"], "HOLD_NATIVE_TOOL_UNAVAILABLE")
        self.assertEqual(result["ready_now"][0]["task_key"], "a")
        self.assertIsNone(result["reported_native_tool"])
        self.assertFalse(result["agent_spawned"])

    def test_invalid_args_and_unknown_host_rejected(self):
        self.task("a")
        for args in ({"max_parallel": 3}, {"max_parallel": True},
                     {"host": "fake-host"},
                     {"available_host_tools": ["invoke_subagent", "invoke_subagent"]}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.preview(**args)

    def test_more_than_forty_registered_tasks_holds_without_truncation(self):
        for n in range(41):
            self.task(f"task-{n:02}")
        result = self.preview()
        self.assertEqual(result["status"], "HOLD_GRAPH_TOO_LARGE")
        self.assertEqual(result["registered_tasks"], 41)
        self.assertEqual(result["ready_now"], [])

    def test_corrupted_protected_scopes_never_scheduled(self):
        self.task("a", paths=[".gemini/config.json"])
        result = self.preview()
        self.assertEqual(result["status"], "HOLD_INVALID_TASK_RECORD")
        self.assertEqual(result["task_key"], "a")


if __name__ == "__main__":
    unittest.main()
