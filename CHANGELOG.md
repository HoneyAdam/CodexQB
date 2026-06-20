# Changelog

## Unreleased

- Bumped the release surface to 0.3.0 with deterministic Goal previews and artifact-based Step 4 apply-run contracts.
- Added `references/goal-compiler.md`, stage goal specs, and dependency-free `scripts/goal_run.py` for `Goal-Run.json`, `Goal-Prompt.md`, and `Goal-Result.json` generation.
- Added `references/apply-orchestrator.md` and dependency-free `scripts/apply_run.py` for `.codexqb/apply-runs/<apply-run-id>/` artifacts, apply modes, `no_action` mode, review-order validation, and default `commit_policy: none`.
- Added `goal_run_schema_version: 1` and `apply_run_schema_version: 1` runtime artifact contracts.
- Hardened strict planner validation against shell chaining, command substitution, mutation/deploy validation commands, high-risk security-review bypasses, and empty framework/invariant rows.
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
