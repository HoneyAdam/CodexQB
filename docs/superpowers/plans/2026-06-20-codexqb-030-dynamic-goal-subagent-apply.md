# CodexQB 0.3.0 Dynamic Goal Compiler and Subagent Apply Orchestrator

## Current-State Audit

- Repository: `<repo-root>`.
- Branch state at kickoff: `main...origin/main`, clean worktree.
- Baseline validation:
  - `python3 -m unittest discover -s tests -v` passed with 84 tests.
  - `make check` passed, including unit tests and fixture corpus checks.
  - `git diff --check` passed.
- Current version surface is 0.2.2 with `artifact_schema_version: 3` and `handoff_contract_version: 2`.
- Official upstream references reviewed:
  - OpenAI Goal guidance: durable goal, verifiable stopping condition, checkpoints, and progress log.
  - OpenAI subagent guidance: subagents inherit sandbox and runtime policy.
  - OpenAI skills guidance: `SKILL.md`, references, scripts, assets, and agents are the right packaging surface.
  - Local Superpowers subagent-driven-development guidance: fresh implementer, independent spec/quality review, fix/re-review loop, and final review.

## Feedback Disposition Matrix

| Feedback | Disposition | Evidence | Action |
|---|---|---|---|
| Unsafe validation command shell chains pass strict validation. | confirmed | `exact_validation_command()` accepts broad prefixes and does not reject `&&`, `;`, pipes, or command substitution. | Add structured argv command schema, reject shell metacharacters, and reject mutation/deploy executables. |
| Mutation-oriented commands can be blessed as validation commands. | confirmed | `bash scripts/deploy-prod.sh` and `npm run deploy` satisfy current prefix checks. | Add denylist and script-name intent checks for deploy/install/push/delete/destroy patterns. |
| High-risk plans can set `security_review_required: false`. | confirmed | Validator currently checks only boolean type. | Add `risk_class`, `risk_domains`, and semantic consistency between high-risk work and security review. |
| Framework and invariant tables pass with empty rows. | confirmed | Current table check proves headers and at least one row, not meaningful cells. | Require evidence-bearing cells, safe wrapper paths, validation probes, and unique IDs. |
| Step 3 lifecycle is missing. | rejected | Step 3 preflight, Step 3, and Step 4 audit lifecycle already exist and are tested. | Keep lifecycle, but update direct SKILL command wording to make preflight the first command. |
| Step 4 queue/readiness lifecycle is missing. | rejected | READY, READY_WITH_WARNINGS, NO_ACTION_REQUIRED, blockers, and unsafe path checks exist. | Keep existing lifecycle and extend methodology. |
| Step 4 lacks full Superpowers-style apply loop. | confirmed | Current docs mention roles but do not encode fresh implementer, dual verdicts, fix/re-review, and final review. | Add CodexQB-native apply modes and review loop wording. |
| Dynamic Goal Compiler is absent. | confirmed | No named `goal-compiler.md`, goal specs, `goal_run.py`, or tests exist. | Add deterministic Goal compiler references, script, artifacts, and tests. |
| Apply Orchestrator is absent as an implementation surface. | confirmed | Current Step 4 is a handoff contract, not a resumable runtime artifact protocol. | Add apply run protocol, runtime artifact shape, tests, and docs. |
| Installed plugin/cache sync is required. | out of scope for this run | The governing request forbids global Codex config/cache edits. | Do not sync installed copies in this branch. |

## Architecture Decisions

- Keep validator read-only. It validates planner artifacts and must never execute validation commands.
- Treat structured validation commands as planner contracts, not shell snippets. Preferred shape is `argv`, `cwd`, `expected_exit_code`, `timeout_seconds`, `network`, and `probe_tier`.
- Keep legacy `command` strings parseable only for compatibility, but strict validation rejects shell metacharacters and mutation/deploy intent.
- Model risk explicitly with `risk_class` and `risk_domains`; high or critical risk and sensitive domains require `security_review_required: true`.
- Keep Step 4 documentation CodexQB-native. Do not copy upstream Superpowers templates verbatim or import commit-per-slice behavior.
- Apply orchestration is artifact-based and resumable under target repos at `.codexqb/apply-runs/<apply-run-id>/`; source-tree changes are limited to docs, scripts, tests, and fixtures.
- Default commit policy for generated apply runs is `none`; commit, push, PR, deploy, and external mutations remain opt-in.

## Implementation Checkpoints

### Checkpoint 0 - Baseline and Plan

Status: complete.

Tasks:
- Confirm repo, branch, remote, and worktree state.
- Run baseline unit/check/diff validation.
- Review required repo files, official OpenAI references, and local Superpowers prompts.
- Collect read-only subagent audits.
- Create this plan file.

### Checkpoint 1 - Validator and Lifecycle Hardening

Status: complete.

