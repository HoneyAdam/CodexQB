# CodexQB Feedback Closure Audit

Date: 2026-06-21
Reviewed feedback source: `/Users/alicankiraz/.codex/attachments/897b1b78-e5fd-48e7-a42b-c27a2b456a98/pasted-text-1.txt`
Review baseline head: `cf9d80f Carry Goal implementation contracts`

This audit maps the external feedback items to current repository evidence. It is not a release tag decision; it records what is closed, what is partially covered, and what still needs stronger evidence before declaring the full feedback objective complete.

## Summary

| Area | Current status | Evidence |
|---|---|---|
| Release-blocker safety defects | Mostly closed | `scripts/export_sanitized.py`, `scripts/validate.sh`, `scripts/safety_contracts.py`, `tests/test_export_sanitized.py`, `tests/test_validate_planner_docs.py`, `tests/test_goal_run.py`, `tests/test_apply_run.py` |
| Goal compiler project-specificity | Mostly closed for preview artifacts | `plugins/codexqb/skills/codexqb/scripts/goal_run.py`, `tests/test_goal_run.py::test_goal_scope_collectors_include_project_specific_subplans_and_ready_queue` |
| Apply orchestrator durability | Mostly closed for artifact controller semantics | `plugins/codexqb/skills/codexqb/scripts/apply_run.py`, `plugins/codexqb/skills/codexqb/references/apply-run-schema.json`, `evals/run_apply_behavior_smoke.py` |
| Subagent methodology contracts | Mostly closed at artifact/prompt level | `plugins/codexqb/skills/codexqb/references/apply/*.md`, `tests/test_skill_content.py::test_apply_role_templates_and_durable_controller_contract_are_wired` |
| Live release-grade orchestration proof | Remaining risk | Current tests are deterministic artifact/controller smoke tests; they do not prove live multi-agent execution across real downstream projects. |

## Release Blocker Items

| Feedback item | Status | Evidence / notes |
|---|---|---|
| Sanitized exporter rejects symlink traversal and untracked secrets | Closed | `scripts/export_sanitized.py` rejects symlinks, outside-root resolved paths, ignored/runtime paths, and secret-like content. Covered by `tests/test_export_sanitized.py::test_export_rejects_symlink_candidates` and `test_include_untracked_scans_secret_content`. |
| Export defaults to tracked files, optional untracked inclusion is scanned | Closed | `scripts/export_sanitized.py::candidate_paths`; documented in `README.md` and covered by `test_default_export_excludes_untracked_files`. |
| Shared structured command policy for planner, Goal, Apply, and export | Closed | `plugins/codexqb/skills/codexqb/scripts/safety_contracts.py`; wiring covered by `tests/test_skill_content.py::test_shared_safety_contracts_are_wired`. |
| Reject arbitrary `python -c`, unsafe shell scripts, mutating make/npm/uv, unsafe path args | Closed | `safety_contracts.py::safe_validation_argv`; adversarial planner coverage in `tests/test_validate_planner_docs.py` and apply coverage in `tests/test_apply_run.py::test_apply_run_rejects_unsafe_queue_command`. |
| Goal wildcard/path overlap policy | Closed | `goal_run.py::validate_goal_run`, `safety_contracts.py::glob_patterns_overlap`; covered by `test_goal_run_rejects_unsafe_wildcards_and_glob_overlap`. |
| Goal render validates before writing prompt | Closed | `goal_run.py::render_goal_file`; covered by `test_goal_render_validates_before_writing_prompt`. |
| Goal spec/run ID collision and silent overwrite | Closed | `goal_spec_id` is deterministic, `goal_run_id` is invocation-specific, existing output dirs require `--replace` or `--resume`; covered by `test_goal_run_id_includes_mode_and_objective_and_does_not_overwrite`. |
| Stage prerequisites block missing/invalid inputs | Closed | `goal_run.py::stage_prerequisite_blockers`; covered by `test_goal_prepare_blocks_missing_stage_prerequisites` and `test_goal_prepare_blocks_when_stage_validator_fails`. |
| Apply run ID/progress overwrite | Closed | `apply_spec_id` and unique `apply_run_id`; covered by `tests/test_apply_run.py::test_apply_run_does_not_overwrite_existing_progress_by_default` and `test_apply_run_snapshot_mismatch_blocks_resume`. |
| Ledger-mutable snapshot model | Closed for Apply resume validation | `apply_run.py::collect_snapshot` excludes `Planing-Ledger.md` and tracks workspace baseline separately. |
| Task ID traversal | Closed | Generated IDs use `AR-<run>-T<nnn>` and validation resolves task dirs inside run dir; covered by `test_apply_run_rejects_task_id_traversal_and_no_action_queue`. |
| VERIFIED task evidence schema | Closed for artifact validation | `apply_run.py::validate_task_artifacts` requires matching brief hash, implementer identity, changed files, passing validation evidence, independent reviewer identity, review evidence, and final validation evidence. Covered by `test_verified_task_requires_evidence_bearing_reports`. |
| `no_action` queue consistency | Closed | `apply_run.py::validate_apply_run`; covered by `test_no_action_mode_has_no_queue` and `test_apply_run_rejects_task_id_traversal_and_no_action_queue`. |

