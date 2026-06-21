# Usage

CodexQB runs a vibecoding-first, repo-aware planning workflow with an optional Step 1.5 Autopsy and ontology pass for existing projects.

Release contracts:

```text
plugin_version: 0.3.0
artifact_schema_version: 3
handoff_contract_version: 2
goal_run_schema_version: 1
apply_run_schema_version: 1
```


## Vibecoding, Subagents, and Durable Memory

CodexQB plans for coding agents, not for static slideware. Plans should identify the next useful verified moves, preserve room for discovery, and keep work in small reversible slices with fast validation signals. Vibecoding does not relax safety, secret handling, approval, validation, or file-boundary rules.

When the repo is large or ambiguous, CodexQB may ask Codex Goal mode to use bounded subagents for read-only repo exploration, readiness/security review, ontology mapping, phase drafting, Step 3 audit, or Step 4 implementation/review separation. Subagents should gather evidence or review; the parent CodexQB agent owns official artifact writes.

CodexQB may use these optional durable artifacts when they exist:

```text
Planner-docs/Project-Ontology.md
Planner-docs/Project-Comprehension.md
Planner-docs/Planing-Ledger.md
```

`Project-Ontology.md` helps future planning understand vocabulary, entities, workflows, boundaries, integrations, and invariants. `Project-Comprehension.md` records evidence confidence, comprehension questions, domain-to-code traces, architecture reflexion, quality scenarios, and open hypotheses. `Planing-Ledger.md` records planning runs, implementation summaries, current state snapshots, and replanning inputs so future CodexQB runs can understand what was planned and what was actually applied.

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
- `KNOWN_CONSTRAINTS`: team, infrastructure, budget, timeline, stack, compliance, must-use tools, must-not-use tools, desired autonomy, human review cadence, and any token/usage budget.

CodexQB asks intake questions in the user's language when practical. Generated Planner-docs artifacts are English by default unless the user explicitly requests another content language. Required document headings remain English for validator stability. If the user provides a weekly/monthly token or usage budget, CodexQB can estimate whether the planned Goal run is likely to be low, medium, or high relative usage; it should not invent exact token spend without a baseline.

Future language-mode work should add an explicit `PLANNER_DOC_LANGUAGE` or intake-level language setting. Until then, headings stay English and only body content should vary when the user requests another language.

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
Planner-docs/Project-Ontology.md   # optional when enough evidence exists
Planner-docs/Project-Comprehension.md  # optional for non-trivial existing projects
```

The Autopsy report analyzes project sections, feature inventory, placeholders/stubs/skeletons, technical debt, missing or broken integrations, test and CI gaps, security/governance issues, operational readiness, and alignment with `Planner-docs/Main-Planing.md`. The optional ontology captures domain vocabulary, entities, workflows, boundaries, integrations, invariants, and open concept questions. The optional comprehension artifact captures `CQ-*`, `TRACE-*`, `ARC-*`, evidence/confidence, QAW/ATAM-lite quality scenarios, and open validation probes.

Step 1.5 is skipped for empty or nearly empty repositories. In that case, `Autopsy.md` is not required and Step 2 should continue without it.

## Step 2: Phase Sub-Plans

After Step 1, CodexQB prints a text block for Goal mode. Copy it, open Goal mode, and send it.

The prompt is:

```text
Use $codexqb. Read and return the exact canonical handoff from references/handoffs/run-step2.md, then execute it.
```

Expected outputs:

```text
Planner-docs/Sub-Planing-Index.md
Planner-docs/Faz-<n>-Plans/Faz<n>.<m>-*.md
```

Step 2 is allowed to modify only files under `Planner-docs/`.

`Planner-docs/Main-Planing.md` remains the primary source of truth. `Planner-docs/Autopsy.md`, `Planner-docs/Project-Ontology.md`, `Planner-docs/Project-Comprehension.md`, and `Planner-docs/Planing-Ledger.md`, when present, are supporting evidence that should influence sub-plan evidence, work breakdowns, acceptance criteria, risks, ontology consistency, traceability, confidence calibration, and replanning continuity.

Step 2 defaults to `wave` mode: it details only the active planning horizon from explicit user intent, `Main-Planing.md` Step 2 Preparation Notes, active ledger state, or the next useful CodexQB wave. Later phases stay visible as deferred roadmap cards in `Sub-Planing-Index.md`. `full` mode requires an explicit user request. `refresh` updates existing planning artifacts incrementally, and `repair` updates audit-selected files only.

`Sub-Planing-Index.md` includes a Planning Scope Manifest with `planning_mode`, `active_phases`, `deferred_phases`, `max_detailed_subplans`, `max_output_words`, `goal_token_risk`, and `review_checkpoint`. It also carries Execution Waves, Parent Acceptance Traceability, and a central Decision Register so repeated global blockers are not copied into every sub-plan.

Active detailed sub-plans keep the 13-section structure and add a machine-readable `### Implementation Contract` JSON block with implementation paths, structured validation commands, parent acceptance signal IDs, dependency graph labels, concrete outputs, risk metadata, and security review flags. Rewritten public planning artifacts use `artifact_schema_version: 3`, `generated_by: codexqb`, and `plugin_version: 0.3.0` frontmatter.

