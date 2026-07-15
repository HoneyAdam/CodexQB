# Maintaining CodexQB

This document covers validation and release maintenance for CodexQB.

Current release contracts:

```text
plugin_version: 0.3.0
artifact_schema_version: 3
handoff_contract_version: 2
goal_run_schema_version: 1
apply_run_schema_version: 3
```

## Dependency-Free Repo Check

Run the default repository validation before every release:

```bash
make check
```

This checks JSON manifests, required package files, `agents/openai.yaml` semantic fields, stale invocation names, vibecoding/subagent/ledger/ontology/comprehension prompt wiring, deterministic fixture corpus inputs, downstream Step 2 -> Step 4 Goal/Apply dry-run coverage, Goal/Apply prompt-size metric checks, tracked-file secret hygiene, archive hygiene, sanitized zip path/content hygiene, and the Python unit test suite. It intentionally uses only shell and Python standard-library commands, preserving the dependency-free runtime and default local gate.

CI and schema maintainers must additionally validate the public Apply schema with a real Draft 2020-12 engine:

```bash
python3 -m pip install --requirement requirements-ci.txt
make check-schema
```

This development/CI-only gate checks the schema meta-contract and validates artifacts by their filename-mapped intended `$defs` definition. The schema's root `anyOf` remains a non-discriminating compatibility surface and must not be used as the security or CI acceptance gate. Runtime validation in `apply_run.py` remains dependency-free. Structural JSON Schema checks complement, but do not replace, runtime relational checks such as budget relationships and cross-artifact provenance.

The required package set includes `plugins/codexqb/skills/codexqb/scripts/artifact_io.py`. Keep its contract aligned across code, tests, and public docs: Goal writes only below one direct, non-symlink `Planner-docs/Goal-Runs/<run>/`; Apply mutations require a registered and HMAC-verified direct `.codexqb/apply-runs/<run>/`; managed-parent and final-target symlinks fail closed. Secure replacement uses a random same-directory `O_EXCL | O_NOFOLLOW` temporary, a full write loop, file and directory `fsync`, descriptor-relative atomic replace, and cleanup before commit. Apply uses a run-directory `flock` to serialize cooperating mutations, and rewrites the complete validated `Events.jsonl` atomically while allocating a unique, contiguous sequence under that lock. Every event must bind the previous event SHA-256 and its own canonical SHA-256; partial trailing lines, malformed records, colliding or reordered sequences, and broken hash links fail closed. When post-replace directory `fsync` first fails, the append path may return success only after observing the exact intended file under the lock and completing a retry; persistent or unreadable ambiguity raises `event_log_commit_state_unknown`, and callers must inspect and validate instead of blindly retrying. Validation rejects a transition-event/`Progress.json` mismatch; there is no automatic multi-file recovery, so archive the affected run and prepare a fresh run. Test and document these as per-file integrity guarantees, not a multi-file transaction or independent host attestation. The unkeyed chain has no trusted external head anchor, so complete valid-tail deletion and a full recomputed replacement remain outside its detection boundary. Unsupported hosts must fail closed when required primitives are unavailable.

Apply runtime artifacts use schema v3 while the planner artifact schema remains v3 and the handoff contract remains v2. Apply schema-v1 and schema-v2 runs are archive-only and must not be validated, resumed, replaced, trusted-verified, finalized, or migrated by synthesizing missing receipts. The current unreleased v3 contract also requires `event_chain_version: 1`; pre-chain v3 development snapshots are archive-only and must not be resumed or appended. Prepare a new v3 run instead.

`make check` duration is host-dependent and the full Apply regression suite can take tens of minutes. Do not wrap the complete gate in a 45-second timeout. Validator CLI smoke tests retain their focused per-fixture timeout, and a test that exceeds its declared timeout or stops making progress is a release blocker. CI runs both the dependency-free gate and the pinned development-only Draft 2020-12 schema parity gate on Python 3.12 and 3.13 with `actions/setup-python`.

