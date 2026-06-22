# CodexQB 0.3.0 Release Integrity Closure

## Baseline Repository State

- Repository: `<repo-root>`
- Branch: `main`
- HEAD: `c30814e5d7d855f51f2b23c4a12792d9c1d3660a`
- origin/main: `c30814e5d7d855f51f2b23c4a12792d9c1d3660a`
- Initial worktree: clean, `## main...origin/main`
- `AGENTS.md`: absent
- Plugin version: `0.3.0`
- Artifact schema version: `3`
- Goal run schema version: `1`
- Apply run schema version: `1`
- Existing tags: none reported by `git tag --list --sort=v:refname`
- Continuation note: a later in-progress handoff resumed with expected release-integrity modifications already present in the worktree; those changes were preserved and audited rather than reverted.

## Feedback Disposition Matrix

| Finding | Status | Evidence | Planned action |
|---|---|---|---|
| Bind embedded Goal implementation contracts to source sub-plans. | CONFIRMED | Temp fixture allowed self-consistent Goal contract, validation ID, and security flag tampering with `validate_goal_run()` returning `[]`. | Add canonical source contract parser and validate Goal scope items against source files. |
| Bind Apply task contracts and downstream artifacts to source sub-plans. | CONFIRMED | Temp fixture allowed Apply task contract, source hash/path, Brief, and dispatch prompt tampering with `validate_apply_run()` returning `[]`. | Recompute source contract and compare every task, Brief, dispatch packet, and reports/reviews. |
| Split Goal snapshots into immutable inputs, mutable outputs, and workspace baselines. | CONFIRMED | Step 3 Audit creation and Step 4 Ledger update both produced `source_snapshot_mismatch`. | Add stage-aware snapshot layers and allow stage-owned mutable outputs while blocking immutable drift. |
| Remove private paths and machine identifiers from release artifacts. | CONFIRMED | `rg` found macOS user paths, private temp paths, local Codex attachment paths, and raw run IDs in release audit/evidence docs. | Sanitize docs, add public privacy gate, and update tests. |
| Harden package-fallback testing and release docs. | CONFIRMED | No-Git package fallback test skips unit tests only and still runs behavior smoke/downstream dry run. | Add skip for behavior smoke in fallback test and assert bounded fallback output. |
| Add explicit Goal/subagent budget contracts and regression coverage. | CONFIRMED | Goal budget is qualitative `context_token_budget`; Apply has max depth/writers but no structured budget schema. | Add schema, validation, prompt/result summaries, selected-task/fix/subagent attempt limits. |
| Update feedback closure audit honestly. | CONFIRMED | Existing closure matrix marks several items closed despite missing source binding/privacy evidence. | Rewrite closure matrix with CLOSED/PARTIAL/OPEN/REJECTED and evidence levels. |
| Prepare for separate FB-012 release/tag operation. | CONFIRMED | `CHANGELOG.md` keeps `0.3.0` under Unreleased and FB-012 remains OPEN. | Keep FB-012 open and report readiness only. |

## Affected Components

- Goal compiler: `plugins/codexqb/skills/codexqb/scripts/goal_run.py`
- Apply orchestrator: `plugins/codexqb/skills/codexqb/scripts/apply_run.py`
- Shared safety/contracts: `plugins/codexqb/skills/codexqb/scripts/safety_contracts.py`
- Public schema/reference docs: `plugins/codexqb/skills/codexqb/references/**`
- Release/export validation: `scripts/validate.sh`, `scripts/export_sanitized.py`, `Makefile`
- Regression tests: `tests/test_goal_run.py`, `tests/test_apply_run.py`, `tests/test_skill_content.py`, `tests/test_export_sanitized.py`
- Release docs: `README.md`, `docs/USAGE.md`, `docs/MAINTAINING.md`, `docs/INSTALLATION.md`, `CHANGELOG.md`, `docs/release-audits/**`, `docs/release-evidence/**`

## Architecture Decisions

- Use one canonical Implementation Contract helper shared by Goal and Apply.
- Canonical JSON digest uses sorted keys, compact separators, UTF-8, and standard library JSON.
- Runtime validators must re-read source sub-plans; artifact-provided digests are never authoritative by themselves.
- Goal snapshots become stage-aware: immutable inputs, mutable outputs, and workspace baseline.
- Stage-owned mutable outputs are allowed only for the stage that declares them.
- Apply validation must tie task, Brief, dispatch, implementer report, task review, security review, fix report, final review, and result back to the source contract digest.
- Privacy scanning is dependency-free and only reports file/line, not content.
- Budget enforcement is honest: deterministic task/retry/fan-out limits are enforced; token usage is recorded as `not_observed` unless runtime data exists.

## Compatibility Decisions

- Preserve `Planing` spelling and required English headings.
- Preserve schema versions unless a breaking field removal becomes necessary; prefer additive fields.
- Preserve existing Step 1 / Step 1.5 / Step 2 / Step 3 / Step 4 workflow.
- Do not add dependencies, MCP servers, Apps SDK artifacts, keys, or global config edits.
- Do not commit, push, tag, publish a release, deploy, or sync installed/plugin-cache copies.
- Keep final clean-tree export as an FB-012 gate if the worktree is intentionally dirty.

## Test-First Implementation Tasks

