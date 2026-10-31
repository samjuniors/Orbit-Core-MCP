"""Fail-closed pre-invocation review for up to two host-native subagents.

This module is intentionally orchestration *planning*, not execution. It never
launches, resumes, cancels, releases or approves a host agent; native host
permissions and source/test verification remain independent.
"""
from __future__ import annotations

import json

import orbit_delegation
import orbit_tasks


def review(conn, root, project, args):
    slots = args["tasks"]
    if not isinstance(slots, list) or not 1 <= len(slots) <= orbit_tasks.MAX_CONCURRENT:
        raise ValueError("Select one or two already-reserved tasks")
    selected = {}
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("Task selection must be an object")
        key = orbit_tasks.key(slot)
        revision = slot.get("expected_revision")
        if type(revision) is not int or revision < 1:
            raise ValueError("Each task requires its current positive integer revision")
        if key in selected:
            raise ValueError("Duplicate selected task: " + key)
        selected[key] = revision

    host = args.get("host")
    mode = orbit_delegation.workspace_mode(args)
    reported_tools = args.get("available_host_tools", [])
    if host not in orbit_delegation.HOST_NATIVE_TOOLS:
        raise ValueError("Unknown coding host")
    if (not isinstance(reported_tools, list) or len(reported_tools) > 32 or
            any(not isinstance(t, str) or
                    not orbit_delegation.ALLOWED_TOOL_PATTERN.fullmatch(t)
                    for t in reported_tools) or len(set(reported_tools)) != len(reported_tools)):
        raise ValueError("Invalid or duplicated host tool names")

    base = {
        "project": project, "project_root": str(root),
        "host": host, "requested_task_keys": sorted(selected),
        "mode": "READ_ONLY_HOST_PREFLIGHT",
        "native_invoked": False, "host_permissions_verified": False,
        "host_liveness_verified": False, "source_tests_verified": False,
        "state_written": False, "host_tools_caller_reported": True,
        "host_workspace_mode_reported": mode,
        "host_workspace_writes_verified": False,
        "next": ("If all tasks pass, obtain real host permission for EACH one, "
                 "invoke only with its native host tool, then record the real "
                 "returned session through orbit_task_started. Recheck live "
                 "revisions before each invocation."),
    }
    # Query only the selected project and root, without exposing another
    # project's task keys or files.
    rows = {}
    for key in selected:
        row = conn.execute(
            "SELECT * FROM orbit_agent_tasks WHERE project=? AND project_root=? AND task_key=?",
            (project, str(root), key)).fetchone()
        if row is None:
            return {**base, "status": "HOLD_TASK_MISSING",
                    "task_key": key, "handoffs": [],
                    "reason": "Refresh this exact project's task ledger."}
        rows[key] = dict(row)

    issues = []
    for key in sorted(rows):
        row = rows[key]
        if row["revision"] != selected[key]:
            issues.append({"task_key": key, "status": "STALE_REVISION",
                           "actual_revision": row["revision"],
                           "next": "Refresh task ledger; never invoke using a stale reservation."})
        elif row["status"] == "RUNNING":
            issues.append({"task_key": key, "status": "HOLD_RUNNING_SESSION",
                           "next": "Inspect the real host session and exact session ID. After a host-confirmed terminal state, use orbit_task_report; never stop an agent from this preflight."})
        elif row["status"] == "RESERVED" and row["host_session"]:
            issues.append({"task_key": key, "status": "HOLD_SESSION_ALREADY_RECORDED",
                           "next": "Reconcile this recorded host session before issuing another invocation."})
        elif row["status"] == "RESERVED":
            pass
        elif row["status"] == "BLOCKED" and row["note"].startswith("HOST_PERMISSION_DENIED:"):
            issues.append({"task_key": key, "status": "HOLD_PERMISSION_DENIED",
                           "next": "Do not reuse denied consent. Obtain a fresh host/user approval before reserving again."})
        else:
            issues.append({"task_key": key, "status": "HOLD_NOT_RESERVED",
                           "recorded_status": row["status"],
                           "next": "Register/approve/review as required; use orbit_task_reserve with a fresh revision only after permission."})

    # This is a conservative preflight: if there is any unrelated same-root
    # active reservation, make the operator reconcile it first. Do not leak
    # names/identities of other projects in the response.
    active = [dict(row) for row in conn.execute(
        """SELECT project,task_key,write_paths,status FROM orbit_agent_tasks
           WHERE project_root=? AND status IN ('RESERVED','RUNNING')""",
        (str(root),))]
    unrelated = [row for row in active if (row["project"], row["task_key"]) not in
                 {(project, key) for key in selected}]
    if unrelated:
        issues.append({
            "status": "HOLD_OTHER_ACTIVE_RECORDS",
            "other_active_count": len(unrelated),
            "next": "Inspect real host sessions for existing reservations at this workspace before adding new invocations.",
        })
    if len(active) > orbit_tasks.MAX_CONCURRENT:
        issues.append({"status": "HOLD_CONCURRENCY_LIMIT",
                       "next": "Active reservations already exceed the supported concurrency cap."})

    scopes = {}
    for key in sorted(rows):
        try:
            paths = orbit_tasks._scopes(json.loads(rows[key]["write_paths"]))
        except (ValueError, TypeError, json.JSONDecodeError):
            issues.append({"task_key": key, "status": "HOLD_INVALID_WRITE_SCOPE",
                           "next": "Repair the saved task definition through an approved task workflow."})
            continue
        try:
            # A symlink may have changed after task reservation. Check both
            # original and physically resolved ownership before returning any
            # parallel host invocation packets.
            resolved = orbit_tasks._resolved_scopes(root, paths)
        except ValueError:
            issues.append({"task_key": key, "status": "HOLD_UNSAFE_WRITE_SCOPE",
                           "next": "Inspect changed workspace aliases and replan safely; do not invoke any native worker."})
            continue
        scopes[key] = (paths, resolved)
    if len(scopes) == len(rows):
        keys = sorted(rows)
        for i, key in enumerate(keys):
            for other in keys[i + 1:]:
                paths, resolved = scopes[key]
                other_paths, other_resolved = scopes[other]
                if (orbit_tasks._collisions(paths, other_paths)
                        or orbit_tasks._collisions(resolved, other_resolved)):
                    issues.append({"status": "HOLD_WRITE_SCOPE_CONFLICT",
                                   "task_keys": [key, other],
                                   "next": "Do not run overlapping tasks simultaneously. Replan or run serially after approval."})

    # A native tool can be present while the host sandbox disallows writes.
    # Surface the observed constraint before returning ANY batch handoff.
    # This is a caller-reported hint, not a permission attestation.
    if mode == "read-only":
        for key in sorted(scopes):
            paths, _resolved = scopes[key]
            if paths:
                issues.append({
                    "task_key": key, "status": "HOLD_HOST_WORKSPACE_READ_ONLY",
                    "next": ("Request legitimate writable host permissions before "
                             "invoking this specialist, or replan it as read-only. "
                             "Release an unused reservation only after host confirmation."),
                })

    handoffs = []
    for key in sorted(rows):
        if issues:
            # If the batch is already unsafe, don't present a partial runnable
            # packet that a host might misread as permission to invoke.
            break
        packet = orbit_delegation.handoff(
            conn, {"project": project, "task_key": key, "host": host,
                   "available_host_tools": reported_tools,
                   "host_workspace_mode": mode,
                   "include_research": False}, root)
        if packet["status"] != "HOST_INVOCATION_REQUIRED":
            recovery = ("If host denied or native tool is unavailable, use "
                        "orbit_task_release with the current task revision, "
                        "reason_code=HOST_PERMISSION_DENIED or HOST_TOOL_UNAVAILABLE "
                        "and confirm_write only after observing the actual host.")
            issues.append({"task_key": key, "status": packet["status"],
                           "next": packet["next_action"], "recovery": recovery})
            break
        handoffs.append({
            "task_key": key,
            "expected_revision": selected[key],
            "native_tool": packet["native_tool"],
            "handoff": packet["handoff"],
            "next": "Invoke in the host with its own permission controls; use orbit_task_started only after receiving a real session reference.",
        })

    if issues:
        return {**base, "status": "HOLD_HOST_PREFLIGHT",
                "handoffs": [], "issues": issues,
                "recovery": ("An unstarted RESERVED task with a confirmed native "
                             "denial or failed invocation can be released using "
                             "orbit_task_release with a fresh revision and "
                             "appropriate reason_code. RUNNING tasks require "
                             "host-confirmed terminal observation and orbit_task_report. "
                             "This operation performs neither."),
                "no_partial_launch": True}

    return {
        **base, "status": "HOST_INVOCATIONS_REQUIRED",
        "handoffs": handoffs, "concurrency_limit": orbit_tasks.MAX_CONCURRENT,
        "all_revisions_current_at_read": True,
        "no_partial_launch": True,
        "warning": ("The selected reservation records and reported host tools are "
                    "not cryptographic proof of user approval or host capability. "
                    "Do not invoke without checking real host permissions, "
                    "current task state and workspace scope."),
    }