Keep the language contract stable: required Planner-docs headings stay English for validator stability, while body content may use another language only when the user explicitly asks. If a future release adds language selection, document and test a `PLANNER_DOC_LANGUAGE` or equivalent intake-level setting before changing prompt behavior.

If a real key is exposed in chat, logs, docs, examples, or commits, treat it as compromised and rotate it outside the repository before release. Validation output must identify only the file, line, and pattern name; it must not print the matched secret value.

When run inside an exact Git checkout root, `make check` uses `git ls-files` for tracked-file secret hygiene and `git archive` for archive hygiene. A tree that is not the exact Git root must contain `PACKAGE-MANIFEST.json`; missing-manifest package copies fail closed. The validator verifies that manifest against the exact packaged file set and SHA-256 digests, ignoring only known regenerated runtime-cache files while still rejecting symlinks or special files inside those caches, then falls back to clearly labeled filesystem checks: package secret hygiene and package path hygiene. The package fallback is useful for validating shared archives, but it does not claim tracked-file or `git archive` coverage.

Use separate validation tiers when diagnosing portability or release blockers:

```bash
make check-fast
make check-behavior
make check-release
```

`check-fast` skips behavior smokes while keeping unit/content/schema and fixture checks. `check-behavior` runs the Apply lifecycle, downstream Goal/Apply dry run, and prompt-size metric gates. `check-release` runs the normal, schema, and public-privacy gates, creates a strict tracked-only release zip only in a temporary directory, verifies the ZIP manifest before extraction, extracts it without Git metadata, and runs bounded package validation including a second manifest check. It never overwrites a repository-root historical zip.

`make export-sanitized` is the strict release export target. The root itself must be a Git checkout; it requires a clean worktree, exact dated plugin-version heading in `CHANGELOG.md`, matching `v<version>` tag at `HEAD`, and `HEAD == origin/main` when that ref exists. `PACKAGE-MANIFEST.json` records the explicit export mode, payload-derived Git/changelog/tag provenance, clean/tracked-only state, and schema-v2 entries whose path, SHA-256, and normalized `0644`/`0755` mode are covered by the tree digest. `make export-sanitized-worktree` is an explicitly non-release pre-commit snapshot that may include scanned untracked files. `make export-sanitized-source-package` is the explicit non-release filesystem mode for Gitless, extracted, or copied trees and always records `tracked_only: false`; available Git provenance is recorded honestly but never upgrades it into a release claim. The exporter enforces bounded file-count and byte limits and portable manifest paths. It keeps the verified, `fsync`ed temporary inode open through atomic replace, reopens and verifies the destination, rechecks mutable Git evidence immediately before publication, and restores an identity-pinned same-directory backup after publication failure. A backup is deliberately retained if automatic restoration cannot be completed safely. Run `scripts/verify_package_manifest.py --zip <package>` before extraction and `--root <extracted-root>` afterwards. The verifier rejects non-canonical, traversal, symlink, duplicate, case/Unicode-colliding, file/ancestor-conflicting, unsafe-mode, standalone-bytecode, and oversized inputs. ZIP and manifest ancestor checks are linear; extracted verification uses no-follow descriptor traversal, compares each hash-open identity to the first inventory, and repeats the inventory before success. The manifest is an unkeyed consistency record, not a publisher signature, trusted timestamp, or host attestation.

`make check-public-privacy` runs `scripts/check_public_privacy.py` over public release-facing docs and evidence. It rejects local user paths, attachment paths, UUID-like attachment identifiers, and live Codex agent/thread IDs. Keep raw live runtime logs outside public docs unless they are intentionally redacted and independently reviewable.

