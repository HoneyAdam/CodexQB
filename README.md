# CodexQB

**Repo-aware planning for Codex.** CodexQB turns a project repository into a durable planning package: main plan, phase sub-plans, QA audit, and a gated implementation handoff.

![CodexQB workflow](docs/assets/codexqb-workflow.png)

CodexQB is a Codex plugin that installs the `$codexqb` skill. It is built for software, AI, infrastructure, security, and automation projects where planning needs to be evidence-backed, reviewable, and ready for step-by-step execution.

## Why CodexQB

- **Repo-aware intake:** CodexQB inspects the current repository before asking questions, then proposes evidence-backed defaults for project name, intent, target end state, and constraints.
- **Durable planning docs:** Output is written under `Planner-docs/` so long planning work survives context changes and can be reviewed like normal project documentation.
- **Full phase decomposition:** The main plan can be expanded into ordered phase folders and detailed sub-plan files.
- **QA before implementation:** The audit step checks coverage, naming, ordering, section structure, readiness, security/governance, and implementation preparedness.
- **Gated execution handoff:** CodexQB does not implement product changes itself. It prints a separate Goal mode prompt only when the audit says implementation can begin.

## Workflow

| Step | What CodexQB Does | Output |
| --- | --- | --- |
| 1. Repo Scan + Main Plan | Reads the repository, asks four enriched intake questions, and creates the master plan. | `Planner-docs/Main-Planing.md` |
| 2. Phase Sub-Plans | Expands every main phase into detailed implementation-ready sub-plans. | `Planner-docs/Sub-Planing-Index.md`, `Planner-docs/Faz-*-Plans/*.md` |
| 3. QA Audit | Audits coverage, structure, quality, readiness, and governance without repairing files. | `Planner-docs/Sub-Planing-Audit.md` |
| 4. Gated Handoff | Prints a copy-ready implementation Goal prompt when Step 3 passes. | Text-only Goal mode prompt |

Step 1 runs in the current Codex thread. Steps 2, 3, and 4 are intentionally handed off as text-only `Hedefi Takip Et` / Goal mode prompts so the user stays in control of long-running work.

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

For existing repositories, the questions include repo-derived suggestions. For empty or minimal repositories, CodexQB falls back to concise generic questions and marks repository evidence as limited.

## Generated Artifacts

CodexQB writes planning artifacts under the target project's `Planner-docs/` directory:

```text
Planner-docs/
  Main-Planing.md
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
python3 ~/.codex/skills/codexqb/scripts/validate_planner_docs.py --root . --mode step2 --strict
python3 ~/.codex/skills/codexqb/scripts/validate_planner_docs.py --root . --mode step3 --strict
python3 ~/.codex/skills/codexqb/scripts/validate_planner_docs.py --root . --mode step4
```

It checks required sections, phase folders, filename conventions, index references, duplicate numbering, unindexed files, length-bounded secret patterns, and Step 4 readiness. P0/P1 audit findings block the implementation handoff.

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
plugins/codexqb/
  .codex-plugin/plugin.json
  skills/codexqb/
    SKILL.md
    agents/openai.yaml
    scripts/validate_planner_docs.py
    references/
      First-Planner.md
      Second-Planner.md
      Third-Planner.md
      Fourth-Planner.md
      repo-aware-intake.md
      workflow-quality.md
docs/
  INSTALLATION.md
  MAINTAINING.md
  USAGE.md
  assets/codexqb-workflow.png
tests/
LICENSE
README.md
```

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Usage](docs/USAGE.md)
- [Maintaining CodexQB](docs/MAINTAINING.md)

## Public Plugin Directory Status

CodexQB is packaged as a Codex plugin repository and repo marketplace. The official public Codex Plugin Directory does not currently provide a documented self-serve publishing flow, so this repository is the distribution surface for now.

## License

MIT. See [LICENSE](LICENSE).
