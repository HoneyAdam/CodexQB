# CodexQB Planning Ledger

CodexQB uses `Planner-docs/Planing-Ledger.md` as an optional durable memory artifact for planning and implementation history.

The spelling `Planing` is intentionally preserved to match the existing CodexQB artifact naming convention.

## Purpose

The ledger answers:

- What planning runs were completed?
- Which plans were implemented?
- What did each implementation run change?
- Which validation commands passed or failed?
- What is the latest known project state?
- What should future replanning read before creating new phases?

## Recommended File

```text
Planner-docs/Planing-Ledger.md
```

## Recommended Headings

Ledger v3 is the default structure for new files:

```markdown
# Planing Ledger

## 1. Purpose
## 2. Planning Runs
## 3. Plan Snapshot Registry
## 4. Sub-Plan Status Matrix
## 5. Planning Evidence
## 6. Implementation Evidence
## 7. Implementation Runs
## 8. Current State Snapshot
## 9. Replanning Inputs
## 10. Open Decisions and Follow-Ups
```

Existing Ledger v2 files and legacy v1 ledgers remain valid for compatibility outside strict Step 4 execution. Non-strict validation accepts v1/v2 with a compatibility warning. Strict Step 4 execution requires migration to Ledger v3 before implementation starts.

## Update Rules

- Step 1 and Step 1.5 should read the ledger when it exists.
- Step 2 should read the ledger when it exists and carry relevant implementation history into sub-plans.
- Step 4 should append a concise implementation summary after each verified slice or stop event.
- Step 4 should record when a `Project-Comprehension.md` hypothesis is confirmed or contradicted, with concise evidence.
- Do not store secrets, tokens, credentials, private paths, or large logs.
- Store concise links or file paths to evidence instead of dumping full output.

## Plan Snapshot Registry

Use this section to map major planning artifacts to their current status and evidence.

```markdown
| Artifact | Status | Source evidence | Notes |
|---|---|---|---|
```

## Sub-Plan Status Matrix

Ledger v3 separates planning status from execution status.

Allowed planning status values are `draft`, `audited`, `needs_repair`, `approved`, and `superseded`.

Allowed execution status values are `not_started`, `ready`, `ready_with_warnings`, `in_progress`, `implemented`, `verified`, `blocked`, and `superseded`.

Use the Ledger v3 table shape:

```markdown
| Sub-plan Path | Planning Status | Execution Status | Snapshot ID | Run ID | Planning Evidence | Implementation Evidence | Blocker | Next Action | Superseded By | Updated At |
|---|---|---|---|---|---|---|---|---|---|---|
```

Planning status semantics:

- `draft`: planning artifact exists but has not been audited.
- `audited`: Step 3 reviewed the artifact; Planning Evidence is required.
- `needs_repair`: audit or validator found issues; Blocker and Next Action are required.
- `approved`: planning artifact is ready for execution; Planning Evidence is required.
- `superseded`: Superseded By is required.

Execution status semantics:

- `not_started`: no execution run exists yet.
- `ready`: audit says the slice is executable.
- `ready_with_warnings`: only open/accepted P2/P3 or accepted risks remain.
- `in_progress`: Run ID is required. Next Action alone is not enough evidence.
- `implemented`: Implementation Evidence is required; final acceptance/repo gate may still be pending.
- `verified`: acceptance criteria and required repo gates passed; Implementation Evidence is required.
- `blocked`: Blocker and Next Action are required.
- `superseded`: Superseded By is required.

Sub-plan Path must be repo-relative, must not contain `..`, must not be absolute, and should use this shape:

```text
Planner-docs/Faz-<n>-Plans/Faz<n>.<m>-<slug>.md
```

Do not keep two active rows for the same sub-plan with conflicting statuses.

## Step 4 Implementation Run Summary

Each Step 4 summary entry should include:

```markdown
### <date/time or run label> — <short run title>

- Source plan(s): <sub-plan paths>
- Slice(s) completed: <brief list>
- Files changed: <paths>
- Validation run: <commands and status>
- Evidence/artifacts: <paths or summaries>
- Remaining blockers: <none or concise blockers>
- Next recommended slice: <next queue item>
```

## Replanning Use

When a user reruns CodexQB for follow-up development, the agent should read the ledger before asking intake questions when possible. The agent should use the ledger as evidence, not as an unquestioned source of truth. Repository state, tests, and current user intent still win when they conflict with old ledger entries.
