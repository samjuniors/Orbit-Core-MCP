"""v0.27 source-bound integration review: fail-closed, project-scoped metadata checks.

Synthetic browser records in these tests are NOT evidence of actual Playwright
or IDE sessions. The response deliberately never calls them independently
verified QA and never performs an approval or Git operation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source" / "runtime"))
import orbit_build
import orbit_mcp
import orbit_tasks


class SwarmIntegrationReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = (Path(tmp.name) / "workspace").resolve()
        self.root.mkdir()
        (self.root / "index.html").write_text("<html><body>Fixture</body></html>", encoding="utf-8")
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        orbit_tasks.setup(self.db)
        orbit_build.setup(self.db)
        orbit_build.setup_browser(self.db)
        self.project = "integration-fixture"
        self.fingerprint = orbit_build.code_fingerprint(self.root)
        self.assertIsNotNone(self.fingerprint)
        self.tasks = [{"task_key": "ui", "expected_revision": 2}]
        self.task("ui")

    def task(self, key, *, project=None, status="REVIEW_ACCEPTED",
             revision=2, paths=None, changed=None, deps=None):
        self.db.execute(
            """INSERT INTO orbit_agent_tasks
               (project,project_root,task_key,step,role,goal,reason,write_paths,
                depends_on,status,revision,changed_paths,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (project or self.project, str(self.root), key, "Implement", "frontend",
             "Implement approved frontend source with QA", "Test task review safety",
             json.dumps(paths if paths is not None else ["index.html"]),
             json.dumps(deps or []), status, revision,
             json.dumps(changed if changed is not None else ["index.html"]),
             "2026-10-30", "2026-10-30"))
        self.db.commit()

    def build(self, project=None):
        self.db.execute(
            "INSERT INTO build_runs(project,root,build_id,stage,revision,objective,"
            "evidence_json,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (project or self.project, str(self.root), "web-app", "BROWSER_QA",
             4, "Fixture integration review", "{}", "2026-10-30"))
        self.db.commit()

    def qa(self, *, status="PASS", **overrides):
        summary = {
            "source_fingerprint": self.fingerprint,
            "preview_id": "local-fixture",
            "preview_started_at": 123.0,
            "qa_build_revision": 4,
            "actions": [{"action": "inspect-ui", "status": "PASS"}],
            "blocked_remote_hosts": [],
            "errors": [],
            "failures": [],
            **overrides,
        }
        self.db.execute(
            "INSERT INTO browser_results(project,root,build_id,status,summary,created_at)"
            " VALUES(?,?,?,?,?,?)",
            (self.project, str(self.root), "web-app", status,
             json.dumps(summary), "2026-10-30"))
        self.db.commit()

    def review(self, **overrides):
        return orbit_mcp.execute(self.db, "orbit_swarm_integration_review", {
            "project_root": str(self.root), "project": self.project,
            "tasks": self.tasks,
            "expected_source_fingerprint": self.fingerprint,
            **overrides,
        })

    def test_matching_source_and_recorded_browser_pass_never_attest_user_or_qa(self):
        self.build()
        self.qa()
        before = self.db.total_changes
        result = self.review(build_id="web-app")
        self.assertEqual(result["status"], "READY_FOR_INDEPENDENT_REVIEW")
        self.assertTrue(result["source_matches"])
        self.assertTrue(result["recorded_browser_qa_matches_source"])
        for key in ("state_written", "agent_spawned", "git_diff_verified",
                    "tests_independently_verified", "host_permission_verified",
                    "approval_verified", "merge_performed"):
            self.assertFalse(result[key])
        self.assertEqual(before, self.db.total_changes)
        tool = next(t for t in orbit_mcp.TOOLS
                    if t["name"] == "orbit_swarm_integration_review")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertEqual(len(orbit_mcp.TOOLS), 47)

    def test_file_change_invalidates_previous_qa(self):
        self.build()
        self.qa()
        (self.root / "index.html").write_text("<html>Changed</html>", encoding="utf-8")
        result = self.review(build_id="web-app")
        self.assertEqual(result["status"], "HOLD_STALE_SOURCE")
        self.assertFalse(result["source_matches"])

    def test_latest_failed_or_malformed_qa_never_reuses_older_success(self):
        self.build()
        self.qa()
        self.qa(status="FAIL")
        self.assertEqual(self.review(build_id="web-app")["status"], "HOLD_INDEPENDENT_QA")
        self.db.execute("DELETE FROM browser_results WHERE status='FAIL'")
        self.db.commit()
        self.qa(actions=[{"status": "FAIL"}])
        self.assertEqual(self.review(build_id="web-app")["status"], "HOLD_STALE_OR_INVALID_QA")

    def test_missing_browser_build_and_qa_require_explicit_host_verification(self):
        self.assertEqual(self.review()["status"], "HOLD_INDEPENDENT_QA")
        self.assertEqual(self.review(build_id="web-app")["status"], "HOLD_INDEPENDENT_QA")
        self.build()
        self.assertEqual(self.review(build_id="web-app")["status"], "HOLD_INDEPENDENT_QA")

    def test_stale_revision_unreviewed_task_and_cross_project_isolation(self):
        self.build()
        self.qa()
        self.assertEqual(
            self.review(tasks=[{"task_key": "ui", "expected_revision": 1}],
                        build_id="web-app")["issues"][0]["reason"], "STALE_TASK_REVISION")
        self.db.execute("UPDATE orbit_agent_tasks SET status='REWORK' WHERE task_key='ui'")
        self.db.commit()
        self.assertEqual(self.review(build_id="web-app")["issues"][0]["reason"],
                         "TASK_REVIEW_REQUIRED")
        other = self.review(project="other-project", build_id="web-app")
        self.assertEqual(other["status"], "HOLD_TASK_INTEGRATION")
        self.assertEqual(other["issues"][0]["reason"], "MISSING_TASK")
        self.assertNotIn("integration-fixture", str(other["issues"]))

    def test_scope_violation_and_missing_dependency_fail_closed(self):
        self.build()
        self.qa()
        self.db.execute(
            "UPDATE orbit_agent_tasks SET changed_paths='[\"private/secret.py\"]' WHERE task_key='ui'")
        self.db.commit()
        self.assertEqual(self.review(build_id="web-app")["issues"][0]["reason"],
                         "UNSAFE_CHANGED_PATHS")
        self.db.execute(
            "UPDATE orbit_agent_tasks SET changed_paths='[\"index.html\"]',"
            "depends_on='[\"base\"]' WHERE task_key='ui'")
        self.db.commit()
        self.assertEqual(self.review(build_id="web-app")["issues"][0]["reason"],
                         "DEPENDENCY_REVIEW_REQUIRED")

    def test_unrelated_live_agent_at_same_workspace_blocks_integration_privately(self):
        self.build()
        self.qa()
        self.task("private-secret-worker", project="other-project",
                  status="RUNNING", revision=1,
                  paths=["private/secret.py"], changed=[])
        before = self.db.total_changes
        result = self.review(build_id="web-app")
        self.assertEqual(result["status"], "HOLD_HOST_RECONCILIATION")
        self.assertEqual(result["active_records_same_root"], 1)
        self.assertNotIn("private-secret-worker", json.dumps(result))
        self.assertNotIn("other-project", json.dumps(result))
        self.assertEqual(self.db.total_changes, before)

    def test_declared_directory_does_not_allow_changed_symlink_escape(self):
        self.build()
        self.qa()
        assigned = self.root / "src"
        assigned.mkdir()
        outside = self.root.parent / "outside"
        outside.mkdir()
        try:
            os.symlink(str(outside), str(assigned / "escape"), target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest("OS symlink unavailable: " + type(error).__name__)
        self.db.execute(
            "UPDATE orbit_agent_tasks SET write_paths=?, changed_paths=? WHERE task_key='ui'",
            (json.dumps(["src/"]), json.dumps(["src/escape/secret.py"])))
        self.db.commit()
        result = self.review(build_id="web-app")
        self.assertEqual(result["status"], "HOLD_SOURCE_UNSCANNABLE")
        self.assertNotIn(str(outside), json.dumps(result))

    def test_unscannable_source_and_bad_args_hold(self):
        (self.root / "index.html").unlink()
        result = self.review()
        self.assertEqual(result["status"], "HOLD_SOURCE_UNSCANNABLE")
        for bad in (
            {"expected_source_fingerprint": "0" * 63},
            {"tasks": [{"task_key": "ui", "expected_revision": True}]},
            {"tasks": [{"task_key": "ui", "expected_revision": 2},
                       {"task_key": "ui", "expected_revision": 2}]},
            {"extra_field": True},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.review(**bad)


if __name__ == "__main__":
    unittest.main()
