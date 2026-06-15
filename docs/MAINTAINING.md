# Maintaining CodexQB

This document covers validation and release maintenance for CodexQB.

## Dependency-Free Repo Check

Run the default repository validation before every release:

```bash
make check
```

This checks JSON manifests, required package files, `agents/openai.yaml` semantic fields, stale invocation names, vibecoding/subagent/ledger/ontology prompt wiring, tracked-file secret hygiene, archive hygiene, and the Python unit test suite. It intentionally uses only shell and Python standard-library commands so CI does not depend on local Codex validator dependencies.

On a normal local development machine, `make check` is expected to complete well under 30 seconds. Validator CLI smoke tests have a 30-second timeout, and any timeout or hang is a release blocker. CI pins Python 3.12 with `actions/setup-python`.

If a real key is exposed in chat, logs, docs, examples, or commits, treat it as compromised and rotate it outside the repository before release. Validation output must identify only the file, line, and pattern name; it must not print the matched secret value.

When run inside a Git checkout, `make check` uses `git ls-files` for tracked-file secret hygiene and `git archive` for archive hygiene. When run from an extracted source package without `.git/`, it falls back to clearly labeled filesystem checks: package secret hygiene and package path hygiene. The package fallback is useful for validating shared archives, but it does not claim tracked-file or `git archive` coverage.

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
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step3 --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step4
```

When running through an installed plugin, use the bundled validator path exposed by the active skill. If that path is unavailable, perform equivalent all-file validation and report the fallback clearly.

When changing the validator, test at least:

- a valid Step 2 fixture;
- a missing-section fixture;
- a normal filename containing `sk-` such as `task-spec.yaml`;
- a fake long secret token that should be detected;
- roadmap table extraction with historical phase references such as `Faz 0B-10` or `Phase 11`;
- optional `Autopsy.md`, `Project-Ontology.md`, and `Planing-Ledger.md` validation when present, and no failure when they are absent;
- Step 4 readiness gating for missing audit, `BLOCKED`, `PASS`, `PASS_WITH_WARNINGS`, and prose such as `no P0/P1 findings`.

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

When changing replanning behavior, verify that `Planing-Ledger.md` and `Project-Ontology.md` are read as supporting evidence and never treated as stronger than current repository state or explicit user intent.

## Optional Local Skill Copy Parity

If you maintain a local global skill copy, compare it with the repo-bundled skill after syncing:

```bash
CODEXQB_GLOBAL_SKILL="${CODEXQB_GLOBAL_SKILL:-$HOME/.codex/skills/codexqb}"
diff -ru plugins/codexqb/skills/codexqb "$CODEXQB_GLOBAL_SKILL"
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

Use the tracked-file export target:

```bash
make export-sanitized
```

This writes `CodexQB-sanitized.zip` with `git archive`.

The default `make check` gate validates tracked archive contents in Git checkouts and fails if forbidden tracked paths such as `.git/`, `__pycache__/`, `.env`, `artifacts/`, `logs/`, `tmp/`, `__MACOSX/`, `.pyc`, `.pem`, `.key`, or `.local` files would be included. In extracted packages, `make check` performs equivalent package-content hygiene where possible and labels the result as package validation.

## Release Flow

1. Update `plugins/codexqb/.codex-plugin/plugin.json`.
2. Update `plugins/codexqb/skills/codexqb/SKILL.md` and references as needed.
3. Update `plugins/codexqb/skills/codexqb/references/repo-aware-intake.md` if Step 1 intake behavior changes.
4. Update `plugins/codexqb/skills/codexqb/references/Autopsy-Planner.md` if Step 1.5 autopsy behavior changes.
5. Update `plugins/codexqb/skills/codexqb/references/vibecoding-principles.md`, `subagent-playbook.md`, `planning-ledger.md`, `project-ontology.md`, `assessment-and-budget.md`, or `engineering-principles.md` when planning behavior changes.
6. Update `plugins/codexqb/skills/codexqb/references/Fourth-Planner.md` if implementation handoff behavior changes.
7. Update `plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py` if planner structure or readiness gates change.
8. Run `make check`.
9. Optionally run the Codex skill/plugin validator scripts if their Python dependencies are available.
10. Optionally sync and compare the local global skill copy for manual testing.
11. Commit with a focused message.
12. Push to `main`.
13. Reinstall the plugin in Codex:

   ```bash
   codex plugin add codexqb@codexqb
   ```

14. If Codex reports stale marketplace metadata, refresh the marketplace and retry:

   ```bash
   codex plugin marketplace upgrade
   codex plugin add codexqb@codexqb
   ```

15. Start a new Codex thread before testing.

## Public Directory Status

CodexQB currently uses repository marketplace distribution. Public directory or workspace sharing distribution can be revisited separately; this release focuses on repo-marketplace installation and local/team validation.

## Contribution Guidelines

- Keep the skill concise.
- Keep long planner prompts in `references/`.
- Preserve the `Planner-docs/*Planing*` filenames required by the bundled prompts.
- Do not add MCP servers, apps, hooks, or assets unless the plugin manifest and validator are updated accordingly.
- Do not put secrets or environment-specific credentials into docs, planner prompts, or examples.
