# Apply Implementer Role

Use this role for a fresh-context worker that implements exactly one active task brief. Do not include parent chat history beyond the brief and cited source files.

## Required Inputs

- `Brief.md`
- active sub-plan path and hash
- allowed and forbidden paths
- validation commands
- stop conditions

## Required Return

Return these facts to the controller without inventing validation evidence:

- `task_id`
- `brief_sha256`
- `implementer_agent_id`
- `status`: `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, or `BLOCKED`
- `files_changed`
- `concerns`

The implementer writes no Apply artifact. Before recording completion or moving to `IMPLEMENTED`, the controller persists this return through `normalize-writer --role implementer` and binds its hash and normalization event to the current attempt. The controller then captures the live change set, executes the exact planned commands, and normalizes the enriched report again so the durable `Implementer-Report.json` binds controller-issued `validation_receipt_ids`, `change_set_id`, and `diff_sha256`; the implementer must not supply fabricated command hashes or receipt IDs.

## Model Profile

Default `model_profile`: `balanced`; sandbox `workspace-write`.
