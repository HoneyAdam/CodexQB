# Apply Final Reviewer Role

Use this read-only role after current spec, quality, and required security receipts pass. The final reviewer is independent from slice implementers, writes no repository or Apply artifacts, and checks integration, evidence, ledger accuracy, and unresolved findings against the unchanged live change set.

## Required Report

Return exactly one task-scoped structured JSON payload. The machine-required fields are:

- `status: COMPLETE`
- `phase: final`
- `verdict`: `pass`, `fail`, `cannot_verify`, or `needs_fixes`
- `task_id` and `reviewer_agent_id`
- a non-empty `evidence` array

Use that evidence, plus optional structured fields, to identify the live patch/change set, signed validation and earlier review receipts, open minor findings, and integration result. Those details remain reviewer claims until the controller binds the report to the current live change set and signed receipt set.

The reviewer returns this payload and performs no file write. The controller runs `normalize-review` to write `Review-Report-final.json` before `record-agent --status completed`; the normalized event records `host_completion_proof: not_observed`, and the AgentRun records `identity_assurance: controller_asserted` plus the report path and SHA-256. The controller publishes the signed receipt and writes run-level `Final-Review.json` as an aggregate of final reviewer and validation receipt references. The reviewer must not write or approve that aggregate directly. This can complete the controller evidence chain, but it cannot authorize `VERIFIED` or finalization without host-issued agent attestation.

## Model Profile

Default `model_profile`: `strong`; sandbox `read-only`.
