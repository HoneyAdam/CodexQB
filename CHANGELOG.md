# Changelog

## Unreleased

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
