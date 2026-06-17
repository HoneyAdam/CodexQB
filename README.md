# CodexQB

[![validate](https://github.com/alicankiraz1/CodexQB/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/alicankiraz1/CodexQB/actions/workflows/validate.yml)

**Vibecoding-first repo planning for Codex.** CodexQB turns a project repository into a durable planning package: main plan, existing-project autopsy, project ontology, planning ledger, phase sub-plans, QA audit, and a gated implementation handoff.

![CodexQB workflow and release validation](docs/assets/codexqb-workflow.png)

CodexQB is a Codex plugin that installs the `$codexqb` skill. It is built for software, AI, infrastructure, security, and automation projects where planning needs to be evidence-backed, reviewable, adaptive, and ready for small verified execution slices.

The current release is hardened for repository marketplace distribution: dependency-free `make check`, GitHub Actions validation, and tracked-file sanitized exports through `make export-sanitized`.

## Why CodexQB

- **Repo-aware intake:** CodexQB inspects the current repository before asking questions, then proposes evidence-backed defaults for project name, intent, target end state, constraints, autonomy/review cadence, and token/context budget assumptions.
- **Durable planning docs:** Output is written under `Planner-docs/` so long planning work, ontology, and implementation history survive context changes and can be reviewed like normal project documentation.
- **Project Autopsy + Ontology:** Existing projects get a focused `Autopsy.md` report and may get `Project-Ontology.md` to capture vocabulary, entities, boundaries, workflows, integrations, and invariants.
- **Full phase decomposition:** The main plan can be expanded into ordered phase folders and detailed sub-plan files, using Autopsy feedback when available.
- **QA before implementation:** The audit step checks coverage, naming, ordering, section structure, readiness, ontology consistency, planning-history continuity, security/governance, vibecoding slice quality, and implementation preparedness.
- **Gated execution handoff:** CodexQB does not implement product changes itself. It prints a separate Goal mode prompt only when the audit says implementation can begin, then guides that run through the READY queue in small verified slices and asks Step 4 to append concise implementation summaries to `Planing-Ledger.md`.


## Vibecoding-First Behavior

CodexQB is intentionally vibecoding-first: it keeps the target vision clear, reads the repository's real shape, avoids fake certainty, and plans the next useful verified moves instead of freezing unnecessary implementation detail too early. Generated plans should favor small reversible slices, fast validation signals, explicit deferrals, and human-review checkpoints. Vibecoding never relaxes safety, secret handling, approval, validation, or file-boundary rules.

When a project is large or ambiguous, CodexQB may recommend or explicitly request bounded subagents for read-only repo exploration, readiness/security review, ontology mapping, phase drafting, Step 3 audit, or Step 4 implementation/review separation. The parent CodexQB agent remains responsible for final artifact writes.

## Workflow

| Step | What CodexQB Does | Output |
| --- | --- | --- |
| 1. Repo Scan + Main Plan | Reads the repository, asks four enriched intake questions, and creates the master plan. | `Planner-docs/Main-Planing.md` |
| 1.5 Autopsy + Ontology | For existing projects, audits current project structure and may capture project vocabulary, entities, workflows, boundaries, and invariants. | `Planner-docs/Autopsy.md`, optional `Planner-docs/Project-Ontology.md` |
| 2. Phase Sub-Plans | Expands every main phase into detailed implementation-ready sub-plans. | `Planner-docs/Sub-Planing-Index.md`, `Planner-docs/Faz-*-Plans/*.md` |
| 3. QA Audit | Audits coverage, structure, quality, readiness, and governance without repairing files. | `Planner-docs/Sub-Planing-Audit.md` |
| 4. Gated Handoff | Prints a copy-ready implementation Goal prompt when Step 3 passes and tracks implementation summaries through the optional ledger. | Text-only Goal mode prompt, optional `Planner-docs/Planing-Ledger.md` updates |

Step 1 runs in the current Codex thread. Steps 2, 3, and 4 are intentionally handed off as text-only Goal mode prompts so the user stays in control of long-running work. The Goal handoffs include outcome, unchanged boundaries, validation checkpoints, stop gates, token/context risk, and subagent guidance.

## Quick Start

Add this repository as a Codex plugin marketplace:

```bash
codex plugin marketplace add alicankiraz1/CodexQB --ref main
codex plugin add codexqb@codexqb
```

If the repository is private, your Codex/GitHub environment must have access to `alicankiraz1/CodexQB`.

Start a new Codex thread in the project you want to plan, then ask:

```text
Use $codexqb to inspect this repo and plan this project.
```

CodexQB will inspect the repository briefly, then ask for:

- `PROJECT_NAME`
- `PROJECT_INTENT`
- `TARGET_END_STATE`
- `KNOWN_CONSTRAINTS`

CodexQB asks intake questions in the user's language when practical. Generated Planner-docs artifacts are English by default unless the user explicitly requests another content language. Required document headings remain English for validator stability. Intake should also surface desired autonomy, human review cadence, and any token/usage budget so CodexQB can describe rough Goal-mode cost/context risk without pretending to know exact spend.

Future language-mode work should add an explicit `PLANNER_DOC_LANGUAGE` or intake-level language setting. Until then, headings stay English and only body content should vary when the user requests another language.

For existing repositories, the questions include repo-derived suggestions. For empty or minimal repositories, CodexQB falls back to concise generic questions and marks repository evidence as limited.

## Generated Artifacts

CodexQB writes planning artifacts under the target project's `Planner-docs/` directory:

```text
Planner-docs/
  Main-Planing.md
  Autopsy.md
  Project-Ontology.md
  Planing-Ledger.md
  Sub-Planing-Index.md
  Sub-Planing-Audit.md
  Faz-0-Plans/
    Faz0.1-*.md
  Faz-1-Plans/
    Faz1.1-*.md
```

The `Planing` spelling is intentionally preserved because the bundled planner prompts and validators use these exact filenames.

## Validator

The skill includes a read-only validator:

```bash
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode autopsy --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step2 --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step3 --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step4
```

These commands are for manual validation from a CodexQB repository checkout. When running through an installed plugin, CodexQB should use the bundled validator path exposed by the active skill; if that path is unavailable, it should perform equivalent all-file validation and report the fallback clearly.

The validator checks required sections, optional ontology/ledger headings, phase folders, filename conventions, index references, duplicate numbering, unindexed files, length-bounded secret patterns, and Step 4 readiness. P0/P1 audit findings block the implementation handoff.

Repository maintainers can run the dependency-free repo check with:

```bash
make check
```

`make check` validates plugin JSON, required package files, `agents/openai.yaml` semantic fields, stale invocation names, tracked-file secret hygiene, archive hygiene, and the unit test suite without requiring PyYAML or local Codex validator dependencies.

On a normal local development machine, `make check` is expected to finish well under 30 seconds. A timeout or hang in validator tests is a release blocker, not a warning to ignore.

## Release Validation

Run this before sharing, committing, or pushing release changes:

```bash
make check
```

The repository also includes GitHub Actions at `.github/workflows/validate.yml`, which runs the same check on pushes to `main` and pull requests.

For sanitized zip sharing, use the tracked-file archive target instead of Finder or generic directory compression:

```bash
make export-sanitized
```

This creates `CodexQB-sanitized.zip` from `git archive`, excluding `.git/`, ignored Python caches, local env files, runtime folders, and other untracked local clutter. The default validation gate also checks that forbidden tracked archive entries are not present.

## Safety Model

CodexQB is planning-first. Steps 1-3 should not:

- implement product features;
- refactor source code;
- install dependencies;
- run destructive commands;
- commit, push, deploy, or open pull requests;
- write secrets, tokens, credentials, private keys, or local sensitive environment values into planning files.

Generated plans should distinguish documentation readiness, local readiness, live readiness, production readiness, and operational evidence.

## Repository Layout

```text
.agents/plugins/marketplace.json
.github/workflows/validate.yml
Makefile
plugins/codexqb/
  .codex-plugin/plugin.json
  skills/codexqb/
    SKILL.md
    agents/openai.yaml
    scripts/validate_planner_docs.py
    references/
      First-Planner.md
      Autopsy-Planner.md
      Second-Planner.md
      Third-Planner.md
      Fourth-Planner.md
      repo-aware-intake.md
      workflow-quality.md
      vibecoding-principles.md
      subagent-playbook.md
      planning-ledger.md
      project-ontology.md
      assessment-and-budget.md
      engineering-principles.md
docs/
  INSTALLATION.md
  MAINTAINING.md
  USAGE.md
  assets/codexqb-workflow.png
scripts/
  validate.sh
tests/
LICENSE
README.md
```

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Usage](docs/USAGE.md)
- [Maintaining CodexQB](docs/MAINTAINING.md)

## Public Plugin Directory Status

CodexQB currently uses repository marketplace distribution. Public directory or workspace sharing distribution can be revisited separately; this release focuses on repo-marketplace installation and local/team validation.

## License

MIT. See [LICENSE](LICENSE).
