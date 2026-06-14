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
5. It asks for `KNOWN_CONSTRAINTS`, including detected stack, infra, validation, security, and unknown constraints.
6. It uses the confirmed values to create or update `Planner-docs/Main-Planing.md`.

## Troubleshooting

If `$codexqb` is not recognized:

- start a new Codex thread;
- confirm the plugin is installed;
- reinstall with `codex plugin add codexqb@codexqb`;
- confirm the repository or local clone is accessible;
- if installed from a private repository, confirm Codex has GitHub access to that repository.

If Step 2, Step 3, or the gated Step 4 implementation handoff does not run automatically, that is expected. CodexQB prints text-only Goal mode prompts so you can explicitly launch long-running decomposition, audit, or implementation runs.