Tasks:
- Add safe structured validation command checks.
- Reject unsafe legacy command strings.
- Enforce risk/security consistency.
- Strengthen Framework Ownership Matrix and Algorithmic Invariant Register row semantics.
- Update Step 3 direct execution guidance to start with `step3-preflight`.
- Add focused tests for all confirmed bypasses.

Result:
- Added structured validation command support with safe `argv` checks, `network` enum validation, and integer probe tiers.
- Rejected shell metacharacters, command substitution, mutation/deploy intent, path traversal, absolute private paths, and secret-like values in validation commands.
- Added `risk_class` and `risk_domains` validation with high-risk/security review consistency.
- Strict Step 2 now requires structured `argv`; legacy `command` strings are accepted only outside strict mode when safe.
- Strengthened Framework Ownership Matrix and Algorithmic Invariant Register row semantics.
- Updated Step 3 direct guidance to run `step3-preflight` before writing the audit.
- Added regression tests for unsafe commands, high-risk security-review bypass, blank framework/invariant rows, safe legacy command compatibility, and Step 4 apply review-loop wording.
- Targeted validation passed: `python3 -m unittest tests.test_validate_planner_docs tests.test_skill_content -v`.

### Checkpoint 2 - Dynamic Goal Compiler

Status: complete.

Tasks:
- Add `references/goal-compiler.md`.
- Add stage goal specs for Step 1.5, Step 2, Step 3, and Step 4.
- Add dependency-free `scripts/goal_run.py`.
- Generate deterministic `Goal-Run.json`, `Goal-Prompt.md`, and `Goal-Result.json` previews from source snapshots.
- Add goal compiler tests and fixtures.

Result:
- Added `references/goal-compiler.md`.
- Added stage specs for `step15`, `step2`, `step3`, and `step4`.
- Added dependency-free `scripts/goal_run.py`.
- Added `goal_run_schema_version: 1`, deterministic rendering from `Goal-Run.json`, source snapshot digest checks, `collect`/`prepare`/`validate`/`render` operations, default `Planner-docs/Goal-Runs/<goal-run-id>/` output, and tests covering stable run IDs, all stages, stale snapshot, secret-like content, overlapping paths, and repo-contained output.

### Checkpoint 3 - Subagent Apply Orchestrator

Status: complete.

Tasks:
- Add CodexQB-native Step 4 apply modes: `direct`, `subagent_serial`, `external_superpowers`, and `no_action`.
- Add per-slice fresh implementer, spec review, quality/security review, fix/re-review, and final review protocol.
- Add resumable apply-run artifact contract for `.codexqb/apply-runs/<apply-run-id>/`.
- Add apply-run tests for happy path, fix/review, blocked, needs-context, resume, stale snapshot, security-required, no-action, unsafe command, and unavailable external Superpowers adapter.

Result:
- Added `references/apply-orchestrator.md`.
- Added dependency-free `scripts/apply_run.py`.
- Added `apply_run_schema_version: 1`, `direct`/`subagent_serial`/`external_superpowers`/`no_action` modes, `Progress.json`, task folders, task state machine, review result shape, `no_action` mode, commit policy default, unsafe command validation, stale snapshot detection, external Superpowers fallback validation, and review-order validation.
- Added tests for artifact creation, `no_action`, repo-contained output, unsafe queue command, stale snapshot, non-READY/P0/P1 queue rejection, security-review-required tasks, final review, one-writer policy, recursive subagent rejection, and verified-task redispatch rejection.

### Checkpoint 4 - Documentation and Release Surface

Status: complete.

Tasks:
- Update README, CHANGELOG, USAGE, MAINTAINING, SKILL.md, openai.yaml, plugin.json, and marketplace metadata.
- Bump to `plugin_version: 0.3.0` only after tests and package checks pass.
- Preserve public wording that CodexQB is a gated planning/apply workflow, not a misleading three-step workflow.

Result:
- Updated README, CHANGELOG, USAGE, MAINTAINING, INSTALLATION, SKILL.md, openai.yaml, plugin metadata, and planner references.
- Bumped public release surface and validator expected plugin version to `0.3.0`.
- Documented structured validation command contracts, risk/security gates, Goal Compiler, Goal/apply schema versions, apply-run artifacts, apply modes, `no_action` mode, external Superpowers adapter fallback, and no commit/push/PR/deploy defaults.

### Checkpoint 5 - Final Validation

Status: complete with one packaging gate blocked by dirty-tree policy.

Commands:
- `python3 -m unittest discover -s tests -v`
- `make check`
- `python3 evals/run_fixture_corpus_checks.py`
- `git diff --check`
- `make export-sanitized`
- Extract sanitized zip and run `make check` without `.git`.