When validating an extracted package or copied tree that is not the exact Git root, `scripts/validate.sh` requires and verifies `PACKAGE-MANIFEST.json` before falling back to filesystem package hygiene. Use `make export-sanitized-source-package` rather than an unmanifested directory copy. Set both `CODEXQB_VALIDATE_SKIP_UNITTESTS=1` and `CODEXQB_VALIDATE_SKIP_BEHAVIOR_SMOKE=1` only for this package fallback; otherwise behavior smokes remain part of the normal release gate.

## Optional Codex Validator Checks

The Codex skill/plugin validator scripts may require PyYAML in the active Python environment. Use them when available, but do not make them the only release gate.

```bash
CODEX_SKILL_VALIDATOR="${CODEX_SKILL_VALIDATOR:-$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py}"
CODEX_PLUGIN_VALIDATOR="${CODEX_PLUGIN_VALIDATOR:-$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py}"

python3 "$CODEX_SKILL_VALIDATOR" plugins/codexqb/skills/codexqb
python3 "$CODEX_PLUGIN_VALIDATOR" plugins/codexqb
```

To validate an optional local global skill copy:

```bash
CODEXQB_GLOBAL_SKILL="${CODEXQB_GLOBAL_SKILL:-$HOME/.codex/skills/codexqb}"
python3 "$CODEX_SKILL_VALIDATOR" "$CODEXQB_GLOBAL_SKILL"
```

## Validate Planner Docs

The skill ships a read-only validator for generated `Planner-docs/` outputs. From a CodexQB repository checkout, run:

```bash
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step1
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode autopsy --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step2 --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step3-preflight --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step3 --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step4 --strict
```

Mode contract:

- `step3-preflight` validates Step 2 artifacts before `Sub-Planing-Audit.md` exists.
- `step3` requires `Planner-docs/Sub-Planing-Audit.md` and validates post-audit structure.
- `step4` enforces semantic readiness rows, finding status consistency, NO_ACTION_REQUIRED, and strict Ledger v3 execution gates.
- Exit codes are stable: `0` passed, `1` document validation failed, `2` invocation/configuration/I/O error.
- Output includes `validation_status=...`, `validation_mode=...`, `error_count=...`, and `warning_count=...`.

When running through an installed plugin, use the bundled validator path exposed by the active skill. If that path is unavailable, perform equivalent all-file validation and report the fallback clearly.

When changing the validator, test at least:

