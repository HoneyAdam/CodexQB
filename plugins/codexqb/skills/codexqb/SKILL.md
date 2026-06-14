---
name: codexqb
description: Run the CodexQB three-step Codex project planning workflow using bundled First-Planner, Second-Planner, and Third-Planner prompts. Use when the user asks to create a main project plan, decompose it into phase sub-plans, audit sub-plan coverage and quality, or use the planner workflow with Planner-docs/Main-Planing.md, Planner-docs/Sub-Planing-Index.md, or Planner-docs/Sub-Planing-Audit.md.
---

# CodexQB

## Overview

Run the bundled three-step planning workflow for a project repository. Keep Step 1 conversational and local to the current thread; hand off Step 2 and Step 3 as text-only Goal mode prompts unless the user explicitly asks for a different flow.

The bundled prompts are:

- `references/First-Planner.md` for Step 1 main planning.
- `references/Second-Planner.md` for Step 2 phase sub-planning.
- `references/Third-Planner.md` for Step 3 sub-plan QA and coverage audit.

Bundled support files:

- `scripts/validate_planner_docs.py` for read-only structural validation of `Planner-docs/`.
- `references/workflow-quality.md` for Goal mode reliability, validation, token discipline, and handoff practices.

## Workflow Selection

1. If the user asks for normal planner startup, run Step 1.
2. If the user directly asks for Step 2, read `references/Second-Planner.md` and execute it.
3. If the user directly asks for Step 3, read `references/Third-Planner.md` and execute it.
4. If the user asks only for the Goal mode prompt text, print the matching Step 2 or Step 3 copy block without modifying files.

Do not run `migrate-to-codex` for this workflow. This is a native Codex skill workflow, not a Claude migration.

## Step 1 Intake

Ask these four questions one at a time in the user's language. Use plain text questions, not pop-ups or multiple-choice UI.

1. Ask for `PROJECT_NAME`.
2. Ask for `PROJECT_INTENT`: what the project is for and what it should become.
3. Ask for `TARGET_END_STATE`: what done looks like from product, engineering, operations, security, and user-value perspectives.
4. Ask for `KNOWN_CONSTRAINTS`: team size, infrastructure, budget, timeline, preferred stack, compliance boundaries, must-use tools, and must-not-use tools.

After all four values are available:

1. Read `references/First-Planner.md`.
2. Substitute the four collected values into the matching placeholders.
3. Follow the substituted Step 1 prompt exactly.
4. Create or update only `Planner-docs/Main-Planing.md`, as required by the Step 1 prompt.
5. After completing Step 1, ask the user in plain text whether they have feedback for the main plan.
6. If feedback is provided, apply it under the same Step 1 file boundary: only `Planner-docs/Main-Planing.md`.

## Step 2 Handoff

After Step 1 feedback is handled, ask whether the user wants to continue to Step 2. If yes, tell the user to copy the following text, click `Hedefi Takip Et`, and send it:

```text
Use $codexqb. Step 2'yi references/Second-Planner.md talimatlarına göre yürüt.

Planner-docs/Main-Planing.md dosyasındaki tüm ana fazları okuyup, her faz için Planner-docs altında Faz-<n>-Plans klasörleri ve Faz<n>.<m>-*.md detaylı alt plan dosyaları oluştur. Tüm fazlar kapsanmadan durma. Sadece Planner-docs altında değişiklik yap.
```

When executing Step 2 directly:

1. Read `references/Second-Planner.md`.
2. Read `references/workflow-quality.md`.
3. Follow repository inspection, file-boundary, naming, all-file validation, and stopping rules exactly.
4. Run the bundled validator after generation when available:
   `python3 ~/.codex/skills/codexqb/scripts/validate_planner_docs.py --root . --mode step2 --strict`
5. Do not modify files outside `Planner-docs/`.
6. After the Step 2 summary, print the Step 3 `Hedefi Takip Et` handoff block from this skill.

## Step 3 Handoff

After Step 2 is complete, ask whether the user wants to continue to Step 3. If yes, tell the user to copy the following text, click `Hedefi Takip Et`, and send it:

```text
Use $codexqb. Step 3'ü references/Third-Planner.md talimatlarına göre yürüt.

Planner-docs/Main-Planing.md, Planner-docs/Sub-Planing-Index.md ve Planner-docs/Faz-*-Plans/*.md dosyalarını denetle. Ana faz coverage, dosya isimlendirme, sıralama, zorunlu bölüm yapısı, index tutarlılığı, içerik kalitesi, scope drift, readiness gerçekçiliği, güvenlik/governance ve Step 4 hazırlığını analiz et. Hiçbir plan dosyasını düzeltme; yalnızca Planner-docs/Sub-Planing-Audit.md raporunu üret. Tüm fazlar ve alt planlar incelenmeden durma.
```

When executing Step 3 directly:

1. Read `references/Third-Planner.md`.
2. Read `references/workflow-quality.md`.
3. Run the bundled validator first when available and incorporate its findings into the audit:
   `python3 ~/.codex/skills/codexqb/scripts/validate_planner_docs.py --root . --mode step3 --strict`
4. Follow audit, file-boundary, validation, and stopping rules exactly.
5. Modify only `Planner-docs/Sub-Planing-Audit.md`.

## Quality and Validation

- Prefer `scripts/validate_planner_docs.py` over ad hoc validation scripts.
- Use `--mode step1`, `--mode step2`, or `--mode step3` for the active workflow step.
- Use `--strict` in Goal mode so generic or repeated section warnings become failures.
- Do not report section counts from memory; report counts only after reading the active prompt or running validation.
- For untracked `Planner-docs/`, use `find Planner-docs -maxdepth 4 -type f | sort`, `git status --short -- Planner-docs`, and `git diff -- Planner-docs` together.
- Keep long Goal mode stdout concise. Put detailed evidence in the generated Markdown artifacts.

## Safety Rules

- Treat the current working directory as the project being planned.
- Inspect the repository before writing any planning file, using the safe read-only commands required by the active planner prompt.
- Do not implement product features, refactor source code, install dependencies, commit, push, deploy, or open pull requests.
- Do not write secrets, tokens, credentials, private keys, or local sensitive environment values into planning files.
- Preserve the required misspelled filenames exactly: `Main-Planing.md`, `Sub-Planing-Index.md`, and `Sub-Planing-Audit.md`.
- If a required source file is missing, follow the blocker behavior in the active planner prompt instead of inventing speculative output.

## Completion Reporting

For each executed step, report concisely:

- which planner step ran;
- which files were created or updated;
- whether the step succeeded or was blocked;
- the highest-priority next action;
- any uncertainty or blocker discovered.
