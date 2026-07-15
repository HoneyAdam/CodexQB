# Goal Spec: Step 2

Stage ID: `step2`

Purpose: compile a Goal prompt for adaptive Step 2 wave planning.

Required source references:
- `references/Second-Planner.md`
- `references/handoffs/run-step2.md`
- `references/workflow-quality.md`
- `references/planning-ledger.md`
- `references/project-ontology.md`

Safety:
- Detail only the active planning horizon unless full planning is explicit.
- Represent later phases as deferred roadmap cards.
- Require the closed seven-field structured validation command contract for every executable validation; legacy command prose is informational only.
- Do not implement product code.

Ready condition:
- Goal prompt includes the canonical Step 2 handoff and points Step 2 final output to the canonical Step 3 handoff.
