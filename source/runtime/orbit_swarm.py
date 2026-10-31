"""Orbit-native swarm DAG preview over the existing project task ledger.

No model calls, agent spawning, reservations, writes, or attestations. The
host alone decides whether/how a user-approved native subagent is invoked.
"""
from __future__ import annotations

import json

import orbit_delegation
import orbit_tasks

MAX_GRAPH_TASKS = 40
CANDIDATE_STATUSES = frozenset({"PLANNED"})
TERMINAL_NOT_READY = frozenset({
    "FAILED", "REWORK", "BLOCKED", "CANCELLED", "REPORTED_DONE",
})
UPSTREAM_FAILURE_STATES = frozenset({"FAILED", "REWORK", "BLOCKED", "CANCELLED"})


def _graph_cycle(rows):
    """Return a bounded closed cycle path, or [] for an acyclic graph."""
    edges = {k: list(v["depends_on"]) for k, v in rows.items()}
    state = {}
    stack = []

    def visit(key):
        if state.get(key) == 1:
            return stack[stack.index(key):] + [key]
        if state.get(key) == 2:
            return []
        state[key] = 1
        stack.append(key)
        for dep in edges[key]:
            if dep in edges:
                cycle = visit(dep)
                if cycle:
                    return cycle
        stack.pop()
        state[key] = 2
        return []

    for key in sorted(edges):
        if state.get(key) != 2:
            cycle = visit(key)
            if cycle:
                return cycle
    return []


