# Usage

CodexQB runs a repo-aware three-step planning workflow.

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

For existing repositories, the questions should include repo-derived defaults or draft summaries. For example, CodexQB may say that the README and package manifests suggest a specific project name, then ask whether to use that name or a different official name. For empty or minimal repositories, CodexQB should clearly say repository evidence is limited and ask the concise generic version of each question.

After the answers are collected, CodexQB loads `First-Planner.md`, substitutes the values, inspects the repository, and creates or updates:

```text
Planner-docs/Main-Planing.md
```

Step 1 is allowed to modify only that file.

## Step 2: Phase Sub-Plans

After Step 1, CodexQB prints a text block for Goal mode. Copy it, click `Hedefi Takip Et`, and send it.

The prompt is:

```text
Use $codexqb. Step 2'yi references/Second-Planner.md talimatlarına göre yürüt.

Planner-docs/Main-Planing.md dosyasındaki tüm ana fazları okuyup, her faz için Planner-docs altında Faz-<n>-Plans klasörleri ve Faz<n>.<m>-*.md detaylı alt plan dosyaları oluştur. Tüm fazlar kapsanmadan durma. Sadece Planner-docs altında değişiklik yap.
```

Expected outputs:

```text
Planner-docs/Sub-Planing-Index.md
Planner-docs/Faz-<n>-Plans/Faz<n>.<m>-*.md
```

Step 2 is allowed to modify only files under `Planner-docs/`.

At the end of Step 2, CodexQB should run the bundled validator or an equivalent all-file check, summarize the result, and print the Step 3 Goal mode handoff block. Do not rely on sampled reads alone for Step 2 structure checks.

The preferred validator command is:

```bash
python3 ~/.codex/skills/codexqb/scripts/validate_planner_docs.py --root . --mode step2 --strict
```

## Step 3: Sub-Plan QA Audit

After Step 2, CodexQB prints another text block for Goal mode. Copy it, click `Hedefi Takip Et`, and send it.

The prompt is:

```text
Use $codexqb. Step 3'ü references/Third-Planner.md talimatlarına göre yürüt.

Planner-docs/Main-Planing.md, Planner-docs/Sub-Planing-Index.md ve Planner-docs/Faz-*-Plans/*.md dosyalarını denetle. Ana faz coverage, dosya isimlendirme, sıralama, zorunlu bölüm yapısı, index tutarlılığı, içerik kalitesi, scope drift, readiness gerçekçiliği, güvenlik/governance ve Step 4 hazırlığını analiz et. Hiçbir plan dosyasını düzeltme; yalnızca Planner-docs/Sub-Planing-Audit.md raporunu üret. Tüm fazlar ve alt planlar incelenmeden durma.
```

Expected output:

```text
Planner-docs/Sub-Planing-Audit.md
```

Step 3 is an audit step. It reports problems but does not fix the sub-plans.

Step 3 should run the validator first and incorporate its findings into `Planner-docs/Sub-Planing-Audit.md`:

```bash
python3 ~/.codex/skills/codexqb/scripts/validate_planner_docs.py --root . --mode step3 --strict
```

If the validator exits nonzero because it found structural issues, Step 3 should still write the audit unless required source files are missing.

## Step 4: Gated Implementation Handoff

After Step 3, CodexQB may print a Step 4 Goal mode prompt. This prompt is for a separate implementation run; CodexQB itself does not implement product changes during Steps 1-3.

CodexQB should print the Step 4 prompt only when:

- `Planner-docs/Sub-Planing-Audit.md` exists;
- the audit status is `PASS`, or `PASS_WITH_WARNINGS` with no P0/P1 findings;
- the Step 4 validator passes.

The preferred readiness check is:

```bash
python3 ~/.codex/skills/codexqb/scripts/validate_planner_docs.py --root . --mode step4
```

If the audit is `BLOCKED` or contains P0/P1 findings, repair the planning package first. If only P2/P3 warnings remain, the implementation prompt may be used but the warnings should stay visible.

The implementation handoff tells Codex to use relevant skills/plugins by scope, work on one small reversible slice at a time, test before or with code changes, report exact blockers, avoid secrets, and limit token use by reading the audit/index first and only the selected sub-plan afterward.

## Direct Step Invocation

You can invoke Step 2 or Step 3 directly:

```text
Use $codexqb to run Step 2 on the existing Planner-docs/Main-Planing.md.
```

```text
Use $codexqb to run Step 3 and audit the existing sub-plans.
```

CodexQB skips the Step 1 repo-aware intake when the requested step is explicit.

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

## Safety Expectations

CodexQB is not an implementation tool. It is designed to produce planning artifacts only.

If CodexQB finds missing source files or missing planner outputs, it should follow the blocker behavior in the active planner prompt instead of inventing speculative output.