## Goal Compiler Items

| Feedback item | Status | Evidence / notes |
|---|---|---|
| Step 2 active/deferred scope and sub-plan inventory | Closed for preview | `goal_run.py::collect_stage_scope` and Step 2 validator fixtures; covered by `test_goal_scope_collectors_include_project_specific_subplans_and_ready_queue`. |
| Step 3 exact sub-plan inventory and dual checkpoints | Closed | `validation_checkpoints_for("step3")` emits `step3-preflight` and `step3`; covered by `test_step3_goal_includes_preflight_and_post_audit_checkpoints`. |
| Step 4 READY queue with sub-plan contracts | Closed for preview | `extract_ready_queue`, `subplan_scope_item`, structured `implementation_contract` inclusion; covered by `test_goal_scope_collectors_include_project_specific_subplans_and_ready_queue`. |
| Acceptance signals, security flags, validation commands, subagent roles | Mostly closed | `subplan_scope_item` carries contract signals and structured contracts; `build_subagent_plan` selects roles and security reviewer when needed. |
| Absolute local path removal | Closed | `active_scope.project_root` is `"."`; covered in `test_compile_goal_writes_stable_spec_and_unique_run_artifacts`. |
| Stored snapshot integrity | Closed for current repo validation | `stored_source_snapshot_digest_mismatch`, template bundle digest, compiler digest, result prompt/run hashes. |
| Standalone prompt reproduction from only `Goal-Run.json` | Partial | Current renderer validates the pinned template/compiler hashes against the installed repo copy, then renders from current template files. It does not embed full template bodies in `Goal-Run.json`; byte-identical reproduction therefore still requires the matching template bundle on disk. |
| Selected batch semantics | Partial | Step 4 queue is compiled and ordered, but there is no explicit `selected_batch` field distinct from the full READY queue. |

## Apply Orchestrator Items