def preview(conn, root, project, a):
    """Compute a conservative, read-only scheduling proposal.

    Only previously registered tasks qualify; task creation remains under
    orbit_task_plan(confirm_write=...). NEVER treat a caller-supplied host tool
    as evidence of capability, user permission, or real agent execution.
    """
    host = a.get("host", "generic")
    if host not in orbit_delegation.HOST_NATIVE_TOOLS:
        raise ValueError("Unsupported native-agent host")
    tools = a.get("available_host_tools", [])
    if (not isinstance(tools, list) or len(tools) > 32 or
            any(not isinstance(t, str) or
                not orbit_delegation.ALLOWED_TOOL_PATTERN.fullmatch(t)
                for t in tools) or len(set(tools)) != len(tools)):
        raise ValueError("Invalid or duplicate reported host tool names")
    mode = orbit_delegation.workspace_mode(a)
    width = a.get("max_parallel", orbit_tasks.MAX_CONCURRENT)
    if type(width) is not int or not 1 <= width <= orbit_tasks.MAX_CONCURRENT:
        raise ValueError("max_parallel must be 1..2")
    native = next((name for name in orbit_delegation.HOST_NATIVE_TOOLS[host]
                   if name in tools), None)

    count = conn.execute(
        "SELECT COUNT(*) FROM orbit_agent_tasks WHERE project=? AND project_root=?",
        (project, str(root)),
    ).fetchone()[0]
    base = {
        "project": project,
        "project_root": str(root),
        "registered_tasks": count,
        "max_parallel": width,
        "host": host,
        "reported_native_tool": native,
        "tool_availability_caller_reported": True,
        "host_workspace_mode_reported": mode,
        "host_workspace_writes_verified": False,
        "agent_spawned": False,
        "approval_verified": False,
        "host_liveness_verified": False,
        "source_tests_verified": False,
        "state_written": False,
        "mode": "READ_ONLY_PREVIEW",
        "next": "Register tasks individually, then reserve with explicit approval and invoke the host's real native tool.",
    }
    if count > MAX_GRAPH_TASKS:
        return {**base, "status": "HOLD_GRAPH_TOO_LARGE",
                "ready_now": [], "deferred": [],
                "reason": "Split the project workload before making a swarm preview."}

    raw = conn.execute(
        """SELECT task_key, status, revision, role, goal, write_paths, depends_on
           FROM orbit_agent_tasks WHERE project=? AND project_root=?
           ORDER BY task_key""",
        (project, str(root)),
    ).fetchall()
    rows = {}
    for raw_row in raw:
        row = dict(raw_row)
        try:
            deps = json.loads(row["depends_on"])
            paths = json.loads(row["write_paths"])
            if not isinstance(deps, list) or not isinstance(paths, list):
                raise ValueError("invalid task scope encoding")
            if (len(deps) > 8 or any(not isinstance(dep, str) for dep in deps)
                    or len(deps) != len(set(deps))):
                raise ValueError("invalid dependency array")
            # The existing ledger owns path validation and overlap semantics.
            paths = orbit_tasks._scopes(paths)
            resolved = orbit_tasks._resolved_scopes(root, paths)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return {**base, "status": "HOLD_INVALID_TASK_RECORD",
                    "task_key": row["task_key"], "ready_now": [],
                    "deferred": [], "reason": str(exc)[:150]}
        rows[row["task_key"]] = {**row, "depends_on": deps, "write_paths": paths,
                                "resolved_write_paths": resolved}

    missing = sorted({dep for row in rows.values()
                      for dep in row["depends_on"] if dep not in rows})
    if missing:
        return {**base, "status": "HOLD_MISSING_DEPENDENCIES",
                "missing_dependency_keys": missing[:16],
                "ready_now": [], "deferred": [],
                "reason": "Resolve missing task records before scheduling."}
    cycle = _graph_cycle(rows)
    if cycle:
        return {**base, "status": "HOLD_DEPENDENCY_CYCLE",
                "cycle": cycle, "ready_now": [], "deferred": [],
                "reason": "Fix the cyclic task dependencies; do not execute."}

    # Orbit's existing reserve() checks active slots across the *same root*,
    # not just the current project. Do not expose other project details.
    active = conn.execute(
        """SELECT COUNT(*) FROM orbit_agent_tasks
           WHERE project_root=? AND status IN ('RESERVED','RUNNING')""",
        (str(root),),
    ).fetchone()[0]
    if active:
        return {**base, "status": "HOLD_HOST_RECONCILIATION",
                "active_records_same_root": active, "ready_now": [],
                "deferred": [],
                "reason": "Inspect real host sessions and reservations before further delegation; stored status is not host liveness."}

    # Surface actual upstream failures, including indirect failed ancestors.
    # No task is automatically failed/cancelled and unrelated ready tasks stay
    # eligible. All data is already restricted to the exact project and root.
    blocked_memo = {}

    def blocking_dependencies(key):
        if key in blocked_memo:
            return blocked_memo[key]
        blockers = set()
        for dep in rows[key]["depends_on"]:
            state = rows[dep]["status"]
            if state in UPSTREAM_FAILURE_STATES:
                blockers.add(dep)
            elif state != "REVIEW_ACCEPTED":
                blockers.update(blocking_dependencies(dep))
        blocked_memo[key] = sorted(blockers)
        return blocked_memo[key]

    ready = []
    deferred = []
    selected_scopes = []
    for key, task in rows.items():
        status = task["status"]
        if status == "REVIEW_ACCEPTED":
            continue
        if status not in CANDIDATE_STATUSES:
            deferred.append({"task_key": key, "reason": "REVIEW_TASK_STATE",
                             "recorded_status": status})
            continue
        blocked = blocking_dependencies(key)
        if blocked:
            deferred.append({"task_key": key, "reason": "UPSTREAM_REWORK_REQUIRED",
                             "blocking_task_keys": blocked,
                             "next": "Review failed, cancelled or rework prerequisites before scheduling dependents."})
            continue
        unmet = [dep for dep in task["depends_on"]
                 if rows[dep]["status"] != "REVIEW_ACCEPTED"]
        if unmet:
            deferred.append({"task_key": key, "reason": "DEPENDENCY_REVIEW_REQUIRED",
                             "unaccepted_dependencies": unmet})
            continue
        if mode == "read-only" and task["write_paths"]:
            deferred.append({
                "task_key": key, "reason": "HOST_WORKSPACE_READ_ONLY",
                "next": ("Do not reserve a writable specialist in this host "
                         "session. Obtain legitimate host permissions first "
                         "or select a read-only task."),
            })
            continue
        clashes = [other for other, scopes, resolved in selected_scopes
                   if orbit_tasks._collisions(task["write_paths"], scopes)
                   or orbit_tasks._collisions(task["resolved_write_paths"], resolved)]
        if clashes:
            deferred.append({"task_key": key, "reason": "OVERLAPPING_WRITE_SCOPE",
                             "conflicts_with": clashes})
            continue
        if len(ready) >= width:
            deferred.append({"task_key": key, "reason": "PARALLEL_CAP_REACHED"})
            continue
        ready.append({
            "task_key": key, "revision": task["revision"],
            "role": task["role"], "goal": task["goal"][:180],
            "write_paths": task["write_paths"],
            "next": "Request actual host/user approval; then call orbit_task_reserve with this task revision before native handoff.",
        })
        selected_scopes.append((key, task["write_paths"], task["resolved_write_paths"]))

    read_only_blocked = any(row["reason"] == "HOST_WORKSPACE_READ_ONLY"
                            for row in deferred)
    state = ("HOLD_NATIVE_TOOL_UNAVAILABLE" if not native else
             "READY_FOR_HOST_REVIEW" if ready else
             "HOLD_HOST_WORKSPACE_READ_ONLY" if read_only_blocked else
             "NO_READY_TASKS")
    fallback = (None if native or not ready else {
        "mode": "MANUAL_SERIAL_REVIEW_ONLY",
        "task_key": ready[0]["task_key"],
        "expected_revision": ready[0]["revision"],
        "native_agent_invoked": False,
        "host_permission_verified": False,
        "next": ("With separate real user/host approval, the host lead may handle "
                 "only this task serially within its allowed write scope; "
                 "review source and tests before accepting it. Do not reserve "
                 "or claim a native subagent session for a manual fallback."),
    })
    return {**base, "status": state, "ready_now": ready,
            "serial_fallback": fallback,
            "deferred": deferred, "candidate_count": len(ready),
            "native_invocation_required": True,
            "reason": ("Observed read-only host workspace cannot satisfy "
                       "writable tasks; real host permissions are still authoritative."
                       if state == "HOLD_HOST_WORKSPACE_READ_ONLY" else
                       "Real host capability and permission must still be verified."
                       if native else
                       "Use a supported native host tool or explicitly authorized serial fallback; never fabricate an invocation.")}
