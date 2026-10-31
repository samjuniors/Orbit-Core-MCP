"""Orbit M2: portable, *non-executing* host-native specialist handoffs.

The IDE invokes its own native delegation tool after user/host permission. No
MCP API can introspect a host's private tool registry or attest a subagent
session from a caller-provided string. An advertised tool is a hint, not proof.
"""
from __future__ import annotations

import json
import re

import orbit_evidence
import orbit_tasks

HOST_NATIVE_TOOLS = {
    "antigravity": ("invoke_subagent",),
    "codex": ("spawn_agent",),
    "claude-code": ("Agent", "Task"),
    "vscode": (),
    "claude-desktop": (),
    "generic": (),
}
TRUST_NOTE = ("All host tools, approval references and session identifiers in MCP "
              "arguments are caller-reported. Only the connected IDE can attest a "
              "real native invocation and permission. No agent has been spawned.")
NO_SIDE_EFFECTS = (
    "No delete, push, merge, deploy, secrets, new tools, external installs or "
    "model-provider switches without separate real host/user approval."
)
ALLOWED_TOOL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
HOST_WORKSPACE_MODES = ("unknown", "read-only", "workspace-write")


def workspace_mode(args):
    """Caller-observed hint, never a host-sandbox or approval attestation."""
    mode = args.get("host_workspace_mode", "unknown")
    if mode not in HOST_WORKSPACE_MODES:
        raise ValueError("host_workspace_mode must be unknown, read-only or workspace-write")
    return mode