Validation commands should use `argv`, `cwd`, `expected_exit_code`, `timeout_seconds`, `network`, and `probe_tier`. `network` is an enum such as `deny`, `local`, `live`, or `allow`; `probe_tier` is an integer tier. Legacy `command` strings are compatibility-only outside strict mode, and strict validation rejects shell chaining, command substitution, deploy/install/delete/push intent, and other external mutation patterns. High or critical risk classes and domains such as `auth`, `authorization`, `credential`, `secret`, `external_provider`, `network`, `command_execution`, `deployment`, `migration`, `stateful_runtime`, `distributed_runtime`, `online_learning`, `reinforcement_learning`, `cache`, `resume`, `checkpoint`, `payment`, `personal_data`, or `algorithmic_invariant` require `security_review_required: true`.

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
Use $codexqb. Read and return the exact canonical handoff from references/handoffs/run-step3.md, then execute it.
```

Expected output:

```text
Planner-docs/Sub-Planing-Audit.md
```

Step 3 is an audit step. It reports problems but does not fix the sub-plans.

Step 3 should run the bundled validator first and incorporate its findings into `Planner-docs/Sub-Planing-Audit.md`. When manually validating from a CodexQB repository checkout, use:

```bash
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step3-preflight --strict
python3 plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py --root /path/to/project --mode step3 --strict
```

When running through an installed plugin, CodexQB should use the bundled validator path exposed by the active skill. If that path is unavailable, it should perform equivalent all-file validation and state that validator execution was unavailable.

If the validator exits nonzero because it found structural issues, Step 3 should still write the audit unless required source files are missing.

## Step 4: Gated Implementation Handoff

After Step 3, CodexQB may print a Step 4 Goal mode prompt. This prompt is for a separate implementation run; CodexQB itself does not implement product changes during Steps 1-3.

The canonical Step 4 handoff lives in `references/handoffs/run-step4.md`. When CodexQB prints a Step 4 prompt, it may include audit-derived queue details, but the structure must still follow that canonical handoff.

A manual Step 4 handoff request can use this shape:

```text
Use $codexqb. Read and return the exact canonical handoff from references/handoffs/run-step4.md, then execute it only if Planner-docs/Sub-Planing-Audit.md allows implementation.
```

The generated handoff should include the Goal Run Contract, the READY or READY_WITH_WARNINGS implementation queue or `NO_ACTION_REQUIRED`, source precedence, validation gates, stop gates, context-budget and subagent policy, and per-slice reporting requirements.

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

The implementation handoff tells Codex to use relevant skills/plugins or subagents by scope, execute the READY/READY_WITH_WARNINGS queue continuously in small reversible slices, test before or with code changes, report exact blockers, avoid secrets, update `Planner-docs/Planing-Ledger.md` with concise implementation summaries, and limit token use by reading the audit/index first and only the active sub-plan afterward.

Step 4 should not stop after the first successful slice. It should continue to the next acceptance criterion or next eligible sub-plan until the queue is complete or a stop gate is hit, such as a P0/P1 finding, failing test, missing source file, required credential/live approval, unsafe external mutation, unrelated dirty worktree, or token/context budget pressure.

Step 4 apply modes are `direct`, `subagent_serial`, `external_superpowers`, and `no_action`. Non-trivial slices should use a fresh-slice implementer when useful, followed by independent spec review, quality/security review, fix/re-review when needed, and final review for the selected batch or queue. Commit, push, PR, deploy, and external mutation remain opt-in.

## Goal Preview and Apply Artifacts

CodexQB 0.3.0 includes dependency-free helpers for local preview and artifact validation. They do not execute implementation or validation commands.

Compile a deterministic Goal preview:

```bash
python3 plugins/codexqb/skills/codexqb/scripts/goal_run.py --root /path/to/project --stage step2
```

Supported stages are `step15`, `step2`, `step3`, and `step4`. Output is written under `Planner-docs/Goal-Runs/<goal-run-id>/` as `Goal-Run.json`, `Goal-Prompt.md`, and `Goal-Result.json`. Step 2/3 previews include active sub-plan inventory when present; Step 4 previews include READY/READY_WITH_WARNINGS audit queue entries when present.
If a stage prerequisite is missing, `Goal-Result.json` is written with `status: blocked` and no `Goal-Prompt.md` execution prompt is produced. Rendering an existing `Goal-Run.json` validates schema, source snapshot, path policy, and secret hygiene before writing prompt text. Existing run directories are not overwritten unless `--replace` or `--resume` is explicit.

Create or validate an apply-run artifact directory:

```bash
python3 plugins/codexqb/skills/codexqb/scripts/apply_run.py init --root /path/to/project --mode subagent_serial
python3 plugins/codexqb/skills/codexqb/scripts/apply_run.py validate --run-dir /path/to/project/.codexqb/apply-runs/<apply-run-id>
```

Output is written under `.codexqb/apply-runs/<apply-run-id>/` as `Apply-Run.json`, `Progress.json`, per-task brief/report/review/fix artifacts, `Final-Review.json`, and `Result.json`. Non-`no_action` modes derive initial task briefs from Step 4 READY/READY_WITH_WARNINGS audit entries when available. The default commit policy is `none`.
Apply validation rejects unsafe validation commands, path-traversal task IDs, no-action runs with queued tasks, recursive subagent depth, multiple writers, silent progress overwrite, and VERIFIED tasks that lack files changed, validation evidence, independent review evidence, and final repo-level validation evidence.
`Goal-Run.json` records `goal_run_schema_version: 1`; `Apply-Run.json` records `apply_run_schema_version: 1`.

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
validation_status=passed
mode=step2
validation_mode=step2
phase_folder_count=9
subplan_count=35
warning_count=0
error_count=0
```

