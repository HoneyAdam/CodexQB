# Installation

CodexQB is distributed as a Codex plugin repository with a repo-local marketplace manifest.

## Requirements

- Codex with plugin support.
- GitHub access to `alicankiraz1/CodexQB`.
- A new Codex thread after installation so the `$codexqb` skill is loaded into context.

If this repository is private, installation only works for users and workspaces that can access the repository.

## Install From The Repository Marketplace

Run these commands in Codex:

```bash
codex plugin marketplace add alicankiraz1/CodexQB --ref main
codex plugin add codexqb@codexqb
```

Then start a new Codex thread and test the skill:

```text
Use $codexqb to plan this project.
```

## Install From A Local Clone

Clone the repository:

```bash
git clone git@github.com:alicankiraz1/CodexQB.git
cd CodexQB
```

Add the local marketplace root:

```bash
codex plugin marketplace add .
codex plugin add codexqb@codexqb
```

Start a new Codex thread before testing.

## Verify Installation

In a project repository, ask:

```text
Use $codexqb to create a main plan for this project.
```

Expected behavior:

1. CodexQB performs a bounded read-only scan of the current repository.
2. It asks for `PROJECT_NAME`, ideally with a repo-derived default.
3. It asks for `PROJECT_INTENT`, ideally with a repo-derived draft.
4. It asks for `TARGET_END_STATE`, ideally across product, engineering, operations, security, and user value.
5. It asks for `KNOWN_CONSTRAINTS`, including detected stack, infra, validation, security, autonomy level, review cadence, budget/context assumptions, and unknown constraints.
6. It uses the confirmed values to create or update `Planner-docs/Main-Planing.md`.
7. For existing or partially built repositories, it may create or update `Planner-docs/Autopsy.md` as Step 1.5.
8. When enough evidence exists, it may create or update `Planner-docs/Project-Ontology.md`.
9. Later Goal-mode implementation handoffs may update `Planner-docs/Planing-Ledger.md` with concise verified-slice summaries.

## Update An Existing Local Install

After pulling repository changes or switching to a newer local clone, refresh the plugin and start a new Codex thread:

```bash
codex plugin add codexqb@codexqb
```

If Codex reports stale marketplace metadata, refresh marketplaces first:

```bash
codex plugin marketplace upgrade
codex plugin add codexqb@codexqb
```

For a manually maintained global skill copy, sync and verify parity from the repository root:

```bash
rsync -a --delete --exclude '__pycache__/' --exclude '*.pyc' plugins/codexqb/skills/codexqb/ "$HOME/.codex/skills/codexqb/"
diff -ru -x __pycache__ plugins/codexqb/skills/codexqb "$HOME/.codex/skills/codexqb"
```

## Troubleshooting

If `$codexqb` is not recognized:

- start a new Codex thread;
- confirm the plugin is installed;
- reinstall with `codex plugin add codexqb@codexqb`;
- confirm the repository or local clone is accessible;
- if installed from a private repository, confirm Codex has GitHub access to that repository.

If Step 2, Step 3, or the gated Step 4 implementation handoff does not run automatically, that is expected. CodexQB prints text-only Goal mode prompts so you can explicitly launch long-running decomposition, audit, or implementation runs. Step 1.5 Autopsy is local to the initial planning thread and runs only when the repository has meaningful existing-project evidence.