def handoff(conn, args, root):
    mode = workspace_mode(args)
    host = args.get("host")
    tools = args.get("available_host_tools", [])
    if host not in HOST_NATIVE_TOOLS:
        raise ValueError("Unsupported host label")
    if not isinstance(tools, list) or len(tools) > 32 or any(
            not isinstance(t, str) or not ALLOWED_TOOL_PATTERN.fullmatch(t)
            for t in tools):
        raise ValueError("Host tools must be 0..32 bounded tool names")
    if len(set(tools)) != len(tools):
        raise ValueError("Duplicate reported host tool names")
    # _row scopes on both verified project directory and project slug.
    task = orbit_tasks.public(orbit_tasks._row(conn, args, root))
    deps = []
    for key in task["depends_on"]:
        row = conn.execute(
            "SELECT status FROM orbit_agent_tasks WHERE project=? AND project_root=? AND task_key=?",
            (task["project"], str(root), key)).fetchone()
        status = row["status"] if row else "MISSING"
        if status != "REVIEW_ACCEPTED":
            deps.append({"task_key": key, "status": status})

    # Filesystem aliases may change after reservation. Fail closed again
    # before exposing a native host invocation packet; the host must still
    # enforce actual filesystem scope and user permission at invocation time.
    unsafe_scope = False
    own_scopes = []
    resolved_scopes = []
    if task['status'] == 'RESERVED':
        try:
            own_scopes = orbit_tasks._scopes(task['write_paths'])
            resolved_scopes = orbit_tasks._resolved_scopes(root, own_scopes)
        except (TypeError, ValueError):
            unsafe_scope = True

    # A direct per-task handoff must not bypass the all-or-nothing swarm
    # preflight. Imported/corrupt state or filesystem aliases can introduce
    # a conflicting reservation *after* reserve() checked the same root.
    # Never disclose another project's task keys, file paths or identities.
    competing_status = None
    if task['status'] == 'RESERVED' and not unsafe_scope:
        active = conn.execute(
            """SELECT project, task_key, write_paths FROM orbit_agent_tasks
               WHERE project_root=? AND status IN ('RESERVED','RUNNING')""",
            (str(root),)).fetchall()
        if len(active) > orbit_tasks.MAX_CONCURRENT:
            competing_status = "HOLD_ACTIVE_CAPACITY_UNVERIFIED"
        else:
            for other in active:
                if (other['project'], other['task_key']) == (task['project'], task['task_key']):
                    continue
                try:
                    other_scopes = orbit_tasks._scopes(json.loads(other['write_paths']))
                    other_resolved = orbit_tasks._resolved_scopes(root, other_scopes)
                except (TypeError, ValueError, json.JSONDecodeError):
                    competing_status = "HOLD_OTHER_ACTIVE_SCOPE_UNVERIFIED"
                    break
                if (orbit_tasks._collisions(own_scopes, other_scopes)
                        or orbit_tasks._collisions(resolved_scopes, other_resolved)):
                    competing_status = "HOLD_ACTIVE_SCOPE_CONFLICT"
                    break

    # The host tool names are exact; installed agent Markdown metadata and MCP
    # configuration are not evidence of a running host-native agent.
    approved_tool = next(
        (name for name in HOST_NATIVE_TOOLS[host] if name in tools), None)
    if task["status"] != "RESERVED":
        status = "HOLD_RESERVE_TASK_FIRST"
        next_step = ("Reserve this existing task using orbit_task_reserve with "
                     "the latest revision and genuine host/user consent.")
    elif task['role'] not in orbit_tasks.ROLES:
        status = "HOLD_INVALID_SPECIALIST_ROLE"
        next_step = ("Reconcile the saved task role against supported Orbit "
                     "specialists before any native host invocation.")
    elif task['host_session']:
        status = "HOLD_SESSION_ALREADY_RECORDED"
        next_step = ("Inspect the actual host session before delegating again. "
                     "Never reuse a reserved task with a recorded session.")
    elif deps:
        status = "HOLD_UNACCEPTED_DEPENDENCIES"
        next_step = "Review and accept every prerequisite before delegation."
    elif unsafe_scope:
        status = "HOLD_UNSAFE_WRITE_SCOPE"
        next_step = ("Workspace symlink or path ownership changed after reservation. "
                     "Do not invoke a native agent; reconcile the unused reservation "
                     "with real host consent and repair the task scope.")
    elif mode == "read-only" and own_scopes:
        status = "HOLD_HOST_WORKSPACE_READ_ONLY"
        next_step = ("The connected host reports a read-only workspace. Do not "
                     "invoke a writable specialist; ask the host for legitimate "
                     "workspace permissions or use a read-only task. Reconcile "
                     "any unused reservation through orbit_task_release.")
    elif competing_status:
        status = competing_status
        next_step = ("Reconcile existing active workspace reservations and "
                     "their file ownership in the real host; do not start a "
                     "worker or expose unrelated project details.")
    elif not approved_tool:
        status = "HOLD_NATIVE_TOOL_UNAVAILABLE"
        next_step = ("Release an unused reservation with orbit_task_release, "
                     "then use permitted serial host execution or a handoff. "
                     "Never substitute an external CLI or claim a subagent ran.")
    else:
        status = "HOST_INVOCATION_REQUIRED"
        next_step = ("Invoke this exact native tool through the connected "
                     "host under its real permission controls. When it "
                     "returns a real session/reference, call orbit_task_started "
                     "with the fresh revision. The MCP never invokes it.")

    # Source pointers (not external content) provide only a minimal, optional
    # context for research or architecture tasks. They are project-bound to
    # the exact resolved root, and never auto-activate a skill.
    sources = []
    if args.get("include_research", False):
        pack = orbit_evidence.context(
            conn, root, task["project"],
            {"objective": task["goal"][:600], "limit": 2, "max_chars": 1300})
        sources = [
            {"url": item["url"], "title": item["title"],
             "note": item["note"][:150]}
            for item in pack["sources"]]
    handoff_data = {
        "project": task["project"],
        "project_root": str(root),
        "task_key": task["task_key"],
        "task_revision": task["revision"],
        "milestone_step": task["step"],
        "role": task["role"],
        # Name is a *candidate*, not proof a specialist agent is installed
        # or permitted in the connected host; let the host resolve/fallback.
        "specialist_agent_hint": ("orbit-" + task["role"]
                                  if task["role"] in orbit_tasks.ROLES else None),
        "specialist_verified_in_host": False,
        "model_selected_by_orbit": False,
        "goal": task["goal"],
        "reason": task["reason"],
        "write_paths": task["write_paths"],
        "read_policy": "Read only the relevant files and canonical project docs",
        "dependent_task_keys": task["depends_on"],
        "requires": "Actual host consent; inspect Git diff and run real tests",
        "prohibited_actions": NO_SIDE_EFFECTS,
        "output": "Actual host session ID, source revision, changed paths, test commands and exit codes, risks and blockers",
        "host_return_checklist": [
            "Identify the real native specialist and host tool used",
            "Confirm the host-approved scope and independent session reference",
            "Inspect source diff and executed tests before separate task review",
        ],
        "research_pointers_untrusted": sources,
    }
    # Never truncate a scope or expectation silently. A broad packet requires
    # task decomposition, not silently withholding part of the write boundary.
    if len(json.dumps(handoff_data, ensure_ascii=True)) > 7600:
        status = "HOLD_HANDOFF_TOO_LARGE"
        next_step = "Split or simplify the task before delegation."
        handoff_data = None
    return {
        "status": status,
        "task_status": task["status"],
        "host": host,
        "available_host_tools_are_caller_reported": True,
        "host_workspace_mode_reported": mode,
        "host_workspace_writes_verified": False,
        "native_tool": approved_tool if status == "HOST_INVOCATION_REQUIRED" else None,
        "native_invoked": False,
        "host_session_verified": False,
        "host_execution_verified": False,
        "approval_verified": False,
        "unaccepted_dependencies": deps,
        "handoff": handoff_data if status == "HOST_INVOCATION_REQUIRED" else None,
        "next_action": next_step,
        "fallback": "Host lead acts serially within existing permissions; no new model runner",
        "warning": TRUST_NOTE,
    }
