# CodexQB 0.2.1 Gate Integrity Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden CodexQB semantic validation gates while keeping 0.2.0 artifacts readable through compatibility warnings and documented migration paths.

**Architecture:** Keep validation dependency-free in `validate_planner_docs.py`, add explicit semantic parsers for audit readiness, findings, comprehension, and ledger rows, and move handoff contract text into canonical references. Keep live Codex evals out of CI; rename current fixture checks to corpus checks.

**Tech Stack:** Python 3 stdlib, Bash, unittest, Markdown prompt/reference files, Codex plugin/skill metadata.

---

### Task 1: Regression Tests

**Files:**
- Modify: `tests/test_validate_planner_docs.py`
- Modify: `tests/test_skill_content.py`

- [x] Add tests proving `step3-preflight --strict` passes valid Step 2 docs without audit.
- [x] Add tests proving `step3 --strict` fails without `Planner-docs/Sub-Planing-Audit.md`.
- [x] Add tests proving headings-only audit fails Step 4.
- [x] Add tests proving headings-only `Project-Comprehension.md` fails strict validation.
- [x] Add tests for readiness path safety, duplicate rows, `NO_ACTION_REQUIRED`, finding statuses, Ledger v2 statuses, claim classes, and explicit markers.
- [x] Add content tests for canonical handoff files, corpus-check naming, bounded Goal/subagent policy, and docs/metadata versioning.

### Task 2: Validator Semantics

**Files:**
- Modify: `plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py`

- [x] Add `step3-preflight` mode and stable exit-code/marker output.
- [x] Require audit for `step3`, `step4`, and `all`.
- [x] Parse canonical audit readiness and priority-fix tables.
- [x] Enforce execution queue states, readiness statuses, dependency states, path safety, and finding-status consistency.
- [x] Enforce strict optional artifact minimums while preserving non-strict 0.2.0 compatibility warnings.
- [x] Enforce Ledger v2 status semantics and strict Step 4 migration requirement for legacy ledgers.

### Task 3: Corpus Checker Rename

**Files:**
- Rename: `evals/run_fixture_checks.py` -> `evals/run_fixture_corpus_checks.py`
- Create: `evals/run_fixture_checks.py`
- Modify: `scripts/validate.sh`
- Modify: `tests/test_skill_content.py`

- [x] Rename output markers from `fixture_eval_*` to `fixture_corpus_*`.
- [x] Keep a compatibility wrapper returning the same exit code.
- [x] Update `make check` validation path and docs references.

### Task 4: Canonical Handoffs and References

**Files:**
- Create: `plugins/codexqb/skills/codexqb/references/handoffs/run-step2.md`
- Create: `plugins/codexqb/skills/codexqb/references/handoffs/run-step3.md`
- Create: `plugins/codexqb/skills/codexqb/references/handoffs/run-step4.md`
- Create: `plugins/codexqb/skills/codexqb/references/probe-policy.md`
- Modify: `plugins/codexqb/skills/codexqb/SKILL.md`
- Modify: `plugins/codexqb/skills/codexqb/references/*.md`

- [x] Move full Goal Run Contract text into canonical handoff files with `contract_version: 1`.
- [x] Replace duplicated handoff blocks with instructions to read and return the canonical handoff.
- [x] Add resume/recovery protocol, Step 4 batch limits, bounded subagent policy, and probe tiers.
- [x] Update Step 2 index guidance and ledger ownership rules without expanding Step 1/1.5 file boundaries.

### Task 5: Release Docs and Metadata

**Files:**
- Modify: `plugins/codexqb/.codex-plugin/plugin.json`
- Modify: `plugins/codexqb/skills/codexqb/agents/openai.yaml`
- Modify: `README.md`
- Modify: `docs/USAGE.md`
- Modify: `docs/MAINTAINING.md`
- Modify: `docs/INSTALLATION.md`
- Create or modify: `CHANGELOG.md`

- [x] Bump plugin version to `0.2.1`.
- [x] Document `artifact_schema_version: 2` and `handoff_contract_version: 1`.
- [x] Document validator mode changes, legacy migration behavior, corpus-check terminology, and live eval deferral.

### Task 6: Verification and Local Install Parity

**Files:**
- No source changes expected during this task.

- [x] Run `make check`.
- [x] Run `python3 -m unittest discover -s tests -v`.
- [x] Run `python3 evals/run_fixture_corpus_checks.py`.
- [x] Run `git diff --check`.
- [ ] Run `make export-sanitized`. Blocked until the worktree/index is clean because the target intentionally archives `HEAD` only.
- [ ] Extract `CodexQB-sanitized.zip` and run `make check` without `.git`. Blocked by the same clean-HEAD export guard.
- [x] Run `.git`-less package fallback check from a temp working-tree copy with `make check`.
- [x] Sync `plugins/codexqb/skills/codexqb/` to `$HOME/.codex/skills/codexqb/`.
- [x] Run `codex plugin add codexqb@codexqb`.
- [x] Diff repo skill against installed skill and plugin cache.
