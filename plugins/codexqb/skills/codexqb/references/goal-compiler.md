# CodexQB Dynamic Goal Compiler

The Dynamic Goal Compiler turns CodexQB source contracts into a deterministic Goal preview before a user starts Goal mode.

It is not an executor. It does not run validation commands, edit global Codex configuration, install dependencies, sync plugin caches, commit, push, create pull requests, deploy, or mutate external systems.

## Inputs

- Target repository root.
- Goal stage: `step15`, `step2`, `step3`, or `step4`.
- Canonical handoff source when the stage has one.
- Stage goal spec under `references/goal-specs/`.
- Relevant existing `Planner-docs/` artifacts.
- Optional output directory inside the target repository.

## Outputs

The compiler writes a deterministic run directory:

```text
Planner-docs/Goal-Runs/<goal-run-id>/
  Goal-Run.json
  Goal-Prompt.md
  Goal-Result.json
```

`Goal-Run.json` records source snapshot hashes, stage, handoff contract version, artifact schema version, output paths, and safety policy. `Goal-Prompt.md` is the user-facing Goal prompt. `Goal-Result.json` is a preview result describing whether the prompt is ready or blocked.

`Goal-Prompt.md` must be rendered deterministically from `Goal-Run.json`. The same valid `Goal-Run.json` must produce byte-identical prompt text.

## Security Rules

- Output directory must be inside the target repository.
- Default output is `Planner-docs/Goal-Runs/<goal-run-id>/`.
- Source snapshots include hashes and relative paths only.
- The compiler must never include secrets, environment values, local credentials, or full logs.
- The compiler must never execute validation commands from planner docs.
- Step 4 prompts must preserve no-commit/no-push/no-PR/no-deploy defaults unless the user explicitly opts in during the implementation run.

## Stage Behavior

- `step15`: prepare Step 1.5 Autopsy context for existing projects.
- `step2`: prepare adaptive wave/full/refresh/repair planning handoff.
- `step3`: prepare Step 3 preflight and audit handoff.
- `step4`: prepare gated apply handoff only as a prompt preview; actual implementation remains user-triggered.
