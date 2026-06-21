# Changelog

## Unreleased

- Bumped the release surface to 0.3.0 with deterministic Goal previews and artifact-based Step 4 apply-run contracts.
- Added `references/goal-compiler.md`, stage goal specs, and dependency-free `scripts/goal_run.py` for `Goal-Run.json`, `Goal-Prompt.md`, and `Goal-Result.json` generation.
- Added `references/apply-orchestrator.md` and dependency-free `scripts/apply_run.py` for `.codexqb/apply-runs/<apply-run-id>/` artifacts, apply modes, `no_action` mode, review-order validation, and default `commit_policy: none`.
- Added packaged `references/apply-run-schema.json` so Apply runtime artifacts have a public JSON Schema contract alongside dependency-free Python validation.
- Added `goal_run_schema_version: 1` and `apply_run_schema_version: 1` runtime artifact contracts.
- Hardened strict planner validation against shell chaining, command substitution, mutation/deploy validation commands, high-risk security-review bypasses, and empty framework/invariant rows.
- Added shared safety contracts for planner, Goal, Apply, and export helpers; safe command profiles now reject arbitrary `python -c`, unchecked shell scripts, unsafe path arguments, mutating `make` targets, and custom package-manager scripts.
- Hardened sanitized export against symlink traversal and untracked secret leakage. `make export-sanitized` is now a strict tracked-only release export with package provenance manifest, clean-worktree enforcement, and `origin/main` mismatch checks when available; `make export-sanitized-worktree` explicitly includes untracked files only after symlink and content secret scanning.
- Hardened Goal previews with stage prerequisite blockers, relative project scope, unsafe glob/path overlap checks, stored snapshot digest validation, render-time validation, and no silent overwrite of existing Goal run artifacts.
- Hardened Goal preview preparation so stage prerequisites run the bundled validator and produce blocked results instead of execution prompts when Step 1, Step 3 preflight, or Step 4 readiness validation fails.
- Hardened Goal run semantic controls for supported stage modes, non-empty objectives and work steps, safe validation checkpoints, single-depth subagent plans, and bounded token-risk declarations.
- Added project-specific Goal scope collectors for active sub-plans and Step 4 READY queues.
- Added no-subplans Step 2 planning horizon collection from `Main-Planing.md`, validation command ID propagation, and contract-derived Step 4 work steps.
- Added Python 3.13 to the GitHub Actions validation matrix.
- Hardened Apply artifacts with audit-derived task queues, no silent progress overwrite, no-action queue consistency, task ID traversal rejection, shared validation-command policy, immutable plan snapshot separation from `Planing-Ledger.md`, schema-documented workspace baseline hashes, Git untracked inventory drift detection, non-Git file inventory drift detection, and evidence-bearing VERIFIED/final-review gates.
- Hardened Apply workspace safety so action modes block non-Git repositories by default unless the caller explicitly passes `--allow-non-git-unsafe`, which records `workspace_mode: non_git_unsafe` and `user_approval: true`.
- Hardened Apply Git workspace posture so action modes record `worktree_path`, `base_branch`, `working_branch`, and `dirty_state`, then block dirty or protected current Git worktrees unless `--allow-unverified-git-worktree` records explicit user approval.
- Hardened Apply preparation so `prepare` runs strict Step 4 validation, records validator evidence in `Apply-Run.json`, and derives READY queues from both prose and readiness-table audit rows.
- Added Apply transition control with `prepare`/`transition` CLI support, append-only `Events.jsonl`, atomic JSON writes, create-exclusive `Writer-Lock.json`, state-transition validation, and agent profile drift checks.
- Added `dispatch` and `record-agent` CLI support for `subagent_serial` runs so fresh-context `Dispatch-Packet.json` artifacts and spawned/completed/failed agent-run records bind task briefs to parent Codex `multi_agent_v1.spawn_agent` execution before implementation states advance.
- Added expired writer-lock validation and `recover-lock` CLI support for abandoned `IMPLEMENTING` tasks.
- Split deterministic Goal/Apply spec IDs from unique invocation run IDs, made resume require an explicit output directory, recorded Step 4 readiness summaries in apply runs, and added external Superpowers readiness/reconcile validation.
- Pinned Goal template/compiler hashes into `Goal-Run.json`, added `goal_run_sha256` result evidence, switched generated Apply task IDs to `AR-<apply-run-id>-T<nnn>`, added apply-run `finalize`, and added sanitized zip content/path hygiene to `make check`.
- Added an apply-run behavior smoke to `make check` that drives `prepare`, `dispatch`, `record-agent`, `transition`, `validate`, `recover-lock`, and `finalize` through subprocesses in a disposable repository.
- Added a 0.3.0 live subagent smoke evidence note that records docs-scope live spawn/review evidence without closing the full downstream Apply/Ralph multi-role e2e gate.
- Added fresh-context Apply role templates for controller, implementer, task reviewer, security reviewer, fixer, and final reviewer.
- Expanded the fixture corpus from 8 to 20 fixtures with Goal, Apply, resume, security, no-action, and sanitized-export edge-case coverage.
- Added 0.2.2 adaptive Step 2 release notes covering wave/full planning, artifact schema v3, handoff contract v2, structured implementation contracts, and stricter semantic validator gates.
- Added GitHub issue and pull request templates for evidence-backed contribution intake.
- Added a README community supporters section for public issue and PR contributors.
- Documented `make test` and pull request validation expectations in the README.
- Clarified the default `$codexqb` prompt so it describes explicit planning steps instead of implying a single automatic full-workflow run.

## 0.2.1

- Added Step 3 preflight validation and made Step 3 require `Planner-docs/Sub-Planing-Audit.md`.
- Added semantic Step 4 readiness parsing, NO_ACTION_REQUIRED support, finding status semantics, unsafe path rejection, and Ledger v2 strict execution checks.
- Added schema/version contracts: `artifact_schema_version: 2` and `handoff_contract_version: 1`.
- Moved Goal Run Contract handoff text into canonical `references/handoffs/run-step2.md`, `run-step3.md`, and `run-step4.md` files.
- Strengthened optional `Project-Comprehension.md` validation with minimum content checks, explicit markers, claim classes, and evidence requirements.
- Renamed deterministic fixture checks to fixture corpus checks while keeping `evals/run_fixture_checks.py` as a compatibility wrapper.
- Added `references/probe-policy.md` for static, local, stateful, and external/live probe boundaries.
- Documented 0.2.0 artifact compatibility and Ledger v1 migration behavior.

## 0.2.0

- Added evidence-backed project comprehension, optional ontology, planning ledger guidance, and fixture corpus inputs.
- Hardened repo validation, package hygiene, secret scanning, and installed skill parity workflows.
