# Usage

CodexQB runs a three-step planning workflow.

## Step 1: Main Plan

Open the project repository you want Codex to analyze and ask:

```text
Use $codexqb to create a main plan for this project.
```

CodexQB asks four intake questions, one at a time:

- `PROJECT_NAME`: the project name.
- `PROJECT_INTENT`: what the project is for and what it should become.
- `TARGET_END_STATE`: what done looks like across product, engineering, operations, security, and user value.
- `KNOWN_CONSTRAINTS`: team, infrastructure, budget, timeline, stack, compliance, must-use tools, and must-not-use tools.

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

## Direct Step Invocation

You can invoke Step 2 or Step 3 directly:

```text
Use $codexqb to run Step 2 on the existing Planner-docs/Main-Planing.md.
```

```text
Use $codexqb to run Step 3 and audit the existing sub-plans.
```

CodexQB skips the Step 1 intake when the requested step is explicit.

## Safety Expectations

CodexQB is not an implementation tool. It is designed to produce planning artifacts only.

If CodexQB finds missing source files or missing planner outputs, it should follow the blocker behavior in the active planner prompt instead of inventing speculative output.
