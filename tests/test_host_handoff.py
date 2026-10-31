"""M2 handoff: actual host execution is required, never simulated by the MCP."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/runtime"))
import orbit_delegation
import orbit_evidence
import orbit_mcp
import orbit_tasks


class HostHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "demo"
        self.other = Path(self.tmp.name) / "other"
        self.root.mkdir()
        self.other.mkdir()
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        orbit_tasks.setup(self.db)
        orbit_evidence.setup(self.db)

    def call(self, name, **fields):
        return orbit_mcp.execute(self.db, name, {
            "project_root": str(self.root), "project": "todo", **fields})

    def register(self, *, key="frontend", deps=None, scope=None):
        answer = self.call("orbit_task_plan", task_key=key, step="IMPLEMENT",
                          role="frontend", goal="Research memory and build an accessible todo interface",
                          reason="Deliver a verified working feature without replacing user files",
                          depends_on=deps or [], write_paths=scope or ["src/ui/"],
                          confirm_write=True)
        self.assertEqual(answer["status"], "PLANNED")
        return answer["task"]

    def reserve(self, key="frontend"):
        task = self.db.execute(
            "SELECT revision FROM orbit_agent_tasks WHERE project=? AND task_key=?",
            ("todo", key)).fetchone()
        return self.call("orbit_task_reserve", task_key=key,
                         expected_revision=task["revision"],
                         approval_reference="host-approved-plan-123",
                         confirm_write=True)

    def handoff(self, *, host="antigravity", tools=None, key="frontend",
                include_research=False, **overrides):
        return self.call("orbit_task_handoff",
                         task_key=key, host=host,
                         available_host_tools=(["invoke_subagent"] if tools is None else tools),
                         include_research=include_research, **overrides)

    def test_without_reservation_never_claims_delegation(self):
        self.register()
        result = self.handoff()
        self.assertEqual(result["status"], "HOLD_RESERVE_TASK_FIRST")
        self.assertIsNone(result["handoff"])
        self.assertFalse(result["native_invoked"])
        self.assertFalse(result["host_execution_verified"])
        self.assertFalse(result["approval_verified"])

    def test_supported_antigravity_handoff_does_not_invoke(self):
        self.register()
        self.assertEqual(self.reserve()["status"], "RESERVED")
        prior = self.db.execute("SELECT revision,status FROM orbit_agent_tasks").fetchone()
        packet = self.handoff()
        self.assertEqual(packet["status"], "HOST_INVOCATION_REQUIRED")
        self.assertEqual(packet["native_tool"], "invoke_subagent")
        self.assertEqual(packet["handoff"]["write_paths"], ["src/ui/"])
        self.assertEqual(packet["handoff"]["task_revision"], 2)
        self.assertEqual(packet["handoff"]["specialist_agent_hint"], "orbit-frontend")
        self.assertFalse(packet["handoff"]["specialist_verified_in_host"])
        self.assertFalse(packet["handoff"]["model_selected_by_orbit"])
        self.assertIn("source revision", packet["handoff"]["output"])
        self.assertEqual(len(packet["handoff"]["host_return_checklist"]), 3)
        self.assertFalse(packet["native_invoked"])
        self.assertIsNone(packet.get("host_session"))
        now = self.db.execute("SELECT revision,status FROM orbit_agent_tasks").fetchone()
        self.assertEqual(tuple(prior), tuple(now))
        self.assertFalse((self.root / ".orbit").exists())

    def test_host_name_mismatch_is_honest_hold(self):
        self.register()
        self.reserve()
        result = self.handoff(host="codex", tools=["invoke_subagent"])
        self.assertEqual(result["status"], "HOLD_NATIVE_TOOL_UNAVAILABLE")
        self.assertIn("orbit_task_release", result["next_action"])
        self.assertIsNone(result["native_tool"])
        self.assertIsNone(result["handoff"])

    def test_codex_and_claude_code_reported_native_tool_names(self):
        self.register()
        self.reserve()
        for host, tools, expected in (
            ("codex", ["spawn_agent"], "spawn_agent"),
            ("claude-code", ["Agent"], "Agent"),
            ("claude-code", ["Task"], "Task")):
            with self.subTest(host=host, tools=tools):
                packet = self.handoff(host=host, tools=tools)
                self.assertEqual(packet["native_tool"], expected)
                self.assertEqual(packet["status"], "HOST_INVOCATION_REQUIRED")

    def test_direct_handoff_holds_writable_task_in_read_only_host(self):
        self.register()
        self.reserve()
        before = self.db.total_changes
        blocked = self.handoff(host_workspace_mode="read-only")
        self.assertEqual(blocked["status"], "HOLD_HOST_WORKSPACE_READ_ONLY")
        self.assertIsNone(blocked["handoff"])
        self.assertFalse(blocked["native_invoked"])
        self.assertFalse(blocked["host_workspace_writes_verified"])
        self.assertEqual(blocked["host_workspace_mode_reported"], "read-only")
        self.assertEqual(before, self.db.total_changes)
        permitted_hint = self.handoff(host_workspace_mode="workspace-write")
        self.assertEqual(permitted_hint["status"], "HOST_INVOCATION_REQUIRED")
        self.assertFalse(permitted_hint["approval_verified"])
        self.assertFalse(permitted_hint["host_workspace_writes_verified"])

    def test_direct_read_only_task_still_handoffs_and_invalid_mode_is_rejected(self):
        planned = self.call(
            "orbit_task_plan", task_key="audit", step="DISCOVER",
            role="research", goal="Inspect project files without editing source or data",
            reason="Provide independent evidence for the reviewed application",
            write_paths=[], depends_on=[], confirm_write=True)
        self.assertEqual(planned["status"], "PLANNED")
        reserved = self.call(
            "orbit_task_reserve", task_key="audit",
            expected_revision=planned["task"]["revision"],
            approval_reference="host-approved-audit-456", confirm_write=True)
        self.assertEqual(reserved["status"], "RESERVED")
        packet = self.handoff(key="audit", host_workspace_mode="read-only")
        self.assertEqual(packet["status"], "HOST_INVOCATION_REQUIRED")
        self.assertEqual(packet["handoff"]["write_paths"], [])
        self.assertEqual(packet["handoff"]["specialist_agent_hint"], "orbit-research")
        self.assertFalse(packet["host_workspace_writes_verified"])
        with self.assertRaises(ValueError):
            self.handoff(key="audit", host_workspace_mode="unrestricted")

    def test_unsupported_hosts_and_empty_tool_set_fail_closed(self):
        self.register()
        self.reserve()
        for host in ("vscode", "claude-desktop", "generic"):
            with self.subTest(host=host):
                self.assertEqual(
                    self.handoff(host=host, tools=["invoke_subagent"])["status"],
                    "HOLD_NATIVE_TOOL_UNAVAILABLE")
        self.assertEqual(self.handoff(tools=[])["status"], "HOLD_NATIVE_TOOL_UNAVAILABLE")

    def test_disjoint_parallel_reservations_keep_direct_handoffs_available(self):
        self.register()
        self.assertEqual(self.reserve()["status"], "RESERVED")
        other = self.call(
            "orbit_task_plan", task_key="backend", step="IMPLEMENT",
            role="backend", goal="Create a bounded and testable backend service",
            reason="Independent API work for an approved application feature",
            write_paths=["src/api/"], depends_on=[], confirm_write=True)
        reserved = self.call(
            "orbit_task_reserve", task_key="backend",
            expected_revision=other["task"]["revision"],
            approval_reference="host-approved-plan-456", confirm_write=True)
        self.assertEqual(reserved["status"], "RESERVED")
        before = self.db.total_changes
        for key, expected in (("frontend", "orbit-frontend"),
                              ("backend", "orbit-backend")):
            with self.subTest(key=key):
                out = self.handoff(key=key)
                self.assertEqual(out["status"], "HOST_INVOCATION_REQUIRED")
                self.assertEqual(out["handoff"]["specialist_agent_hint"], expected)
                self.assertFalse(out["handoff"]["specialist_verified_in_host"])
        self.assertEqual(self.db.total_changes, before)

    def test_direct_handoff_blocks_imported_cross_project_scope_conflict_without_leak(self):
        self.register()
        self.reserve()
        ghost = orbit_tasks.plan(self.db, {
            "project": "confidential-other-project", "task_key": "hidden",
            "step": "IMPLEMENT", "role": "backend",
            "goal": "Implement a different owner's confidential backend code",
            "reason": "Synthetic imported ledger record for scope isolation",
            "write_paths": ["src/ui/subdir/"], "depends_on": [],
            "confirm_write": True,
        }, self.root.resolve())
        self.assertEqual(ghost["status"], "PLANNED")
        self.db.execute(
            "UPDATE orbit_agent_tasks SET status='RESERVED' "
            "WHERE project='confidential-other-project'")
        self.db.commit()
        before = self.db.total_changes
        out = self.handoff()
        self.assertEqual(out["status"], "HOLD_ACTIVE_SCOPE_CONFLICT")
        self.assertIsNone(out["handoff"])
        self.assertFalse(out["native_invoked"])
        self.assertNotIn("confidential-other-project", json.dumps(out))
        self.assertNotIn("subdir", json.dumps(out))
        self.assertEqual(self.db.total_changes, before)

    def test_direct_handoff_blocks_corrupt_other_active_scope(self):
        self.register()
        self.reserve()
        ghost = orbit_tasks.plan(self.db, {
            "project": "hidden-scope", "task_key": "other",
            "step": "IMPLEMENT", "role": "backend",
            "goal": "Implement unrelated source with independent test evidence",
            "reason": "Simulate imported corrupt project ledger state",
            "write_paths": ["unrelated/"], "depends_on": [],
            "confirm_write": True,
        }, self.root.resolve())
        self.assertEqual(ghost["status"], "PLANNED")
        self.db.execute(
            "UPDATE orbit_agent_tasks SET status='RESERVED',write_paths='invalid-json' "
            "WHERE project='hidden-scope'")
        self.db.commit()
        before = self.db.total_changes
        out = self.handoff()
        self.assertEqual(out["status"], "HOLD_OTHER_ACTIVE_SCOPE_UNVERIFIED")
        self.assertIsNone(out["handoff"])
        self.assertNotIn("hidden-scope", json.dumps(out))
        self.assertEqual(self.db.total_changes, before)

    def test_direct_handoff_holds_reserved_session_already_recorded(self):
        self.register()
        self.reserve()
        self.db.execute(
            "UPDATE orbit_agent_tasks SET host_session='prior-native-session-123' "
            "WHERE task_key='frontend'")
        self.db.commit()
        before = self.db.total_changes
        out = self.handoff()
        self.assertEqual(out["status"], "HOLD_SESSION_ALREADY_RECORDED")
        self.assertIsNone(out["handoff"])
        self.assertFalse(out["native_invoked"])
        self.assertEqual(before, self.db.total_changes)

    def test_direct_handoff_rejects_imported_unsupported_specialist_role(self):
        self.register()
        self.reserve()
        self.db.execute(
            "UPDATE orbit_agent_tasks SET role='injected-foreign-role' "
            "WHERE task_key='frontend'")
        self.db.commit()
        before = self.db.total_changes
        result = self.handoff()
        self.assertEqual(result["status"], "HOLD_INVALID_SPECIALIST_ROLE")
        self.assertIsNone(result["handoff"])
        self.assertFalse(result["native_invoked"])
        self.assertEqual(self.db.total_changes, before)

    def test_direct_handoff_blocks_broken_capacity_state(self):
        self.register()
        self.reserve()
        for key in ("other-1", "other-2"):
            ghost = orbit_tasks.plan(self.db, {
                "project": "hidden-project", "task_key": key,
                "step": "IMPLEMENT", "role": "qa",
                "goal": "Independently test an isolated historical workload",
                "reason": "Simulate imported extra active records at workspace root",
                "write_paths": [key + "/"], "depends_on": [],
                "confirm_write": True,
            }, self.root.resolve())
            self.assertEqual(ghost["status"], "PLANNED")
        self.db.execute("UPDATE orbit_agent_tasks SET status='RESERVED' WHERE project='hidden-project'")
        self.db.commit()
        before = self.db.total_changes
        out = self.handoff()
        self.assertEqual(out["status"], "HOLD_ACTIVE_CAPACITY_UNVERIFIED")
        self.assertIsNone(out["handoff"])
        self.assertNotIn("hidden-project", json.dumps(out))
        self.assertEqual(self.db.total_changes, before)

    def test_delegation_does_not_enable_cross_project_or_folder_access(self):
        self.register()
        self.reserve()
        with self.assertRaises(ValueError):
            self.call("orbit_task_handoff", project="different",
                      task_key="frontend", host="antigravity",
                      available_host_tools=["invoke_subagent"])
        with self.assertRaises(ValueError):
            self.call("orbit_task_handoff", project_root=str(self.other),
                      task_key="frontend", host="antigravity",
                      available_host_tools=["invoke_subagent"])

    def test_research_context_is_optional_and_scoped_source_pointer(self):
        self.register()
        self.reserve()
        record = orbit_evidence.save(self.db, self.root.resolve(), "todo", {
            "source_key": "research-guide", "title": "Research memory architecture",
            "url": "https://example.com/agent/research", "tags": ["research","agent"],
            "note": "Read current source independently", "confirm_write": True})
        self.assertEqual(record["status"], "SAVED")
        self.assertEqual(self.handoff()["handoff"]["research_pointers_untrusted"], [])
        with_notes = self.handoff(include_research=True)
        links = with_notes["handoff"]["research_pointers_untrusted"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["url"], "https://example.com/agent/research")
        self.assertNotIn("external content", json.dumps(with_notes))

    def test_handoff_rejects_malformed_reported_tool_names(self):
        self.register()
        self.reserve()
        for tool_names in (["invoke_subagent", "invoke_subagent"],
                           ["invoke_subagent; rm -rf /"], ["../invoke_subagent"]):
            with self.subTest(names=tool_names), self.assertRaises(ValueError):
                self.handoff(tools=tool_names)
        with self.assertRaises(ValueError):
            self.handoff(host="randomhost")

    def test_running_task_is_not_reinvoked(self):
        self.register()
        self.reserve()
        started = self.call("orbit_task_started", task_key="frontend",
                            expected_revision=2,
                            host_session="native-session-12345",
                            confirm_write=True)
        self.assertEqual(started["status"], "RUNNING_REPORTED")
        packet = self.handoff()
        self.assertEqual(packet["status"], "HOLD_RESERVE_TASK_FIRST")
        self.assertFalse(packet["native_invoked"])

    def test_m3_host_permission_denial_releases_unused_slot_without_invocation(self):
        self.register()
        self.assertEqual(self.reserve()['status'],'RESERVED')
        preview=self.call('orbit_task_release',task_key='frontend',
            expected_revision=2, reason_code='HOST_PERMISSION_DENIED',
            reason='The host refused the native agent permission request')
        self.assertEqual(preview['status'],'PREVIEW_ONLY')
        self.assertEqual(preview['proposed_status'],'BLOCKED')
        self.assertEqual(self.call('orbit_task_list')['tasks'][0]['status'],'RESERVED')
        denied=self.call('orbit_task_release',task_key='frontend',
            expected_revision=2,reason_code='HOST_PERMISSION_DENIED',
            reason='The host refused the native agent permission request',
            confirm_write=True)
        self.assertEqual(denied['status'],'BLOCKED')
        self.assertFalse(denied['agent_stopped_by_mcp'])
        self.assertFalse(denied['host_permission_verified'])
        self.assertEqual(denied['task']['revision'],3)
        self.assertEqual(denied['task']['host_session'],'')
        self.assertIn('HOST_PERMISSION_DENIED',denied['task']['note'])
        # A declined reservation does not claim a host invocation or accepted QA.
        self.assertEqual(self.handoff()['status'],'HOLD_RESERVE_TASK_FIRST')
        self.register(key='other',scope=['src/ui/'])
        self.assertEqual(self.reserve(key='other')['status'],'RESERVED')

    def test_m3_denied_task_needs_a_new_approval_reference_before_retry(self):
        self.register()
        self.reserve()
        self.call('orbit_task_release',task_key='frontend',expected_revision=2,
                  reason_code='HOST_PERMISSION_DENIED',
                  reason='Host denied access to the requested agent',
                  confirm_write=True)
        with self.assertRaisesRegex(ValueError,'fresh host/user approval'):
            self.call('orbit_task_reserve',task_key='frontend',
                      expected_revision=3,approval_reference='host-approved-plan-123',
                      confirm_write=True)
        task=self.call('orbit_task_list')['tasks'][0]
        self.assertEqual(task['status'],'BLOCKED')
        self.assertEqual(task['revision'],3)
        resumed=self.call('orbit_task_reserve',task_key='frontend',
                         expected_revision=3,approval_reference='new-real-host-approval-456',
                         confirm_write=True)
        self.assertEqual(resumed['status'],'RESERVED')
        self.assertFalse(resumed['agent_spawned'])
        self.assertEqual(resumed['task']['revision'],4)

    def test_m3_unavailable_and_failed_invocation_remain_blocked(self):
        for key,code in (('native-tool','HOST_TOOL_UNAVAILABLE'),
                         ('invocation','HOST_INVOCATION_FAILED')):
            with self.subTest(code=code):
                self.register(key=key,scope=['src/'+key+'/'])
                self.reserve(key=key)
                event=self.call('orbit_task_release',task_key=key,
                    expected_revision=2,reason_code=code,
                    reason='Host reported no working tool before invocation',
                    confirm_write=True)
                self.assertEqual(event['status'],'BLOCKED')
                self.assertFalse(event['agent_stopped_by_mcp'])
        self.register(key='cancelled',scope=['src/cancelled/'])
        default=self.call('orbit_task_release',task_key='cancelled',
            expected_revision=1, reason='User cancelled this pending task',
            confirm_write=True)
        self.assertEqual(default['status'],'CANCELLED')
        self.assertEqual(default['reason_code'],'USER_CANCELLED')

    def test_m3_denial_cannot_cancel_live_agent_or_use_stale_revision(self):
        self.register()
        self.reserve()
        stale=self.call('orbit_task_release',task_key='frontend',
            expected_revision=1,reason_code='HOST_PERMISSION_DENIED',
            reason='Native permission denied during handoff',confirm_write=True)
        self.assertEqual(stale['status'],'STALE_REVISION')
        self.assertEqual(self.call('orbit_task_list')['tasks'][0]['status'],'RESERVED')
        self.call('orbit_task_started',task_key='frontend',
                  expected_revision=2,host_session='actual-host-session-123',
                  confirm_write=True)
        with self.assertRaisesRegex(ValueError,'running tasks must be stopped in the host'):
            self.call('orbit_task_release',task_key='frontend',
                      expected_revision=3,reason_code='HOST_PERMISSION_DENIED',
                      reason='Attempted to release running host agent',
                      confirm_write=True)
        task=self.call('orbit_task_list')['tasks'][0]
        self.assertEqual(task['status'],'RUNNING')
        self.assertEqual(task['revision'],3)
        with self.assertRaises(ValueError):
            orbit_mcp.validate('orbit_task_release',{
                'project_root':str(self.root),'project':'todo',
                'task_key':'frontend','expected_revision':3,
                'reason':'Permission reported denied','reason_code':'FORCE_SUCCESS'})

    def running_for_recovery(self, *, key="frontend"):
        self.register(key=key)
        self.assertEqual(self.reserve(key=key)['status'],'RESERVED')
        result=self.call('orbit_task_started',task_key=key,expected_revision=2,
            host_session='actual-session-123456',confirm_write=True)
        self.assertEqual(result['status'],'RUNNING_REPORTED')
        return result

    def test_m33_uncertain_host_state_keeps_running_task_and_lock(self):
        self.running_for_recovery()
        before=self.call('orbit_task_list')
        self.assertTrue(before['host_reconciliation']['needs_host_reconciliation'])
        self.assertEqual(before['host_reconciliation']['active'][0]['host_session'],'actual-session-123456')
        for fields in (
            {},
            {'observed_host_session':'wrong-session','host_state':'STOPPED'},
            {'observed_host_session':'actual-session-123456','host_state':'UNKNOWN'},
            {'observed_host_session':'actual-session-123456','host_state':'RUNNING'},
            {'observed_host_session':'actual-session-123456','host_state':'COMPLETED'},
        ):
            with self.subTest(fields=fields):
                response=self.call('orbit_task_report',task_key='frontend',expected_revision=3,
                    outcome='CANCELLED',evidence='Requested cancellation; host state unconfirmed',
                    confirm_write=True,**fields)
                self.assertEqual(response['status'],'HOLD_HOST_RECONCILIATION',response)
                self.assertFalse(response['host_status_verified'])
        state=self.call('orbit_task_list')
        self.assertEqual(state['tasks'][0]['status'],'RUNNING')
        self.assertEqual(state['tasks'][0]['revision'],3)
        self.register(key='overlap',scope=['src/ui/'])
        with self.assertRaisesRegex(ValueError,'Overlapping writable scopes'):
            self.reserve(key='overlap')

    def test_m33_confirmed_cancel_requires_exact_session_and_preserves_checkpoint(self):
        self.running_for_recovery()
        cp=self.root/'.orbit'/'STATE.md'
        cp.parent.mkdir()
        cp.write_text('owner checkpoint: preserve this')
        preview=self.call('orbit_task_report',task_key='frontend',expected_revision=3,
            outcome='CANCELLED',evidence='Native agent panel reports stopped after user cancellation',
            observed_host_session='actual-session-123456',host_state='STOPPED')
        self.assertEqual(preview['status'],'PREVIEW_ONLY')
        self.assertEqual(self.call('orbit_task_list')['tasks'][0]['status'],'RUNNING')
        finished=self.call('orbit_task_report',task_key='frontend',expected_revision=3,
            outcome='CANCELLED',evidence='Native agent panel reports stopped after user cancellation',
            observed_host_session='actual-session-123456',host_state='STOPPED',confirm_write=True)
        self.assertEqual(finished['status'],'CANCELLED')
        self.assertFalse(finished['host_status_verified'])
        self.assertFalse(finished['agent_stopped_by_mcp'])
        self.assertEqual(finished['task']['revision'],4)
        self.assertEqual(finished['task']['host_session'],'actual-session-123456')
        self.assertIn('HOST_TERMINAL_REPORTED:STOPPED',finished['task']['note'])
        self.assertEqual(cp.read_text(),'owner checkpoint: preserve this')
        self.assertFalse(self.call('orbit_task_list')['host_reconciliation']['needs_host_reconciliation'])
        with self.assertRaises(ValueError):
            self.call('orbit_task_review',task_key='frontend',expected_revision=4,
                verdict='ACCEPT',review_evidence='Cannot accept a cancelled task',confirm_write=True)

    def test_m33_failed_task_requires_host_terminal_observation_before_retry(self):
        self.running_for_recovery()
        hold=self.call('orbit_task_report',task_key='frontend',expected_revision=3,
            outcome='FAILED',evidence='Host session disappeared unexpectedly')
        self.assertEqual(hold['status'],'HOLD_HOST_RECONCILIATION')
        with self.assertRaisesRegex(ValueError,'Overlapping writable scopes'):
            self.register(key='blocked-scope',scope=['src/ui/'])
            self.reserve(key='blocked-scope')
        result=self.call('orbit_task_report',task_key='frontend',expected_revision=3,
            outcome='FAILED',evidence='Inspected host session, exit code nonzero and error log',
            observed_host_session='actual-session-123456',host_state='FAILED',confirm_write=True)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['task']['revision'],4)
        self.assertEqual(self.call('orbit_task_reserve',task_key='frontend',expected_revision=4,
            approval_reference='fresh-host-approval-456',confirm_write=True)['status'],'RESERVED')

    def test_m33_resume_after_sqlite_restart_reports_unverified_host_liveness(self):
        self.running_for_recovery()
        dbfile=Path(self.tmp.name)/'recovery.sqlite'
        saved=sqlite3.connect(str(dbfile))
        try:
            self.db.backup(saved)
        finally:
            saved.close()
        recovered=sqlite3.connect(str(dbfile))
        recovered.row_factory=sqlite3.Row
        try:
            # Match the canonical project_root used by Orbit's MCP on Windows
            # (temp path casing/normalization may differ from an unresolved Path).
            canonical=orbit_mcp.project_root({'project_root':str(self.root)})
            listing=orbit_tasks.read_tasks(recovered,
                {'project':'todo'},canonical)
            self.assertEqual(listing['tasks'][0]['status'],'RUNNING')
            self.assertTrue(listing['host_reconciliation']['needs_host_reconciliation'])
            self.assertFalse(listing['host_reconciliation']['agent_liveness_verified'])
            self.assertEqual(listing['host_reconciliation']['active'][0]['revision'],3)
            # A process restart does not grant permission to erase the reservation.
            rec=orbit_tasks.reported(recovered,{'project':'todo','task_key':'frontend',
                'expected_revision':3,'outcome':'BLOCKED','evidence':'MCP restarted and cannot find host state',
                'observed_host_session':'actual-session-123456','host_state':'UNKNOWN',
                'confirm_write':True},canonical)
            self.assertEqual(rec['status'],'HOLD_HOST_RECONCILIATION')
            self.assertEqual(listing['tasks'][0]['host_session'],'actual-session-123456')
            self.assertEqual(recovered.execute('SELECT status FROM orbit_agent_tasks').fetchone()[0],'RUNNING')
        finally:
            recovered.close()

    def test_m33_preserves_existing_owner_note_when_terminal_observation_added(self):
        self.running_for_recovery()
        note='Existing historical owner note: '+'important-context-'*45
        with self.db:
            self.db.execute('UPDATE orbit_agent_tasks SET note=? WHERE project=? AND task_key=?',
                (note,'todo','frontend'))
        report=self.call('orbit_task_report',task_key='frontend',expected_revision=3,
            outcome='BLOCKED',evidence='Host panel reported stopped unexpectedly; needs rework',
            observed_host_session='actual-session-123456',host_state='STOPPED',
            confirm_write=True)
        self.assertEqual(report['status'],'BLOCKED')
        self.assertTrue(report['task']['note'].startswith(note))
        self.assertTrue(report['task']['note'].endswith('HOST_TERMINAL_REPORTED:STOPPED'))

    def test_m33_report_schema_accepts_explicit_host_observation_only(self):
        schema=orbit_mcp.TOOL_MAP['orbit_task_report']
        self.assertIn('observed_host_session',schema['properties'])
        self.assertIn('host_state',schema['properties'])
        self.assertIn('UNKNOWN',schema['properties']['host_state']['enum'])
        self.assertNotIn('TERMINATE_PROCESS',schema['properties']['host_state']['enum'])
        valid={'project_root':str(self.root),'project':'todo',
               'task_key':'frontend','expected_revision':3,'outcome':'FAILED',
               'evidence':'Host reported failure with task details',
               'observed_host_session':'actual-session-123456','host_state':'FAILED'}
        orbit_mcp.validate('orbit_task_report',valid)
        with self.assertRaises(ValueError):
            orbit_mcp.validate('orbit_task_report',{**valid,'host_state':'KILL_AGENT'})

    def test_m3_attempt_budget_counts_retries_of_same_task(self):
        self.register()
        for attempt in (1,2,3):
            reservation=self.reserve()
            self.assertEqual(reservation['status'],'RESERVED')
            self.assertEqual(reservation['attempt_number'],attempt)
            self.assertEqual(reservation['attempt_budget']['step_used'],attempt)
            revision=reservation['task']['revision']
            started=self.call('orbit_task_started',task_key='frontend',
                expected_revision=revision,host_session=f'native-session-{attempt}-abc',
                confirm_write=True)
            failed=self.call('orbit_task_report',task_key='frontend',
                expected_revision=started['task']['revision'],outcome='FAILED',
                evidence='Host reported a real failing regression test result',
                observed_host_session=f'native-session-{attempt}-abc',host_state='FAILED',
                confirm_write=True)
            self.assertEqual(failed['status'],'FAILED')
        with self.assertRaisesRegex(ValueError,'Per-step agent budget exhausted'):
            self.reserve()
        records=self.db.execute(
            'SELECT attempt_number,disposition FROM orbit_task_attempts WHERE task_key=? ORDER BY attempt_number',
            ('frontend',)).fetchall()
        self.assertEqual([x['attempt_number'] for x in records],[1,2,3])
        self.assertEqual([x['disposition'] for x in records],['HOST_REPORTED_FAILED']*3)

    def test_m3_daily_budget_counts_distinct_steps_and_retries(self):
        # Distinct step labels previously concealed repeated same-day execution.
        for n in range(12):
            key=f'job-{n}'
            planned=self.call('orbit_task_plan',task_key=key,
                step=f'milestone-{n//3}',role='backend',
                goal='Work on one bounded task and verify behavior with tests',
                reason='Run a recorded attempt without assuming host permissions',
                write_paths=[f'packages/module-{n}/'],confirm_write=True)
            self.assertEqual(planned['status'],'PLANNED')
            reservation=self.call('orbit_task_reserve',task_key=key,
                expected_revision=1,approval_reference='host-consent-report-12345',
                confirm_write=True)
            self.assertEqual(reservation['status'],'RESERVED')
            self.assertEqual(reservation['attempt_budget']['day_used'],n+1)
            started=self.call('orbit_task_started',task_key=key,
                expected_revision=2,host_session=f'native-{n}-session',confirm_write=True)
            self.call('orbit_task_report',task_key=key,
                expected_revision=started['task']['revision'],outcome='FAILED',
                evidence='Host reported failed validation for this module',
                observed_host_session=f'native-{n}-session',host_state='FAILED',
                confirm_write=True)
        planned=self.call('orbit_task_plan',task_key='over-limit',
            step='new-step',role='backend',
            goal='A separate new task that should be blocked by day budget',
            reason='The daily attempt limit is shared by project root',
            write_paths=['packages/over-limit/'],confirm_write=True)
        self.assertEqual(planned['status'],'PLANNED')
        with self.assertRaisesRegex(ValueError,'Daily agent budget exhausted'):
            self.call('orbit_task_reserve',task_key='over-limit',expected_revision=1,
                approval_reference='host-consent-report-12345',confirm_write=True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM orbit_task_attempts').fetchone()[0],12)

    def test_m3_unused_reservations_are_refunded_without_erasing_history(self):
        for n in range(4):
            key=f'unused-{n}'
            self.register(key=key,scope=[f'src/component-{n}/'])
            reservation=self.reserve(key=key)
            self.assertEqual(reservation['attempt_budget']['step_used'],1)
            released=self.call('orbit_task_release',task_key=key,
                expected_revision=reservation['task']['revision'],
                reason='No native host agent was started; user cancelled the slot',
                confirm_write=True)
            self.assertEqual(released['status'],'CANCELLED')
        rows=self.db.execute('SELECT disposition FROM orbit_task_attempts').fetchall()
        self.assertEqual(len(rows),4)
        self.assertEqual({row['disposition'] for row in rows},{'RELEASED_UNUSED'})

    def test_m3_legacy_failed_task_is_counted_without_rewriting_history(self):
        self.register()
        with self.db:
            self.db.execute("""UPDATE orbit_agent_tasks SET status='FAILED',
                revision=4, host_session='previous-native-host-session',
                reserved_at=? WHERE project='todo' AND task_key='frontend'""",
                (orbit_tasks.utc_now(),))
        first=self.call('orbit_task_reserve',task_key='frontend',
            expected_revision=4,approval_reference='fresh-user-consent-12345',
            confirm_write=True)
        self.assertEqual(first['attempt_number'],2)
        self.assertEqual(first['attempt_budget']['step_used'],2)
        legacy=self.db.execute("""SELECT disposition,attempt_number FROM orbit_task_attempts
                                  WHERE task_key='frontend' ORDER BY attempt_number""").fetchall()
        self.assertEqual([(r['disposition'],r['attempt_number']) for r in legacy],
                         [('LEGACY_UNVERIFIED',1),('RESERVED',2)])
        self.assertEqual(first['task']['revision'],5)
        self.assertEqual(first['task']['host_session'],'')
        self.assertEqual(self.db.execute(
            "SELECT host_session FROM orbit_task_attempts WHERE task_key='frontend' AND attempt_number=1"
        ).fetchone()[0],'previous-native-host-session')
        # Simulate a second terminal result after actual host invocation.
        self.call('orbit_task_started',task_key='frontend',expected_revision=5,
            host_session='current-real-native-session',confirm_write=True)
        self.call('orbit_task_report',task_key='frontend',expected_revision=6,
            outcome='FAILED',evidence='Host confirmed this second attempt failed',
            observed_host_session='current-real-native-session',host_state='FAILED',
            confirm_write=True)
        third=self.call('orbit_task_reserve',task_key='frontend',
            expected_revision=7,approval_reference='fresh-third-user-consent',
            confirm_write=True)
        self.assertEqual(third['attempt_number'],3)
        self.assertEqual(third['attempt_budget']['step_used'],3)

    def test_m3_retry_never_inherits_prior_host_session_or_burns_unused_slot(self):
        self.register()
        first=self.reserve()
        self.call('orbit_task_started',task_key='frontend',
            expected_revision=2,host_session='first-real-native-session-123',
            confirm_write=True)
        failed=self.call('orbit_task_report',task_key='frontend',
            expected_revision=3,outcome='FAILED',
            evidence='Host reported failed validation and stopped',
            observed_host_session='first-real-native-session-123',host_state='FAILED',
            confirm_write=True)
        retry=self.call('orbit_task_reserve',task_key='frontend',
            expected_revision=failed['task']['revision'],
            approval_reference='fresh-real-approval-reference',
            confirm_write=True)
        self.assertEqual(retry['attempt_number'],2)
        self.assertEqual(retry['task']['host_session'],'')
        release=self.call('orbit_task_release',task_key='frontend',
            expected_revision=retry['task']['revision'],
            reason='Second attempt never launched a host agent, release it',
            confirm_write=True)
        self.assertEqual(release['status'],'CANCELLED')
        rows=self.db.execute(
            "SELECT disposition,host_session FROM orbit_task_attempts WHERE task_key='frontend' ORDER BY attempt_number"
        ).fetchall()
        self.assertEqual([(x['disposition'],x['host_session']) for x in rows],
                         [('HOST_REPORTED_FAILED','first-real-native-session-123'),
                          ('RELEASED_UNUSED','')])
        # The first started agent is still budgeted even if the retry was unused.
        step,day=orbit_tasks._attempt_usage(self.db,'todo',
            orbit_mcp.project_root({'project_root':str(self.root)}),
            'IMPLEMENT',orbit_tasks.utc_now()[:10])
        self.assertEqual((step,day),(1,1))

    def test_m3_attempt_budget_survives_sqlite_restart(self):
        self.register()
        reserved=self.reserve()
        self.call('orbit_task_started',task_key='frontend',
            expected_revision=reserved['task']['revision'],
            host_session='session-before-restart-1234',confirm_write=True)
        terminal=self.call('orbit_task_report',task_key='frontend',
            expected_revision=3,outcome='FAILED',
            evidence='Host reported regression failure before restarting MCP',
            observed_host_session='session-before-restart-1234',host_state='FAILED',
            confirm_write=True)
        self.assertEqual(terminal['status'],'FAILED')
        path=Path(self.tmp.name)/'attempt-restart.sqlite'
        saved=sqlite3.connect(str(path))
        try:
            self.db.backup(saved)
        finally:
            saved.close()
        reopened=sqlite3.connect(str(path))
        reopened.row_factory=sqlite3.Row
        try:
            orbit_tasks.setup(reopened)
            canonical=orbit_mcp.project_root({'project_root':str(self.root)})
            retried=orbit_tasks.reserve(reopened,{
                'project':'todo','task_key':'frontend','expected_revision':4,
                'approval_reference':'approved-after-restart-1234',
                'confirm_write':True},canonical)
            self.assertEqual(retried['status'],'RESERVED')
            self.assertEqual(retried['attempt_number'],2)
            self.assertEqual(retried['attempt_budget']['step_used'],2)
            self.assertEqual(retried['task']['host_session'],'')
            prior=reopened.execute(
                "SELECT host_session FROM orbit_task_attempts WHERE task_key='frontend' AND attempt_number=1"
            ).fetchone()
            self.assertEqual(prior['host_session'],'session-before-restart-1234')
        finally:
            reopened.close()

    def test_m3_stale_reservation_has_no_attempt_history_side_effect(self):
        self.register()
        stale=self.call('orbit_task_reserve',task_key='frontend',
            expected_revision=99,approval_reference='user-consent-12345',
            confirm_write=True)
        self.assertEqual(stale['status'],'STALE_REVISION')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM orbit_task_attempts').fetchone()[0],0)
        good=self.reserve()
        self.assertEqual(good['attempt_number'],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM orbit_task_attempts').fetchone()[0],1)

    def test_m3_integrated_denial_refunds_slot_but_requires_fresh_approval(self):
        self.register()
        reserved=self.reserve()
        self.assertEqual(reserved['attempt_number'],1)
        refused=self.call('orbit_task_release',task_key='frontend',expected_revision=2,
            reason_code='HOST_PERMISSION_DENIED',
            reason='Native host explicitly refused this delegated task',
            confirm_write=True)
        self.assertEqual(refused['status'],'BLOCKED')
        history=self.db.execute(
            "SELECT disposition FROM orbit_task_attempts WHERE task_key='frontend'").fetchone()
        self.assertEqual(history['disposition'],'RELEASED_UNUSED')
        self.assertEqual(orbit_tasks._attempt_usage(
            self.db,'todo',orbit_mcp.project_root({'project_root':str(self.root)}),
            'IMPLEMENT',orbit_tasks.utc_now()[:10]),(0,0))
        with self.assertRaisesRegex(ValueError,'fresh host/user approval'):
            self.call('orbit_task_reserve',task_key='frontend',expected_revision=3,
                approval_reference='host-approved-plan-123',confirm_write=True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM orbit_task_attempts').fetchone()[0],1)
        retried=self.call('orbit_task_reserve',task_key='frontend',expected_revision=3,
            approval_reference='fresh-actual-host-approval-123',confirm_write=True)
        self.assertEqual(retried['status'],'RESERVED')
        self.assertEqual(retried['attempt_number'],2)
        self.assertEqual(retried['attempt_budget']['step_used'],1)
        self.assertEqual(retried['task']['host_session'],'')
        started=self.call('orbit_task_started',task_key='frontend',expected_revision=4,
            host_session='host-new-session-123456',confirm_write=True)
        hold=self.call('orbit_task_report',task_key='frontend',expected_revision=5,
            outcome='FAILED',evidence='MCP restarted while host state is unknown',
            observed_host_session='host-new-session-123456',host_state='UNKNOWN',
            confirm_write=True)
        self.assertEqual(hold['status'],'HOLD_HOST_RECONCILIATION')
        self.assertEqual(self.call('orbit_task_list')['tasks'][0]['status'],'RUNNING')
        self.assertEqual(self.db.execute(
            "SELECT disposition FROM orbit_task_attempts WHERE task_key='frontend' AND attempt_number=2"
        ).fetchone()['disposition'],'HOST_REPORTED_STARTED')
        terminal=self.call('orbit_task_report',task_key='frontend',expected_revision=5,
            outcome='FAILED',evidence='Actual host session exited with failing test',
            observed_host_session='host-new-session-123456',host_state='FAILED',
            confirm_write=True)
        self.assertEqual(terminal['status'],'FAILED')
        history=self.db.execute(
            "SELECT disposition,host_session FROM orbit_task_attempts WHERE task_key='frontend' ORDER BY attempt_number"
        ).fetchall()
        self.assertEqual([(x['disposition'],x['host_session']) for x in history],[
            ('RELEASED_UNUSED',''),('HOST_REPORTED_FAILED','host-new-session-123456')])

    def test_m3_integrated_running_agent_uses_budget_and_keeps_scope_locked(self):
        self.register()
        first=self.reserve()
        self.call('orbit_task_started',task_key='frontend',expected_revision=2,
            host_session='running-retry-agent-123456',confirm_write=True)
        self.register(key='overlap',scope=['src/ui/'])
        self.assertEqual(self.call('orbit_task_report',task_key='frontend',expected_revision=3,
            outcome='CANCELLED',evidence='Cancellation was requested but not confirmed',
            observed_host_session='running-retry-agent-123456',host_state='RUNNING',
            confirm_write=True)['status'],'HOLD_HOST_RECONCILIATION')
        with self.assertRaisesRegex(ValueError,'Overlapping writable scopes'):
            self.reserve(key='overlap')
        self.assertEqual(self.db.execute(
            "SELECT disposition FROM orbit_task_attempts WHERE task_key='frontend'").fetchone()['disposition'],
            'HOST_REPORTED_STARTED')
        confirmed=self.call('orbit_task_report',task_key='frontend',expected_revision=3,
            outcome='BLOCKED',evidence='Host confirmed worker stopped after interrupted process',
            observed_host_session='running-retry-agent-123456',host_state='STOPPED',
            confirm_write=True)
        self.assertEqual(confirmed['status'],'BLOCKED')
        self.assertEqual(confirmed['task']['host_session'],'running-retry-agent-123456')
        self.assertEqual(self.db.execute(
            "SELECT disposition FROM orbit_task_attempts WHERE task_key='frontend'").fetchone()['disposition'],
            'HOST_REPORTED_BLOCKED')
        retry=self.call('orbit_task_reserve',task_key='frontend',expected_revision=4,
            approval_reference='approved-new-retry-12345',confirm_write=True)
        self.assertEqual(retry['status'],'RESERVED')
        self.assertEqual(retry['attempt_number'],2)
        self.assertEqual(retry['attempt_budget']['step_used'],2)
        self.assertEqual(retry['task']['host_session'],'')
        self.assertEqual(self.db.execute(
            "SELECT host_session FROM orbit_task_attempts WHERE task_key='frontend' AND attempt_number=1"
        ).fetchone()['host_session'],'running-retry-agent-123456')

    def test_m3_integration_reservation_update_failure_rolls_back_attempt_insert(self):
        self.register()
        self.db.execute("""CREATE TRIGGER reject_task_reservation
             BEFORE UPDATE ON orbit_agent_tasks WHEN NEW.status='RESERVED'
             BEGIN SELECT RAISE(ABORT,'synthetic task update failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'synthetic task update failure'):
            self.reserve()
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM orbit_task_attempts").fetchone()[0],0)
        task=self.call('orbit_task_list')['tasks'][0]
        self.assertEqual((task['status'],task['revision']),('PLANNED',1))
        self.db.execute('DROP TRIGGER reject_task_reservation')
        reservation=self.reserve()
        self.assertEqual(reservation['status'],'RESERVED')
        self.assertEqual(reservation['attempt_number'],1)

    def test_m3_integration_started_and_reported_failure_preserve_attempt_state(self):
        self.register()
        self.reserve()
        self.db.execute("""CREATE TRIGGER reject_task_start
             BEFORE UPDATE ON orbit_agent_tasks WHEN NEW.status='RUNNING'
             BEGIN SELECT RAISE(ABORT,'synthetic start failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'synthetic start failure'):
            self.call('orbit_task_started',task_key='frontend',expected_revision=2,
                host_session='host-session-rollback-123',confirm_write=True)
        self.assertEqual(self.call('orbit_task_list')['tasks'][0]['status'],'RESERVED')
        self.assertEqual(self.db.execute(
            "SELECT disposition FROM orbit_task_attempts").fetchone()['disposition'],'RESERVED')
        self.db.execute('DROP TRIGGER reject_task_start')
        started=self.call('orbit_task_started',task_key='frontend',expected_revision=2,
            host_session='host-session-rollback-123',confirm_write=True)
        self.assertEqual(started['status'],'RUNNING_REPORTED')
        self.db.execute("""CREATE TRIGGER reject_task_report
             BEFORE UPDATE ON orbit_agent_tasks WHEN NEW.status='FAILED'
             BEGIN SELECT RAISE(ABORT,'synthetic report failure'); END""")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'synthetic report failure'):
            self.call('orbit_task_report',task_key='frontend',expected_revision=3,
                outcome='FAILED',evidence='Host reported failed validation in a real session',
                observed_host_session='host-session-rollback-123',host_state='FAILED',
                confirm_write=True)
        self.assertEqual(self.call('orbit_task_list')['tasks'][0]['status'],'RUNNING')
        self.assertEqual(self.db.execute(
            "SELECT disposition,host_session FROM orbit_task_attempts").fetchone()['disposition'],
            'HOST_REPORTED_STARTED')
        self.db.execute('DROP TRIGGER reject_task_report')
        reported=self.call('orbit_task_report',task_key='frontend',expected_revision=3,
            outcome='FAILED',evidence='Host reported failed validation in a real session',
            observed_host_session='host-session-rollback-123',host_state='FAILED',
            confirm_write=True)
        self.assertEqual(reported['status'],'FAILED')
        self.assertEqual(self.db.execute(
            "SELECT disposition FROM orbit_task_attempts").fetchone()['disposition'],
            'HOST_REPORTED_FAILED')

    def test_tool_contract_read_only_and_arguments_tight(self):
        tool = next(t for t in orbit_mcp.TOOLS if t["name"] == "orbit_task_handoff")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])
        with self.assertRaises(ValueError):
            orbit_mcp.validate("orbit_task_handoff", {
                "project_root": str(self.root), "project": "todo", "task_key": "frontend",
                "host": "antigravity", "confirm_write": True})


if __name__ == "__main__":
    unittest.main()
