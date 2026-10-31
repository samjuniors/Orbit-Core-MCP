# Orbit Core — current development track (2026-10-31)

**Engineering state:** `main` is at v0.27.1 **source**, but the latest
verified public prerelease may still be v0.27.0; consult the canonical
[release page](https://github.com/samjuniors/Orbit-Core/releases) for
actual tags/assets. The v0.27.1 rename-compatibility PR #67 has been
merged into main as engineering source. Never infer publication from
a merged PR.

**v0.28.0 proposed development:** `dev/v0.28.0-delivery-blueprint`
extends the existing Orbit native-agent Swarm by producing an adaptive
read-only delivery plan across software roles and product types, inspired
by the [ECC research reference](https://github.com/affaan-m/ECC).
This is **source development only**, requires real user permissions
and host-native execution, and is not a new model/automatic coding service.
The current plan targets safe vertical slices, implementation, QA,
security review and release approval, with 47 preview tools in the
development branch. No v0.28.0 tag or publication authorized.

Older historical progress snapshots below are retained and superseded
by this current summary where they contradict a verified release/branch.

---

# Orbit Core — current release and roadmap status

**Current public prerelease:** [v0.27.0](https://github.com/samjuniors/Orbit-Core/releases/tag/v0.27.0)
(2026-10-31); `main` is source authority. The `v0.27.1` patch is a
**separate unpublished candidate**, scoped to repository rename URLs and
update/download continuity. `NEXT_VERSION=0.28.0` remains future
development planning and does not authorize a release.

**Open release-quality issues:** native permission-dialog denial,
live-worker cancellation/restart, independent publisher provenance,
tested user migration/rollback and second-host acceptance. See the
[Swarm acceptance evidence](SWARM-ENGINEERING-ACCEPTANCE.md).

The older v0.27.0 development-lane notes below are **historical**
and were superseded by the published release. Do not restart
those completed milestones.

---

# Orbit Core roadmap — M1/M2 owner-accepted; M3 engineering in progress (2026-10-29)

The focus is **a trustworthy local orchestrator inside existing coding IDEs**, not duplicating an entire cloud app-building platform. This is a prioritized engineering backlog, not an automated promise of completed features.

## v0.27.0 — isolated next-feature development lane (PROVISIONAL)

**Branch:** `dev/v0.27.0`, forked from `main` at `7344a12c2056b586974e654733e1b3a78685827d` on 2026-10-30. This is a **development integration branch**, not a release candidate and not a published version. `NEXT_VERSION=0.27.0` on **this branch only** is a planning label because the planned work adds capabilities; `VERSION` remains `0.26.0` until an explicitly reviewed release cutline. The public release remains `v0.25.1`.

**Project Pulse (MERGED to dev, release acceptance pending):** [PR #49](https://github.com/samjuniors/Orbit-Core/pull/49) now provides optional `orbit_project_resume(compact=true,pulse=true)` and bounded local task counts with unverified next-action hints. No model/agent execution, external data sync or host liveness attestation. Real host UX and model-context benchmarks still required. Integrated along with Swarm in `dev/v0.27.0`; not in `main` or a published release.

**Agent Swarm Phase 3 — native-host batch handoff review SOURCE IMPLEMENTED, real hosts pending:** `orbit_swarm_host_preflight` checks one or two existing reserved task revisions as an all-or-nothing group before native delegation. It reuses `orbit_task_handoff`, checks exact host and permission preconditions, and returns zero invocation packets if any task is stale, scope-conflicting, already running, denied, or blocked by unrelated active work. Recovery uses existing revision-guarded `orbit_task_release` for unstarted denied/failed tasks and `orbit_task_report` only after a genuinely observed terminal host session. No actual host agent is invoked or terminated by the MCP. See [swarm engineering acceptance](SWARM-ENGINEERING-ACCEPTANCE.md). Real Antigravity/Codex/Claude permission/denial tests, real native-session recovery and independently executed integration QA remain open; the source-level freshness and readiness guards are implemented in v0.27 development.

**Agent Swarm Phase 2 — draft DAG preflight MERGED to dev, live acceptance OPEN:** `orbit_swarm_draft_preview` accepts a user/host-proposed task graph and validates all identities, roles, goal text, dependencies, path scopes, cycle/size limits and existing ledger conflicts before exposing deterministic review waves. Max 12 task drafts and 2 safe tasks per wave. It does **not** interpret natural language autonomously, register tasks, approve work, invoke native subagents or attest tests. See [Swarm engineering acceptance](SWARM-ENGINEERING-ACCEPTANCE.md). Host-reviewed registrations and read-only QA readiness are in development source; actual native delegation, cancellation, test execution and host acceptance remain open. The reviewed phase sources #50–53 are now integrated in dependency order to this development lane; do not merge the entire version lane to main before the v0.26 release decision.

**Agent Swarm mission — Phase 1 SOURCE MERGED to dev, host acceptance OPEN:** [Engineering checklist](SWARM-ENGINEERING-ACCEPTANCE.md). The new read-only `orbit_swarm_preview` tool (43rd candidate MCP tool) groups existing registered tasks by dependency readiness and non-overlapping write scopes. It checks missing dependencies, cycles, protected paths, existing reservations and a fixed maximum of two candidates. A candidate is **not** a launched agent or an approved task. `orbit_task_reserve` and host-native handoff still require actual permission and fresh revisions. The implementation is an original Orbit coordinator; the [Claude Swarm external reference](https://github.com/affaan-m/claude-swarm) is research only, without imported source or Claude SDK. **Future work:** real-host parallel execution, denial/cancellation/rollback, independent integration QA, context benchmarks and observable swarm progress. Draft validation and host preflight are already implemented in the integrated development source. No main merge or v0.27 release is authorized. The integrated development commit `7130eb381ccdbc3d1792b55b2889e139385c9dbf` includes [PR #57](https://github.com/samjuniors/Orbit-Core/pull/57) Windows alias/independent OS-process SQLite checks and [PR #58](https://github.com/samjuniors/Orbit-Core/pull/58) symlink containment and post-reservation handoff safety. Exact PR-head matrices passed [#57 CI](https://github.com/samjuniors/Orbit-Core/actions/runs/41079246959) and [#58 CI](https://github.com/samjuniors/Orbit-Core/actions/runs/41082050055), each 5/5 Ubuntu/Windows; the matching integrated development [post-merge CI](https://github.com/samjuniors/Orbit-Core/actions/runs/41082365287) passed 5/5 on Ubuntu Python 3.10–3.13 and Windows Python 3.12. Actual host agent sessions, host approvals, cancellation, independently executed integration QA and cross-PC recovery remain NOT VERIFIED.

**2026-10-30 source-development cutline (NOT A RELEASE):** [PR #60](https://github.com/samjuniors/Orbit-Core/pull/60) added transitive failed/rework dependency decisions and manual serial host-review fallback. [PR #61](https://github.com/samjuniors/Orbit-Core/pull/61) added read-only, source-fingerprint-bound task/QA integration readiness, with the installer, packaged MCP and host handoff guidance updated together. Both were merged into `dev/v0.27.0`; latest source merge `0d231b3508cf7c69bef85412a8efb2f02c714382`. [Exact #61 PR-head CI 5/5 PASS](https://github.com/samjuniors/Orbit-Core/actions/runs/41085894528); final [post-merge dev CI](https://github.com/samjuniors/Orbit-Core/actions/runs/41086243865) is a separate gate. The development source exposes **46 MCP tools**. This establishes implementation of the planned code-level readiness guards, **not** authenticated host sessions, genuine independent QA execution, installed-user migration, performance gains, security certification or permission to merge to `main`. Remaining live acceptance and release hold are tracked in the existing [Swarm engineering checklist](SWARM-ENGINEERING-ACCEPTANCE.md) and [Notion version tracker](https://app.notion.com/p/4074f681d48881a7a407c3bdc2054409). No new orchestrator backend, LLM runner or automatic worker was introduced.

**Working rules:** New independent v0.27 features use `feat/v027-<scope>` branches based on `dev/v0.27.0`, undergo review and CI, and merge into **this version development branch** after explicit approval. Do not merge the entire lane to `main` while v0.26.0 is frozen or unapproved. Once the feature scope is agreed and prior-version release rules are reconciled, create `release/v0.27.0-candidate` from an exact reviewed commit and perform release-specific tests. No feature or metadata change in this lane authorizes v0.26.0 publication, bypasses its approval gates, or retags an existing release.


## Orbit-native research and intelligence roadmap — approved direction (2026-10-27)

**Product principle:** build an original, lightweight Orbit experience, not an ECC fork or clone. Research links, annotations and retrieval records belong in **authorized local project-scoped SQLite outside the Git repository**. Owner documentation remains authoritative. External references are untrusted inputs, never auto-executed skills or agent instructions. This roadmap preserves Issue #13 product-experience commitments and Issue #9 release/security gates.

### M1 — P0: Orbit Evidence Lens (core scope OWNER-REPORTED PASS; source and CI verified)
- Save an individual reviewed research **source pointer** (URL, topic tags, short annotation, original status) with an explicit write preview and revision-guarded update. Use project folder + stable project key as namespace. Never seed global memory by default or push research links to Git.
- Recover only sources relevant to an objective within a predictable character budget; return provenance, limits, unverified-source warning and explicit live verification guidance. No network request or third-party code execution from source content.
- Support project- and folder-level isolation, duplicate identity updates, malicious URLs and stale-revision tests; retain existing local SQLite and legacy memories. A trusted local IDE user manually imports the previously prepared 9-link research packet after connecting, not a Git checkout or ChatGPT cloud session.
- **Gate / acceptance update (2026-10-29):** PR #16 merged and the source/bundle regression matrix passed. The owner reported Antigravity research-pointer save/readback and checkpoint recovery as PASS. Treat M1's core functionality as **OWNER-ACCEPTED**, not independently attested host consent or proof of automatically synchronized Notion references. Evidence: [v0.25.1 release host reports](https://github.com/samjuniors/Orbit-Core/releases/tag/v0.25.1) and [Evidence Lens tests](../tests/test_evidence_lens.py).

### M2 — P0: Reliable real-host delegation and handoff (core scope OWNER-REPORTED PASS; extended checks open)
- Add a read-only `orbit_task_handoff` adapter contract: checked task/reservation/dependencies, exact supported native host tool names (caller-reported), limited file ownership, optional minimal Evidence Lens links, safe HOLD/serial fallback. The host **must** actually invoke its native tool; a packet is not an agent run. Real host session references and changed-file/test inspection remain prerequisites; the MCP never spawns an agent.
- **Gate / acceptance update (2026-10-29):** [PR #17](https://github.com/samjuniors/Orbit-Core/pull/17) merged with passing automated host-handoff tests. The owner's actual-host reports record **Antigravity PASS** (native delegation, Todo checks, restart/resume) and **Codex PASS** (native delegation, 14 regression checks, `todo-filter-codex` REVIEW_ACCEPTED revision 5, checkpoint/files restored after restart). Those reports are documented in the [v0.25.1 release](https://github.com/samjuniors/Orbit-Core/releases/tag/v0.25.1); the MCP cannot independently attest host session/consent. Mark **M2 core two-host acceptance OWNER-ACCEPTED**, without claiming every new-project/existing-project or denial/fallback scenario was independently verified. Any untested scenario remains a targeted M3 follow-up, not an assumed PASS.

### M3 — P1: Independent QA, permissions and scoped recovery (IMPLEMENTATION PARTLY MERGED; LIVE ACCEPTANCE DEFERRED)
- **Objective:** Make verification evidence independently checkable where host capabilities permit, ensure permission/denial behavior is accurately represented, and recover from interrupted or cross-host work without fabricating PASS.
- **M3.1 — QA freshness:** Attach QA/test records to source revision, acceptance case, execution environment and preview generation; invalidate stale PASS after code changes. Include regression tests for stale evidence.
- **M3.2 — Host permissions:** Verify real host consent/denial paths; do not treat `confirm_write`, reported tool names or supplied session IDs as authenticated consent. Retain HOLD/serial fallback when native delegation cannot be attested.
- **M3.3 — Scoped recovery:** Exercise interrupted, cancelled, failed and rework task paths with revision checks, safe file ownership, and rollback/backup review on Windows and Linux. Do not alter older accepted task history.
- **M3.4 — Portability limitations:** [PR #22](https://github.com/samjuniors/Orbit-Core/pull/22) merged portable task/research export/import and checkpoint-only detection; **live cross-PC transfer remains NOT VERIFIED**. Test on two actual hosts/PCs only with approved, disposable project data; imported approvals and sessions remain untrusted historical records. Build/intake and legacy memory are not included.
- **Acceptance gate:** real revised-code QA (including stale-PASS rejection), host denied-permission evidence, interrupted/rework recovery, independently inspected Git diffs/tests, and an explicitly recorded cross-PC test result (PASS/FAIL/DEFERRED). Separate optional platform/GUI, provenance/signing and Issue #9 security gates are not silently closed.
- **Engineering progress:** [PR #25](https://github.com/samjuniors/Orbit-Core/pull/25) source/preview-bound QA, [PR #26](https://github.com/samjuniors/Orbit-Core/pull/26) host-first browser selection, [PR #27](https://github.com/samjuniors/Orbit-Core/pull/27) denial bookkeeping, [PR #29](https://github.com/samjuniors/Orbit-Core/pull/29) native-agent session reconciliation and [PR #32](https://github.com/samjuniors/Orbit-Core/pull/32) persistent retry budgets have merged to development `main`. Browser QA origin isolation was integrated and merged through [PR #33](https://github.com/samjuniors/Orbit-Core/pull/33), superseding the conflicting standalone #30. See [M3 engineering acceptance checklist](M3-ENGINEERING-ACCEPTANCE.md) for case/evidence requirements. Do not confuse merging with live IDE acceptance, verified permissions, two-PC continuity or production security; these remain deferred or open.

### M4 — P1: Adaptive capability surfaces and reusable context
- Reuse native host features, owned code, on-demand skills or a small MCP surface according to task—not a universal dependency pile. Extend the M1 compact pack to accepted decisions and checkpoint context only after verifying project-root binding and provenance.
- **Gate:** compare tool-turns, context bytes, recovery accuracy and install friction on Orbit's real product benchmarks.
- **M4.2 v0.26.0 source follow-up:** Existing `orbit_capability_select` now recommends focused compact resume, multi-stage full review, or high-risk permission/review gates based on the objective and caller-reported host tool names. No subagent executes from a selector, no model is switched, and actual host permissions remain external. Synthetic JSON-byte savings tests are useful but do not establish real model-token/credit savings; benchmark signed-in IDE use later.

### M5 — P2: Evidence-backed learning (opt-in)
- Suggest reusable project-scoped practices only after repeated reviewer-accepted outcomes and human review; never silently create/modify global skills, run continuous watchers, store full chats, or promote untrusted research prose to trusted instructions.
- **Owner-approved development integration (v0.26.0 source still unpublished):** two optional MCP tools expose repeated-task-pattern suggestions and explicitly reviewed SQLite practice decisions, with revisioned approve/reject/archive/supersede history. Evidence is caller-reported and must be independently inspected in the host. No background learning, automatic skill generation, cross-project knowledge transfer, model execution or token-savings claim.
- **Gate:** [M5 engineering acceptance](M5-ENGINEERING-ACCEPTANCE.md) — deterministic isolation/preview/revision/freshness tests and exact-head Linux/Windows CI have passed; real-host UX, independent permission/privacy acceptance, upgrade/rollback and separate owner release approval remain pending. M5 source merge is not permission to publish v0.26.0.

**Research inspiration:** prior user-shared sources ECC, Emergent, Lovable, Scram, Neura, etc. stay **outside Git as source pointers**. Compare behaviors and adapt ideas independently with license/security review; no copying source code or installing external components. The M1 implementation is specific to Orbit's existing SQLite and host-neutral execution model.

## v0.26.0 — Plugin-first distribution and Antigravity native-agent contract (owner-directed, 2026-10-30)

**Status: APPROVED PRODUCT DIRECTION; PACKAGING/INSTALLATION/REAL-HOST ACCEPTANCE NOT IMPLEMENTED/VERIFIED.** This mission is part of the *unpublished* 0.26.0 development target, not another project or authorization to release. Research and rationale are recorded in the existing [Orbit Core Notion research hub](https://app.notion.com/p/4074f681d488816e9fe7f4504982c948), especially the 2026-10-30 Antigravity custom-subagents supplement. Host authority: [Antigravity custom subagents](https://antigravity.google/docs/subagents?tab=cli) and [Antigravity plugins](https://antigravity.google/docs/plugins?tab=cli).

**Goal:** Install Orbit once as the host-supported combination of a selectable lead agent, reusable skill, host-native specialist profiles and locally launched stdio MCP — *no external Orbit cloud server*. Codex and Claude use their respective plugin/agent/skill formats, not Antigravity's YAML verbatim. In agent/skill-only fallback, never invent persistent SQLite checkpoints, practices or 42 MCP tool calls.

**Antigravity binding contract:**
- Existing `source/agents/orbit.md`: exactly one selectable primary `mainAgent: true`, `subagent: false`, `model: inherit`. Twelve specialist `orbit-*.md`: `mainAgent: false`, `subagent: true`. Both flags default to true in this host, so neither may be implicit. Current source profile inspection found 13 expected files with explicit role flags; this is source inspection, not live plugin-origin agent acceptance.
- Delegate *only* through actually available host `invoke_subagent`, using `inherit`, `branch` (isolated Git worktree) or `share` according to scoped file ownership and user permissions. Pass a bounded handoff: child starts with a new conversation context, not the parent's entire context. Orbit MCP itself never spawns agents.
- Treat host child session states `Running`, `Idle` (can be re-awoken) and `Killed` (terminal) distinctly. Obtain host session IDs and actual end state before changing task ledger, reviewing, retrying, or claiming cancellation. Do not exceed a practical concurrency/nesting budget; the host states a maximum nesting depth of 10 but that is not Orbit's recommended operating depth.
- Subagents inherit parent file/terminal/sandbox restrictions; tool requests needing extra consent bubble to the actual host UI. Report denied/unknown consent as HOLD, never bypass with another tool/provider. Use `model: inherit` by default; allow `flash`/`pro` recommendations only when the user's installed host makes them available and the work merits them.
- Host built-in `research` and `self` are special native roles. Built-in `browser` is invoked **only by `/browser`**, not a generic `invoke_subagent` call. Host `/boost` and `/teamwork` are plan-gated native capabilities, not mandatory Orbit dependencies or permissions to execute automatically. Host `/agents`, `/tasks`, `Alt+J` and `Ctrl+K` remain host UI controls, not Orbit MCP tools.
- Exact `tools` allowlists must be validated against the actual installed Antigravity build. Official docs warn an unknown tool string can **hang a subagent**. Review all specialist profiles including `orbit-writer.md` (`write_to_file`) before dispatch; do not assume that spelling is supported everywhere.

**Distribution and migration contract:**
- Antigravity plugin: `plugin.json`, `mcp_config.json` (NOT `mcp.json` in this manifest dialect), `skills/orbit/SKILL.md` and on-demand references, `agents/orbit.md` plus twelve specialist profiles, versioned local runtime. Prefer host-supported `${PLUGIN_ROOT}` for the code and `${PLUGIN_DATA}` for newly provisioned state, with backup-first preservation/mapping of an existing `ORBIT_LOCAL_DB`. No automatic hooks, downloads or cloud setup.
- A disposable plugin prototype validated on installed `agy 1.4.11` with `agy plugin validate --strict`: **1 skill, 13 agents, 1 MCP server; PASS** after removing UTF-8 BOM, using `mcp_config.json`, and shortening the initial skill below the host's observed 24 KB direct-load limit with full content moved into `references/`. **Prototype NOT installed**; no claim of actual plugin-origin connection or migration acceptance.
- Preserve the existing standalone v0.25.1 Orbit registrations, agent/skill customizations and user SQLite data during trial; prevent duplicate MCP tool identities if legacy and plugin distributions coexist. Provide detect/preview, upgrade/repair, disable, uninstall and rollback without deleting owner files. Use one canonical Orbit runtime and host-specific thin packages for Codex, Claude Code and Claude Desktop.
- Package version/source parity, platform interpreter resolution, offline startup, skills load limits, path-variable expansion, permission failures, unchanged user files, stale/revision evidence, stop/resume and no-MCP graceful fallback must have regression and **live-host** acceptance before publishing.

**v0.26.0 acceptance gate:** [ ] strict plugin manifest/skills/agent/allowlist tests; [ ] disposable real App installation and Orbit lead selectable in chat; [ ] authorized `invoke_subagent` with observed session ID, `branch` worktree, correct permission bubbling/deny/cancel/idle/restart; [ ] browser `/browser` routing and no fake BROWSER_QA PASS; [ ] 42 actual local MCP tools + SQLite readback without duplicate old/new registration; [ ] clean upgrade/rollback from v0.25.1 with existing database and customizations; [ ] distinct Codex and Claude plugin QA; [ ] independent security/provenance review and owner publication decision. **Do not equate validator success with real-host or release PASS.**

## P0: release and host acceptance

- Validate Windows Antigravity/Codex/Claude Code setup from **downloaded, signed-in, authorized machines**, including preview/backup of customized files, restart, actual tool discovery and user decision flow.
- Run real Windows Edge/Chrome browser QA and native Android/iOS flows where applicable; optional Playwright tests may be skipped in CI and **must not** be described as live acceptance.
- **v0.25.1 was published as a prerelease on 2026-10-29** with four ZIP/MCPB/checksum assets after passing CI. This is not production security, GUI or independent native-host acceptance. Preserve v0.24.1 assets and verify real device/installer/backup/rollback separately. See [published release](https://github.com/samjuniors/Orbit-Core/releases/tag/v0.25.1) and [release acceptance](RELEASE-ACCEPTANCE-v0.25.1.md).

## P1: reliability and evidence authenticity

- Bind QA results to source revision, acceptance case and preview generation; invalidate stale PASS after edits.
- Persist and supervise preview process trees across MCP restarts; Windows stop must not kill unrelated processes.
- Retry, cancel and reconcile task reservations after failure, with per-attempt history and bounded time/quota budgets.
- Add transactional SQLite compare-and-swap tests for concurrent intake edits; atomically checkpoint files.
- Strengthen stable project identity to avoid cross-folder slug collision in memory keys.
- Configure branch protection, required CI statuses, independent code review and real production-threat model.

## P2: productivity and product experience

- Thin IDE plan/task/progress panel with explicit plan approval, blocked-reason status and native model availability.
- Keep model routing host-supported and cost-aware with real measurements; do not infer credits or force cheaper models for difficult tasks.
- Build a small **tested/versioned** reusable component catalog only after repeated practical demand and license review. Astryx, shadcn, Jetpack Compose, SwiftUI, Context7 and agent-browser are candidates for *different* tasks, not universal defaults.
- Selective retrieval from compact accepted briefs, checkpoints and targeted files; avoid dumping all docs every turn.
- Improve human milestone acceptance and accessibility/performance tests for chosen project types.

## Acceptance and rollback policy

Merges to `main` may contain reviewed release candidates, but must not imply production certification. Release tags are immutable; repair with new SemVer patch, preserve user data and historical runtime folders, and require explicit authorization for installs/deployments. If an installer reports a manual-review conflict, protect the file and provide an actionable diff/backup path, never silently overwrite unknown content.


## Product experience first (current development priority)

Deliver a reliable one-glance resume/decision view and correctly frozen stage progression before investing in deployment infrastructure, service supervision, distributed locks or managed hosting. Evaluate a host-native editable plan/task panel only after the lightweight MCP UX contract has been tested in Antigravity and another coding host. No premature live-production claim based solely on CI.

## Cross-PC continuity correction (2026-10-29)

A moved checkpoint does not imply the other PC's SQLite database moved. Resume
now reports the server-selected database path and exact task/research counts.
A checkpoint with no local records returns `CHECKPOINT_ONLY_LOCAL_CONTEXT_MISSING`:
continue inspecting existing code without onboarding or inventing missing history.
This is a portability limitation, not evidence of same-PC persistence failure.

Use `orbit_project_transfer` with `action: export` on the original PC. It returns a
bounded JSON bundle (100 tasks + 100 research pointers, 90 KB maximum), without
writing files. Review notes/URLs for sensitive content and manually transfer it
outside Git. No other projects, host settings, credentials or legacy global
memories are collected; notes may still contain owner-entered sensitive text.

On the destination, use the same project key, the new absolute project root,
`action: import`, and the bundle string. Review the preview, then explicitly
confirm with its `expected_revision` digest and `confirm_write: true`. Imports
are transactional, refuse existing keys, remap scope, preserve historical task
revisions, and clear approvals/reservations. Active/reported-but-unreviewed work
becomes BLOCKED. Sessions and accepted results remain unverified historical
claims, never proof of execution on this host. Existing checkpoint files are not
overwritten; transfer the project folder including `.orbit/STATE.md` separately.
Build/intake state and legacy memories are not transferred in this bounded version.
Without the original PC/export, only the available checkpoint can be recovered.

The published v0.25.1 and current development tool inventory are **40** tools.
The older 39-tool acceptance prompt predates the portable-transfer feature.
The owner reported Antigravity and Codex same-PC native delegation/restart PASS;
**live cross-PC transfer and native delegation on the destination are NOT VERIFIED**.
Neither published prerelease nor these host reports constitute production certification.


## v0.26.0 source candidate (2026-10-29)

The M3 engineering improvements and M4.1 optional compact project resume are merged into development source. `release/v0.26.0-candidate` is preparing a compatible **minor** candidate because the accumulated work adds user-facing capabilities, not just fixes. Its `VERSION=0.26.0` and `NEXT_VERSION=0.26.1` are **source metadata** until a separately authorized release. CI builds unpublished test ZIP/MCPB artifacts and checks bundle parity, SQLite upgrade behavior and Linux/Windows regressions. Do not mark the live native-host, installer, browser or Issue #9 security gates PASS based on this work; publication is separately approval-gated.
