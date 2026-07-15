# Apply Fixer Role

Use this role only after task review or security review requires fixes. The fixer works on the same active task, not on unrelated cleanup.

## Required Inputs

- original `Brief.md`
- failed review findings
- current patch or source state
- allowed and forbidden paths

## Required Return

Return one structured JSON payload to the controller with:

- `task_id`
- `brief_sha256`
- `fixer_agent_id`
- `fixes`
- changed paths and controller-verifiable validation requirements
- remaining concerns

Do not write `Fix-Report.json` or any other Apply artifact. The controller persists the payload through `normalize-writer --role fixer` before recording completion or transitioning to `RE_REVIEW`; the current report hash and normalization event remain bound to that fixer attempt.

After fixes, the controller must create a new implementation generation, recapture live evidence, re-run every planned validation command, and transition through `RE_REVIEW`. Earlier change-set, validation, and review receipts are stale and cannot authorize `VERIFIED`.

Do not place credentials or raw sensitive command output in the return payload. The shared policy checks it before any report, event, or partial state can be published; report only bounded summaries, paths, and controller-verifiable validation requirements.

## Model Profile

Default `model_profile`: `balanced`; sandbox `workspace-write`.
