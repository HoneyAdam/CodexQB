# CodexQB

CodexQB is a Codex plugin that packages a repo-aware three-step project planning workflow as a reusable skill, then prepares a gated implementation handoff prompt when the audit says the plan is ready.

It helps Codex:

- inspect the current repository and ask evidence-backed intake questions;
- create a high-level master plan at `Planner-docs/Main-Planing.md`;
- decompose that master plan into phase sub-plans under `Planner-docs/Faz-*-Plans/`;
- audit the generated sub-plans for coverage, ordering, readiness, quality, and governance;
- print a copy-ready Step 4 Goal mode implementation handoff only when the audit allows implementation.

The plugin is designed for planning-heavy software, AI, infrastructure, and automation projects where durable Markdown plans and clear phase gates matter.

## What It Provides

CodexQB installs the `$codexqb` skill. The skill contains bundled planner references:

- `First-Planner.md`: Step 1 master project plan.
- `Second-Planner.md`: Step 2 phase and sub-plan generation.
- `Third-Planner.md`: Step 3 sub-plan QA and coverage audit.
- `Fourth-Planner.md`: Step 4 implementation handoff prompt template.
- `repo-aware-intake.md`: Step 1 evidence-backed intake question protocol.

Step 1 runs in the current Codex thread. It first performs a bounded read-only repository scan, then asks the same four required fields with inferred defaults or draft summaries where evidence exists. Step 2 and Step 3 are handed off as text-only Goal mode prompts so the user stays in control of long-running planning jobs. Step 2 is expected to finish by printing the Step 3 Goal handoff block. Step 3 may print a Step 4 Goal handoff only after audit gating passes.

CodexQB also includes a read-only validator at `scripts/validate_planner_docs.py` inside the skill. It checks required sections, phase folders, filename conventions, index references, duplicate numbering, unindexed files, length-bounded secret patterns, and Step 4 implementation readiness.

## Quick Install

From Codex, add this repository as a plugin marketplace:

```bash
codex plugin marketplace add alicankiraz1/CodexQB --ref main
codex plugin add codexqb@codexqb
```

If the repository is private, your Codex/GitHub environment must have access to `alicankiraz1/CodexQB`.

After installation, start a new Codex thread and invoke:

```text
Use $codexqb to plan this project.
```

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for detailed setup and troubleshooting.

## Basic Usage

1. Open the project repository you want to plan.
2. Ask Codex:

   ```text
   Use $codexqb to create a main plan for this project.
   ```

3. Let CodexQB inspect the repository briefly, then answer the four intake questions:
   - `PROJECT_NAME`
   - `PROJECT_INTENT`
   - `TARGET_END_STATE`
   - `KNOWN_CONSTRAINTS`

   For existing repositories, CodexQB should propose repo-derived defaults and ask you to confirm or correct them. For empty or minimal repositories, it falls back to concise generic questions.

4. Review `Planner-docs/Main-Planing.md`.
5. If you want the detailed phase decomposition, copy the Step 2 prompt that CodexQB prints and send it with Goal mode.
6. After Step 2 finishes, review the validator result in the final summary, then copy the Step 3 audit prompt that CodexQB prints and send it with Goal mode.
7. After Step 3 finishes, copy the Step 4 implementation handoff prompt only if CodexQB prints it. If the audit is blocked or has P0/P1 findings, repair the plans first.

See [docs/USAGE.md](docs/USAGE.md) for the full workflow.

## Output Files

CodexQB writes planning artifacts under `Planner-docs/` in the target project:

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

The file names intentionally preserve the existing `Planing` spelling required by the bundled prompts.

## Safety Model

CodexQB is planning-first. Steps 1-3 are planning and audit work only. Step 4 is a user-controlled Goal mode handoff prompt for a separate implementation run.

The bundled prompts instruct Codex not to:

- implement product features;
- refactor source code;
- install dependencies;
- run destructive commands;
- commit, push, deploy, or open pull requests;
- write secrets, tokens, credentials, private keys, or local sensitive environment values into planning files.

The generated plans should distinguish documentation, local readiness, live readiness, production readiness, and operational evidence.

## Repository Layout

```text
.agents/plugins/marketplace.json
plugins/codexqb/
  .codex-plugin/plugin.json
  skills/codexqb/
    SKILL.md
    agents/openai.yaml
    scripts/
      validate_planner_docs.py
    references/
      First-Planner.md
      Second-Planner.md
      Third-Planner.md
      Fourth-Planner.md
      repo-aware-intake.md
      workflow-quality.md
docs/
LICENSE
README.md
```

## Maintenance

Validation commands and release notes are in [docs/MAINTAINING.md](docs/MAINTAINING.md).

## Public Plugin Directory Status

CodexQB is packaged as a Codex plugin repository and repo marketplace. The official public Codex Plugin Directory does not currently provide a documented self-serve publishing flow, so this repository is the distribution surface for now.

## License

MIT. See [LICENSE](LICENSE).
