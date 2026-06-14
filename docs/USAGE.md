# Usage

CodexQB runs a repo-aware planning workflow with an optional Step 1.5 Autopsy for existing projects.

## Step 1: Main Plan

Open the project repository you want Codex to analyze and ask:

```text
Use $codexqb to create a main plan for this project.
```

CodexQB first performs a bounded read-only scan of the current repository. It may inspect files such as `README.md`, `AGENTS.md`, manifests, CI workflows, docs indexes, deployment files, tests, and top-level service directories.

Then it asks four intake questions, one at a time:

- `PROJECT_NAME`: the project name.
- `PROJECT_INTENT`: what the project is for and what it should become.
- `TARGET_END_STATE`: what done looks like across product, engineering, operations, security, and user value.
- `KNOWN_CONSTRAINTS`: team, infrastructure, budget, timeline, stack, compliance, must-use tools, and must-not-use tools.

CodexQB asks intake questions in the user's language when practical. Generated Planner-docs artifacts are English by default unless the user explicitly requests another body language. Required document headings remain English for validator stability.

For existing repositories, the questions should include repo-derived defaults or draft summaries. For example, CodexQB may say that the README and package manifests suggest a specific project name, then ask whether to use that name or a different official name. For empty or minimal repositories, CodexQB should clearly say repository evidence is limited and ask the concise generic version of each question.

After the answers are collected, CodexQB loads `First-Planner.md`, substitutes the values, inspects the repository, and creates or updates:

```text
Planner-docs/Main-Planing.md
```

Step 1 is allowed to modify only that file.

## Step 1.5: Existing Project Autopsy

When the target repository is an existing or partially built project, CodexQB runs `Autopsy-Planner.md` after Step 1.

Expected output:

```text
Planner-docs/Autopsy.md
```

The Autopsy report analyzes project sections, feature inventory, placeholders/stubs/skeletons, technical debt, missing or broken integrations, test and CI gaps, security/governance issues, operational readiness, and alignment with `Planner-docs/Main-Planing.md`.

Step 1.5 is skipped for empty or nearly empty repositories. In that case, `Autopsy.md` is not required and Step 2 should continue without it.

## Step 2: Phase Sub-Plans

After Step 1, CodexQB prints a text block for Goal mode. Copy it, open Goal mode, and send it.

The prompt is:

```text
Use $codexqb. Run Step 2 according to references/Second-Planner.md.

Read all main phases in Planner-docs/Main-Planing.md. If Planner-docs/Autopsy.md exists, read it fully as a supporting feedback source and account for it in the sub-phase plans. For each phase, create Faz-<n>-Plans folders and detailed Faz<n>.<m>-*.md sub-plan files under Planner-docs. Do not stop until all phases are covered. Modify only Planner-docs.
```

Expected outputs:

```text
Planner-docs/Sub-Planing-Index.md
Planner-docs/Faz-<n>-Plans/Faz<n>.<m>-*.md
```

Step 2 is allowed to modify only files under `Planner-docs/`.

`Planner-docs/Main-Planing.md` remains the primary source of truth. `Planner-docs/Autopsy.md`, when present, is supporting feedback that should influence sub-plan evidence, work breakdowns, acceptance criteria, and risk sections.

At the end of Step 2, CodexQB should run the bundled validator or an equivalent all-file validation, summarize the result, and print the Step 3 Goal mode handoff block. Do not rely on sampled reads alone for Step 2 structure checks.

When manually validating from a CodexQB repository checkout, use:

```bash
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step2 --strict
```

When running through an installed plugin, CodexQB should use the bundled validator path exposed by the active skill. If that path is unavailable, it should perform equivalent all-file validation and state that validator execution was unavailable.

## Step 3: Sub-Plan QA Audit

After Step 2, CodexQB prints another text block for Goal mode. Copy it, open Goal mode, and send it.

The prompt is:

```text
Use $codexqb. Run Step 3 according to references/Third-Planner.md.

Audit Planner-docs/Main-Planing.md, Planner-docs/Sub-Planing-Index.md, and Planner-docs/Faz-*-Plans/*.md. Analyze main-phase coverage, file naming, sequencing, required section structure, index consistency, content quality, scope drift, readiness realism, security/governance, and Step 4 readiness. Do not fix any plan files; produce only Planner-docs/Sub-Planing-Audit.md. Do not stop until all phases and sub-plans have been reviewed.
```

Expected output:

```text
Planner-docs/Sub-Planing-Audit.md
```

Step 3 is an audit step. It reports problems but does not fix the sub-plans.

Step 3 should run the bundled validator first and incorporate its findings into `Planner-docs/Sub-Planing-Audit.md`. When manually validating from a CodexQB repository checkout, use:

```bash
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step3 --strict
```

When running through an installed plugin, CodexQB should use the bundled validator path exposed by the active skill. If that path is unavailable, it should perform equivalent all-file validation and state that validator execution was unavailable.

If the validator exits nonzero because it found structural issues, Step 3 should still write the audit unless required source files are missing.

## Step 4: Gated Implementation Handoff

After Step 3, CodexQB may print a Step 4 Goal mode prompt. This prompt is for a separate implementation run; CodexQB itself does not implement product changes during Steps 1-3.

CodexQB should print the Step 4 prompt only when:

- `Planner-docs/Sub-Planing-Audit.md` exists;
- the audit status is `PASS`, or `PASS_WITH_WARNINGS` with no P0/P1 findings;
- the Step 4 validator passes.

When manually checking readiness from a CodexQB repository checkout, use:

```bash
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step4
```

When running through an installed plugin, CodexQB should use the bundled validator path exposed by the active skill. If that path is unavailable, it should perform equivalent all-file validation and state that validator execution was unavailable.

If the audit is `BLOCKED` or contains P0/P1 findings, repair the planning package first. If only P2/P3 warnings remain, the implementation prompt may be used but the warnings should stay visible.

The implementation handoff tells Codex to use relevant skills/plugins by scope, execute the READY/READY_WITH_WARNINGS queue continuously in small reversible slices, test before or with code changes, report exact blockers, avoid secrets, and limit token use by reading the audit/index first and only the active sub-plan afterward.

Step 4 should not stop after the first successful slice. It should continue to the next acceptance criterion or next eligible sub-plan until the queue is complete or a stop gate is hit, such as a P0/P1 finding, failing test, missing source file, required credential/live approval, unsafe external mutation, unrelated dirty worktree, or token/context budget pressure.

## Direct Step Invocation

You can invoke Step 2 or Step 3 directly:

```text
Use $codexqb to run Step 2 on the existing Planner-docs/Main-Planing.md.
```

```text
Use $codexqb to run Step 3 and audit the existing sub-plans.
```

CodexQB skips the Step 1 repo-aware intake when the requested step is explicit.

You can also invoke Step 1.5 directly when a main plan already exists:

```text
Use $codexqb to run Step 1.5 Autopsy for this existing project.
```

You can also ask for the Step 4 prompt text after a completed audit:

```text
Use $codexqb to print the Step 4 implementation handoff prompt if the audit allows it.
```

## Validator Output

The validator prints deterministic summary lines such as:

```text
planner_docs_validation=passed
mode=step2
phase_folder_count=9
subplan_count=35
warning_count=0
error_count=0
```

It exits nonzero on structural failures. With `--strict`, repeated or generic section warnings are treated as failures. Secret scanning uses length-bounded token patterns so normal filenames such as `task-spec.yaml` are not flagged. In `--mode step4`, P0/P1 audit findings block implementation readiness while P2/P3 findings are warnings.

If `Planner-docs/Autopsy.md` exists, the validator checks its required heading order during Step 2/3 validation. If it does not exist, Step 2/3 validation continues without treating Autopsy as required.

## Safety Expectations

CodexQB is not an implementation tool. It is designed to produce planning artifacts only.

If CodexQB finds missing source files or missing planner outputs, it should follow the blocker behavior in the active planner prompt instead of inventing speculative output.
