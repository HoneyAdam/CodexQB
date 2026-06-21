#!/usr/bin/env python3
"""Compile deterministic CodexQB Goal run previews.

This script is intentionally non-executing: it reads source contracts, hashes
source snapshots, validates a Goal-Run schema, and renders Goal prompts inside
the target repo.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from safety_contracts import (  # noqa: E402
    glob_patterns_overlap,
    has_secret_like,
    is_safe_repo_path,
    path_is_inside,
)


ARTIFACT_SCHEMA_VERSION = 3
HANDOFF_CONTRACT_VERSION = 2
GOAL_RUN_SCHEMA_VERSION = 1
PLUGIN_VERSION = "0.3.0"

SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
VALIDATOR_PATH = SCRIPT_PATH.with_name("validate_planner_docs.py")

STAGE_REFERENCES = {
    "step15": ["references/Autopsy-Planner.md", "references/goal-specs/step15.md"],
    "step2": ["references/handoffs/run-step2.md", "references/Second-Planner.md", "references/goal-specs/step2.md"],
    "step3": ["references/handoffs/run-step3.md", "references/Third-Planner.md", "references/goal-specs/step3.md"],
    "step4": ["references/handoffs/run-step4.md", "references/Fourth-Planner.md", "references/goal-specs/step4.md"],
}

STAGE_MODES = {
    "step15": {"wave", "autopsy", "refresh"},
    "step2": {"wave", "full", "refresh", "repair"},
    "step3": {"wave", "audit", "repair"},
    "step4": {"direct", "subagent_serial", "external_superpowers", "no_action"},
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

def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def repo_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def is_inside(parent: Path, child: Path) -> bool:
    return path_is_inside(parent, child)


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


def template_bundle(stage: str) -> dict[str, object]:
    templates = []
    for rel in STAGE_REFERENCES[stage]:
        path = SKILL_ROOT / rel
        templates.append({"path": rel, "sha256": sha256_bytes(path.read_bytes())})
    compiler = {
        "path": "scripts/goal_run.py",
        "sha256": sha256_bytes(SCRIPT_PATH.read_bytes()),
    }
    payload = {"templates": templates, "compiler": compiler}
    digest = sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return {"digest": digest, **payload}


def goal_spec_digest(stage: str, sources: list[dict[str, str]], mode: str, objective: str, active_scope: dict[str, object]) -> str:
    payload = {
        "stage": stage,
        "sources": sources,
        "mode": mode,
        "objective": objective,
        "active_scope": active_scope,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "handoff_contract_version": HANDOFF_CONTRACT_VERSION,
        "goal_run_schema_version": GOAL_RUN_SCHEMA_VERSION,
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def invocation_suffix(value: str | None = None) -> str:
    raw = value or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{os.getpid()}"
    suffix = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-._")
    if not suffix:
        raise ValueError("invalid_run_id_suffix")
    return suffix[:64]


def goal_run_id_for(stage: str, spec_digest: str, run_id_suffix: str | None = None) -> str:
    return f"goal-{stage}-{spec_digest[:12]}-{invocation_suffix(run_id_suffix)}"


def run_bundled_validator(root: Path, mode: str, *, strict: bool = True) -> tuple[int, str]:
    command = [sys.executable, VALIDATOR_PATH.as_posix(), "--root", root.as_posix(), "--mode", mode]
    if strict:
        command.append("--strict")
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"validator_unavailable={type(exc).__name__}"
    return completed.returncode, f"{completed.stdout}\n{completed.stderr}".strip()


def stage_validator_mode(stage: str) -> str:
    return {
        "step15": "step1",
        "step2": "step1",
        "step3": "step3-preflight",
        "step4": "step4",
    }[stage]


def stage_prerequisite_blockers(root: Path, stage: str) -> list[str]:
    docs = root / "Planner-docs"
    blockers: list[str] = []
    if stage in {"step15", "step2"} and not (docs / "Main-Planing.md").is_file():
        blockers.append("missing_prerequisite=Planner-docs/Main-Planing.md")
    if stage == "step3":
        if not (docs / "Sub-Planing-Index.md").is_file():
            blockers.append("missing_prerequisite=Planner-docs/Sub-Planing-Index.md")
        if not any(docs.glob("Faz-*-Plans/Faz*.md")):
            blockers.append("missing_prerequisite=active_subplans")
    if stage == "step4":
        audit = docs / "Sub-Planing-Audit.md"
        if not audit.is_file():
            blockers.append("missing_prerequisite=Planner-docs/Sub-Planing-Audit.md")
        else:
            text = audit.read_text(encoding="utf-8", errors="replace")
            if "READY" not in text and "NO_ACTION_REQUIRED" not in text:
                blockers.append("missing_prerequisite=step4_ready_queue_or_no_action")
    if blockers:
        return blockers
    validator_mode = stage_validator_mode(stage)
    code, output = run_bundled_validator(root, validator_mode, strict=True)
    if code != 0:
        blockers.append(f"validator_failed={validator_mode}")
        blockers.append(f"validator_output_sha256={sha256_bytes(output.encode('utf-8'))}")
    return blockers


def project_name(root: Path) -> str:
    main = root / "Planner-docs" / "Main-Planing.md"
    if main.is_file():
        text = main.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"Project\s+Name\s*[:|-]\s*(.+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()[:120]
    return root.name


def extract_ready_queue(root: Path) -> list[dict[str, str]]:
    audit = root / "Planner-docs" / "Sub-Planing-Audit.md"
    if not audit.is_file():
        return []
    text = audit.read_text(encoding="utf-8", errors="replace")
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(
        r"\b(READY_WITH_WARNINGS|READY)\b\s*:?\s*`?((?:Planner-docs/)?Faz-\d+-Plans/Faz\d+\.\d+-[a-z0-9-]+\.md)`?",
        text,
        flags=re.IGNORECASE,
    ):
        path = match.group(2)
        if not path.startswith("Planner-docs/"):
            path = f"Planner-docs/{path}"
        key = (match.group(1).upper(), path)
        if key not in seen:
            seen.add(key)
            items.append({"readiness_status": key[0], "subplan_path": path})
    for line in text.splitlines():
        if "|" not in line or "---" in line:
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        path, status = cells[0], cells[1].upper()
        if status not in {"READY", "READY_WITH_WARNINGS"}:
            continue
        if not re.fullmatch(r"(?:Planner-docs/)?Faz-\d+-Plans/Faz\d+\.\d+-[a-z0-9-]+\.md", path):
            continue
        if not path.startswith("Planner-docs/"):
            path = f"Planner-docs/{path}"
        key = (status, path)
        if key not in seen:
            seen.add(key)
            items.append({"readiness_status": status, "subplan_path": path})
    return items


def extract_contract_signals(text: str) -> dict[str, list[str]]:
    patterns = {
        "acceptance_criteria": r"(?:acceptance|behavior|mp-ph\d+-as-\d+)",
        "allowed_paths": r"(?:allowed.*path|implementation[_ ]path|write[_ ]path)",
        "forbidden_paths": r"(?:forbidden[_ ]path|forbidden.*path|must not modify|do not modify)",
        "parent_signals": r"(?:parent[_ ]signal|parent acceptance|acceptance signal|signal id)",
        "dependencies": r"(?:depends_on|dependency|blocks|can_run_in_parallel|activation_conditions)",
        "framework_ownership": r"(?:framework ownership|ownership matrix|trl|vllm|peft)",
        "algorithmic_invariants": r"(?:invariant|rollout|policy fingerprint|trainer-step|stateful)",
        "structured_validation_commands": r"(?:validation[_ ]command|argv|expected_exit_code|probe_tier)",
        "security_requirements": r"(?:security[_ ]review|required security|risk[_ ]domain|secret|credential)",
    }
    signals = {key: [] for key in patterns}
    for line in text.splitlines():
        stripped = line.strip().strip("|").strip()
        if not stripped or len(stripped) > 240:
            continue
        lowered = stripped.lower()
        for key, pattern in patterns.items():
            if re.search(pattern, lowered):
                signals[key].append(stripped)
    return signals


def subplan_scope_item(root: Path, subplan_path: str) -> dict[str, object]:
    path = root / subplan_path
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    contract = extract_contract_signals(text)
    item: dict[str, object] = {
        "subplan_path": subplan_path,
        "subplan_sha256": sha256_bytes(path.read_bytes()) if path.is_file() else None,
        "contract_signals": contract,
    }
    item["security_review_required"] = any(
        "required" in signal.lower() or "risk" in signal.lower()
        for signal in contract["security_requirements"]
    )
    item["validation_command_count"] = len(contract["structured_validation_commands"])
    return item


def collect_subplan_scope(root: Path, subplans: list[str]) -> list[dict[str, object]]:
    return [subplan_scope_item(root, path) for path in subplans]


def collect_stage_scope(root: Path, stage: str) -> dict[str, object]:
    docs = root / "Planner-docs"
    subplans = [
        repo_relative(root, path)
        for path in sorted(docs.glob("Faz-*-Plans/Faz*.md"))
        if path.is_file()
    ] if docs.is_dir() else []
    scope: dict[str, object] = {"stage": stage, "project_root": "."}
    if stage in {"step2", "step3"}:
        scope["detailed_subplans"] = subplans
        scope["subplan_contracts"] = collect_subplan_scope(root, subplans)
        scope["subplan_count"] = len(subplans)
        scope["index_path"] = "Planner-docs/Sub-Planing-Index.md" if (docs / "Sub-Planing-Index.md").is_file() else None
    if stage == "step4":
        ready_queue = extract_ready_queue(root)
        enriched_queue: list[dict[str, object]] = []
        for item in ready_queue:
            enriched = dict(item)
            enriched.update(subplan_scope_item(root, item["subplan_path"]))
            enriched_queue.append(enriched)
        scope["ready_queue"] = enriched_queue
        scope["ready_count"] = len(ready_queue)
        scope["no_action_required"] = bool((docs / "Sub-Planing-Audit.md").is_file() and "NO_ACTION_REQUIRED" in (docs / "Sub-Planing-Audit.md").read_text(encoding="utf-8", errors="replace"))
    return scope


def stage_work_steps(stage: str, scope: dict[str, object]) -> list[str]:
    base = ["verify snapshot", "load canonical references"]
    if stage == "step2":
        subplans = scope.get("detailed_subplans", [])
        return base + [f"detail active sub-plan {path}" for path in subplans] + ["run Step 2 validation checkpoints", "write final report"]
    if stage == "step3":
        subplans = scope.get("detailed_subplans", [])
        return base + [f"audit sub-plan {path}" for path in subplans] + ["run step3-preflight then step3 validation", "write final report"]
    if stage == "step4":
        queue = scope.get("ready_queue", [])
        if isinstance(queue, list) and queue:
            return base + [f"execute ready sub-plan {item.get('subplan_path')}" for item in queue if isinstance(item, dict)] + ["update ledger/result artifacts", "write final report"]
        return base + ["confirm NO_ACTION_REQUIRED or blocked Step 4 readiness", "write final report"]
    return base + ["perform stage-specific work", "run validation checkpoints", "write final report"]


def validation_checkpoints_for(stage: str) -> list[dict[str, object]]:
    mode = stage if stage != "step15" else "autopsy"
    modes = ["step3-preflight", "step3"] if stage == "step3" else [mode]
    return [
        {
            "id": f"VAL-{index:02d}",
            "argv": [
                "python3",
                "plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py",
                "--root",
                ".",
                "--mode",
                checkpoint_mode,
            ],
            "network": "deny",
            "probe_tier": 1,
        }
        for index, checkpoint_mode in enumerate(modes, start=1)
    ]


def checkpoint_is_safe(checkpoint: object) -> bool:
    if not isinstance(checkpoint, dict):
        return False
    argv = checkpoint.get("argv")
    if not isinstance(argv, list):
        return False
    expected_prefix = [
        "python3",
        "plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py",
        "--root",
        ".",
        "--mode",
    ]
    if len(argv) != len(expected_prefix) + 1:
        return False
    if argv[: len(expected_prefix)] != expected_prefix:
        return False
    if not isinstance(argv[-1], str) or argv[-1] not in {"autopsy", "step2", "step3-preflight", "step3", "step4"}:
        return False
    if checkpoint.get("network") != "deny":
        return False
    if checkpoint.get("probe_tier") != 1:
        return False
    return True


def default_goal_run(
    root: Path,
    stage: str,
    mode: str | None = None,
    objective: str | None = None,
    run_id_suffix: str | None = None,
) -> dict[str, object]:
    sources = collect_sources(root, stage)
    digest = snapshot_digest(stage, sources)
    selected_mode = mode or ("subagent_serial" if stage == "step4" else "wave")
    selected_objective = objective or f"Run CodexQB {stage} using current repository planning evidence."
    active_scope = collect_stage_scope(root, stage)
    spec_digest = goal_spec_digest(stage, sources, selected_mode, selected_objective, active_scope)
    bundle = template_bundle(stage)
    suffix = invocation_suffix(run_id_suffix)
    run_id = goal_run_id_for(stage, spec_digest, suffix)
    allowed_writes = {
        "step15": ["Planner-docs/Autopsy.md", "Planner-docs/Project-Ontology.md", "Planner-docs/Project-Comprehension.md"],
        "step2": ["Planner-docs/Sub-Planing-Index.md", "Planner-docs/Planing-Ledger.md", "Planner-docs/Faz-*-Plans/*.md"],
        "step3": ["Planner-docs/Sub-Planing-Audit.md"],
        "step4": ["Planner-docs/Planing-Ledger.md"],
    }[stage]
    return {
        "goal_run_schema_version": GOAL_RUN_SCHEMA_VERSION,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "handoff_contract_version": HANDOFF_CONTRACT_VERSION,
        "goal_spec_id": f"spec-{stage}-{spec_digest[:16]}",
        "goal_spec_digest": spec_digest,
        "goal_run_id": run_id,
        "goal_run_invocation_id": suffix,
        "stage": stage,
        "stage_contract_version": HANDOFF_CONTRACT_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "template_bundle": bundle["templates"],
        "template_bundle_digest": bundle["digest"],
        "compiler": bundle["compiler"],
        "project_name": project_name(root),
        "mode": selected_mode,
        "objective": selected_objective,
        "source_snapshot": sources,
        "source_snapshot_digest": digest,
        "required_inputs": [item["path"] for item in sources if item["scope"] in {"repo", "skill"}],
        "allowed_writes": allowed_writes,
        "forbidden_writes": ["~/.codex/**", ".git/**", ".env", "**/*.key", "**/*.pem"],
        "active_scope": active_scope,
        "work_steps": stage_work_steps(stage, active_scope),
        "validation_checkpoints": validation_checkpoints_for(stage),
        "stop_gates": ["snapshot mismatch", "P0/P1 blocker", "unsafe path", "required user confirmation missing", "dirty unrelated worktree"],
        "subagent_plan": {"max_depth": 1, "roles": []},
        "context_token_budget": {"risk": "medium", "confirmation_required": stage in {"step2", "step4"}},
        "final_report_contract": ["files changed", "validations", "blockers", "next action"],
        "user_confirmation_required": stage in {"step2", "step4"},
        "generated_at": f"invocation:{suffix}",
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
    mode = str(run.get("mode", ""))
    if mode not in STAGE_MODES[stage]:
        errors.append(f"invalid_goal_mode={mode or 'missing'}")
    objective = run.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        errors.append("objective_required")
    work_steps = run.get("work_steps")
    if (
        not isinstance(work_steps, list)
        or not work_steps
        or any(not isinstance(item, str) or not item.strip() for item in work_steps)
    ):
        errors.append("work_steps_required")
    checkpoints = run.get("validation_checkpoints")
    if (
        not isinstance(checkpoints, list)
        or not checkpoints
        or any(not checkpoint_is_safe(item) for item in checkpoints)
    ):
        errors.append("invalid_validation_checkpoints")
    subagent_plan = run.get("subagent_plan")
    if not isinstance(subagent_plan, dict) or subagent_plan.get("max_depth") != 1:
        errors.append("invalid_subagent_plan")
    token_budget = run.get("context_token_budget")
    if not isinstance(token_budget, dict) or token_budget.get("risk") not in {"low", "medium", "high"}:
        errors.append("invalid_context_token_budget")
    bundle = template_bundle(stage)
    if run.get("template_bundle") != bundle["templates"]:
        errors.append("template_bundle_mismatch")
    if run.get("template_bundle_digest") != bundle["digest"]:
        errors.append("template_bundle_digest_mismatch")
    if run.get("compiler") != bundle["compiler"]:
        errors.append("compiler_digest_mismatch")
    spec_digest = goal_spec_digest(
        stage,
        run.get("source_snapshot", []) if isinstance(run.get("source_snapshot"), list) else [],
        str(run.get("mode", "")),
        str(run.get("objective", "")),
        run.get("active_scope", {}) if isinstance(run.get("active_scope"), dict) else {},
    )
    if run.get("goal_spec_digest") != spec_digest:
        errors.append("stored_goal_spec_digest_mismatch")
    if run.get("goal_spec_id") != f"spec-{stage}-{spec_digest[:16]}":
        errors.append("stored_goal_spec_id_mismatch")
    invocation = str(run.get("goal_run_invocation_id", ""))
    if not invocation or invocation_suffix(invocation) != invocation:
        errors.append("invalid_goal_run_invocation_id")
    expected_run_id = f"goal-{stage}-{spec_digest[:12]}-{invocation}" if invocation else ""
    if run.get("goal_run_id") != expected_run_id:
        errors.append("stored_goal_run_id_mismatch")
    text = json.dumps(run, sort_keys=True)
    if has_secret_like(text):
        errors.append("secret_like_content")

    allowed = set(str(item) for item in run.get("allowed_writes", []) if isinstance(item, str))
    forbidden = set(str(item) for item in run.get("forbidden_writes", []) if isinstance(item, str))
    if allowed & forbidden or any(glob_patterns_overlap(left, right) for left in allowed for right in forbidden):
        errors.append("overlapping_allowed_forbidden_writes")
    for path in allowed:
        if not is_safe_repo_path(path, allow_glob=True):
            errors.append(f"unsafe_path={path}")
    for path in forbidden:
        if not is_safe_repo_path(path, allow_glob=True, allow_home=True):
            errors.append(f"unsafe_path={path}")

    stored_sources = run.get("source_snapshot")
    if not isinstance(stored_sources, list):
        errors.append("invalid_source_snapshot")
        stored_sources = []
    elif run.get("source_snapshot_digest") != snapshot_digest(stage, stored_sources):
        errors.append("stored_source_snapshot_digest_mismatch")

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


def compile_goal(
    root: Path,
    stage: str,
    output_dir: Path | None = None,
    mode: str | None = None,
    objective: str | None = None,
    *,
    replace: bool = False,
    resume: bool = False,
    run_id_suffix: str | None = None,
) -> dict[str, object]:
    root = root.resolve()
    if stage not in STAGE_REFERENCES:
        raise ValueError(f"unsupported stage: {stage}")
    if resume and output_dir is None:
        raise ValueError("resume_requires_output_dir")
    run = default_goal_run(root, stage, mode, objective, run_id_suffix)
    errors = validate_goal_run(root, run)
    if errors:
        raise ValueError(";".join(errors))
    out_dir = (output_dir or root / "Planner-docs" / "Goal-Runs" / str(run["goal_run_id"])).resolve()
    if not is_inside(root, out_dir):
        raise ValueError("output_dir must be inside the target repository")
    if resume:
        run_path = out_dir / "Goal-Run.json"
        if not run_path.is_file():
            raise ValueError(f"goal_run_resume_missing={out_dir.relative_to(root).as_posix()}")
        existing = load_goal_run(run_path)
        existing_errors = validate_goal_run(root, existing)
        if existing_errors:
            raise ValueError(";".join(existing_errors))
        result_path = out_dir / "Goal-Result.json"
        result = load_goal_run(result_path) if result_path.is_file() else {
            "goal_run_id": existing.get("goal_run_id"),
            "stage": existing.get("stage"),
            "status": "resumed",
        }
        return {"run": existing, "result": result, "output_dir": out_dir.as_posix()}
    if out_dir.exists() and not replace and not resume:
        raise ValueError(f"goal_run_already_exists={out_dir.relative_to(root).as_posix()}")
    out_dir.mkdir(parents=True, exist_ok=True)

    blockers = stage_prerequisite_blockers(root, stage)
    run_json = json.dumps(run, indent=2, sort_keys=True) + "\n"
    if blockers:
        result = {
            "goal_run_id": run["goal_run_id"],
            "stage": stage,
            "status": "blocked",
            "blockers": blockers,
            "goal_run_sha256": sha256_bytes(run_json.encode("utf-8")),
            "source_count": len(run["source_snapshot"]),
            "next_action": "Repair missing prerequisites, then prepare this Goal run again.",
        }
        (out_dir / "Goal-Run.json").write_text(run_json, encoding="utf-8")
        prompt_path = out_dir / "Goal-Prompt.md"
        if prompt_path.exists():
            prompt_path.unlink()
        (out_dir / "Goal-Result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"run": run, "result": result, "output_dir": out_dir.as_posix()}

    prompt = render_prompt_from_run(run)
    result = {
        "goal_run_id": run["goal_run_id"],
        "stage": stage,
        "status": "ready",
        "goal_run_sha256": sha256_bytes(run_json.encode("utf-8")),
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        "source_count": len(run["source_snapshot"]),
        "next_action": "Review Goal-Prompt.md, then paste it into Goal mode only if the stage and safety policy match the intended run.",
    }
    (out_dir / "Goal-Run.json").write_text(run_json, encoding="utf-8")
    (out_dir / "Goal-Prompt.md").write_text(prompt, encoding="utf-8")
    (out_dir / "Goal-Result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"run": run, "result": result, "output_dir": out_dir.as_posix()}


def render_goal_file(root: Path, goal_run_path: Path, output: Path | None = None) -> str:
    run = load_goal_run(goal_run_path)
    errors = validate_goal_run(root.resolve(), run)
    if errors:
        raise ValueError(";".join(errors))
    prompt = render_prompt_from_run(run)
    if output:
        output.write_text(prompt, encoding="utf-8")
    return prompt


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
    prepare.add_argument("--replace", action="store_true")
    prepare.add_argument("--resume", action="store_true")
    prepare.add_argument("--run-id-suffix")
    validate = sub.add_parser("validate", help="Validate Goal-Run.json against current snapshot.")
    validate.add_argument("--root", default=".")
    validate.add_argument("--goal-run", required=True)
    render = sub.add_parser("render", help="Render Goal-Prompt.md from Goal-Run.json.")
    render.add_argument("--root", default=".")
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
            compiled = compile_goal(
                Path(args.root),
                args.stage,
                Path(args.output_dir) if args.output_dir else None,
                args.mode,
                args.objective,
                replace=args.replace,
                resume=args.resume,
                run_id_suffix=args.run_id_suffix,
            )
            print(f"goal_run_status={compiled['result']['status']}")
            print(f"goal_run_id={compiled['result']['goal_run_id']}")
            print(f"output_dir={compiled['output_dir']}")
            return 0 if compiled["result"]["status"] == "ready" else 1
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
            prompt = render_goal_file(Path(args.root), Path(args.goal_run), Path(args.output) if args.output else None)
            if not args.output:
                print(prompt, end="")
            return 0
    except Exception as exc:
        print("goal_run_status=failed", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
