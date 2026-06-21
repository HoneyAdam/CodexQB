# CodexQB Subagent Apply Orchestrator

The Apply Orchestrator defines a resumable Step 4 artifact protocol. It does not execute implementation by itself.

## Runtime Location

Target repositories store apply artifacts under:

```text
.codexqb/apply-runs/<apply-run-id>/
  Apply-Run.json
  Progress.json
  task-<n>/Brief.md
  task-<n>/Implementer-Report.json
  task-<n>/Review-Package.patch
  task-<n>/Task-Review.json
  task-<n>/Fix-Report.json
  Final-Review.json
  Result.json
```

These runtime directories are created in the target repository, not in the CodexQB source tree except for tests and examples.
Non-`no_action` runs derive initial task briefs from Step 4 READY or READY_WITH_WARNINGS entries in `Planner-docs/Sub-Planing-Audit.md` when available. The audit-derived source sub-plan path and hash are recorded in both `Progress.json` and `Brief.md`.

## Modes

- `direct`: parent-only execution for a bounded selected batch.
- `subagent_serial`: parent controller dispatches one fresh implementer at a time, then runs independent reviews.
- `external_superpowers`: optional adapter when Superpowers is already installed; CodexQB remains top-level controller.
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

## Review Result Shape

```json
{
  "task_id": "task-1",
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
- `no_action` runs must not contain queued tasks.
- Task IDs must use the controller-generated `task-<n>` format and resolve inside the apply-run directory.
- VERIFIED tasks require matching brief hashes, implementer identity, changed-file inventory, passing validation evidence, independent reviewer identity, review evidence, and final repo-level validation evidence.