- a valid Step 2 fixture;
- a missing-section fixture;
- a normal filename containing `sk-` such as `task-spec.yaml`;
- a fake long secret token that should be detected;
- roadmap table extraction with historical phase references such as `Faz 0B-10` or `Phase 11`;
- optional `Autopsy.md`, `Project-Ontology.md`, and `Planing-Ledger.md` validation when present, and no failure when they are absent;
- optional `Project-Comprehension.md` validation when present, including evidence types, confidence values, architecture statuses, trace anchors, and open hypothesis probes;
- fenced code block heading false positives and duplicate real headings;
- Ledger v3 headings with split planning/execution status and split planning/implementation evidence, while v2 and legacy v1 ledgers remain accepted outside strict Step 4 execution with compatibility warnings;
- Step 2 Planning Scope Manifest validation, including active/deferred phase consistency and `wave` vs explicit `full` planning behavior;
- semantic Step 2 gates for implementation paths, exact validation commands, behavioral acceptance criteria, parent acceptance signals, dependency labels, concrete outputs, and domain-specific risks;
- shared 0.3.0 command safety gates for closed seven-field validation envelopes, root-bound non-symlink cwd checks, deny-only network and Tier-1 probes, canonical no-write pytest/unittest/Ruff profiles, unknown option/field rejection, shell-metacharacter and executable-spoof rejection, sensitive/output path rejection, full planned/evidence envelope binding, risk/security review consistency, and meaningful framework/invariant rows;
- Goal compiler artifacts from `scripts/goal_run.py`, including deterministic spec IDs, unique invocation run IDs, project-specific active sub-plan and READY queue collectors, compiler version metadata, template bundle digests, implementation contract digests, direct non-symlink `Planner-docs/Goal-Runs/<run>/` output boundaries, parent/final-target symlink rejection, explicit-output resume behavior, bundled-validator stage prerequisite blockers, render-time validation, unsafe glob/path overlap rejection, source snapshot digest integrity, and no silent overwrite;
- Goal-run artifacts from `scripts/goal_run.py`, including no-subplans Step 2 `planning_horizon` collection from `Main-Planing.md`, active/deferred phase recommendations, parent acceptance signals, planning budget estimates, framework/invariant requirement flags, structured contract summaries, `implementation_contract_digest`, `validation_command_ids`, and contract-derived Step 4 work steps for parent signals, implementation paths, validation IDs, security review, dependency state, and outputs;
- Apply-run artifacts from `scripts/apply_run.py`, including deterministic apply spec IDs, unique invocation run IDs, strict Step 4 validator gating before prepare writes action artifacts, audit-derived task briefs, Step 4 readiness summaries, registered/HMAC-verified direct-run mutation boundaries, parent/task/final-target symlink rejection, run-directory `flock` serialization, full-file atomic Events replacement with unique contiguous sequences and a canonical previous-hash/hash chain, `workspace_baseline` hashes for branch/base commit and canonical no-exec Git plumbing evidence covering HEAD/index state, staged changes, unstaged tracked content, untracked inventory, and non-Git file inventory when applicable (historical status/diff field names carry versioned canonical evidence digests), descriptor/root-and-mount-bound two-pass full-worktree inventory with a shared 100,000-path, 64 MiB-per-file, 512 MiB aggregate-read, and 60-second deadline contract whose limit/identity/mount failures fail closed, required posture fields (`worktree_path`, `base_branch`, `working_branch`, `dirty_state`), default blocking for non-Git action runs unless `--allow-non-git-unsafe` records `workspace_mode: non_git_unsafe` and `user_approval: true`, default blocking for dirty/protected current Git worktrees unless `--allow-unverified-git-worktree` records explicit approval, `no_action` mode, default `commit_policy: none`, unsafe command rejection, no-action queue rejection, task ID traversal rejection, transition/reconcile CLI event log enforcement, writer-lock consistency, workspace baseline drift detection, external Superpowers readiness/reconcile validation, agent profile drift detection, `validation_command_ids` in tasks and briefs, controller-signed `capture-evidence` live change sets with changed-file hashes, complete `run-validation` receipts for every planned command, phase-aware `dispatch`/`record-agent`, signed `publish-review` receipts in spec/quality/security-if-required/final order, latest-published-event enforcement per validation ID and review phase, receipt tamper/context/reuse/staleness rejection, diff invalidation, direct-mode trusted-verification refusal, no silent progress overwrite, and fail-closed finalization;
- normalized duplicate ratio and uniform sub-plan count anomaly checks;
- Step 4 readiness gating for missing audit, headings-only audit, `BLOCKED`, `PASS`, `PASS_WITH_WARNINGS`, NO_ACTION_REQUIRED, unsafe readiness paths, duplicate conflicting rows, and prose such as `no P0/P1 findings`.

Run the tracked validator test suite:

```bash
python3 -m unittest discover -s tests -v
```

## Validate Skill Prompt Content

The test suite also checks that the Step 1 repo-aware intake contract remains wired into the skill:

```bash
python3 -m unittest discover -s tests -v
```

When changing Step 1 behavior, verify that:

