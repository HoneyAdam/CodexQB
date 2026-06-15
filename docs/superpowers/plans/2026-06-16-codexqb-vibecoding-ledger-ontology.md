# CodexQB Vibecoding, Ledger, Ontology, and Goal-Mode Hardening Plan

## Summary

Implement CodexQB hardening by adapting the reviewed `CodexQB-revised.zip` reference implementation into the current repository without copying it blindly. Preserve the current release gates, add vibecoding/ledger/ontology/subagent guidance, add `--mode autopsy` validator support, and make `make check` usable from both Git checkouts and extracted source packages.

## Key Changes

- Add reference guidance for vibecoding-first planning, subagent usage, planning ledger memory, project ontology, assessment/budget notes, and engineering principles.
- Wire planner prompts so Step 1 reads optional continuity docs, Step 1.5 may produce ontology, Step 2/3 consume continuity docs as supporting evidence, and Step 4 appends concise ledger entries after verified slices or stop events.
- Extend `validate_planner_docs.py` with `autopsy` mode and optional `Project-Ontology.md` / `Planing-Ledger.md` heading validation.
- Keep `make check` strong in Git checkouts with tracked-file secret hygiene and `git archive` hygiene; add clearly labeled filesystem fallbacks for extracted packages without `.git/`.
- Update README, usage, maintenance, installation, skill metadata, and tests to document and lock the new behavior.
- Sync the installed local Codex skill copy after repo validation passes, then verify parity.

## Test Plan

- `make check`
- `python3 -m unittest discover -s tests -v`
- `make export-sanitized`
- Extract `CodexQB-sanitized.zip` into a temporary directory and run `make check` there to verify gitless package fallback.
- `git diff --check`
- `diff -ru plugins/codexqb/skills/codexqb "$HOME/.codex/skills/codexqb"`
- `git status --short`

## Assumptions

- No MCP server, Apps SDK artifact, hooks, or ChatGPT app submission files are added.
- No new dependencies are introduced; validation stays shell plus Python standard library.
- `Planing` filenames stay misspelled intentionally for current CodexQB compatibility.
- The attached zip is a reference implementation, not the source of truth.
