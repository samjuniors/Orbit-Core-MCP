"""Orbit v0.28 software delivery blueprints (ECC research-inspired, original code)."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"source"/"runtime"))
import orbit_mcp
import orbit_intake
import orbit_tasks
import orbit_swarm_draft


class SoftwareDeliveryPreviewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name,"app").resolve()
        self.other=Path(tmp.name,"other").resolve()
        self.root.mkdir()
        self.other.mkdir()
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        orbit_tasks.setup(self.db)
        orbit_intake.setup(self.db)

    def preview(self, **kwargs):
        params={"project_root":str(self.root),"project":"demo",
                "objective":"Create a reliable todo app with offline-first persistence",
                "product_type":"web-app","operation":"build","maturity":"new"}
        params.update(kwargs)
        return orbit_mcp.execute(self.db,"orbit_software_delivery_preview",params)

    def test_web_app_has_complete_cross_functional_vertical_slice_and_no_writes(self):
        old=self.db.total_changes
        x=self.preview()
        self.assertEqual(x["status"],"BLUEPRINT_READY")
        self.assertEqual(x["draft_review"]["status"],"DRAFT_VALIDATED")
        roles=[x["role"] for x in x["proposed_tasks"]]
        self.assertIn("research",roles)
        self.assertIn("architect",roles)
        for role in ("ux","data","backend","frontend","integrator","qa","security","reviewer","writer","devops"):
            self.assertIn(role,roles)
        self.assertLessEqual(len(x["proposed_tasks"]),12)
        bykey={x["task_key"]:x for x in x["proposed_tasks"]}
        self.assertEqual(bykey["interface"]["depends_on"],["service"])
        self.assertEqual(bykey["service"]["depends_on"],["contracts"])
        self.assertEqual(set(bykey["review"]["depends_on"]),{"quality","security"})
        self.assertEqual(bykey["release"]["depends_on"],["handoff"])
        self.assertEqual(bykey["quality"]["step"],"QA")
        self.assertEqual(bykey["security"]["step"],"SECURITY")
        self.assertEqual(bykey["scope"]["step"],"PLAN")
        self.assertEqual(bykey["service"]["step"],"IMPLEMENT")
        self.assertTrue(all(x["write_paths"]==[] for x in x["proposed_tasks"]))
        self.assertTrue(x["needs_write_scope_selection"])
        self.assertFalse(x["implementation_ready"])
        self.assertFalse(x["agent_spawned"])
        self.assertFalse(x["approval_verified"])
        self.assertFalse(x["state_written"])
        self.assertFalse(x["model_selected"])
        self.assertFalse(x["tests_verified"])
        self.assertEqual(old,self.db.total_changes)
        self.assertEqual(self.db.execute("SELECT count(*) FROM orbit_agent_tasks").fetchone()[0],0)

    def test_nonvisual_cli_skips_ui_backend_service_and_preserves_release_gate(self):
        x=self.preview(product_type="cli",maturity="existing",operation="maintain")
        self.assertEqual(x["status"],"BLUEPRINT_READY")
        keys={x["task_key"] for x in x["proposed_tasks"]}
        self.assertNotIn("experience",keys)
        self.assertNotIn("interface",keys)
        self.assertNotIn("service",keys)
        self.assertIn("implementation",keys)
        self.assertIn("quality",keys)
        self.assertIn("security",keys)
        self.assertIn("release",keys)

    def test_visual_redesign_preserves_existing_data_and_service_contracts(self):
        x=self.preview(product_type="web-app",operation="redesign",maturity="completed",
                       objective="Redesign navigation and loading states without API changes")
        self.assertEqual(x["status"],"BLUEPRINT_READY")
        tasks={task["task_key"]:task for task in x["proposed_tasks"]}
        self.assertIn("experience",tasks)
        self.assertIn("interface",tasks)
        self.assertNotIn("contracts",tasks)
        self.assertNotIn("service",tasks)
        self.assertEqual(tasks["interface"]["depends_on"],["experience"])
        self.assertEqual(tasks["integration"]["depends_on"],["interface"])
        self.assertIn("preserve behavior",tasks["experience"]["goal"])
        self.assertIn("preserve those contracts",tasks["interface"]["goal"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM orbit_agent_tasks").fetchone()[0],0)

    def test_implementation_requires_test_first_or_explicit_blocker(self):
        for product_type in ("web-app","cli","api-service"):
            with self.subTest(product_type=product_type):
                x=self.preview(product_type=product_type,operation="build",maturity="new")
                tasks={task["task_key"]:task for task in x["proposed_tasks"]}
                self.assertIn("test runner",tasks["scope"]["goal"])
                self.assertIn("test-first is blocked",tasks["scope"]["goal"])
                for key in ("service","interface","implementation"):
                    if key in tasks:
                        self.assertIn("before implementation",tasks[key]["goal"].lower())
                self.assertTrue(all(not item["write_paths"] for item in x["proposed_tasks"]))
                self.assertFalse(x["agent_spawned"])
                self.assertFalse(x["tests_verified"])

    def test_bugfix_is_small_and_reproduces_before_repair_without_release(self):
        x=self.preview(product_type="api-service",operation="fix",maturity="stalled",
                       objective="Fix failing validation without altering existing API")
        self.assertEqual(x["status"],"BLUEPRINT_READY")
        bykey={a["task_key"]:a for a in x["proposed_tasks"]}
        self.assertIn("reproduce",bykey)
        self.assertIn("repair",bykey)
        self.assertEqual(bykey["repair"]["depends_on"],["reproduce"])
        self.assertNotIn("release",bykey)
        self.assertNotIn("experience",bykey)
        self.assertEqual(len(bykey),9)
        self.assertIn("FAIL to PASS",x["acceptance_contracts"]["repair"]["review_evidence"])

    def test_new_slice_key_prevents_overwriting_accepted_prior_work(self):
        first=self.preview()
        original=first["proposed_tasks"][0]
        self.db.execute("""INSERT INTO orbit_agent_tasks
          (project,project_root,task_key,step,role,goal,reason,write_paths,depends_on,
           status,revision,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
           ("demo",str(self.root),original["task_key"],original["step"],
            original["role"],original["goal"],original["reason"],"[]","[]",
            "REVIEW_ACCEPTED",5,"2026-10-31","2026-10-31"))
        self.db.commit()
        self.assertTrue(self.preview()["status"].startswith("HOLD_DRAFT_"))
        fresh=self.preview(slice_key="alerts")
        self.assertEqual(fresh["status"],"BLUEPRINT_READY")
        self.assertTrue(all(item["task_key"].startswith("alerts-")
                            for item in fresh["proposed_tasks"]))
        self.assertTrue(all(dep.startswith("alerts-")
                            for item in fresh["proposed_tasks"]
                            for dep in item["depends_on"]))
        self.assertEqual(self.db.execute("SELECT revision FROM orbit_agent_tasks").fetchone()[0],5)

    def test_targeted_fix_can_select_real_specialist_role(self):
        x=self.preview(operation="fix",maturity="stalled",focus_role="frontend")
        self.assertEqual(x["status"],"BLUEPRINT_READY")
        repair=next(item for item in x["proposed_tasks"] if item["task_key"]=="repair")
        self.assertEqual(repair["role"],"frontend")
        self.assertEqual(x["focus_role"],"frontend")
        with self.assertRaises(ValueError):
            self.preview(operation="build",focus_role="frontend")
        for bad in ("Other","../outside","with space","toolong-"*6):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.preview(slice_key=bad)

    def test_no_product_classification_does_not_invent_stack_or_selection(self):
        x=orbit_mcp.execute(self.db,"orbit_software_delivery_preview",
             {"project_root":str(self.root),"project":"demo","objective":"Build a project"})
        self.assertEqual(x["status"],"NEEDS_PROJECT_CLASSIFICATION")
        self.assertFalse(x["agent_spawned"])
        self.assertFalse(x["state_written"])

    def test_draft_output_is_compatible_with_existing_dag_validator(self):
        x=self.preview()
        check=orbit_mcp.execute(self.db,"orbit_swarm_draft_preview",
                    {"project_root":str(self.root),"project":"demo","tasks":x["proposed_tasks"]})
        self.assertEqual(check["status"],"DRAFT_VALIDATED")
        self.assertEqual([w["task_keys"] for w in check["review_waves"]],
                         [w["task_keys"] for w in x["draft_review"]["waves"]])
        self.assertTrue(all(len(w["task_keys"])<=2 for w in check["review_waves"]))

    def test_existing_task_key_blocked_without_resetting_evidence(self):
        self.db.execute("""INSERT INTO orbit_agent_tasks
          (project,project_root,task_key,step,role,goal,reason,write_paths,depends_on,
           status,revision,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
           ("demo",str(self.root),"scope","IMPLEMENT","architect","Approved prior work",
            "Existing accepted history","[]","[]","REVIEW_ACCEPTED",5,
            "2026-10-31","2026-10-31"))
        self.db.commit()
        before=self.db.total_changes
        x=self.preview()
        self.assertEqual(x["status"],"HOLD_DRAFT_HOLD_EXISTING_TASK_KEYS")
        self.assertEqual(x["draft_review"]["conflicting_keys"],["scope"])
        self.assertEqual(self.db.total_changes,before)
        self.assertEqual(self.db.execute("SELECT revision FROM orbit_agent_tasks WHERE task_key='scope'").fetchone()[0],5)

    def test_other_project_task_not_leaked_or_reset(self):
        self.db.execute("""INSERT INTO orbit_agent_tasks
          (project,project_root,task_key,step,role,goal,reason,write_paths,depends_on,
           status,revision,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
           ("private-project",str(self.root),"secret","IMPLEMENT","architect",
            "Sensitive other work","Unrelated","[]","[]","REVIEW_ACCEPTED",2,
            "2026-10-31","2026-10-31"))
        self.db.commit()
        x=self.preview()
        self.assertEqual(x["status"],"BLUEPRINT_READY")
        self.assertNotIn("\"task_key\": \"secret\"",json.dumps(x))
        self.assertNotIn("private-project",json.dumps(x))

    def test_invalid_schema_rejects_unreviewed_ops_paths_and_oversized_input(self):
        for params in (
            {"operation":"delete-everything"},
            {"product_type":"unknown"}, {"maturity":"made-up"},
            {"objective":"x"*901}, {"constraints":"x"*451},
            {"confirm_write":True},
        ):
            with self.subTest(params=str(params)[:100]):
                with self.assertRaises(ValueError):
                    self.preview(**params)

    def test_metadata_exposes_read_only_and_never_executes_host(self):
        m=next(x for x in orbit_mcp.TOOLS if x["name"]=="orbit_software_delivery_preview")
        self.assertTrue(m["annotations"]["readOnlyHint"])
        self.assertFalse(m["annotations"]["destructiveHint"])
        self.assertIn("model",m["description"])
        self.assertEqual(len(orbit_mcp.TOOLS),47)


if __name__=="__main__":
    unittest.main()