- `SKILL.md` references `references/repo-aware-intake.md`;
- the intake reference still asks only the four stable fields;
- `SKILL.md` references `references/Autopsy-Planner.md` for Step 1.5;
- `Second-Planner.md` reads `Planner-docs/Autopsy.md`, `Planner-docs/Project-Ontology.md`, and `Planner-docs/Planing-Ledger.md` as optional supporting sources;
- Step 1.5, Step 2, Step 3, and Step 4 references mention `Planner-docs/Project-Comprehension.md` and `references/project-comprehension-methods.md`;
- `First-Planner.md` still accepts the same four required placeholders;
- `SKILL.md` references vibecoding, subagent, planning ledger, project ontology, assessment/budget, and engineering-principles guidance;
- prompts do not contain `rg -n "sk-` scans that could print secret-bearing lines.

## Goal Mode and Replanning Memory Checks

When changing Goal handoff behavior, verify that Step 2, Step 3, and Step 4 prompts define:

- the desired outcome;
- unchanged file boundaries;
- validation checkpoints;
- stop gates;
- token/context risk guidance;
- subagent usage rules;
- ledger update expectations for Step 4.
- comprehension evidence expectations, especially that tentative claims must be verified before implementation.

When changing replanning behavior, verify that `Planing-Ledger.md`, `Project-Ontology.md`, and `Project-Comprehension.md` are read as supporting evidence and never treated as stronger than current repository state or explicit user intent.

## Fixture Corpus Checks

CodexQB includes lightweight deterministic fixture corpus checks. They do not run live `codex exec`; they keep the fixture repos and expected signals stable for future live skill evals.

```bash
python3 evals/run_fixture_corpus_checks.py
```

`make check` runs this command. `python3 evals/run_fixture_checks.py` remains as a compatibility wrapper and should return the same exit code. Optional live skill evals may be added later with `codex exec --json` and structured rubric output, but they must not become required for dependency-free CI until the runtime is stable in CI.

CodexQB also tracks deterministic Goal/Apply prompt-size estimates:

```bash
python3 evals/run_goal_apply_metric_checks.py
```

This emits approximate token counts for the static Step 4 handoff, dynamic direct and `subagent_serial` Goal prompts, direct Apply briefs, and subagent dispatch messages. These estimates are for regression tracking only; they are not exact model billing. Goal and Apply artifacts include a structured `budget_contract`; runtime token usage stays `not_observed` unless an actual runtime usage source is available.

CodexQB also keeps a repeatable downstream artifact dry run:

```bash
python3 evals/run_downstream_goal_apply_dry_run.py
```

This builds a disposable git-backed project with small source and test files, runs strict Step 2, Step 3 preflight, Step 3, and Step 4 validation, compiles Goal previews, prepares a `subagent_serial` Apply run, captures the live change set, executes planned validations, and exercises the ordered review-receipt protocol. It does not call live Codex tools or prove real multi-agent model execution; a live E2E run is required for that claim.

## Optional Local Skill Copy Parity

If you maintain a local global skill copy, sync without generated Python caches and compare it with the repo-bundled skill:

```bash
CODEXQB_GLOBAL_SKILL="${CODEXQB_GLOBAL_SKILL:-$HOME/.codex/skills/codexqb}"
rsync -a --delete --exclude '__pycache__/' --exclude '*.pyc' plugins/codexqb/skills/codexqb/ "$CODEXQB_GLOBAL_SKILL/"
diff -ru -x __pycache__ plugins/codexqb/skills/codexqb "$CODEXQB_GLOBAL_SKILL"
```

This is a local-only workflow check. It is not required for CI or repository marketplace releases.

## Check For Stale Invocation Names

CodexQB should use `$codexqb` as the skill invocation name and must retain `policy.allow_implicit_invocation: false`; ordinary Codex requests must not activate the workflow. The default release check includes this scan:

```bash
make check
```

No public-facing stale references should remain.

## Sanitized Export

Do not create release zips with Finder or generic directory compression, because ignored files such as `.git/`, `__pycache__/`, `.env`, `artifacts/`, `logs/`, or `tmp/` can be included.

Use the sanitized export target:

```bash
make export-sanitized
```

