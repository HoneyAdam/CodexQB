# Maintaining CodexQB

This document covers validation and release maintenance for CodexQB.

Current release contracts:

```text
plugin_version: 0.3.0
artifact_schema_version: 3
handoff_contract_version: 2
goal_run_schema_version: 1
apply_run_schema_version: 1
```

## Dependency-Free Repo Check

Run the default repository validation before every release:

```bash
make check
```

This checks JSON manifests, required package files, `agents/openai.yaml` semantic fields, stale invocation names, vibecoding/subagent/ledger/ontology/comprehension prompt wiring, deterministic fixture corpus inputs, downstream Step 2 -> Step 4 Goal/Apply dry-run coverage, Goal/Apply prompt-size metric checks, tracked-file secret hygiene, archive hygiene, sanitized zip path/content hygiene, and the Python unit test suite. It intentionally uses only shell and Python standard-library commands so CI does not depend on local Codex validator dependencies.

On a normal local development machine, `make check` is expected to complete under 45 seconds. Validator CLI smoke tests have a 30-second timeout for focused fixture runs, and any timeout or hang is a release blocker. CI pins Python 3.12 with `actions/setup-python`.

Keep the language contract stable: required Planner-docs headings stay English for validator stability, while body content may use another language only when the user explicitly asks. If a future release adds language selection, document and test a `PLANNER_DOC_LANGUAGE` or equivalent intake-level setting before changing prompt behavior.

If a real key is exposed in chat, logs, docs, examples, or commits, treat it as compromised and rotate it outside the repository before release. Validation output must identify only the file, line, and pattern name; it must not print the matched secret value.

When run inside a Git checkout, `make check` uses `git ls-files` for tracked-file secret hygiene and `git archive` for archive hygiene. When run from an extracted source package without `.git/`, it falls back to clearly labeled filesystem checks: package secret hygiene and package path hygiene. The package fallback is useful for validating shared archives, but it does not claim tracked-file or `git archive` coverage.

Use separate validation tiers when diagnosing portability or release blockers:

```bash
make check-fast
make check-behavior
make check-release
```

`check-fast` skips behavior smokes while keeping unit/content/schema and fixture checks. `check-behavior` runs the Apply lifecycle, downstream Goal/Apply dry run, and prompt-size metric gates. `check-release` runs the normal gate, creates a strict tracked-only release zip with `PACKAGE-MANIFEST.json`, extracts it, and validates the package copy.

`make export-sanitized` is the release export target. It requires a clean Git worktree and fails when `HEAD` differs from `origin/main` if that ref exists. It also records `plugin_version`, `git_commit`, `git_branch`, `working_tree_clean`, `head_matches_origin_main`, `file_count`, and `tree_sha256` in `PACKAGE-MANIFEST.json`. Use `make export-sanitized-worktree` only for explicit pre-commit worktree package checks that intentionally include untracked files.

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
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step4
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
- shared 0.3.0 command safety gates for structured `argv` validation commands, shell-metacharacter rejection, arbitrary `python -c` rejection, unchecked shell-script rejection, unsafe path argument rejection, mutation/deploy intent rejection, safe target/script allowlists, risk/security review consistency, and meaningful framework/invariant rows;
- Goal compiler artifacts from `scripts/goal_run.py`, including deterministic spec IDs, unique invocation run IDs, project-specific active sub-plan and READY queue collectors, repo-contained output directories, explicit-output resume behavior, bundled-validator stage prerequisite blockers, render-time validation, unsafe glob/path overlap rejection, source snapshot digest integrity, and no silent overwrite;
- Goal-run artifacts from `scripts/goal_run.py`, including no-subplans Step 2 `planning_horizon` collection from `Main-Planing.md`, active/deferred phase recommendations, parent acceptance signals, planning budget estimates, framework/invariant requirement flags, structured contract summaries, `validation_command_ids`, and contract-derived Step 4 work steps for parent signals, implementation paths, validation IDs, security review, dependency state, and outputs;
- Apply-run artifacts from `scripts/apply_run.py`, including deterministic apply spec IDs, unique invocation run IDs, strict Step 4 validator gating before prepare writes action artifacts, audit-derived task briefs, Step 4 readiness summaries, `workspace_baseline` hashes for branch/base commit, Git status, staged diff, unstaged diff, untracked inventory, and non-Git file inventory when applicable, required posture fields (`worktree_path`, `base_branch`, `working_branch`, `dirty_state`), default blocking for non-Git action runs unless `--allow-non-git-unsafe` records `workspace_mode: non_git_unsafe` and `user_approval: true`, default blocking for dirty/protected current Git worktrees unless `--allow-unverified-git-worktree` records explicit approval, `no_action` mode, default `commit_policy: none`, unsafe command rejection, no-action queue rejection, task ID traversal rejection, transition/reconcile CLI event log enforcement, writer-lock consistency, workspace baseline drift detection, external Superpowers readiness/reconcile validation, agent profile drift detection, `validation_command_ids` in tasks and briefs, VERIFIED evidence requirements, final review validation evidence, no silent progress overwrite, and spec-before-quality review order;
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

This emits approximate token counts for the static Step 4 handoff, dynamic direct and `subagent_serial` Goal prompts, direct Apply briefs, and subagent dispatch messages. These estimates are for regression tracking only; they are not exact model billing.

CodexQB also keeps a repeatable downstream artifact dry run:

```bash
python3 evals/run_downstream_goal_apply_dry_run.py
```

This builds a disposable git-backed project with small source and test files, runs strict Step 2, Step 3 preflight, Step 3, and Step 4 validation, compiles Goal previews, prepares a `subagent_serial` Apply run, records artifact-level agent lifecycle evidence, and finalizes the run. It does not call live Codex tools or prove real multi-agent model execution.

## Optional Local Skill Copy Parity

If you maintain a local global skill copy, sync without generated Python caches and compare it with the repo-bundled skill:

```bash
CODEXQB_GLOBAL_SKILL="${CODEXQB_GLOBAL_SKILL:-$HOME/.codex/skills/codexqb}"
rsync -a --delete --exclude '__pycache__/' --exclude '*.pyc' plugins/codexqb/skills/codexqb/ "$CODEXQB_GLOBAL_SKILL/"
diff -ru -x __pycache__ plugins/codexqb/skills/codexqb "$CODEXQB_GLOBAL_SKILL"
```

This is a local-only workflow check. It is not required for CI or repository marketplace releases.

## Check For Stale Invocation Names

CodexQB should use `$codexqb` as the skill invocation name. The default release check includes this scan:

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

This writes `CodexQB-sanitized.zip` with `scripts/export_sanitized.py`. The script default includes only tracked files. The Makefile target passes `--include-untracked` explicitly so release/package smoke tests can include new pre-commit files after safety checks. Export candidates are rejected when they are symlinks, resolve outside the repository, match blocked local/runtime paths such as `.git/`, `.codexqb/`, caches, local env files, runtime folders, local zips, or blocked key/certificate suffixes, or contain a length-bounded secret pattern.

The default `make check` gate validates tracked archive contents in Git checkouts and fails if forbidden tracked paths such as `.git/`, `__pycache__/`, `.env`, `artifacts/`, `logs/`, `tmp/`, `__MACOSX/`, `.pyc`, `.pem`, `.key`, or `.local` files would be included. In extracted packages, `make check` performs equivalent package-content hygiene where possible and labels the result as package validation. It also runs the apply-run behavior smoke so the public `prepare`/`transition`/`validate`/`finalize` CLI lifecycle is exercised through subprocesses before release.

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