1. Add adversarial Goal tests for self-consistent source-divergent contract, validation IDs, security flags, missing source sub-plan, and duplicate mappings.
2. Add adversarial Apply tests for task contract/source hash/source path/Brief/dispatch/report/review drift.
3. Add stage-aware Goal resume tests for Step 3 Audit, Step 4 Ledger, immutable sub-plan drift, unrelated workspace drift, and duplicate mutable outputs.
4. Add privacy-gate tests for public docs and redacted evidence.
5. Add no-Git fallback test that skips behavior smoke and proves fallback hygiene only.
6. Add budget schema tests for invalid limits, selected-task cap, subagent attempts, fix cycles, and unobserved token usage.
7. Update docs/content tests to match the new contracts and sanitized evidence.

## Checkpoint Checklist

- [x] Checkpoint 0 baseline repo state verified.
- [x] Checkpoint 0 baseline tests: unit suite, `make check`, `git diff --check`, and clean-tree `make check-release`.
- [x] Checkpoint 0 read-only subagents: source binding, snapshot/resume, release/privacy.
- [x] Checkpoint 0 candidate findings reproduced in temp fixtures.
- [x] Checkpoint 1 source binding code/tests/docs.
- [x] Checkpoint 2 stage-aware snapshot/resume code/tests/docs.
- [x] Checkpoint 3 privacy/evidence code/tests/docs.
- [x] Checkpoint 4 package fallback/docs cleanup.
- [x] Checkpoint 5 budget contracts.
- [x] Checkpoint 6 closure audit updated.
- [x] Checkpoint 6 final validation run; strict clean-tree export stopped on expected dirty-worktree guard.

## Validation Log

- `python3 -m unittest discover -s tests -v`: passed, 146 tests, about 17.7s.
- `make check`: passed, 146 tests plus behavior, downstream dry run, metric checks, fixture corpus; `fixture_count=20`, about 23.5s.
- `git diff --check`: passed.
- `make check-release`: passed before edits from clean tree, exported `file_count=133`, extracted package validation passed.
- Privacy scan before edits found private path and run-ID leaks in release docs.
- No-Git package fallback reproduction ran behavior smoke and downstream dry run when only unit tests were skipped.
- Checkpoint 1 focused validation: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_goal_run tests.test_apply_run -v` passed, 57 tests, about 11.1s.
- Checkpoint 2 focused validation: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_goal_run tests.test_apply_run -v` passed, 66 tests, about 15.7s.
- Checkpoint 3 focused validation: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_skill_content -v` passed, 37 tests, about 6.3s.
- Checkpoint 3 privacy gate: `python3 scripts/check_public_privacy.py --root .` passed; working-tree release-doc scan found no private path, attachment, UUID, or raw agent ID hits.
- Checkpoint 5 first focused validation found one direct-mode injected `agent_runs` attempt-budget gap; fixed by validating agent attempt budgets in the mode-independent task loop.
- Checkpoint 5 focused validation: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_goal_run tests.test_apply_run tests.test_skill_content -v` passed, 110 tests, about 23.5s.
- Final full suite first run found stale content expectation for the old release label; fixed `tests/test_skill_content.py`.
- Final full suite: `python3 -m unittest discover -s tests -v` passed, 180 tests, about 23.8s.
- Final repo gate: `make check` passed; included 180 tests, `apply_behavior_smoke=passed`, `downstream_goal_apply_dry_run=passed`, `goal_apply_metric_checks=passed`, `fixture_corpus_checks=passed`, `fixture_count=20`.
- Standalone fixture gate: `python3 evals/run_fixture_corpus_checks.py` passed, `fixture_count=20`.
- Final whitespace gate: `git diff --check` passed.
- Final privacy/schema gates: `python3 scripts/check_public_privacy.py --root .` passed, `public_privacy_files_scanned=10`; `python3 -m json.tool plugins/codexqb/skills/codexqb/references/apply-run-schema.json >/dev/null` passed.
- Final release gate: `make check-release` ran `check` and `check-public-privacy` successfully, then stopped at strict `make export-sanitized` with `ValueError: working_tree_dirty`, as expected because this Goal leaves changes uncommitted.
- Dirty-worktree package smoke: `make export-sanitized-worktree` passed, `file_count=137`.
- Extracted no-Git package fallback: `CODEXQB_VALIDATE_SKIP_UNITTESTS=1 CODEXQB_VALIDATE_SKIP_BEHAVIOR_SMOKE=1 bash scripts/validate.sh` passed from the extracted worktree package with filesystem hygiene mode, metrics, and fixture corpus.
- Read-only subagent audit follow-up found and closed late issues: legacy Goal CLI blocked-status reporting, Step 4 prompt/write-envelope under-reporting, Goal `work_steps` drift, Goal `subplan_path`/`source_subplan_path` alias drift, Apply validation without inferable root, and raw live Apply run/task IDs in the high-level feedback audit.
- Subagent follow-up focused validation: `python3 -m unittest tests.test_goal_run tests.test_apply_run -v` passed, 78 tests, about 21.1s.

## Unresolved Risks

- Original raw live Apply artifacts may not be available in tracked repo; evidence must remain PARTIAL if only summarized markdown can be verified.
- Final clean-tree export may need to be deferred until after the user commits this work separately.
- The new privacy gate and redacted evidence package are repository modifications but are not release-provenance proof until committed and included in a clean tracked-only export.
- Public evidence must retain enough verification value after sanitization without exposing private local paths or raw internal IDs.
- Budget token enforcement depends on runtime support; deterministic caps are enforceable, token observation may remain `not_observed`.

## FB-012 Release Boundary

FB-012 remains out of scope. This Goal must not create `v0.3.0`, date the final release section as complete, push, publish a GitHub Release, upload release assets, deploy, edit global Codex config, or sync installed/plugin-cache copies.
