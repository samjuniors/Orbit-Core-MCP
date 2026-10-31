"""Preview a user/host-proposed swarm task DAG before any ledger writes.

Host reasoning may suggest the task draft, but Orbit owns deterministic
validation. No model calls, subprocesses, reservations or agent execution.
"""
from __future__ import annotations

import orbit_tasks
import orbit_swarm

MAX_DRAFT_TASKS = 12


def preview(conn, root, project, args):
    """Validate draft tasks and propose bounded, serializable review waves."""
    drafts = args["tasks"]
    if not isinstance(drafts, list) or not 1 <= len(drafts) <= MAX_DRAFT_TASKS:
        raise ValueError("Expected 1..12 draft task objects")
    proposed = {}
    resolved_scopes = {}
    for item in drafts:
        if not isinstance(item, dict):
            raise ValueError("Every draft task must be an object")
        # Reuse the ledger's role, Unicode/path guard, text and key rules.
        task = {**item, "project": project}
        name = orbit_tasks.key(task)
        if name in proposed:
            raise ValueError("Duplicate task key in draft: " + name)
        _, step, role, goal, reason, paths, deps = orbit_tasks.spec(task)
        # Draft waves must honor real filesystem aliases just like reserve().
        # Never expose resolved symlink targets or assume a preview grants writes.
        resolved_scopes[name] = orbit_tasks._resolved_scopes(root, paths)
        proposed[name] = {
            "task_key": name, "step": step, "role": role,
            "goal": goal, "reason": reason, "write_paths": paths,
            "depends_on": deps,
        }

    base = {
        "mode": "READ_ONLY_DRAFT_PREVIEW",
        "project": project, "project_root": str(root),
        "draft_task_count": len(proposed),
        "task_registration_performed": False,
        "approval_verified": False,
        "agent_spawned": False,
        "host_execution_verified": False,
        "state_written": False,
        "host_model_used": False,
        "next": ("Review the draft with the owner. Then register individual tasks "
                 "using orbit_task_plan with confirm_write only after explicit "
                 "approval. Separately reserve and invoke through the real host."),
    }
    existing_count = conn.execute(
        "SELECT COUNT(*) FROM orbit_agent_tasks WHERE project=? AND project_root=?",
        (project, str(root))).fetchone()[0]
    if existing_count > orbit_swarm.MAX_GRAPH_TASKS:
        return {**base, "status": "HOLD_GRAPH_TOO_LARGE",
                "review_waves": [],
                "reason": "Review and scope existing project tasks before proposing another swarm."}
    existing = {row["task_key"]: row["status"] for row in conn.execute(
        "SELECT task_key,status FROM orbit_agent_tasks "
        "WHERE project=? AND project_root=?", (project, str(root)))}
    collisions = sorted(set(proposed).intersection(existing))
    if collisions:
        return {**base, "status": "HOLD_EXISTING_TASK_KEYS",
                "conflicting_keys": collisions,
                "review_waves": [], "reason": "Never overwrite registered tasks."}

    # The registered-task preview hard-caps the entire project DAG at 40.
    # Account for proposed (not-yet-registered) task nodes as well, otherwise
    # this preview could approve a plan that the next preview cannot schedule.
    if existing_count + len(proposed) > orbit_swarm.MAX_GRAPH_TASKS:
        return {**base, "status": "HOLD_GRAPH_TOO_LARGE",
                "review_waves": [],
                "reason": ("Existing and proposed tasks exceed the 40-task "
                           "swarm graph limit. Complete or split the scope "
                           "before registering additional tasks.")}

    missing = sorted({dep for task in proposed.values() for dep in task["depends_on"]
                      if dep not in proposed and dep not in existing})
    if missing:
        return {**base, "status": "HOLD_MISSING_DEPENDENCIES",
                "missing_dependency_keys": missing,
                "review_waves": [], "reason": "Dependency keys must exist in the draft or already registered ledger."}

    unaccepted = sorted({dep for task in proposed.values() for dep in task["depends_on"]
                         if dep in existing and existing[dep] != "REVIEW_ACCEPTED"})
    if unaccepted:
        return {**base, "status": "HOLD_UNACCEPTED_DEPENDENCIES",
                "unaccepted_dependency_keys": unaccepted,
                "review_waves": [],
                "reason": "Existing dependencies require explicit review acceptance before scheduling."}

    cycle = orbit_swarm._graph_cycle(proposed)
    if cycle:
        return {**base, "status": "HOLD_DEPENDENCY_CYCLE",
                "cycle": cycle, "review_waves": [],
                "reason": "Fix the cyclic draft before task registration."}

    # A host restart cannot prove whether a RESERVED or RUNNING agent is alive.
    # Existing reservations at this root, including other project slugs, HOLD.
    active = conn.execute(
        "SELECT COUNT(*) FROM orbit_agent_tasks WHERE project_root=? "
        "AND status IN ('RESERVED','RUNNING')", (str(root),)).fetchone()[0]
    if active:
        return {**base, "status": "HOLD_HOST_RECONCILIATION",
                "active_records_same_root": active, "review_waves": [],
                "reason": "Inspect real host sessions before scheduling additional tasks."}

    # A preview wave is an upper bound for future registration/execution, not
    # an instruction to start concurrent agents. Dependencies need acceptance
    # between waves. Overlapping writes are serialized deterministically.
    remaining = set(proposed)
    completed = set()
    waves = []
    while remaining:
        eligible = [key for key in sorted(remaining)
                    if all(dep in completed or dep in existing
                           for dep in proposed[key]["depends_on"])]
        if not eligible:
            # Defensive fallback: cycle detection already checked.
            return {**base, "status": "HOLD_UNSCHEDULABLE_DAG",
                    "review_waves": [], "reason": "Cannot safely order dependencies."}
        wave = []
        scopes = []
        for key in eligible:
            task = proposed[key]
            if any(orbit_tasks._collisions(task["write_paths"], paths)
                   or orbit_tasks._collisions(resolved_scopes[key], resolved)
                   for paths, resolved in scopes):
                continue
            if len(wave) == orbit_tasks.MAX_CONCURRENT:
                break
            wave.append(key)
            scopes.append((task["write_paths"], resolved_scopes[key]))
        if not wave:
            return {**base, "status": "HOLD_UNSCHEDULABLE_DAG", "review_waves": []}
        waves.append({
            "wave": len(waves) + 1,
            "task_keys": wave,
            "requires_prior_wave_review": len(waves) > 0,
        })
        completed.update(wave)
        remaining.difference_update(wave)

    return {
        **base, "status": "DRAFT_VALIDATED",
        "proposed_tasks": [proposed[key] for key in sorted(proposed)],
        "review_waves": waves,
        "parallel_limit": orbit_tasks.MAX_CONCURRENT,
        "wave_count": len(waves),
        "quality_gate": "Host must review and accept dependency evidence between waves.",
        "warning": ("Task text and scope are caller-proposed and untrusted. "
                    "This preview is NOT approval, verified host capability, "
                    "a task reservation, a launched agent or test evidence."),
    }
