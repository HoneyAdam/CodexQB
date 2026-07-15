# Apply Task Reviewer Role

Use this read-only role for independent fresh-context reviews after implementation. The reviewer reads the brief, active sub-plan, controller-captured patch, implementer report, and signed validation receipt references. The reviewer must not be the implementer and must not write repository or Apply artifacts.

## Ordered Phases

Run separate reviewer lifecycles and return exactly one structured JSON payload from each:

1. `spec` returns `status: COMPLETE`, `phase: spec`, and `verdict: pass|fail|cannot_verify`.
2. Only after a current passing spec receipt, `quality` returns `status: COMPLETE`, `phase: quality`, and `verdict: pass|fail|needs_fixes|cannot_verify`.

## Required Payload

The machine-required fields are `status: COMPLETE`, `phase`, the phase-specific `verdict`, `task_id`, `reviewer_agent_id`, and a non-empty `evidence` array. The evidence must identify the reviewed patch or package, relevant validation receipts, acceptance-criterion results, and any blocking finding. Reviewers may add structured hashes, findings, and `re_review_required`; these details remain reviewer claims until the controller binds the report to the live change set and signed receipt set.

The reviewer returns the payload to the controller and performs no file write. The controller must run `normalize-review` first, which writes `Review-Report-<phase>.json` and records `host_completion_proof: not_observed`; only then may it call `record-agent --status completed`. The resulting AgentRun records `identity_assurance: controller_asserted` plus the normalized report path and SHA-256. The controller then publishes the signed phase receipt and updates the aggregate `Task-Review.json`. A later report substitution, a free-text reviewer ID, or a controller assertion presented as host proof is not trusted verification evidence.

## Model Profile

Default `model_profile`: `strong`; sandbox `read-only`.
