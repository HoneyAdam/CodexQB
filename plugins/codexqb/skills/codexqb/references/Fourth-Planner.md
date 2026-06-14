# Step 4 Implementation Handoff Prompt Template

This reference is not an auto-executed CodexQB planning step.

Use it only after Step 3 writes `Planner-docs/Sub-Planing-Audit.md` and the audit says Step 4 can begin. Print the copy block below for the user to paste into Goal mode.

If the audit status is `BLOCKED`, do not print this prompt. Print the minimal unblock prompt from the audit instead.

If the audit status is `PASS_WITH_WARNINGS` and any P0/P1 finding exists, do not print this prompt. Print a repair prompt targeting those P0/P1 findings first.

If the audit status is `PASS_WITH_WARNINGS` with only P2/P3 findings, this prompt may be printed, but state that the implementation run must keep those warnings visible.

## Copy Block

```text
Treat Planner-docs/Main-Planing.md, Planner-docs/Sub-Planing-Index.md, Planner-docs/Sub-Planing-Audit.md, and Planner-docs/Faz-*-Plans/*.md as source material. Select the first READY or READY_WITH_WARNINGS sub-plan from the audit. If the audit contains P0/P1 findings, stop before implementation and propose a repair prompt.

If installed/available, use relevant Codex skills/plugins by scope: use superpowers:executing-plans or superpowers:subagent-driven-development for implementation, superpowers:test-driven-development for code changes, superpowers:verification-before-completion before finishing, and codex-security for security, policy, secret, or command-execution work. If these skills/plugins are not installed, do not stop; continue using the audit, the selected sub-plan, repo instructions, and existing validation commands with the same principles. Use GitHub publish/PR workflows only when explicitly requested.

Implement one small, reversible, testable improvement slice at a time. First read git status, README.md, AGENTS.md, Makefile, the audit, and the selected sub-plan. Identify the test or validation command before editing; make the minimal change; run focused tests and the relevant make smoke/check target; report the result as an exact blocker or success. Do not write secrets, tokens, private keys, or local credentials. Watch token use: do not load every sub-plan into context; use the index/audit to navigate, then read only the selected sub-plan and required files.
```

## Operator Notes

- Keep the implementation run scoped to one sub-plan and one reversible slice.
- Do not load every sub-plan into context unless the audit requires cross-plan repair.
- Prefer existing repo validation commands over invented commands.
- Report exact blocker strings and separate code-delivery status from external config or credential blockers.
- Do not commit, push, open a PR, deploy, or mutate external systems unless the user explicitly asks in the Step 4 run.
