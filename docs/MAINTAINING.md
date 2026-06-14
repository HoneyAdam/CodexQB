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
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step4
```

When changing the validator, test at least:

- a valid Step 2 fixture;
- a missing-section fixture;
- a normal filename containing `sk-` such as `task-spec.yaml`;
- a fake long secret token that should be detected.
- roadmap table extraction with historical phase references such as `Faz 0B-10` or `Phase 11`;
- Step 4 readiness gating for missing audit, `BLOCKED`, `PASS`, and `PASS_WITH_WARNINGS`.

Run the tracked validator test suite:

```bash
python3 -m unittest discover -s tests -v
```

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
3. Update `plugins/codexqb/skills/codexqb/references/Fourth-Planner.md` if implementation handoff behavior changes.
4. Update `plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py` if planner structure or readiness gates change.
5. Sync the repo skill to `/Users/alicankiraz/.codex/skills/codexqb` for local manual testing.
6. Run the validation commands above.
7. Commit with a focused message.
8. Push to `main`.
9. Reinstall the plugin in Codex:

   ```bash
   codex plugin add codexqb@codexqb
   ```

10. Start a new Codex thread before testing.

## Public Directory Status

CodexQB is ready as a repository marketplace plugin. The official public Codex Plugin Directory does not currently expose a documented self-serve publishing flow, so public directory submission is not part of this release.

## Contribution Guidelines

- Keep the skill concise.
- Keep long planner prompts in `references/`.
- Preserve the `Planner-docs/*Planing*` filenames required by the bundled prompts.
- Do not add MCP servers, apps, hooks, or assets unless the plugin manifest and validator are updated accordingly.
- Do not put secrets or environment-specific credentials into docs, planner prompts, or examples.