Result:
- `python3 -m unittest discover -s tests -v` passed with 99 tests.
- `make check` passed.
- `python3 evals/run_fixture_corpus_checks.py` passed with 8 fixtures.
- `git diff --check` passed.
- `make export-sanitized` was updated to create a sanitized current-worktree zip without requiring a commit.
- `make export-sanitized` passed, producing `CodexQB-sanitized.zip` from 94 files.
- Extracted-package `make check` passed without `.git`; fallback modes were labeled as `package_secret_hygiene_mode=filesystem` and `package_hygiene_mode=filesystem`.

## Test-First Tasks

- Add regression tests that unsafe shell chains and command substitution fail strict validation.
- Add regression tests that deploy/install/delete/push style commands fail strict validation.
- Add valid structured `argv` fixture coverage.
- Add risk/security consistency failure and pass tests.
- Add blank framework/invariant table row failure tests.
- Add SKILL content test for Step 3 preflight-first direct guidance.
- Add goal compiler unit tests before depending on generated docs.
- Add apply-run artifact state machine tests before documenting it as a stable interface.

## Migration and Compatibility Policy

- Existing 0.2.2 planner docs remain readable.
- Strict 0.3.0 validation prefers structured `argv` commands and rejects unsafe legacy strings.
- Legacy `command` fields may remain accepted only when demonstrably safe and non-mutating.
- Ledger v2 remains accepted outside strict Step 4 with warning; Ledger v3 remains preferred.
- Step 4 apply modes extend the existing queue contract without making subagents mandatory.

## Known Risks

- The 0.3.0 scope is larger than a small patch; validator hardening should land before feature expansion.
- Overly broad command denylist could reject legitimate project-specific validation scripts. Tests should document acceptable escape hatches, if any.
- Apply orchestration must avoid becoming a hidden executor. The artifact protocol should describe and validate decisions, not bypass user approval or repo instructions.
- Metadata bump must wait until final package checks pass.

## Completion Criteria

- Confirmed security and semantic bypasses are covered by failing-then-passing tests.
- Goal compiler creates deterministic artifacts and blocks unsafe source/runtime assumptions.
- Apply orchestrator protocol is documented, tested, resumable, and no-action safe.
- README/docs/metadata accurately describe schema v3, handoff contract v2, 0.3.0 behavior, and security gates.
- All final validation commands pass or blockers are documented with exact symptoms.
- No commit, push, PR, global Codex config edit, installed plugin/cache sync, dependency install, or outside-repo write occurs during this run.

## Validation Log

- 2026-06-21: Baseline `python3 -m unittest discover -s tests -v` passed with 84 tests.
- 2026-06-21: Baseline `make check` passed.
- 2026-06-21: Baseline `git diff --check` passed.
- 2026-06-21: Read-only subagent audits completed for repository contracts, security validation, and Step 4 methodology.
- 2026-06-21: Checkpoint 1 targeted tests passed with 91 tests: `python3 -m unittest tests.test_validate_planner_docs tests.test_skill_content -v`.
- 2026-06-21: Checkpoint 2/3 targeted tests passed with 99 tests: `python3 -m unittest tests.test_goal_run tests.test_apply_run tests.test_validate_planner_docs tests.test_skill_content -v`.
- 2026-06-21: Full unit suite passed with 99 tests: `python3 -m unittest discover -s tests -v`.
- 2026-06-21: `make check` passed.
- 2026-06-21: `python3 evals/run_fixture_corpus_checks.py` passed with 8 fixtures.
- 2026-06-21: `git diff --check` passed.
- 2026-06-21: Replaced the dirty-worktree export precondition with a dependency-free sanitized current-worktree exporter.
- 2026-06-21: Full unit suite passed with 106 tests after Goal/Apply schema alignment.
- 2026-06-21: `make check` passed after Goal/Apply schema alignment.
- 2026-06-21: `python3 evals/run_fixture_corpus_checks.py` passed with 8 fixtures.
- 2026-06-21: `git diff --check` passed.
- 2026-06-21: `make export-sanitized` passed; `CodexQB-sanitized.zip` created from 94 files.
- 2026-06-21: Extracted `CodexQB-sanitized.zip` into a temporary directory and ran `make check` without `.git`; package fallback hygiene labels appeared and validation passed.
- 2026-06-21: Follow-up feedback pass added shared safety contracts, exporter symlink/untracked-secret protection, stricter Goal path/render/prerequisite/overwrite checks, and Apply no-action/task/evidence/overwrite checks.
- 2026-06-21: Full unit suite passed with 119 tests after release-blocker hardening.
- 2026-06-21: `make check` passed after release-blocker hardening; fixture corpus passed with 8 fixtures.
- 2026-06-21: `git diff --check` passed after release-blocker hardening.
- 2026-06-21: `make export-sanitized` passed after release-blocker hardening; `CodexQB-sanitized.zip` created from 96 files with explicit untracked-file scanning.
- 2026-06-21: Extracted hardened `CodexQB-sanitized.zip` into a temporary directory and ran `make check` without `.git`; package fallback hygiene labels appeared and validation passed.
