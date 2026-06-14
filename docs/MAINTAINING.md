# Maintaining CodexQB

This document covers local validation and release maintenance for CodexQB.

## Validate The Skill

Validate the local global skill:

```bash
python3 /Users/alicankiraz/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/alicankiraz/.codex/skills/codexqb
```

Validate the plugin-bundled skill:

```bash
python3 /Users/alicankiraz/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/codexqb/skills/codexqb
```

## Validate The Plugin

Run:

```bash
python3 /Users/alicankiraz/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/codexqb
```

## Check Prompt Copies

The bundled references should match the source planner prompt files used to generate the release:

```bash
cmp /Users/alicankiraz/Desktop/BillionDollarsIdeas/Planner/First-Planner.md plugins/codexqb/skills/codexqb/references/First-Planner.md
cmp /Users/alicankiraz/Desktop/BillionDollarsIdeas/Planner/Second-Planner.md plugins/codexqb/skills/codexqb/references/Second-Planner.md
cmp /Users/alicankiraz/Desktop/BillionDollarsIdeas/Planner/Third-Planner.md plugins/codexqb/skills/codexqb/references/Third-Planner.md
```

## Check For Stale Names

CodexQB should use `$codexqb` as the skill invocation name:

```bash
rg -n "project-planner|Project Planner|\\$project-planner" .
```

No public-facing stale references should remain.

## Release Flow

1. Update `plugins/codexqb/.codex-plugin/plugin.json`.
2. Update `plugins/codexqb/skills/codexqb/SKILL.md` and references as needed.
3. Run the validation commands above.
4. Commit with a focused message.
5. Push to `main`.
6. Reinstall the plugin in Codex:

   ```bash
   codex plugin add codexqb@codexqb
   ```

7. Start a new Codex thread before testing.

## Public Directory Status

CodexQB is ready as a repository marketplace plugin. The official public Codex Plugin Directory does not currently expose a documented self-serve publishing flow, so public directory submission is not part of this release.

## Contribution Guidelines

- Keep the skill concise.
- Keep long planner prompts in `references/`.
- Preserve the `Planner-docs/*Planing*` filenames required by the bundled prompts.
- Do not add MCP servers, apps, hooks, or assets unless the plugin manifest and validator are updated accordingly.
- Do not put secrets or environment-specific credentials into docs, planner prompts, or examples.
