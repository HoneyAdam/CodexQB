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

Ledger v2 is the default structure for new files:

```markdown
# Planing Ledger

## 1. Purpose
## 2. Planning Runs
## 3. Plan Snapshot Registry
## 4. Sub-Plan Status Matrix
## 5. Implementation Runs
## 6. Current State Snapshot
## 7. Replanning Inputs
## 8. Open Decisions and Follow-Ups
```

Existing legacy v1 ledgers with the older six-section structure remain valid for compatibility, but new CodexQB runs should prefer Ledger v2.

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

Allowed status values are `planned`, `ready`, `ready_with_warnings`, `in_progress`, `implemented`, `verified`, `blocked`, and `superseded`.

```markdown
| Sub-plan | Status | Validation evidence | Blocker |
|---|---|---|---|
```

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