This writes `CodexQB-sanitized.zip` with `scripts/export_sanitized.py` only after the strict Git/changelog/tag contract passes. Use `make export-sanitized-worktree` only for an explicit non-release pre-commit snapshot, or `make export-sanitized-source-package` for an explicit non-release filesystem package. Export candidates are rejected when they are symlinks, resolve outside the repository, match blocked local/runtime paths such as `.git/`, `.codexqb/`, caches, local env files, runtime folders, local zips, or blocked key/certificate suffixes, or contain a length-bounded secret pattern. Verify generated ZIPs and extracted roots with `scripts/verify_package_manifest.py`; the manifest hashes detect inconsistency but do not authenticate the publisher. Never infer release truth from the filename alone: an existing `CodexQB-sanitized.zip` may be a stale worktree snapshot. Only a freshly passing strict export whose manifest reports dated changelog and tag-at-HEAD provenance is release-eligible.

The default `make check` gate validates tracked archive contents in Git checkouts and fails if forbidden tracked paths such as `.git/`, `__pycache__/`, `.env`, `artifacts/`, `logs/`, `tmp/`, `__MACOSX/`, `.pyc`, `.pem`, `.key`, or `.local` files would be included. In extracted packages, `make check` performs equivalent package-content hygiene where possible and labels the result as package validation. It also runs the apply-run behavior smoke so the public `prepare`/`transition`/`capture-evidence`/`run-validation`/phase-aware `dispatch` and `record-agent`/`publish-review`/`validate`/`finalize` lifecycle is exercised through subprocesses before release. Keep an explicit negative test proving direct mode cannot independently issue reviewer receipts, reach trusted `VERIFIED`, or finalize.

## Release Flow

1. Update `plugins/codexqb/.codex-plugin/plugin.json`.
2. Update `plugins/codexqb/skills/codexqb/SKILL.md` and references as needed.
3. Update `plugins/codexqb/skills/codexqb/references/repo-aware-intake.md` if Step 1 intake behavior changes.
4. Update `plugins/codexqb/skills/codexqb/references/Autopsy-Planner.md` if Step 1.5 autopsy behavior changes.
5. Update `plugins/codexqb/skills/codexqb/references/vibecoding-principles.md`, `subagent-playbook.md`, `planning-ledger.md`, `project-ontology.md`, `assessment-and-budget.md`, or `engineering-principles.md` when planning behavior changes.
6. Update `plugins/codexqb/skills/codexqb/references/Fourth-Planner.md` if implementation handoff behavior changes.
7. Update `plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py` if planner structure or readiness gates change.
8. Update `plugins/codexqb/skills/codexqb/scripts/goal_run.py`, `apply_run.py`, or `references/apply-run-schema.json` if Goal preview or Step 4 apply artifacts change.
9. Run `make check`.
10. Optionally run the Codex skill/plugin validator scripts if their Python dependencies are available.
11. Optionally sync and compare the local global skill copy for manual testing only when the active task permits global cache changes.
12. Commit with a focused message only when the active task permits commits.
13. Push to `main` only when the active task permits pushing.
14. Reinstall the plugin in Codex:

   ```bash
   codex plugin add codexqb@codexqb
   ```

15. If Codex reports stale marketplace metadata, refresh the marketplace and retry:

   ```bash
   codex plugin marketplace upgrade
   codex plugin add codexqb@codexqb
   ```

16. Start a new Codex thread before testing.

## Public Directory Status

CodexQB currently uses repository marketplace distribution. Public directory or workspace sharing distribution can be revisited separately; this release focuses on repo-marketplace installation and local/team validation.

## Contribution Guidelines

- Keep the skill concise.
- Keep long planner prompts in `references/`.
- Preserve the `Planner-docs/*Planing*` filenames required by the bundled prompts.
- Do not add MCP servers, apps, hooks, or assets unless the plugin manifest and validator are updated accordingly.
- Do not put secrets or environment-specific credentials into docs, planner prompts, or examples.
