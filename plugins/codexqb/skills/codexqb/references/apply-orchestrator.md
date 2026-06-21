# CodexQB Subagent Apply Orchestrator

The Apply Orchestrator defines a resumable Step 4 artifact protocol. It does not execute implementation by itself.

## Runtime Location

Target repositories store apply artifacts under:

```text
.codexqb/apply-runs/<apply-run-id>/
  Apply-Run.json
  Progress.json
  Events.jsonl
  Writer-Lock.json
  AR-<apply-run-id>-T<nnn>/Brief.md
  AR-<apply-run-id>-T<nnn>/Implementer-Report.json
  AR-<apply-run-id>-T<nnn>/Review-Package.patch
  AR-<apply-run-id>-T<nnn>/Task-Review.json
  AR-<apply-run-id>-T<nnn>/Fix-Report.json
  Final-Review.json
  Result.json
```

These runtime directories are created in the target repository, not in the CodexQB source tree except for tests and examples.
Non-`no_action` runs derive initial task briefs from Step 4 READY or READY_WITH_WARNINGS entries in `Planner-docs/Sub-Planing-Audit.md` when available. The audit-derived source sub-plan path and hash are recorded in both `Progress.json` and `Brief.md`.
When present in the active sub-plan, the controller also copies fresh-context contract signals into each task: acceptance criteria, allowed/forbidden paths, parent signals, dependencies, framework ownership, algorithmic invariants, structured validation commands, and security requirements.
Use `apply_run.py prepare` for new runs; `init` remains a compatibility alias. Use `apply_run.py transition` for state changes so `Events.jsonl` remains the append-only transition truth. Use `apply_run.py recover-lock` only for expired writer locks to move an abandoned `IMPLEMENTING` task to `BLOCKED` or `NEEDS_CONTEXT`. Use `apply_run.py reconcile` for external adapter fallback before dispatch, and `apply_run.py finalize` only after all tasks are VERIFIED and final review has passed. `Progress.json` is the current state snapshot.
`apply_spec_id` is deterministic for the selected mode, source snapshot, and Step 4 READY queue. `apply_run_id` is unique per invocation. To continue a run, pass `--resume` with the exact `--output-dir`; to intentionally regenerate one directory, pass `--replace`.

## Schema Contract

`Apply-Run.json` is the immutable run envelope: schema versions, requested mode, current mode, spec/run IDs, source snapshot, Step 4 readiness summary, workspace posture, safety defaults, agent profiles, and external adapter policy. `Progress.json` is mutable operational state: task list, task states, writer locks, verified task IDs, final-review requirement, and resume cursor. `Events.jsonl` is the append-only transition truth. Per-task directories use the exact task ID and contain the brief, implementer report, review package, task review, and fix report.

## Modes

- `direct`: parent-only execution for a bounded selected batch.
- `subagent_serial`: parent controller dispatches one fresh implementer at a time, then runs independent reviews.
- `external_superpowers`: optional adapter when Superpowers is already installed; CodexQB remains top-level controller. Availability must be checked before dispatch. If unavailable, run `apply_run.py reconcile` so the artifact mode becomes `subagent_serial` before implementation starts.
- `no_action`: record NO_ACTION_REQUIRED without starting implementation.

## State Machine

Allowed task states:

- `PREFLIGHT`
- `BRIEFED`
- `IMPLEMENTING`
- `IMPLEMENTED`
- `TASK_REVIEW`
- `SECURITY_REVIEW`
- `FIXING`
- `RE_REVIEW`
- `VERIFIED`
- `BLOCKED`
- `NEEDS_CONTEXT`

Each active slice must pass spec review before quality/security review. Failed review requires same-slice fix and re-review before completion.
Existing apply-run directories are not overwritten by default. Use explicit resume/replace behavior when continuing or intentionally regenerating artifacts.

Transitions must follow:

```text
PREFLIGHT -> BRIEFED
BRIEFED -> IMPLEMENTING | BLOCKED | NEEDS_CONTEXT
IMPLEMENTING -> IMPLEMENTED | BLOCKED | NEEDS_CONTEXT
IMPLEMENTED -> TASK_REVIEW
TASK_REVIEW -> SECURITY_REVIEW | FIXING | VERIFIED
FIXING -> RE_REVIEW | BLOCKED | NEEDS_CONTEXT
RE_REVIEW -> SECURITY_REVIEW | VERIFIED | FIXING
SECURITY_REVIEW -> VERIFIED | FIXING | BLOCKED | NEEDS_CONTEXT
```

`IMPLEMENTING` acquires `Writer-Lock.json` atomically. Leaving `IMPLEMENTING` releases it. Expired writer locks are validation blockers until `recover-lock` records a recovery transition to `BLOCKED` or `NEEDS_CONTEXT`. Validation rejects state snapshots that are not backed by a contiguous transition event.

## Role Templates and Model Profiles

Fresh-context role templates live under `references/apply/`:

- `controller.md`
- `implementer.md`
- `task-reviewer.md`
- `security-reviewer.md`
- `fixer.md`
- `final-reviewer.md`

`Apply-Run.json` includes role-level `agent_profiles` with stable model profiles instead of hardcoded model names: `fast`, `balanced`, `strong`, `security_strong`, and `inherit` when a user explicitly asks to inherit the active session. Reviewers default to read-only sandboxes; the implementer and fixer are the only default workspace-write roles.

## Review Result Shape

```json
{
  "task_id": "AR-apply-subagent_serial-<digest>-<invocation>-T001",
  "spec_compliance": "pass",
  "task_quality": "approved",
  "security_review": "pass",
  "reviewer_agent_id": "reviewer-1",
  "brief_sha256": "<sha256>",
  "blocking_findings": [],
  "fixes_required": [],
  "evidence": ["targeted validation passed"],
  "re_review_required": false
}
```

## Safety

- Commit policy defaults to `none`.
- Commit, push, PR, deploy, live probes, and destructive external mutation are opt-in only.
- Only one writer modifies files per slice unless the user explicitly requests separate branches or worktrees.
- Subagents are read-only by default except the selected fresh-slice implementer.
- `Progress.json` is the authoritative operational state for resume.
- `Events.jsonl` is the append-only transition truth.
- JSON snapshots are written with temp-file plus replace; writer lock uses create-exclusive semantics and expired locks must be recovered with an explicit controller event.
- `no_action` runs must not contain queued tasks.
- Task IDs must use the controller-generated `AR-<apply-run-id>-T<nnn>` format and resolve inside the apply-run directory.
- `external_superpowers` runs must record adapter availability and metadata before dispatch; unavailable adapters must be reconciled to `subagent_serial`.
- VERIFIED tasks require matching brief hashes, implementer identity, changed-file inventory, passing validation evidence, independent reviewer identity, review evidence, and final repo-level validation evidence.
