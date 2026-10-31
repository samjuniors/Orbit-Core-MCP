"""All-or-nothing host-native swarm preflight regression, without agent execution."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source" / "runtime"))
import orbit_mcp
import orbit_tasks


class HostPreflightTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = (Path(tmp.name) / "demo").resolve()
        self.other = (Path(tmp.name) / "other").resolve()
        self.root.mkdir()
        self.other.mkdir()
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        orbit_tasks.setup(self.db)
        self.project = "swarm-demo"
        self.request = {
            "project_root": str(self.root), "project": self.project,
            "host": "antigravity", "available_host_tools": ["invoke_subagent"],
        }

    def create(self, key, *, paths=(), depends=(), project=None, root=None):
        project = project or self.project
        root = root or self.root
        args = {
            "project": project, "task_key": key,
            "step": "Implement", "role": "backend",
            "goal": "Implement an independently reviewable unit of work",
            "reason": "Required to finish the requested software feature",
            "write_paths": list(paths), "depends_on": list(depends),
            "confirm_write": True,
        }
        result = orbit_tasks.plan(self.db, args, root)
        self.assertEqual(result["status"], "PLANNED")
        return result["task"]["revision"]

    def reserve(self, key, *, root=None, project=None, approval="approved-by-host-0001"):
        root = root or self.root
        project = project or self.project
        row = self.db.execute(
            "SELECT revision FROM orbit_agent_tasks WHERE project=? AND project_root=? AND task_key=?",
            (project, str(root), key)).fetchone()
        out = orbit_tasks.reserve(self.db, {
            "project": project, "task_key": key, "expected_revision": row["revision"],
            "approval_reference": approval, "confirm_write": True
        }, root)
        self.assertEqual(out["status"], "RESERVED")
        return out["task"]["revision"]

    def preflight(self, slots, **kwargs):
        return orbit_mcp.execute(self.db, "orbit_swarm_host_preflight",
                                 {**self.request, "tasks": slots, **kwargs})

    @staticmethod
    def slot(key, revision):
        return {"task_key": key, "expected_revision": revision}

    def test_one_reserved_handoff_read_only(self):
        self.create("api", paths=["backend/"])
        rev = self.reserve("api")
        before = self.db.total_changes
        response = self.preflight([self.slot("api", rev)])
        self.assertEqual(response["status"], "HOST_INVOCATIONS_REQUIRED")
        self.assertEqual(len(response["handoffs"]), 1)
        self.assertEqual(response["handoffs"][0]["task_key"], "api")
        self.assertEqual(response["handoffs"][0]["native_tool"], "invoke_subagent")
        self.assertFalse(response["host_permissions_verified"])
        self.assertFalse(response["native_invoked"])
        self.assertFalse(response["state_written"])
        self.assertEqual(before, self.db.total_changes)
        tool = next(x for x in orbit_mcp.TOOLS
                    if x["name"] == "orbit_swarm_host_preflight")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertEqual(len(orbit_mcp.TOOLS), 47)

    def test_two_disjoint_reserved_tasks_have_two_complete_packets(self):
        self.create("api", paths=["backend/"])
        self.create("ui", paths=["frontend/"])
        r1 = self.reserve("api")
        r2 = self.reserve("ui")
        response = self.preflight([self.slot("ui", r2), self.slot("api", r1)])
        self.assertEqual(response["status"], "HOST_INVOCATIONS_REQUIRED")
        self.assertEqual([x["task_key"] for x in response["handoffs"]], ["api", "ui"])

    def test_partial_handoff_must_not_escape_if_one_task_has_no_permission_or_tool(self):
        self.create("api", paths=["backend/"])
        self.create("ui", paths=["frontend/"])
        r1 = self.reserve("api")
        r2 = self.reserve("ui")
        result = self.preflight([self.slot("api", r1), self.slot("ui", r2)],
                                available_host_tools=[])
        self.assertEqual(result["status"], "HOLD_HOST_PREFLIGHT")
        self.assertEqual(result["handoffs"], [])
        self.assertIn("orbit_task_release", result["recovery"])

    def test_reported_read_only_host_holds_writable_batch_without_partial_handoffs(self):
        self.create("api", paths=["backend/"])
        self.create("ui", paths=["frontend/"])
        r1 = self.reserve("api")
        r2 = self.reserve("ui")
        before = self.db.total_changes
        out = self.preflight([self.slot("api", r1), self.slot("ui", r2)],
                             host_workspace_mode="read-only")
        self.assertEqual(out["status"], "HOLD_HOST_PREFLIGHT")
        self.assertEqual(out["handoffs"], [])
        self.assertEqual(
            [issue["status"] for issue in out["issues"]],
            ["HOLD_HOST_WORKSPACE_READ_ONLY", "HOLD_HOST_WORKSPACE_READ_ONLY"])
        self.assertEqual(out["host_workspace_mode_reported"], "read-only")
        self.assertFalse(out["host_workspace_writes_verified"])
        self.assertFalse(out["native_invoked"])
        self.assertEqual(self.db.total_changes, before)

    def test_read_only_native_task_may_handoff_in_read_only_workspace(self):
        self.create("inspect", paths=[])
        revision = self.reserve("inspect")
        out = self.preflight([self.slot("inspect", revision)],
                             host_workspace_mode="read-only")
        self.assertEqual(out["status"], "HOST_INVOCATIONS_REQUIRED")
        self.assertEqual(out["handoffs"][0]["handoff"]["write_paths"], [])
        self.assertFalse(out["host_workspace_writes_verified"])
        with self.assertRaises(ValueError):
            self.preflight([self.slot("inspect", revision)],
                           host_workspace_mode="force-write")

    def test_duplicate_and_stale_revisions_hold(self):
        self.create("api")
        rev = self.reserve("api")
        with self.assertRaises(ValueError):
            self.preflight([self.slot("api", rev), self.slot("api", rev)])
        out = self.preflight([self.slot("api", rev-1)])
        self.assertEqual(out["issues"][0]["status"], "STALE_REVISION")
        self.assertEqual(out["handoffs"], [])

    def test_unreserved_and_previously_denied_are_not_runnable(self):
        self.create("api")
        out = self.preflight([self.slot("api", 1)])
        self.assertEqual(out["issues"][0]["status"], "HOLD_NOT_RESERVED")
        rev = self.reserve("api")
        denied = orbit_tasks.release(self.db, {
            "project": self.project, "task_key": "api", "expected_revision": rev,
            "reason_code": "HOST_PERMISSION_DENIED", "reason": "Host refused permission",
            "confirm_write": True,
        }, self.root)
        self.assertEqual(denied["status"], "BLOCKED")
        out = self.preflight([self.slot("api", denied["task"]["revision"])])
        self.assertEqual(out["issues"][0]["status"], "HOLD_PERMISSION_DENIED")
        self.assertIn("fresh", out["issues"][0]["next"])

    def test_running_agent_requires_host_terminal_reconciliation(self):
        self.create("api")
        rev = self.reserve("api")
        started = orbit_tasks.started(self.db, {
            "project": self.project, "task_key": "api",
            "expected_revision": rev, "host_session": "real-host-session-abc",
            "confirm_write": True,
        }, self.root)
        out = self.preflight([self.slot("api", started["task"]["revision"])])
        self.assertEqual(out["issues"][0]["status"], "HOLD_RUNNING_SESSION")
        self.assertFalse(out["host_liveness_verified"])
        self.assertEqual(out["handoffs"], [])

    def test_other_project_same_workspace_not_disclosed(self):
        self.create("secret-agent", project="other-project", paths=["private/"])
        self.reserve("secret-agent", project="other-project")
        self.create("api", paths=["backend/"])
        rev = self.reserve("api")
        out = self.preflight([self.slot("api", rev)])
        self.assertEqual(out["status"], "HOLD_HOST_PREFLIGHT")
        self.assertIn("HOLD_OTHER_ACTIVE_RECORDS",
                      [issue["status"] for issue in out["issues"]])
        self.assertNotIn("secret-agent", json.dumps(out))
        self.assertNotIn("other-project", json.dumps(out))

    def test_forged_two_reserved_tasks_with_overlap_fail_closed(self):
        self.create("api", paths=["src/"])
        self.create("ui", paths=["src/main.py"])
        # Bypass normal reservation protection to simulate corrupt/imported records.
        self.db.execute(
            "UPDATE orbit_agent_tasks SET status='RESERVED',revision=2")
        self.db.commit()
        out = self.preflight([self.slot("api", 2), self.slot("ui", 2)])
        self.assertEqual(out["status"], "HOLD_HOST_PREFLIGHT")
        self.assertEqual(out["handoffs"], [])
        self.assertIn("HOLD_WRITE_SCOPE_CONFLICT",
                      [i["status"] for i in out["issues"]])

    def test_resolved_parallel_alias_collision_holds_all_handoffs(self):
        real = self.root / "src" / "real"
        real.mkdir(parents=True)
        try:
            os.symlink(real, self.root / "src" / "alias",
                       target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Symlinks unavailable on this host: " + type(exc).__name__)
        self.create("real", paths=["src/real/"])
        self.create("alias", paths=["src/alias/"])
        # An imported/corrupt ledger can bypass the normal reservation
        # collision check; final batch preflight must still block it.
        self.db.execute("UPDATE orbit_agent_tasks SET status='RESERVED',revision=2")
        self.db.commit()
        before = self.db.total_changes
        out = self.preflight([self.slot("real", 2), self.slot("alias", 2)])
        self.assertEqual(out["status"], "HOLD_HOST_PREFLIGHT")
        self.assertEqual(out["handoffs"], [])
        self.assertIn("HOLD_WRITE_SCOPE_CONFLICT",
                      [issue["status"] for issue in out["issues"]])
        self.assertEqual(self.db.total_changes, before)
        self.assertFalse(out["native_invoked"])

    def test_symlink_escape_added_after_reservation_blocks_batch(self):
        self.create("api", paths=["src/late/"])
        revision = self.reserve("api")
        self.other.mkdir(parents=True, exist_ok=True)
        (self.root / "src").mkdir(exist_ok=True)
        try:
            os.symlink(self.other, self.root / "src" / "late",
                       target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("Symlinks unavailable on this host: " + type(exc).__name__)
        before = self.db.total_changes
        out = self.preflight([self.slot("api", revision)])
        self.assertEqual(out["status"], "HOLD_HOST_PREFLIGHT")
        self.assertEqual(out["handoffs"], [])
        self.assertIn("HOLD_UNSAFE_WRITE_SCOPE",
                      [issue["status"] for issue in out["issues"]])
        self.assertEqual(self.db.total_changes, before)
        self.assertFalse(out["native_invoked"])

    def test_missing_and_wrong_project_rejected(self):
        self.create("api")
        out = self.preflight([self.slot("missing", 1)])
        self.assertEqual(out["status"], "HOLD_TASK_MISSING")
        out = self.preflight([self.slot("api", 1)], project="other-project")
        self.assertEqual(out["status"], "HOLD_TASK_MISSING")

    def test_unsupported_host_and_false_claims(self):
        self.create("api")
        rev = self.reserve("api")
        out = self.preflight([self.slot("api", rev)],
                             host="codex", available_host_tools=["not-real"])
        self.assertEqual(out["status"], "HOLD_HOST_PREFLIGHT")
        self.assertFalse(out["host_permissions_verified"])
        self.assertFalse(out["host_liveness_verified"])
        with self.assertRaises(ValueError):
            self.preflight([self.slot("api", rev)], host="unknown")

    def test_invalid_tool_names_and_extra_fields_denied(self):
        self.create("api")
        rev = self.reserve("api")
        for args in ({"available_host_tools": ["invoke_subagent", "invoke_subagent"]},
                     {"available_host_tools": ["sudo rm -rf /"]},
                     {"tasks": [{"task_key":"api", "expected_revision":rev,
                                "confirm_write":True}]},
                     {"tasks": [{"task_key":"api", "expected_revision":True}]},
                     {"tasks": []}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.preflight([self.slot("api", rev)], **args)

    def test_accepted_dependency_is_still_checked_by_existing_handoff(self):
        self.create("base")
        self.create("child", depends=["base"], paths=["child/"])
        # Emulate a valid previous approval for a completion record.
        self.db.execute(
            "UPDATE orbit_agent_tasks SET status='REVIEW_ACCEPTED' "
            "WHERE task_key='base'")
        self.db.commit()
        rev = self.reserve("child")
        allowed = self.preflight([self.slot("child", rev)])
        self.assertEqual(allowed["status"], "HOST_INVOCATIONS_REQUIRED")
        # Simulate evidence revoked before invocation.
        self.db.execute("UPDATE orbit_agent_tasks SET status='REWORK' WHERE task_key='base'")
        self.db.commit()
        blocked = self.preflight([self.slot("child", rev)])
        self.assertEqual(blocked["status"], "HOLD_HOST_PREFLIGHT")
        self.assertEqual(blocked["handoffs"], [])


if __name__ == "__main__":
    unittest.main()