It uses stable exit codes: `0` means validation passed, `1` means document validation failed, and `2` means invocation/configuration/I/O error. With `--strict`, missing semantic readiness signals, repeated or generic section warnings, unsafe validation commands, high-risk security-review bypasses, unsupported planning scope, and uniform quota anomalies are treated as failures except documented compatibility warnings. Validation command safety is shared with Goal/Apply helpers and allows only known-safe command families such as `python -m pytest`, `python -m unittest`, safe `make` targets, safe package-manager scripts, `cargo test`, `go test`, `ruff check`, and `mypy`; arbitrary `python -c`, unchecked shell scripts, absolute/traversal path arguments, and mutating targets are rejected. Secret scanning uses length-bounded token patterns so normal filenames such as `task-spec.yaml` are not flagged. In `--mode step4`, open P0/P1 audit findings block implementation readiness, open or accepted P2/P3 findings require `PASS_WITH_WARNINGS`, resolved/not_applicable P2/P3 findings may coexist with `PASS`, and `NO_ACTION_REQUIRED` is valid when all in-scope rows are COMPLETE, SUPERSEDED, or DEFERRED.

If `Planner-docs/Autopsy.md`, `Planner-docs/Project-Ontology.md`, `Planner-docs/Project-Comprehension.md`, or `Planner-docs/Planing-Ledger.md` exists, the validator checks its required heading order and supported semantic fields during Step 2/3 validation. If these optional continuity docs do not exist, Step 2/3 validation continues without treating them as required. Use `--mode autopsy --strict` after Step 1.5 when `Autopsy.md` should be required.

The repository `make check` also runs the deterministic fixture corpus checker. The fixture corpus keeps static input repos and expected signals healthy; it does not measure live Codex behavior.

## Safety Expectations

CodexQB is not an implementation tool. It is designed to produce planning artifacts only.

If CodexQB finds missing source files or missing planner outputs, it should follow the blocker behavior in the active planner prompt instead of inventing speculative output.
