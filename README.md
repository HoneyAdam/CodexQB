# CodexQB

CodexQB is a Codex plugin that packages a three-step project planning workflow as a reusable skill.

It helps Codex:

- create a high-level master plan at `Planner-docs/Main-Planing.md`;
- decompose that master plan into phase sub-plans under `Planner-docs/Faz-*-Plans/`;
- audit the generated sub-plans for coverage, ordering, readiness, quality, and governance.

The plugin is designed for planning-heavy software, AI, infrastructure, and automation projects where durable Markdown plans and clear phase gates matter.

## What It Provides

CodexQB installs the `$codexqb` skill. The skill contains three bundled planner prompts:

- `First-Planner.md`: Step 1 master project plan.
- `Second-Planner.md`: Step 2 phase and sub-plan generation.
- `Third-Planner.md`: Step 3 sub-plan QA and coverage audit.

Step 1 runs in the current Codex thread. Step 2 and Step 3 are handed off as text-only Goal mode prompts so the user stays in control of long-running planning jobs.

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

3. Answer the four intake questions:
   - `PROJECT_NAME`
   - `PROJECT_INTENT`
   - `TARGET_END_STATE`
   - `KNOWN_CONSTRAINTS`

4. Review `Planner-docs/Main-Planing.md`.
5. If you want the detailed phase decomposition, copy the Step 2 prompt that CodexQB prints and send it with Goal mode.
6. After Step 2 finishes, copy the Step 3 audit prompt that CodexQB prints and send it with Goal mode.

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

CodexQB is planning-only.

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
    references/
      First-Planner.md
      Second-Planner.md
      Third-Planner.md
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
