#!/usr/bin/env python3
"""Compile deterministic CodexQB Goal run previews.

This script is intentionally non-executing: it reads source contracts, hashes
source snapshots, validates a Goal-Run schema, and renders Goal prompts inside
the target repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ARTIFACT_SCHEMA_VERSION = 3
HANDOFF_CONTRACT_VERSION = 2
GOAL_RUN_SCHEMA_VERSION = 1
PLUGIN_VERSION = "0.3.0"

SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]

STAGE_REFERENCES = {
    "step15": ["references/Autopsy-Planner.md", "references/goal-specs/step15.md"],
    "step2": ["references/handoffs/run-step2.md", "references/Second-Planner.md", "references/goal-specs/step2.md"],
    "step3": ["references/handoffs/run-step3.md", "references/Third-Planner.md", "references/goal-specs/step3.md"],
    "step4": ["references/handoffs/run-step4.md", "references/Fourth-Planner.md", "references/goal-specs/step4.md"],
}

PLANNER_DOC_SOURCES = [
    "Planner-docs/Main-Planing.md",
    "Planner-docs/Autopsy.md",
    "Planner-docs/Project-Ontology.md",
    "Planner-docs/Project-Comprehension.md",
    "Planner-docs/Sub-Planing-Index.md",
    "Planner-docs/Sub-Planing-Audit.md",
    "Planner-docs/Planing-Ledger.md",
]

SECRET_LIKE_RE = re.compile(
    r"\bsk-[A-Za-z0-9_-]{20,}\b|github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}|BEGIN (?:RSA|OPENSSH|DSA|EC|PRIVATE) KEY",
    re.IGNORECASE,
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def repo_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def is_inside(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def run_git(root: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def safe_rel_path(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def collect_sources(root: Path, stage: str) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for rel in STAGE_REFERENCES[stage]:
        path = SKILL_ROOT / rel
        data = path.read_bytes()
        sources.append({"scope": "skill", "path": rel, "sha256": sha256_bytes(data)})

    for rel in PLANNER_DOC_SOURCES:
        path = root / rel
        if path.is_file():
            data = path.read_bytes()
            sources.append({"scope": "repo", "path": rel, "sha256": sha256_bytes(data)})

    planner = root / "Planner-docs"
    for path in sorted(planner.glob("Faz-*-Plans/*.md")) if planner.is_dir() else []:
        data = path.read_bytes()
        sources.append({"scope": "repo", "path": repo_relative(root, path), "sha256": sha256_bytes(data)})

    branch = run_git(root, ["branch", "--show-current"]) or "unknown"
    commit = run_git(root, ["rev-parse", "HEAD"]) or "unknown"
    sources.append({"scope": "git", "path": "branch", "sha256": sha256_bytes(branch.encode("utf-8")), "value": branch})
    sources.append({"scope": "git", "path": "commit", "sha256": sha256_bytes(commit.encode("utf-8")), "value": commit})
    return sources


def snapshot_digest(stage: str, sources: list[dict[str, str]]) -> str:
    payload = json.dumps({"stage": stage, "sources": sources}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def run_id_for(stage: str, sources: list[dict[str, str]]) -> str:
    return f"goal-{stage}-{snapshot_digest(stage, sources)[:12]}"


def project_name(root: Path) -> str:
    main = root / "Planner-docs" / "Main-Planing.md"
    if main.is_file():
        text = main.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"Project\s+Name\s*[:|-]\s*(.+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()[:120]
    return root.name


def default_goal_run(root: Path, stage: str, mode: str | None = None, objective: str | None = None) -> dict[str, object]:
    sources = collect_sources(root, stage)
    run_id = run_id_for(stage, sources)
    digest = snapshot_digest(stage, sources)
    allowed_writes = {
        "step15": ["Planner-docs/Autopsy.md", "Planner-docs/Project-Ontology.md", "Planner-docs/Project-Comprehension.md"],
        "step2": ["Planner-docs/Sub-Planing-Index.md", "Planner-docs/Faz-*-Plans/*.md"],
        "step3": ["Planner-docs/Sub-Planing-Audit.md"],
        "step4": ["Planner-docs/Planing-Ledger.md"],
    }[stage]
    return {
        "goal_run_schema_version": GOAL_RUN_SCHEMA_VERSION,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "handoff_contract_version": HANDOFF_CONTRACT_VERSION,
        "goal_run_id": run_id,
        "stage": stage,
        "stage_contract_version": HANDOFF_CONTRACT_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "project_name": project_name(root),
        "mode": mode or ("subagent_serial" if stage == "step4" else "wave"),
        "objective": objective or f"Run CodexQB {stage} using current repository planning evidence.",
        "source_snapshot": sources,
        "source_snapshot_digest": digest,
        "required_inputs": [item["path"] for item in sources if item["scope"] in {"repo", "skill"}],
        "allowed_writes": allowed_writes,
        "forbidden_writes": ["~/.codex/**", ".git/**", ".env", "**/*.key", "**/*.pem"],
        "active_scope": {"stage": stage, "project_root": root.as_posix()},
        "work_steps": ["verify snapshot", "load canonical references", "perform stage-specific work", "run validation checkpoints", "write final report"],
        "validation_checkpoints": [
            {"id": "VAL-01", "argv": ["python3", "plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py", "--root", ".", "--mode", stage if stage != "step15" else "autopsy"], "network": "deny", "probe_tier": 1}
        ],
        "stop_gates": ["snapshot mismatch", "P0/P1 blocker", "unsafe path", "required user confirmation missing", "dirty unrelated worktree"],
        "subagent_plan": {"max_depth": 1, "roles": []},
        "context_token_budget": {"risk": "medium", "confirmation_required": stage in {"step2", "step4"}},
        "final_report_contract": ["files changed", "validations", "blockers", "next action"],
        "user_confirmation_required": stage in {"step2", "step4"},
        "generated_at": f"deterministic:{digest[:16]}",
        "safety": {
            "executes_commands": False,
            "allows_global_config_edits": False,
            "allows_commit_push_pr_deploy": False,
            "output_dir_must_be_inside_repo": True,
        },
    }


def validate_goal_run(root: Path, run: dict[str, object]) -> list[str]:
    errors: list[str] = []
    stage = str(run.get("stage", ""))
    if stage not in STAGE_REFERENCES:
        errors.append(f"invalid_stage={stage or 'missing'}")
        return errors
    if run.get("goal_run_schema_version") != GOAL_RUN_SCHEMA_VERSION:
        errors.append("invalid_goal_run_schema_version")
    if run.get("plugin_version") != PLUGIN_VERSION:
        errors.append("invalid_plugin_version")
    text = json.dumps(run, sort_keys=True)
    if SECRET_LIKE_RE.search(text):
        errors.append("secret_like_content")

    allowed = set(str(item) for item in run.get("allowed_writes", []) if isinstance(item, str))
    forbidden = set(str(item) for item in run.get("forbidden_writes", []) if isinstance(item, str))
    if allowed & forbidden:
        errors.append("overlapping_allowed_forbidden_writes")
    for path in allowed | forbidden:
        if path.startswith("~"):
            continue
        if "*" in path:
            continue
        if not safe_rel_path(path):
            errors.append(f"unsafe_path={path}")

    current_sources = collect_sources(root, stage)
    current_digest = snapshot_digest(stage, current_sources)
    if run.get("source_snapshot_digest") != current_digest:
        errors.append("source_snapshot_mismatch")
    return errors


def render_prompt_from_run(run: dict[str, object]) -> str:
    stage = str(run["stage"])
    spec = read_text(SKILL_ROOT / f"references/goal-specs/{stage}.md")
    handoff = ""
    for rel in STAGE_REFERENCES[stage]:
        if "/handoffs/" in rel:
            handoff = read_text(SKILL_ROOT / rel)
            break

    preview = [
        f"Stage: {stage}",
        f"Mode: {run['mode']}",
        f"Objective: {run['objective']}",
        f"Active phases/tasks: {json.dumps(run['active_scope'], sort_keys=True, separators=(',', ':'))}",
        "Deferred phases: see Planner-docs/Sub-Planing-Index.md when present",
        f"Expected writes: {', '.join(run['allowed_writes'])}",
        f"Validation: {len(run['validation_checkpoints'])} checkpoint(s)",
        f"Risk: context/token {run['context_token_budget']['risk']}",
        f"Subagents: {json.dumps(run['subagent_plan'], sort_keys=True, separators=(',', ':'))}",
        f"User confirmation required: {run['user_confirmation_required']}",
        f"Stop gates: {', '.join(run['stop_gates'])}",
    ]

    lines = [
        f"# CodexQB Goal Prompt: {stage}",
        "",
        "Use $codexqb.",
        "",
        "## Goal Preview",
        "",
        *preview,
        "",
        "## Goal Compiler Safety",
        "",
        "- Treat this as a prompt preview, not an executor.",
        "- Do not install dependencies, commit, push, create pull requests, deploy, edit global Codex config, or sync plugin caches unless explicitly asked in the active run.",
        "- Recompute source snapshot hashes before starting or resuming; stop on mismatch.",
        "",
        "## Stage Spec",
        "",
        spec.strip(),
        "",
        "## Source Snapshot",
        "",
    ]
    for source in run["source_snapshot"]:
        visible = f" value={source['value']}" if source.get("scope") == "git" and "value" in source else ""
        lines.append(f"- {source['scope']}:{source['path']} sha256={source['sha256']}{visible}")
    if handoff:
        lines += ["", "## Canonical Handoff", "", handoff.strip()]
    return "\n".join(lines) + "\n"


def compile_goal(root: Path, stage: str, output_dir: Path | None = None, mode: str | None = None, objective: str | None = None) -> dict[str, object]:
    root = root.resolve()
    if stage not in STAGE_REFERENCES:
        raise ValueError(f"unsupported stage: {stage}")
    run = default_goal_run(root, stage, mode, objective)
    errors = validate_goal_run(root, run)
    if errors:
        raise ValueError(";".join(errors))
    out_dir = (output_dir or root / "Planner-docs" / "Goal-Runs" / str(run["goal_run_id"])).resolve()
    if not is_inside(root, out_dir):
        raise ValueError("output_dir must be inside the target repository")
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt = render_prompt_from_run(run)
    result = {
        "goal_run_id": run["goal_run_id"],
        "stage": stage,
        "status": "ready",
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        "source_count": len(run["source_snapshot"]),
        "next_action": "Review Goal-Prompt.md, then paste it into Goal mode only if the stage and safety policy match the intended run.",
    }
    (out_dir / "Goal-Run.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "Goal-Prompt.md").write_text(prompt, encoding="utf-8")
    (out_dir / "Goal-Result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"run": run, "result": result, "output_dir": out_dir.as_posix()}


def load_goal_run(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Goal-Run.json must contain an object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile deterministic CodexQB Goal previews.")
    sub = parser.add_subparsers(dest="command")

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", default=".", help="Target repository root.")
        p.add_argument("--stage", required=True, choices=sorted(STAGE_REFERENCES), help="Goal stage.")

    collect = sub.add_parser("collect", help="Print source snapshot JSON.")
    add_common(collect)
    prepare = sub.add_parser("prepare", help="Write Goal-Run.json, Goal-Prompt.md, and Goal-Result.json.")
    add_common(prepare)
    prepare.add_argument("--mode")
    prepare.add_argument("--objective")
    prepare.add_argument("--output-dir")
    validate = sub.add_parser("validate", help="Validate Goal-Run.json against current snapshot.")
    validate.add_argument("--root", default=".")
    validate.add_argument("--goal-run", required=True)
    render = sub.add_parser("render", help="Render Goal-Prompt.md from Goal-Run.json.")
    render.add_argument("--goal-run", required=True)
    render.add_argument("--output")

    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)
    parser.add_argument("--stage", choices=sorted(STAGE_REFERENCES), help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        if args.command is None:
            if not args.stage:
                parser.error("--stage is required")
            compiled = compile_goal(Path(args.root), args.stage, Path(args.output_dir) if args.output_dir else None)
            print("goal_run_status=ready")
            print(f"goal_run_id={compiled['result']['goal_run_id']}")
            print(f"output_dir={compiled['output_dir']}")
            return 0
        if args.command == "collect":
            root = Path(args.root).resolve()
            sources = collect_sources(root, args.stage)
            print(json.dumps({"stage": args.stage, "source_snapshot": sources}, indent=2, sort_keys=True))
            return 0
        if args.command == "prepare":
            compiled = compile_goal(Path(args.root), args.stage, Path(args.output_dir) if args.output_dir else None, args.mode, args.objective)
            print("goal_run_status=ready")
            print(f"goal_run_id={compiled['result']['goal_run_id']}")
            print(f"output_dir={compiled['output_dir']}")
            return 0
        if args.command == "validate":
            errors = validate_goal_run(Path(args.root).resolve(), load_goal_run(Path(args.goal_run)))
            if errors:
                print("goal_run_status=failed")
                for error in errors:
                    print(f"error={error}")
                return 1
            print("goal_run_status=passed")
            return 0
        if args.command == "render":
            prompt = render_prompt_from_run(load_goal_run(Path(args.goal_run)))
            if args.output:
                Path(args.output).write_text(prompt, encoding="utf-8")
            else:
                print(prompt, end="")
            return 0
    except Exception as exc:
        print("goal_run_status=failed", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