| Feedback item | Status | Evidence / notes |
|---|---|---|
| Audit-derived task queue | Closed | `apply_run.py::extract_ready_queue` and `default_tasks`; covered by `test_init_subagent_serial_creates_safe_artifacts`. |
| Strict Step 4 gate before action artifacts | Closed | `apply_run.py::step4_readiness`; covered by `test_apply_prepare_requires_passing_step4_validator`. |
| Workspace baseline and dirty/protected worktree posture | Closed | `workspace_baseline`, `git_worktree_requires_approval`, posture fields in `Apply-Run.json`; covered by `test_apply_run_workspace_baseline_detects_git_untracked_drift`, `test_apply_run_workspace_baseline_detects_non_git_source_drift`, and `test_apply_run_blocks_dirty_or_protected_git_without_explicit_approval`. |
| `isolated_worktree` overclaim | Closed by wording/model change | Current schema uses `verified_isolated_worktree`, `unverified_current_worktree`, and `non_git_unsafe`; action modes require explicit unsafe approval when not verified. |
| Shared Apply command policy | Closed | `apply_run.py::command_is_safe` delegates to `safe_validation_command_item`. |
| State machine and append-only events | Closed for artifact controller | `transition_task_state`, `Events.jsonl`, validation of contiguous transition events; covered by `test_transition_cli_appends_events_and_manages_writer_lock` and `test_validate_rejects_state_without_transition_event`. |
| Atomic writer lock and stale recovery | Mostly closed | `Writer-Lock.json` is acquired with create-exclusive semantics and stale recovery is explicit. Covered by `test_recover_stale_writer_lock_moves_task_to_needs_context`. Atomic JSON writes are present via helper-level write/replace behavior in runtime code, but live concurrent multi-process stress is not covered. |
| External Superpowers readiness and reconcile | Closed for artifact policy | `validate_external_superpowers`, `reconcile_external_superpowers`; covered by `test_external_superpowers_unavailable_requires_safe_fallback`. |
| Fresh-context implementation contract in task/dispatch | Closed | `implementation_contract` is required in task schema and included in `Progress.json`, `Brief.md`, and dispatch prompts; covered by `test_init_subagent_serial_creates_safe_artifacts` and `test_subagent_serial_requires_dispatch_packet_before_implementation`. |

## Subagent Methodology Items

| Feedback item | Status | Evidence / notes |
|---|---|---|
| Role-specific templates | Closed | `references/apply/controller.md`, `implementer.md`, `task-reviewer.md`, `security-reviewer.md`, `fixer.md`, `final-reviewer.md`. |
| Model profiles instead of hardcoded models | Closed | `AGENT_PROFILES` in `apply_run.py` and `GOAL_AGENT_PROFILES` in `goal_run.py`; schema enum in `apply-run-schema.json`. |
| Review independence | Closed for artifacts | `reviewer_agent_id != implementer_agent_id` and security reviewer independence are validated. Covered by `test_apply_run_requires_security_review_and_final_review_for_verified_task`. |
| One reviewer with two verdicts, separate security reviewer only for high risk | Closed | `Task-Review.json` requires spec and quality verdicts; security reviewer identity required only when security review is required/performed. |
| Fresh-context brief enforcement | Mostly closed | Briefs carry source sub-plan path/hash, fresh context signals, structured implementation contract, validation commands, security flag, and dispatch packets use `fork_context: false`. The live Codex child thread creation is still manual/adapter-driven and is not executed by tests. |

## Eval And Release Evidence

| Feedback item | Status | Evidence / notes |
|---|---|---|
| Add Goal/Apply/export fixture names | Closed for corpus presence | `evals/run_fixture_corpus_checks.py` requires 20 fixtures including all named Goal/Apply/export fixtures. |
| Behavioral Apply controller smoke | Closed for local artifact lifecycle | `evals/run_apply_behavior_smoke.py` drives prepare, dispatch, record-agent, transition, validate, finalize, and stale-lock recovery. |
| Token metrics for static vs dynamic prompts and single-agent vs subagent Step 4 | Remaining | The fixture corpus names exist, but there is no durable metric collector for token size/use deltas. |
| Extracted package smoke | Partially covered | `scripts/validate.sh` supports package validation without `.git`; current closeout should still run extracted-package validation before a final release tag. |
| Release tag/changelog finalization | Remaining | `CHANGELOG.md` still has `0.3.0` under `Unreleased`, which is acceptable before tagging but blocks final release packaging. |

## Current Decision

The original release-blocker list has been substantially addressed in code, docs, tests, and CI. The remaining work is not another narrow safety patch unless a new failing scenario appears; the next release-quality step is a final release audit:

1. Run the full repo gate.
2. Run sanitized export.
3. Extract `CodexQB-sanitized.zip` into a clean temp directory and run `bash scripts/validate.sh`.
4. Run at least one real downstream Step 2 -> Step 3 -> Step 4 Goal/Apply dry run against a representative project.
5. Add token/size metrics for static vs dynamic Goal prompts and Step 4 apply modes.
6. Move `CHANGELOG.md` from `Unreleased` to a dated `0.3.0` section only after those release gates pass.
