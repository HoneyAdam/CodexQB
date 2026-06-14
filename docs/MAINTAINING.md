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

## Validate Planner Docs

The skill ships a read-only validator for generated `Planner-docs/` outputs:

```bash
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step1
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step2 --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step3 --strict
```

When changing the validator, test at least:

- a valid Step 2 fixture;
- a missing-section fixture;
- a normal filename containing `sk-` such as `task-spec.yaml`;
- a fake long secret token that should be detected.

## Check Skill Copy Parity

After syncing the repo skill to the local global skill, compare both copies:

```bash
diff -ru plugins/codexqb/skills/codexqb /Users/alicankiraz/.codex/skills/codexqb
```

## Check For Stale Invocation Names

CodexQB should use `$codexqb` as the skill invocation name:

```bash
python3 - <<'PY'
from pathlib import Path
needles = ["project-" + "planner", "Project " + "Planner", "$" + "project-" + "planner"]
for path in Path(".").rglob("*"):
    if path.is_file() and ".git" not in path.parts:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in needles:
            if needle in text:
                print(f"{path}: contains stale invocation text")
PY
```

No public-facing stale references should remain.

## Release Flow

1. Update `plugins/codexqb/.codex-plugin/plugin.json`.
2. Update `plugins/codexqb/skills/codexqb/SKILL.md` and references as needed.
3. Update `plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py` if planner structure changes.
4. Sync the repo skill to `/Users/alicankiraz/.codex/skills/codexqb` for local manual testing.
5. Run the validation commands above.
6. Commit with a focused message.
7. Push to `main`.
8. Reinstall the plugin in Codex:

   ```bash
   codex plugin add codexqb@codexqb
   ```

9. Start a new Codex thread before testing.

## Public Directory Status

CodexQB is ready as a repository marketplace plugin. The official public Codex Plugin Directory does not currently expose a documented self-serve publishing flow, so public directory submission is not part of this release.

## Contribution Guidelines

- Keep the skill concise.
- Keep long planner prompts in `references/`.
- Preserve the `Planner-docs/*Planing*` filenames required by the bundled prompts.
- Do not add MCP servers, apps, hooks, or assets unless the plugin manifest and validator are updated accordingly.
- Do not put secrets or environment-specific credentials into docs, planner prompts, or examples.
