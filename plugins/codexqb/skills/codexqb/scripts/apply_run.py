#!/usr/bin/env python3
"""Create and validate CodexQB Step 4 apply-run artifacts.

This script manages artifact contracts only. It does not implement code, run
tests, call Codex tools, commit, push, create PRs, deploy, or mutate external
systems.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from safety_contracts import (  # noqa: E402
    path_is_inside,
    safe_validation_command_item,
)


ARTIFACT_SCHEMA_VERSION = 3
HANDOFF_CONTRACT_VERSION = 2
APPLY_RUN_SCHEMA_VERSION = 1
PLUGIN_VERSION = "0.3.0"
VALIDATOR_PATH = Path(__file__).resolve().with_name("validate_planner_docs.py")

APPLY_MODES = {"direct", "subagent_serial", "external_superpowers", "no_action"}
TASK_STATES = {
    "PREFLIGHT",
    "BRIEFED",
    "IMPLEMENTING",
    "IMPLEMENTED",
    "TASK_REVIEW",
    "SECURITY_REVIEW",
    "FIXING",
    "RE_REVIEW",
    "VERIFIED",
    "BLOCKED",
    "NEEDS_CONTEXT",
}
IMPLEMENTER_STATUSES = {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}
SPEC_VERDICTS = {"pass", "fail", "cannot_verify"}
QUALITY_VERDICTS = {"approved", "needs_fixes"}
SECURITY_VERDICTS = {"pass", "fail", "not_required"}
COMMIT_POLICIES = {"none", "local_per_slice", "user_managed"}
READY_STATUSES = {"READY", "READY_WITH_WARNINGS"}
DISPATCH_ROLES = {"implementer", "task_reviewer", "security_reviewer", "fixer"}
DISPATCH_AGENT_STATUSES = {"spawned", "completed", "failed"}
DISPATCH_ROLE_STATE_REQUIREMENTS = {
    "implementer": {"BRIEFED"},
    "task_reviewer": {"IMPLEMENTED", "TASK_REVIEW"},
    "security_reviewer": {"SECURITY_REVIEW"},
    "fixer": {"FIXING"},
}
AGENT_PROFILES = {
    "controller": {"agent_type": "default", "model_profile": "balanced", "sandbox": "workspace-write"},
    "explorer": {"agent_type": "explorer", "model_profile": "fast", "sandbox": "read-only"},
    "implementer": {"agent_type": "worker", "model_profile": "balanced", "sandbox": "workspace-write"},
    "task_reviewer": {"agent_type": "default", "model_profile": "strong", "sandbox": "read-only"},
    "security_reviewer": {"agent_type": "default", "model_profile": "security_strong", "sandbox": "read-only"},
    "fixer": {"agent_type": "worker", "model_profile": "balanced", "sandbox": "workspace-write"},
    "final_reviewer": {"agent_type": "default", "model_profile": "strong", "sandbox": "read-only"},
}
STATE_TRANSITIONS = {
    "PREFLIGHT": {"BRIEFED"},
    "BRIEFED": {"IMPLEMENTING", "BLOCKED", "NEEDS_CONTEXT"},
    "IMPLEMENTING": {"IMPLEMENTED", "BLOCKED", "NEEDS_CONTEXT"},
    "IMPLEMENTED": {"TASK_REVIEW"},
    "TASK_REVIEW": {"SECURITY_REVIEW", "FIXING", "VERIFIED"},
    "FIXING": {"RE_REVIEW", "BLOCKED", "NEEDS_CONTEXT"},
    "RE_REVIEW": {"SECURITY_REVIEW", "VERIFIED", "FIXING"},
    "SECURITY_REVIEW": {"VERIFIED", "FIXING", "BLOCKED", "NEEDS_CONTEXT"},
    "VERIFIED": set(),
    "BLOCKED": set(),
    "NEEDS_CONTEXT": set(),
}
WRITER_LOCK_NAME = "Writer-Lock.json"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: object) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def append_event(run_dir: Path, event: dict[str, object]) -> dict[str, object]:
    path = run_dir / "Events.jsonl"
    sequence = 1
    if path.is_file():
        with path.open("r", encoding="utf-8") as handle:
            sequence += sum(1 for line in handle if line.strip())
    record = {
        "sequence": sequence,
        "timestamp": utc_now(),
        **event,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return record


def load_events(run_dir: Path, errors: list[str]) -> list[dict[str, object]]:
    path = run_dir / "Events.jsonl"
    if not path.is_file():
        errors.append("missing_events_jsonl")
        return []
    events: list[dict[str, object]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"invalid_event_json=line-{line_no}")
            continue
        if not isinstance(event, dict):
            errors.append(f"invalid_event_object=line-{line_no}")
            continue
        events.append(event)
    for expected, event in enumerate(events, start=1):
        if event.get("sequence") != expected:
            errors.append(f"invalid_event_sequence={event.get('sequence')}")
    return events


def safe_task_id(value: str) -> bool:
    return bool(re.fullmatch(r"AR-apply-[A-Za-z0-9_.-]+-T\d{3}", value))


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


def collect_snapshot(root: Path) -> list[dict[str, str]]:
    planner = root / "Planner-docs"
    files = sorted(planner.glob("**/*.md")) if planner.is_dir() else []
    snapshot = [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_bytes(path.read_bytes())}
        for path in files
        if path.is_file() and path.name != "Planing-Ledger.md"
    ]
    branch = run_git(root, ["branch", "--show-current"]) or "unknown"
    commit = run_git(root, ["rev-parse", "HEAD"]) or "unknown"
    status = run_git(root, ["status", "--short"]) or ""
    staged = run_git(root, ["diff", "--cached", "--binary"]) or ""
    unstaged = run_git(root, ["diff", "--binary"]) or ""
    snapshot.append({"path": "git:branch", "sha256": sha256_bytes(branch.encode("utf-8")), "value": branch})
    snapshot.append({"path": "git:commit", "sha256": sha256_bytes(commit.encode("utf-8")), "value": commit})
    snapshot.append({"path": "git:status", "sha256": sha256_bytes(status.encode("utf-8"))})
    snapshot.append({"path": "git:staged_diff", "sha256": sha256_bytes(staged.encode("utf-8"))})
    snapshot.append({"path": "git:unstaged_diff", "sha256": sha256_bytes(unstaged.encode("utf-8"))})
    return snapshot


def snapshot_digest(snapshot: list[dict[str, str]]) -> str:
    return sha256_bytes(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def invocation_suffix(value: str | None = None) -> str:
    raw = value or f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{os.getpid()}"
    suffix = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-._")
    if not suffix:
        raise ValueError("invalid_run_id_suffix")
    return suffix[:64]


def apply_spec_digest(mode: str, snapshot: list[dict[str, str]], ready_queue: list[dict[str, str]]) -> str:
    payload = {
        "mode": mode,
        "source_snapshot": snapshot,
        "ready_queue": ready_queue,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "handoff_contract_version": HANDOFF_CONTRACT_VERSION,
        "apply_run_schema_version": APPLY_RUN_SCHEMA_VERSION,
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def apply_run_id(mode: str, snapshot: list[dict[str, str]], ready_queue: list[dict[str, str]] | None = None, run_id_suffix: str | None = None) -> str:
    digest = apply_spec_digest(mode, snapshot, ready_queue or [])
    return f"apply-{mode}-{digest[:12]}-{invocation_suffix(run_id_suffix)}"


def infer_root(run_dir: Path) -> Path | None:
    parts = run_dir.resolve().parts
    if len(parts) >= 3 and parts[-3:-1] == (".codexqb", "apply-runs"):
        return run_dir.resolve().parents[2]
    return None


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


def audit_text(root: Path) -> str:
    audit = root / "Planner-docs" / "Sub-Planing-Audit.md"
    if not audit.is_file():
        return ""
    return audit.read_text(encoding="utf-8", errors="replace")


def run_step4_validator(root: Path) -> tuple[int, str]:
    command = [
        sys.executable,
        VALIDATOR_PATH.as_posix(),
        "--root",
        root.as_posix(),
        "--mode",
        "step4",
        "--strict",
    ]
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


def validator_metric(output: str, key: str) -> str:
    prefix = f"{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip()
    return ""


def validate_step4_queue(root: Path, mode: str) -> dict[str, str]:
    audit = root / "Planner-docs" / "Sub-Planing-Audit.md"
    if not audit.is_file():
        raise ValueError("missing_step4_audit=Planner-docs/Sub-Planing-Audit.md")
    code, output = run_step4_validator(root)
    output_hash = sha256_bytes(output.encode("utf-8"))
    if code != 0:
        raise ValueError(f"step4_validator_failed={output_hash}")
    queue_state = validator_metric(output, "execution_queue_state") or "unknown"
    if mode == "no_action":
        if queue_state != "NO_ACTION_REQUIRED":
            raise ValueError(f"no_action_requires_no_action_required_audit={queue_state}")
        return {"validator_status": "passed", "execution_queue_state": queue_state, "validator_output_sha256": output_hash}
    if not extract_ready_queue(root):
        if "NO_ACTION_REQUIRED" in audit_text(root):
            raise ValueError("no_action_required_use_no_action_mode")
        raise ValueError("missing_step4_ready_queue")
    if queue_state == "NO_ACTION_REQUIRED":
        raise ValueError("no_action_required_use_no_action_mode")
    return {"validator_status": "passed", "execution_queue_state": queue_state, "validator_output_sha256": output_hash}


def extract_contract_signals(text: str) -> dict[str, list[str]]:
    patterns = {
        "acceptance_criteria": r"(?:acceptance|behavior)",
        "allowed_paths": r"(?:allowed.*path|implementation path|write path)",
        "forbidden_paths": r"(?:forbidden.*path|must not modify|do not modify)",
        "parent_signals": r"(?:parent acceptance|acceptance signal|signal id)",
        "dependencies": r"(?:depends_on|dependency|blocks|can_run_in_parallel|activation_conditions)",
        "framework_ownership": r"(?:framework ownership|ownership matrix|trl|vllm|peft)",
        "algorithmic_invariants": r"(?:invariant|rollout|policy fingerprint|trainer-step|stateful)",
        "structured_validation_commands": r"(?:validation command|argv|expected_exit_code|probe_tier)",
        "security_requirements": r"(?:security review|required security|risk domain|secret|credential)",
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


def extract_subplan_contract(root: Path, subplan_path: str) -> dict[str, list[str]]:
    path = root / subplan_path
    if not path.is_file():
        return {key: [] for key in extract_contract_signals("").keys()}
    return extract_contract_signals(path.read_text(encoding="utf-8", errors="replace"))


def task_id_for(run_id: str, index: int) -> str:
    return f"AR-{run_id}-T{index:03d}"


def default_tasks(root: Path, mode: str, run_id: str, ready_queue: list[dict[str, str]] | None = None) -> list[dict[str, object]]:
    if mode == "no_action":
        return []
    queue = ready_queue if ready_queue is not None else extract_ready_queue(root)
    tasks: list[dict[str, object]] = []
    for index, item in enumerate(queue, start=1):
        subplan_path = item["subplan_path"]
        subplan = root / subplan_path
        contract = extract_subplan_contract(root, subplan_path)
        tasks.append(
            {
                "task_id": task_id_for(run_id, index),
                "state": "BRIEFED",
                "readiness_status": item["readiness_status"],
                "source_subplan_path": subplan_path,
                "source_subplan_sha256": sha256_bytes(subplan.read_bytes()) if subplan.is_file() else None,
                "fresh_context_contract": contract,
                "finding_ids": [],
                "security_review_required": False,
                "writer_lock": None,
                "validation_commands": [],
                "dispatch": None,
                "agent_runs": [],
                "redispatch_count": 0,
            }
        )
    return tasks


def step4_readiness_summary(
    root: Path,
    mode: str,
    ready_queue: list[dict[str, str]],
    validation: dict[str, str],
) -> dict[str, object]:
    audit = root / "Planner-docs" / "Sub-Planing-Audit.md"
    text = audit_text(root)
    queue_state = validation.get("execution_queue_state", "")
    return {
        "audit_path": "Planner-docs/Sub-Planing-Audit.md",
        "audit_present": audit.is_file(),
        "ready_queue_count": len(ready_queue),
        "no_action_required": queue_state == "NO_ACTION_REQUIRED" or "NO_ACTION_REQUIRED" in text,
        "validator_command": [
            "python3",
            "plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py",
            "--root",
            ".",
            "--mode",
            "step4",
        ],
        "validator_status": validation.get("validator_status", "unknown"),
        "validator_output_sha256": validation.get("validator_output_sha256", ""),
        "execution_queue_state": queue_state,
        "execution_gate": "step4_validator_must_pass_before_product_changes",
        "mode": mode,
    }


def create_apply_run(
    root: Path,
    mode: str,
    output_dir: Path | None = None,
    commit_policy: str = "none",
    *,
    replace: bool = False,
    resume: bool = False,
    run_id_suffix: str | None = None,
) -> dict[str, object]:
    root = root.resolve()
    if mode not in APPLY_MODES:
        raise ValueError(f"unsupported apply mode: {mode}")
    if commit_policy not in COMMIT_POLICIES:
        raise ValueError(f"unsupported commit policy: {commit_policy}")
    if commit_policy != "none":
        raise ValueError("commit_policy defaults to none; other policies require explicit controller approval outside apply_run.py")
    if resume and output_dir is None:
        raise ValueError("resume_requires_output_dir")
    if resume:
        run_dir = output_dir.resolve() if output_dir else root
        if not is_inside(root, run_dir):
            raise ValueError("output_dir must be inside the target repository")
        run = load_json_strict(run_dir / "Apply-Run.json")
        errors = validate_apply_run(run_dir, root)
        if errors:
            raise ValueError(";".join(errors))
        return {"apply_run_id": str(run["apply_run_id"]), "run_dir": run_dir.as_posix(), "state": "resumed"}
    snapshot = collect_snapshot(root)
    ready_queue = [] if mode == "no_action" else extract_ready_queue(root)
    spec_digest = apply_spec_digest(mode, snapshot, ready_queue)
    suffix = invocation_suffix(run_id_suffix)
    run_id = apply_run_id(mode, snapshot, ready_queue, suffix)
    run_dir = (output_dir or root / ".codexqb" / "apply-runs" / run_id).resolve()
    if not is_inside(root, run_dir):
        raise ValueError("output_dir must be inside the target repository")
    step4_validation = validate_step4_queue(root, mode)
    if run_dir.exists() and not replace:
        raise ValueError(f"apply_run_already_exists={run_dir.relative_to(root).as_posix()}")
    if run_dir.exists() and replace:
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    tasks = default_tasks(root, mode, run_id, ready_queue)
    run = {
        "apply_run_schema_version": APPLY_RUN_SCHEMA_VERSION,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "handoff_contract_version": HANDOFF_CONTRACT_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "apply_requested_mode": mode,
        "apply_spec_id": f"apply-spec-{mode}-{spec_digest[:16]}",
        "apply_spec_digest": spec_digest,
        "apply_spec_inputs": {"ready_queue": ready_queue},
        "apply_run_id": run_id,
        "apply_run_invocation_id": suffix,
        "mode": mode,
        "workspace_requested": "isolated_worktree",
        "workspace_detected": "git" if run_git(root, ["rev-parse", "--is-inside-work-tree"]) == "true" else "non_git",
        "workspace_verified": False,
        "workspace_mode": "unverified_current_worktree",
        "commit_policy": commit_policy,
        "push_allowed": False,
        "pr_allowed": False,
        "max_writer_agents": 1,
        "max_subagent_depth": 1,
        "agent_profiles": AGENT_PROFILES,
        "source_snapshot": snapshot,
        "source_snapshot_digest": snapshot_digest(snapshot),
        "step4_readiness": step4_readiness_summary(root, mode, ready_queue, step4_validation),
        "external_superpowers": {
            "required": mode == "external_superpowers",
            "availability": "not_checked",
            "fallback_mode": "subagent_serial",
            "adapter_policy": "reconcile_before_dispatch",
        },
        "safety": {
            "executes_implementation": False,
            "allows_commit_push_pr_deploy": False,
            "one_writer_per_slice": True,
            "subagents_read_only_by_default": True,
        },
    }
    progress = {
        "apply_run_id": run_id,
        "mode": mode,
        "tasks": tasks,
        "verified_task_ids": [],
        "active_writer_locks": [],
        "final_review_required": mode != "no_action",
        "final_review_complete": mode == "no_action",
        "resume_cursor": None,
        "events": [],
    }
    result = {
        "apply_run_id": run_id,
        "status": "no_action" if mode == "no_action" else "initialized",
        "completed_tasks": [],
        "blocked_tasks": [],
        "next_action": "Use the Step 4 handoff to execute tasks; update Progress.json after each state transition.",
    }
    atomic_write_json(run_dir / "Apply-Run.json", run)
    atomic_write_json(run_dir / "Final-Review.json", {"status": "not_started" if mode != "no_action" else "not_required"})
    atomic_write_json(run_dir / "Result.json", result)
    for index, task in enumerate(tasks, start=1):
        task_dir = run_dir / str(task["task_id"])
        task_dir.mkdir(parents=True, exist_ok=True)
        brief = "\n".join(
            [
                f"# Task {index} Brief",
                "",
                f"- task_id: {task['task_id']}",
                f"- mode: {mode}",
                "- commit_policy: none",
                f"- source_subplan_path: {task.get('source_subplan_path')}",
                f"- source_subplan_sha256: {task.get('source_subplan_sha256')}",
                f"- readiness_status: {task.get('readiness_status')}",
                f"- fresh_context_contract: {json.dumps(task.get('fresh_context_contract', {}), sort_keys=True, separators=(',', ':'))}",
                "- dispatch_packet: generated by `apply_run.py dispatch` before subagent implementation",
                "- state_machine: BRIEFED -> IMPLEMENTING -> IMPLEMENTED -> TASK_REVIEW -> VERIFIED",
                "- report_paths: Dispatch-Packet.json, Implementer-Report.json, Task-Review.json, Fix-Report.json",
                "- stop_conditions: unsafe path, failing validation, missing evidence, required security review failure, snapshot mismatch",
                "",
            ]
        )
        task["brief_sha256"] = sha256_bytes(brief.encode("utf-8"))
        atomic_write_text(task_dir / "Brief.md", brief)
        atomic_write_json(task_dir / "Implementer-Report.json", {"status": "PENDING"})
        atomic_write_text(task_dir / "Review-Package.patch", "")
        atomic_write_json(task_dir / "Task-Review.json", {"status": "PENDING"})
        atomic_write_json(task_dir / "Fix-Report.json", {"status": "PENDING"})
    atomic_write_json(run_dir / "Progress.json", progress)
    append_event(
        run_dir,
        {
            "event_type": "apply_run_initialized",
            "apply_run_id": run_id,
            "mode": mode,
            "task_ids": [task["task_id"] for task in tasks],
            "actor": "apply_run.py",
        },
    )
    return {"apply_run_id": run_id, "run_dir": run_dir.as_posix(), "state": result["status"]}


def reconcile_external_superpowers(run_dir: Path) -> dict[str, object]:
    run_dir = run_dir.resolve()
    run = load_json_strict(run_dir / "Apply-Run.json")
    progress = load_json_strict(run_dir / "Progress.json")
    external = run.get("external_superpowers")
    if run.get("mode") != "external_superpowers":
        return {"state": "unchanged", "mode": run.get("mode")}
    if not isinstance(external, dict):
        raise ValueError("external_superpowers_policy_missing")
    availability = external.get("availability")
    if availability == "not_checked":
        raise ValueError("external_superpowers_readiness_not_checked")
    if availability == "available":
        missing = []
        for key in ("version", "source_path", "adapter_policy"):
            if not external.get(key):
                missing.append(key)
        if external.get("license_acknowledged") is not True:
            missing.append("license_acknowledged")
        if missing:
            raise ValueError(f"external_superpowers_available_metadata_missing={','.join(missing)}")
        return {"state": "ready", "mode": "external_superpowers"}
    if availability != "unavailable":
        raise ValueError(f"external_superpowers_invalid_availability={availability}")
    if external.get("fallback_mode") != "subagent_serial":
        raise ValueError("external_superpowers_unavailable_requires_subagent_serial_fallback")

    run["mode"] = "subagent_serial"
    external["reconciled_to"] = "subagent_serial"
    external["reconciled_at"] = utc_now()
    external["adapter_policy"] = "fallback_to_subagent_serial"
    progress["mode"] = "subagent_serial"
    event = append_event(
        run_dir,
        {
            "event_type": "external_superpowers_reconciled",
            "from": "external_superpowers",
            "to": "subagent_serial",
            "actor": "apply_run.py",
            "evidence": ["external_superpowers availability unavailable; fallback_mode subagent_serial"],
        },
    )
    progress["events"] = [{"sequence": event["sequence"], "event_type": "external_superpowers_reconciled", "to": "subagent_serial"}]
    atomic_write_json(run_dir / "Apply-Run.json", run)
    atomic_write_json(run_dir / "Progress.json", progress)
    return {"state": "reconciled", "mode": "subagent_serial", "event_sequence": event["sequence"]}


def load_json(path: Path, errors: list[str], label: str) -> object:
    if not path.is_file():
        errors.append(f"missing_{label}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append(f"invalid_json={label}")
        return {}


def load_json_strict(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return data


def find_task(progress: dict[str, object], task_id: str) -> dict[str, object]:
    tasks = progress.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("progress_tasks_must_be_list")
    for task in tasks:
        if isinstance(task, dict) and task.get("task_id") == task_id:
            return task
    raise ValueError(f"unknown_task_id={task_id}")


def lock_payload(run_dir: Path, task_id: str, owner: str) -> dict[str, object]:
    return {
        "lock_id": sha256_bytes(f"{run_dir}:{task_id}:{owner}".encode("utf-8"))[:16],
        "task_id": task_id,
        "owner": owner,
        "acquired_at": utc_now(),
        "expires_in_seconds": 3600,
    }


def lock_expiry(lock: dict[str, object]) -> datetime | None:
    acquired = parse_utc_timestamp(lock.get("acquired_at"))
    expires = lock.get("expires_in_seconds")
    if acquired is None or not isinstance(expires, (int, float)) or expires < 0:
        return None
    return datetime.fromtimestamp(acquired.timestamp() + float(expires), timezone.utc)


def lock_is_expired(lock: dict[str, object], *, now: datetime | None = None) -> bool:
    expiry = lock_expiry(lock)
    if expiry is None:
        return False
    return (now or datetime.now(timezone.utc)) >= expiry


def acquire_writer_lock(run_dir: Path, progress: dict[str, object], task: dict[str, object], owner: str) -> dict[str, object]:
    locks = progress.get("active_writer_locks", [])
    if locks:
        raise ValueError("active_writer_lock_exists")
    lock = lock_payload(run_dir, str(task["task_id"]), owner)
    path = run_dir / WRITER_LOCK_NAME
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, (json.dumps(lock, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    progress["active_writer_locks"] = [lock]
    task["writer_lock"] = lock
    return lock


def release_writer_lock(run_dir: Path, progress: dict[str, object], task: dict[str, object], owner: str | None = None) -> dict[str, object] | None:
    path = run_dir / WRITER_LOCK_NAME
    lock: dict[str, object] | None = None
    if path.is_file():
        lock = load_json_strict(path)
        if owner and lock.get("owner") != owner:
            raise ValueError("writer_lock_owner_mismatch")
        path.unlink()
    progress["active_writer_locks"] = []
    task["writer_lock"] = None
    return lock


def transition_task_state(run_dir: Path, task_id: str, to_state: str, actor: str, evidence: list[str] | None = None) -> dict[str, object]:
    run_dir = run_dir.resolve()
    if not safe_task_id(task_id):
        raise ValueError(f"invalid_task_id={task_id or 'missing'}")
    if to_state not in TASK_STATES:
        raise ValueError(f"invalid_target_state={to_state}")
    if not actor.strip():
        raise ValueError("transition_actor_required")
    run = load_json_strict(run_dir / "Apply-Run.json")
    progress = load_json_strict(run_dir / "Progress.json")
    task = find_task(progress, task_id)
    from_state = str(task.get("state", ""))
    if to_state not in STATE_TRANSITIONS.get(from_state, set()):
        raise ValueError(f"invalid_transition={from_state}->{to_state}")
    if run.get("mode") == "subagent_serial" and to_state == "IMPLEMENTING":
        dispatch = task.get("dispatch")
        if not isinstance(dispatch, dict):
            raise ValueError(f"subagent_dispatch_packet_missing={task_id}")
        if dispatch.get("role") != "implementer" or dispatch.get("status") not in {"spawned", "completed"}:
            raise ValueError(f"subagent_dispatch_spawn_required={task_id}")
    if run.get("mode") == "subagent_serial" and from_state == "IMPLEMENTING" and to_state == "IMPLEMENTED":
        if not agent_run_completed(task, "implementer"):
            raise ValueError(f"subagent_dispatch_completion_required={task_id}")

    lock_event: dict[str, object] | None = None
    if to_state == "IMPLEMENTING":
        lock_event = acquire_writer_lock(run_dir, progress, task, actor)
    elif from_state == "IMPLEMENTING":
        lock_event = release_writer_lock(run_dir, progress, task, actor)

    task["state"] = to_state
    event = append_event(
        run_dir,
        {
            "event_type": "task_transition",
            "task_id": task_id,
            "from": from_state,
            "to": to_state,
            "actor": actor,
            "evidence": evidence or [],
            "writer_lock": lock_event,
        },
    )
    progress["resume_cursor"] = {"task_id": task_id, "state": to_state, "event_sequence": event["sequence"]}
    progress["events"] = [{"sequence": event["sequence"], "event_type": "task_transition", "task_id": task_id, "to": to_state}]
    atomic_write_json(run_dir / "Progress.json", progress)
    return event


def task_dir_for(run_dir: Path, task_id: str) -> Path:
    if not safe_task_id(task_id):
        raise ValueError(f"invalid_task_id={task_id or 'missing'}")
    task_dir = (run_dir / task_id).resolve()
    if not is_inside(run_dir, task_dir):
        raise ValueError(f"invalid_task_id={task_id or 'missing'}")
    return task_dir


def safe_agent_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.:-]{3,160}", value))


def agent_runs(task: dict[str, object]) -> list[dict[str, object]]:
    runs = task.get("agent_runs", [])
    return runs if isinstance(runs, list) else []


def next_agent_attempt(task: dict[str, object], role: str) -> int:
    attempts = [
        run.get("attempt")
        for run in agent_runs(task)
        if isinstance(run, dict) and run.get("role") == role and isinstance(run.get("attempt"), int)
    ]
    return max(attempts, default=0) + 1


def agent_run_completed(task: dict[str, object], role: str) -> bool:
    return any(
        isinstance(run, dict) and run.get("role") == role and run.get("status") == "completed"
        for run in agent_runs(task)
    )


def upsert_agent_run(task: dict[str, object], record: dict[str, object]) -> None:
    runs = agent_runs(task)
    replaced = False
    for index, run in enumerate(runs):
        if (
            isinstance(run, dict)
            and run.get("role") == record.get("role")
            and run.get("attempt") == record.get("attempt")
        ):
            runs[index] = record
            replaced = True
            break
    if not replaced:
        runs.append(record)
    task["agent_runs"] = runs


def dispatch_prompt(run: dict[str, object], task: dict[str, object], role: str, brief_text: str) -> str:
    profile = AGENT_PROFILES[role]
    task_id = str(task["task_id"])
    source_path = task.get("source_subplan_path")
    contract = json.dumps(task.get("fresh_context_contract", {}), indent=2, sort_keys=True)
    return "\n".join(
        [
            f"# CodexQB Fresh {role.replace('_', ' ').title()} Dispatch",
            "",
            "Use only this fresh task context. Do not assume parent chat history.",
            "Do not commit, push, open PRs, deploy, or mutate external systems.",
            "Stop and report a blocker on unsafe paths, missing sources, failed validation, secrets, or scope overflow.",
            "",
            f"- apply_run_id: {run.get('apply_run_id')}",
            f"- task_id: {task_id}",
            f"- role: {role}",
            f"- agent_type: {profile['agent_type']}",
            f"- model_profile: {profile['model_profile']}",
            f"- sandbox: {profile['sandbox']}",
            f"- source_subplan_path: {source_path}",
            f"- brief_sha256: {task.get('brief_sha256')}",
            "",
            "## Fresh Context Contract",
            "",
            "```json",
            contract,
            "```",
            "",
            "## Task Brief",
            "",
            brief_text.rstrip(),
            "",
            "## Required Return",
            "",
            "- List files changed or reviewed.",
            "- Record validation commands as structured argv with exit codes.",
            "- Write the expected report artifact for this role before asking the controller to transition state.",
            "- Include any blocker as a concise, actionable finding with evidence.",
            "",
        ]
    )


def prepare_dispatch_packet(
    run_dir: Path,
    task_id: str,
    role: str,
    actor: str,
    evidence: list[str] | None = None,
) -> dict[str, object]:
    run_dir = run_dir.resolve()
    if role not in DISPATCH_ROLES:
        raise ValueError(f"invalid_dispatch_role={role}")
    if not actor.strip():
        raise ValueError("dispatch_actor_required")
    run = load_json_strict(run_dir / "Apply-Run.json")
    if run.get("mode") != "subagent_serial":
        raise ValueError(f"dispatch_requires_subagent_serial_mode={run.get('mode')}")
    progress = load_json_strict(run_dir / "Progress.json")
    task = find_task(progress, task_id)
    state = str(task.get("state", ""))
    if state not in DISPATCH_ROLE_STATE_REQUIREMENTS[role]:
        raise ValueError(f"dispatch_requires_state={role}:{state or 'missing'}")
    existing = task.get("dispatch")
    if isinstance(existing, dict) and existing.get("status") in {"packet_ready", "spawned"}:
        raise ValueError(f"dispatch_already_active={task_id}")
    task_dir = task_dir_for(run_dir, task_id)
    brief_path = task_dir / "Brief.md"
    if not brief_path.is_file():
        raise ValueError(f"missing_task_brief={task_id}")
    brief_text = brief_path.read_text(encoding="utf-8")
    brief_sha = sha256_bytes(brief_text.encode("utf-8"))
    if task.get("brief_sha256") != brief_sha:
        raise ValueError(f"brief_hash_mismatch={task_id}")

    prompt = dispatch_prompt(run, task, role, brief_text)
    prompt_sha = sha256_bytes(prompt.encode("utf-8"))
    attempt = next_agent_attempt(task, role)
    packet = {
        "dispatch_packet_schema_version": 1,
        "task_id": task_id,
        "role": role,
        "attempt": attempt,
        "dispatch_status": "packet_ready",
        "spawn_tool": "multi_agent_v1.spawn_agent",
        "spawn_request": {
            "agent_type": AGENT_PROFILES[role]["agent_type"],
            "fork_context": False,
            "message": prompt,
        },
        "model_profile": AGENT_PROFILES[role]["model_profile"],
        "model_override": None,
        "sandbox": AGENT_PROFILES[role]["sandbox"],
        "brief_sha256": brief_sha,
        "prompt_sha256": prompt_sha,
        "run_relative_task_dir": task_id,
        "expected_report_paths": {
            "implementer": "Implementer-Report.json",
            "task_reviewer": "Task-Review.json",
            "security_reviewer": "Task-Review.json",
            "fixer": "Fix-Report.json",
        },
        "prepared_by": actor,
        "prepared_at": utc_now(),
    }
    packet_path = task_dir / "Dispatch-Packet.json"
    atomic_write_json(packet_path, packet)
    packet_sha = sha256_bytes(packet_path.read_bytes())
    event = append_event(
        run_dir,
        {
            "event_type": "subagent_dispatch_packet_prepared",
            "task_id": task_id,
            "role": role,
            "actor": actor,
            "evidence": evidence or [],
            "spawn_tool": "multi_agent_v1.spawn_agent",
            "agent_type": AGENT_PROFILES[role]["agent_type"],
            "brief_sha256": brief_sha,
            "prompt_sha256": prompt_sha,
            "packet_sha256": packet_sha,
            "attempt": attempt,
        },
    )
    task["dispatch"] = {
        "status": "packet_ready",
        "role": role,
        "spawn_tool": "multi_agent_v1.spawn_agent",
        "prompt_sha256": prompt_sha,
        "packet_sha256": packet_sha,
        "attempt": attempt,
        "event_sequence": event["sequence"],
    }
    progress["resume_cursor"] = {"task_id": task_id, "state": state, "event_sequence": event["sequence"]}
    progress["events"] = [
        {
            "sequence": event["sequence"],
            "event_type": "subagent_dispatch_packet_prepared",
            "task_id": task_id,
            "role": role,
        }
    ]
    atomic_write_json(run_dir / "Progress.json", progress)
    return {"event": event, "packet_path": packet_path.as_posix(), "packet_sha256": packet_sha}


def record_agent_status(
    run_dir: Path,
    task_id: str,
    role: str,
    agent_id: str,
    status: str,
    actor: str,
    evidence: list[str] | None = None,
    summary: str | None = None,
) -> dict[str, object]:
    run_dir = run_dir.resolve()
    if role not in DISPATCH_ROLES:
        raise ValueError(f"invalid_dispatch_role={role}")
    if status not in DISPATCH_AGENT_STATUSES:
        raise ValueError(f"invalid_agent_status={status}")
    if not safe_agent_id(agent_id):
        raise ValueError(f"invalid_agent_id={agent_id or 'missing'}")
    if not actor.strip():
        raise ValueError("record_agent_actor_required")
    run = load_json_strict(run_dir / "Apply-Run.json")
    if run.get("mode") != "subagent_serial":
        raise ValueError(f"record_agent_requires_subagent_serial_mode={run.get('mode')}")
    progress = load_json_strict(run_dir / "Progress.json")
    task = find_task(progress, task_id)
    dispatch = task.get("dispatch")
    if not isinstance(dispatch, dict):
        raise ValueError(f"subagent_dispatch_packet_missing={task_id}")
    if dispatch.get("role") != role:
        raise ValueError(f"dispatch_role_mismatch={task_id}:{role}")
    if status == "spawned":
        if dispatch.get("status") != "packet_ready":
            raise ValueError(f"dispatch_spawn_requires_packet_ready={task_id}")
    else:
        if dispatch.get("status") != "spawned":
            raise ValueError(f"dispatch_result_requires_spawned={task_id}")
        if dispatch.get("agent_id") != agent_id:
            raise ValueError(f"dispatch_agent_id_mismatch={task_id}")

    attempt = dispatch.get("attempt")
    if not isinstance(attempt, int) or attempt < 1:
        raise ValueError(f"dispatch_attempt_invalid={task_id}")
    now = utc_now()
    previous_runs = [
        item
        for item in agent_runs(task)
        if isinstance(item, dict) and item.get("role") == role and item.get("attempt") == attempt
    ]
    record = {
        "task_id": task_id,
        "role": role,
        "attempt": attempt,
        "agent_id": agent_id,
        "status": status,
        "packet_sha256": dispatch.get("packet_sha256"),
        "prompt_sha256": dispatch.get("prompt_sha256"),
        "spawn_tool": dispatch.get("spawn_tool"),
        "summary": summary or "",
    }
    if status == "spawned":
        record["spawned_at"] = now
    else:
        if previous_runs and previous_runs[0].get("spawned_at"):
            record["spawned_at"] = previous_runs[0]["spawned_at"]
        record[f"{status}_at"] = now
    upsert_agent_run(task, record)
    atomic_write_json(task_dir_for(run_dir, task_id) / f"Agent-Run-{role}-{attempt:02d}.json", record)

    dispatch["status"] = status
    dispatch["agent_id"] = agent_id
    dispatch["updated_at"] = now
    if summary:
        dispatch["summary"] = summary
    if status == "failed":
        dispatch["failure_recoverable"] = True
    task["dispatch"] = dispatch

    event = append_event(
        run_dir,
        {
            "event_type": "subagent_dispatch_status_recorded",
            "task_id": task_id,
            "role": role,
            "attempt": attempt,
            "agent_id": agent_id,
            "status": status,
            "actor": actor,
            "evidence": evidence or [],
            "summary": summary or "",
        },
    )
    progress["resume_cursor"] = {"task_id": task_id, "state": task.get("state"), "event_sequence": event["sequence"]}
    progress["events"] = [
        {
            "sequence": event["sequence"],
            "event_type": "subagent_dispatch_status_recorded",
            "task_id": task_id,
            "role": role,
            "status": status,
        }
    ]
    atomic_write_json(run_dir / "Progress.json", progress)
    return event


def recover_stale_writer_lock(
    run_dir: Path,
    task_id: str,
    to_state: str,
    actor: str,
    evidence: list[str] | None = None,
) -> dict[str, object]:
    run_dir = run_dir.resolve()
    if not safe_task_id(task_id):
        raise ValueError(f"invalid_task_id={task_id or 'missing'}")
    if to_state not in {"BLOCKED", "NEEDS_CONTEXT"}:
        raise ValueError(f"invalid_recovery_state={to_state}")
    if not actor.strip():
        raise ValueError("recovery_actor_required")
    progress = load_json_strict(run_dir / "Progress.json")
    task = find_task(progress, task_id)
    from_state = str(task.get("state", ""))
    if from_state != "IMPLEMENTING":
        raise ValueError(f"recovery_requires_implementing_state={from_state or 'missing'}")
    path = run_dir / WRITER_LOCK_NAME
    if not path.is_file():
        raise ValueError("writer_lock_missing")
    lock = load_json_strict(path)
    locks = progress.get("active_writer_locks", [])
    if not isinstance(locks, list) or len(locks) != 1 or locks[0] != lock or task.get("writer_lock") != lock:
        raise ValueError("writer_lock_recovery_requires_consistent_lock")
    if lock.get("task_id") != task_id:
        raise ValueError("writer_lock_task_mismatch")
    if lock_expiry(lock) is None:
        raise ValueError("writer_lock_expiry_invalid")
    if not lock_is_expired(lock):
        raise ValueError("writer_lock_not_expired")

    path.unlink()
    progress["active_writer_locks"] = []
    task["writer_lock"] = None
    task["state"] = to_state
    event = append_event(
        run_dir,
        {
            "event_type": "task_transition",
            "task_id": task_id,
            "from": from_state,
            "to": to_state,
            "actor": actor,
            "evidence": evidence or [],
            "writer_lock": {"recovered": True, "stale_lock": lock},
            "recovery": "stale_writer_lock",
        },
    )
    progress["resume_cursor"] = {"task_id": task_id, "state": to_state, "event_sequence": event["sequence"]}
    progress["events"] = [
        {
            "sequence": event["sequence"],
            "event_type": "task_transition",
            "task_id": task_id,
            "to": to_state,
            "recovery": "stale_writer_lock",
        }
    ]
    atomic_write_json(run_dir / "Progress.json", progress)
    return event


def finalize_apply_run(run_dir: Path, actor: str, evidence: list[str] | None = None) -> dict[str, object]:
    run_dir = run_dir.resolve()
    if not actor.strip():
        raise ValueError("finalize_actor_required")
    errors = validate_apply_run(run_dir)
    if errors:
        raise ValueError(";".join(errors))
    run = load_json_strict(run_dir / "Apply-Run.json")
    progress = load_json_strict(run_dir / "Progress.json")
    tasks = progress.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("progress_tasks_must_be_list")
    completed = [str(task["task_id"]) for task in tasks if isinstance(task, dict) and task.get("state") == "VERIFIED"]
    blocked = [
        str(task["task_id"])
        for task in tasks
        if isinstance(task, dict) and task.get("state") in {"BLOCKED", "NEEDS_CONTEXT"}
    ]
    if run.get("mode") != "no_action" and (len(completed) != len(tasks) or blocked):
        raise ValueError("finalize_requires_all_tasks_verified")
    final_review = load_json_strict(run_dir / "Final-Review.json")
    if run.get("mode") != "no_action" and final_review.get("status") != "pass":
        raise ValueError("finalize_requires_final_review_pass")
    event = append_event(
        run_dir,
        {
            "event_type": "apply_run_finalized",
            "actor": actor,
            "completed_task_ids": completed,
            "blocked_task_ids": blocked,
            "evidence": evidence or [],
        },
    )
    result = {
        "apply_run_id": run["apply_run_id"],
        "status": "no_action" if run.get("mode") == "no_action" else "complete",
        "completed_tasks": completed,
        "blocked_tasks": blocked,
        "finalized_at": event["timestamp"],
        "finalized_by": actor,
        "event_sequence": event["sequence"],
        "next_action": "Apply run is finalized; start a new apply run for additional READY queue work.",
    }
    atomic_write_json(run_dir / "Result.json", result)
    progress["events"] = [{"sequence": event["sequence"], "event_type": "apply_run_finalized"}]
    atomic_write_json(run_dir / "Progress.json", progress)
    return event


def command_is_safe(command: object) -> bool:
    if isinstance(command, list):
        return safe_validation_command_item({"argv": command})
    if isinstance(command, str):
        return safe_validation_command_item({"command": command})
    if isinstance(command, dict):
        return safe_validation_command_item(command)
    return False


def validate_dispatch_packet(run_dir: Path, run: dict[str, object], task: dict[str, object], errors: list[str]) -> None:
    task_id = str(task.get("task_id", ""))
    if not safe_task_id(task_id):
        return
    task_dir = (run_dir / task_id).resolve()
    packet_path = task_dir / "Dispatch-Packet.json"
    state = str(task.get("state", ""))
    if run.get("mode") == "subagent_serial" and state not in {"BRIEFED", "BLOCKED", "NEEDS_CONTEXT"}:
        if not packet_path.is_file():
            errors.append(f"subagent_dispatch_packet_missing={task_id}")
            return
    if not packet_path.is_file():
        if isinstance(task.get("dispatch"), dict):
            errors.append(f"subagent_dispatch_packet_missing={task_id}")
        return
    packet = load_json(packet_path, errors, f"{task_id}_dispatch_packet")
    if not isinstance(packet, dict):
        return
    role = str(packet.get("role", ""))
    if packet.get("dispatch_packet_schema_version") != 1:
        errors.append(f"invalid_dispatch_packet_schema_version={task_id}")
    if packet.get("task_id") != task_id:
        errors.append(f"dispatch_packet_task_mismatch={task_id}")
    if role not in DISPATCH_ROLES:
        errors.append(f"invalid_dispatch_role={task_id}:{role or 'missing'}")
        return
    if packet.get("spawn_tool") != "multi_agent_v1.spawn_agent":
        errors.append(f"dispatch_spawn_tool_mismatch={task_id}")
    spawn = packet.get("spawn_request")
    if not isinstance(spawn, dict):
        errors.append(f"dispatch_spawn_request_missing={task_id}")
        return
    if spawn.get("agent_type") != AGENT_PROFILES[role]["agent_type"]:
        errors.append(f"dispatch_agent_type_mismatch={task_id}")
    if spawn.get("fork_context") is not False:
        errors.append(f"dispatch_must_use_fresh_context={task_id}")
    message = spawn.get("message")
    if not isinstance(message, str) or not message.strip():
        errors.append(f"dispatch_prompt_missing={task_id}")
    elif packet.get("prompt_sha256") != sha256_bytes(message.encode("utf-8")):
        errors.append(f"dispatch_prompt_hash_mismatch={task_id}")
    brief_path = task_dir / "Brief.md"
    if brief_path.is_file() and packet.get("brief_sha256") != sha256_bytes(brief_path.read_bytes()):
        errors.append(f"dispatch_brief_hash_mismatch={task_id}")
    if packet.get("model_override") is not None:
        errors.append(f"dispatch_model_override_must_be_null={task_id}")
    if packet.get("model_profile") != AGENT_PROFILES[role]["model_profile"]:
        errors.append(f"dispatch_model_profile_mismatch={task_id}")
    if packet.get("sandbox") != AGENT_PROFILES[role]["sandbox"]:
        errors.append(f"dispatch_sandbox_mismatch={task_id}")
    if packet.get("attempt") is not None and not isinstance(packet.get("attempt"), int):
        errors.append(f"dispatch_attempt_invalid={task_id}")
    dispatch = task.get("dispatch")
    if isinstance(dispatch, dict):
        status = dispatch.get("status")
        if status not in {"packet_ready", *DISPATCH_AGENT_STATUSES}:
            errors.append(f"invalid_dispatch_status={task_id}:{status}")
        if dispatch.get("role") not in DISPATCH_ROLES:
            errors.append(f"invalid_dispatch_role={task_id}:{dispatch.get('role')}")
        if dispatch.get("packet_sha256") != sha256_bytes(packet_path.read_bytes()):
            errors.append(f"dispatch_packet_hash_mismatch={task_id}")
    elif run.get("mode") == "subagent_serial" and state not in {"BRIEFED", "BLOCKED", "NEEDS_CONTEXT"}:
        errors.append(f"subagent_dispatch_status_missing={task_id}")
    runs = task.get("agent_runs", [])
    if runs is not None and not isinstance(runs, list):
        errors.append(f"agent_runs_must_be_list={task_id}")
        runs = []
    for item in runs:
        if not isinstance(item, dict):
            errors.append(f"agent_run_must_be_object={task_id}")
            continue
        run_role = str(item.get("role", ""))
        run_status = str(item.get("status", ""))
        agent_id = str(item.get("agent_id", ""))
        if run_role not in DISPATCH_ROLES:
            errors.append(f"invalid_agent_run_role={task_id}:{run_role or 'missing'}")
        if run_status not in DISPATCH_AGENT_STATUSES:
            errors.append(f"invalid_agent_run_status={task_id}:{run_status or 'missing'}")
        if not isinstance(item.get("attempt"), int) or item.get("attempt", 0) < 1:
            errors.append(f"invalid_agent_run_attempt={task_id}")
        if not safe_agent_id(agent_id):
            errors.append(f"invalid_agent_run_agent_id={task_id}:{agent_id or 'missing'}")
        if not item.get("packet_sha256"):
            errors.append(f"agent_run_packet_hash_missing={task_id}")
        if run_status == "spawned" and not item.get("spawned_at"):
            errors.append(f"agent_run_spawned_at_missing={task_id}")
        if run_status in {"completed", "failed"} and not item.get(f"{run_status}_at"):
            errors.append(f"agent_run_result_timestamp_missing={task_id}")
    if isinstance(dispatch, dict) and dispatch.get("status") in DISPATCH_AGENT_STATUSES:
        matching = [
            item
            for item in runs
            if isinstance(item, dict)
            and item.get("role") == dispatch.get("role")
            and item.get("attempt") == dispatch.get("attempt")
            and item.get("agent_id") == dispatch.get("agent_id")
            and item.get("status") == dispatch.get("status")
            and item.get("packet_sha256") == dispatch.get("packet_sha256")
        ]
        if not matching:
            errors.append(f"dispatch_agent_run_missing={task_id}")
    if run.get("mode") == "subagent_serial" and state == "IMPLEMENTING":
        if not isinstance(dispatch, dict) or dispatch.get("role") != "implementer" or dispatch.get("status") not in {"spawned", "completed"}:
            errors.append(f"subagent_dispatch_spawn_required={task_id}")
    if run.get("mode") == "subagent_serial" and state in {"IMPLEMENTED", "TASK_REVIEW", "SECURITY_REVIEW", "FIXING", "RE_REVIEW", "VERIFIED"}:
        if not agent_run_completed(task, "implementer"):
            errors.append(f"subagent_dispatch_completion_required={task_id}")


def validate_task_artifacts(run_dir: Path, task: dict[str, object], errors: list[str]) -> None:
    task_id = str(task.get("task_id", ""))
    state = str(task.get("state", ""))
    if not safe_task_id(task_id):
        errors.append(f"invalid_task_id={task_id or 'missing'}")
        return
    if state not in TASK_STATES:
        errors.append(f"invalid_task_state={task_id}:{state or 'missing'}")
    if task.get("readiness_status") not in READY_STATUSES:
        errors.append(f"non_ready_queue_item={task_id}:{task.get('readiness_status')}")
    severities = {str(item).upper() for item in task.get("finding_ids", []) if isinstance(item, str)}
    if "P0" in severities or "P1" in severities:
        errors.append(f"p0_p1_queue_item_rejected={task_id}")
    for command in task.get("validation_commands", []):
        if not command_is_safe(command):
            errors.append(f"unsafe_validation_command={task_id}")

    task_dir = (run_dir / task_id).resolve()
    if not is_inside(run_dir, task_dir):
        errors.append(f"invalid_task_id={task_id or 'missing'}")
        return
    if not task_dir.is_dir():
        errors.append(f"missing_task_dir={task_id}")
        return
    if not (task_dir / "Brief.md").is_file():
        errors.append(f"missing_task_brief={task_id}")

    implementer = load_json(task_dir / "Implementer-Report.json", errors, f"{task_id}_implementer_report")
    review = load_json(task_dir / "Task-Review.json", errors, f"{task_id}_task_review")
    fix = load_json(task_dir / "Fix-Report.json", errors, f"{task_id}_fix_report")
    if not isinstance(implementer, dict) or not isinstance(review, dict) or not isinstance(fix, dict):
        return
    impl_status = implementer.get("status")
    if impl_status not in IMPLEMENTER_STATUSES and impl_status != "PENDING":
        errors.append(f"invalid_implementer_status={task_id}:{impl_status}")
    if impl_status == "DONE_WITH_CONCERNS" and not implementer.get("controller_decision"):
        errors.append(f"done_with_concerns_requires_controller_decision={task_id}")
    if impl_status == "BLOCKED" and state not in {"BLOCKED", "NEEDS_CONTEXT"}:
        errors.append(f"blocked_task_must_stop_or_replan={task_id}")
    if impl_status == "NEEDS_CONTEXT" and state != "NEEDS_CONTEXT":
        errors.append(f"needs_context_task_must_pause={task_id}")

    spec = review.get("spec_compliance")
    quality = review.get("task_quality")
    security = review.get("security_review", "not_required")
    if spec is not None and spec not in SPEC_VERDICTS and spec != "PENDING":
        errors.append(f"invalid_spec_compliance={task_id}:{spec}")
    if quality is not None and quality not in QUALITY_VERDICTS and quality != "PENDING":
        errors.append(f"invalid_task_quality={task_id}:{quality}")
    if security is not None and security not in SECURITY_VERDICTS and security != "PENDING":
        errors.append(f"invalid_security_review={task_id}:{security}")
    if spec in {"fail", "cannot_verify"} and not review.get("re_review_required"):
        errors.append(f"failed_spec_requires_re_review={task_id}")
    if quality == "needs_fixes" and not review.get("re_review_required"):
        errors.append(f"failed_quality_requires_re_review={task_id}")
    if review.get("re_review_required") is True and not fix.get("fixes"):
        errors.append(f"re_review_requires_fix_report={task_id}")
    if task.get("security_review_required") is True and security != "pass":
        errors.append(f"required_security_review_must_pass={task_id}")
    if state == "VERIFIED":
        if impl_status != "DONE":
            errors.append(f"verified_requires_done_implementer={task_id}")
        if not implementer.get("brief_sha256") or implementer.get("brief_sha256") != task.get("brief_sha256"):
            errors.append(f"verified_requires_matching_brief_hash={task_id}")
        if not implementer.get("implementer_agent_id"):
            errors.append(f"verified_requires_implementer_agent_id={task_id}")
        if not isinstance(implementer.get("files_changed"), list) or not implementer.get("files_changed"):
            errors.append(f"verified_requires_files_changed={task_id}")
        evidence = implementer.get("validation_evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"verified_requires_validation_evidence={task_id}")
        else:
            for item in evidence:
                if not isinstance(item, dict) or item.get("exit_code") != 0 or not command_is_safe(item):
                    errors.append(f"verified_requires_safe_passing_validation_evidence={task_id}")
                    break
        if spec != "pass":
            errors.append(f"verified_requires_spec_pass={task_id}")
        if quality != "approved":
            errors.append(f"verified_requires_quality_approved={task_id}")
        if review.get("brief_sha256") != task.get("brief_sha256"):
            errors.append(f"verified_requires_review_brief_hash={task_id}")
        if not review.get("reviewer_agent_id"):
            errors.append(f"verified_requires_reviewer_agent_id={task_id}")
        if review.get("reviewer_agent_id") and review.get("reviewer_agent_id") == implementer.get("implementer_agent_id"):
            errors.append(f"reviewer_must_be_independent={task_id}")
        if not isinstance(review.get("evidence"), list) or not review.get("evidence"):
            errors.append(f"verified_requires_review_evidence={task_id}")
        if task.get("security_review_required") is True and security != "pass":
            errors.append(f"verified_requires_security_pass={task_id}")


def validate_events(events: list[dict[str, object]], tasks: list[object], errors: list[str]) -> None:
    if events and events[0].get("event_type") != "apply_run_initialized":
        errors.append("first_event_must_initialize_apply_run")
    last_state: dict[str, str] = {}
    for event in events:
        if event.get("event_type") != "task_transition":
            continue
        task_id = str(event.get("task_id", ""))
        from_state = str(event.get("from", ""))
        to_state = str(event.get("to", ""))
        if not safe_task_id(task_id):
            errors.append(f"invalid_event_task_id={task_id or 'missing'}")
            continue
        if to_state not in STATE_TRANSITIONS.get(from_state, set()):
            errors.append(f"invalid_transition_event={task_id}:{from_state}->{to_state}")
        if task_id in last_state and last_state[task_id] != from_state:
            errors.append(f"non_contiguous_transition_event={task_id}")
        last_state[task_id] = to_state
        evidence = event.get("evidence", [])
        if not isinstance(evidence, list):
            errors.append(f"transition_evidence_must_be_list={task_id}")
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id", ""))
        state = str(task.get("state", ""))
        if state != "BRIEFED" and last_state.get(task_id) != state:
            errors.append(f"task_state_missing_transition_event={task_id}")


def validate_writer_lock(run_dir: Path, progress: dict[str, object], tasks: list[object], errors: list[str]) -> None:
    locks = progress.get("active_writer_locks", [])
    if not isinstance(locks, list):
        errors.append("active_writer_locks_must_be_list")
        locks = []
    if len(locks) > 1:
        errors.append("only_one_active_writer_lock_permitted")
    path = run_dir / WRITER_LOCK_NAME
    if locks and not path.is_file():
        errors.append("active_writer_lock_missing_file")
    if path.is_file():
        lock = load_json(path, errors, "writer_lock_json")
        if not isinstance(lock, dict):
            return
        if not locks:
            errors.append("writer_lock_file_without_progress_lock")
        elif lock != locks[0]:
            errors.append("writer_lock_file_progress_mismatch")
        task_id = str(lock.get("task_id", ""))
        owner = str(lock.get("owner", ""))
        if not safe_task_id(task_id):
            errors.append(f"invalid_writer_lock_task_id={task_id or 'missing'}")
        if not owner:
            errors.append("writer_lock_owner_required")
        matching = [task for task in tasks if isinstance(task, dict) and task.get("task_id") == task_id]
        if not matching:
            errors.append(f"writer_lock_unknown_task={task_id}")
            return
        task = matching[0]
        if task.get("writer_lock") != lock:
            errors.append(f"task_writer_lock_mismatch={task_id}")
        if task.get("state") != "IMPLEMENTING":
            errors.append(f"writer_lock_requires_implementing_state={task_id}")
        if lock_expiry(lock) is None:
            errors.append(f"writer_lock_expiry_invalid={task_id}")
        elif lock_is_expired(lock):
            errors.append(f"writer_lock_expired={task_id}")


def validate_agent_profiles(run: dict[str, object], errors: list[str]) -> None:
    profiles = run.get("agent_profiles")
    if not isinstance(profiles, dict):
        errors.append("agent_profiles_missing")
        return
    for role, expected in AGENT_PROFILES.items():
        actual = profiles.get(role)
        if not isinstance(actual, dict):
            errors.append(f"agent_profile_missing={role}")
            continue
        for key, value in expected.items():
            if actual.get(key) != value:
                errors.append(f"agent_profile_mismatch={role}:{key}")


def validate_apply_run(run_dir: Path, root: Path | None = None) -> list[str]:
    errors: list[str] = []
    run_dir = run_dir.resolve()
    root = root.resolve() if root else infer_root(run_dir)
    run = load_json(run_dir / "Apply-Run.json", errors, "apply_run_json")
    progress = load_json(run_dir / "Progress.json", errors, "progress_json")
    final_review = load_json(run_dir / "Final-Review.json", errors, "final_review_json")
    result = load_json(run_dir / "Result.json", errors, "result_json")
    events = load_events(run_dir, errors)
    if errors or not isinstance(run, dict) or not isinstance(progress, dict):
        return errors

    if run.get("apply_run_schema_version") != APPLY_RUN_SCHEMA_VERSION:
        errors.append("invalid_apply_run_schema_version")
    if run.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION:
        errors.append("invalid_artifact_schema_version")
    if run.get("handoff_contract_version") != HANDOFF_CONTRACT_VERSION:
        errors.append("invalid_handoff_contract_version")
    if run.get("plugin_version") != PLUGIN_VERSION:
        errors.append("invalid_plugin_version")
    if run.get("mode") not in APPLY_MODES:
        errors.append(f"invalid_mode={run.get('mode')}")
    requested_mode = str(run.get("apply_requested_mode", run.get("mode", "")))
    if requested_mode not in APPLY_MODES:
        errors.append(f"invalid_apply_requested_mode={requested_mode or 'missing'}")
    source_snapshot = run.get("source_snapshot")
    if not isinstance(source_snapshot, list):
        errors.append("invalid_source_snapshot")
        source_snapshot = []
    spec_inputs = run.get("apply_spec_inputs")
    ready_queue: list[dict[str, str]] = []
    if isinstance(spec_inputs, dict) and isinstance(spec_inputs.get("ready_queue"), list):
        for item in spec_inputs["ready_queue"]:
            if isinstance(item, dict):
                ready_queue.append({str(key): str(value) for key, value in item.items()})
            else:
                errors.append("invalid_apply_spec_ready_queue")
                break
    else:
        errors.append("missing_apply_spec_inputs")
    spec_digest = apply_spec_digest(requested_mode, source_snapshot, ready_queue)
    if run.get("apply_spec_digest") != spec_digest:
        errors.append("stored_apply_spec_digest_mismatch")
    if run.get("apply_spec_id") != f"apply-spec-{requested_mode}-{spec_digest[:16]}":
        errors.append("stored_apply_spec_id_mismatch")
    invocation = str(run.get("apply_run_invocation_id", ""))
    if not invocation or invocation_suffix(invocation) != invocation:
        errors.append("invalid_apply_run_invocation_id")
    expected_run_id = f"apply-{requested_mode}-{spec_digest[:12]}-{invocation}" if invocation else ""
    if run.get("apply_run_id") != expected_run_id:
        errors.append("stored_apply_run_id_mismatch")
    if run.get("source_snapshot_digest") != snapshot_digest(source_snapshot):
        errors.append("stored_source_snapshot_digest_mismatch")
    readiness = run.get("step4_readiness")
    if (
        not isinstance(readiness, dict)
        or not readiness.get("validator_command")
        or readiness.get("execution_gate") != "step4_validator_must_pass_before_product_changes"
    ):
        errors.append("step4_readiness_summary_missing")
    if run.get("commit_policy") != "none":
        errors.append("commit_policy_must_default_to_none")
    if run.get("push_allowed") is not False:
        errors.append("push_must_default_false")
    if run.get("pr_allowed") is not False:
        errors.append("pr_must_default_false")
    if run.get("max_writer_agents") != 1:
        errors.append("only_one_writer_permitted")
    if run.get("max_subagent_depth") != 1:
        errors.append("recursive_subagents_rejected")
    validate_agent_profiles(run, errors)
    external = run.get("external_superpowers", {})
    if run.get("mode") == "external_superpowers":
        if not isinstance(external, dict):
            errors.append("external_superpowers_policy_missing")
        else:
            availability = external.get("availability")
            if availability == "not_checked":
                errors.append("external_superpowers_readiness_not_checked")
            elif availability == "unavailable":
                if external.get("fallback_mode") != "subagent_serial":
                    errors.append("external_superpowers_unavailable_requires_subagent_serial_fallback")
                errors.append("external_superpowers_unavailable_must_reconcile_mode")
            elif availability == "available":
                for key in ("version", "source_path", "adapter_policy"):
                    if not external.get(key):
                        errors.append(f"external_superpowers_available_metadata_missing={key}")
                if external.get("license_acknowledged") is not True:
                    errors.append("external_superpowers_license_acknowledgement_required")
            else:
                errors.append(f"external_superpowers_invalid_availability={availability}")
    elif isinstance(external, dict) and external.get("required") is True and external.get("availability") == "unavailable":
        if run.get("mode") != "subagent_serial" or external.get("reconciled_to") != "subagent_serial":
            errors.append("external_superpowers_unavailable_must_reconcile_mode")

    if root is not None and run.get("source_snapshot_digest") != snapshot_digest(collect_snapshot(root)):
        errors.append("source_snapshot_mismatch")

    tasks = progress.get("tasks", [])
    if not isinstance(tasks, list):
        errors.append("progress_tasks_must_be_list")
        tasks = []
    task_ids: set[str] = set()
    if run.get("mode") == "no_action" and tasks:
        errors.append("no_action_must_not_have_tasks")
    if run.get("mode") == "no_action":
        if progress.get("final_review_required") is not False:
            errors.append("no_action_final_review_must_be_false")
        if isinstance(result, dict) and result.get("status") != "no_action":
            errors.append("no_action_result_status_mismatch")
    for task in tasks:
        if not isinstance(task, dict):
            errors.append("progress_task_must_be_object")
            continue
        task_id = str(task.get("task_id", ""))
        if task_id in task_ids:
            errors.append(f"duplicate_task_id={task_id}")
        task_ids.add(task_id)
        if task.get("state") == "VERIFIED" and task.get("redispatch_count", 0) not in {0, None}:
            errors.append(f"verified_task_not_redispatched={task_id}")
        validate_dispatch_packet(run_dir, run, task, errors)
        validate_task_artifacts(run_dir, task, errors)

    validate_events(events, tasks, errors)
    validate_writer_lock(run_dir, progress, tasks, errors)
    if progress.get("final_review_required") is True:
        if not isinstance(final_review, dict) or final_review.get("status") not in {"pass", "not_started"}:
            errors.append("final_review_required")
        if all(isinstance(task, dict) and task.get("state") == "VERIFIED" for task in tasks) and final_review.get("status") != "pass":
            errors.append("final_review_required")
        if all(isinstance(task, dict) and task.get("state") == "VERIFIED" for task in tasks) and final_review.get("status") == "pass":
            reviewed = set(final_review.get("reviewed_task_ids", [])) if isinstance(final_review, dict) else set()
            if reviewed != task_ids:
                errors.append("final_review_must_cover_verified_tasks")
            global_validations = final_review.get("global_validations") if isinstance(final_review, dict) else None
            if not isinstance(global_validations, list) or not global_validations:
                errors.append("final_review_requires_global_validations")
            else:
                for item in global_validations:
                    if not isinstance(item, dict) or item.get("exit_code") != 0 or not command_is_safe(item):
                        errors.append("final_review_requires_safe_passing_global_validations")
                        break
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage CodexQB apply-run artifact contracts.")
    sub = parser.add_subparsers(dest="command", required=True)
    for command_name in ("init", "prepare"):
        prepare = sub.add_parser(command_name, help="Create an apply-run artifact directory.")
        prepare.add_argument("--root", default=".")
        prepare.add_argument("--mode", default="subagent_serial", choices=sorted(APPLY_MODES))
        prepare.add_argument("--output-dir")
        prepare.add_argument("--replace", action="store_true")
        prepare.add_argument("--resume", action="store_true")
        prepare.add_argument("--run-id-suffix")
    check = sub.add_parser("validate", help="Validate an apply-run artifact directory.")
    check.add_argument("--run-dir", required=True)
    check.add_argument("--root")
    transition = sub.add_parser("transition", help="Apply one checked task state transition and append Events.jsonl.")
    transition.add_argument("--run-dir", required=True)
    transition.add_argument("--task-id", required=True)
    transition.add_argument("--to", required=True, choices=sorted(TASK_STATES))
    transition.add_argument("--actor", required=True)
    transition.add_argument("--evidence", action="append", default=[])
    dispatch = sub.add_parser("dispatch", help="Prepare a fresh-context Codex subagent dispatch packet.")
    dispatch.add_argument("--run-dir", required=True)
    dispatch.add_argument("--task-id", required=True)
    dispatch.add_argument("--role", default="implementer", choices=sorted(DISPATCH_ROLES))
    dispatch.add_argument("--actor", required=True)
    dispatch.add_argument("--evidence", action="append", default=[])
    record_agent = sub.add_parser("record-agent", help="Record a spawned/completed/failed Codex subagent result.")
    record_agent.add_argument("--run-dir", required=True)
    record_agent.add_argument("--task-id", required=True)
    record_agent.add_argument("--role", default="implementer", choices=sorted(DISPATCH_ROLES))
    record_agent.add_argument("--agent-id", required=True)
    record_agent.add_argument("--status", required=True, choices=sorted(DISPATCH_AGENT_STATUSES))
    record_agent.add_argument("--actor", required=True)
    record_agent.add_argument("--summary")
    record_agent.add_argument("--evidence", action="append", default=[])
    reconcile = sub.add_parser("reconcile", help="Reconcile external adapter readiness before dispatch.")
    reconcile.add_argument("--run-dir", required=True)
    recover = sub.add_parser("recover-lock", help="Recover an expired writer lock to BLOCKED or NEEDS_CONTEXT.")
    recover.add_argument("--run-dir", required=True)
    recover.add_argument("--task-id", required=True)
    recover.add_argument("--to", required=True, choices=["BLOCKED", "NEEDS_CONTEXT"])
    recover.add_argument("--actor", required=True)
    recover.add_argument("--evidence", action="append", default=[])
    finalize = sub.add_parser("finalize", help="Finalize a validated apply-run artifact directory.")
    finalize.add_argument("--run-dir", required=True)
    finalize.add_argument("--actor", required=True)
    finalize.add_argument("--evidence", action="append", default=[])
    args = parser.parse_args(argv)

    try:
        if args.command in {"init", "prepare"}:
            result = create_apply_run(
                Path(args.root),
                args.mode,
                Path(args.output_dir) if args.output_dir else None,
                replace=args.replace,
                resume=args.resume,
                run_id_suffix=args.run_id_suffix,
            )
            print("apply_run_status=initialized")
            print(f"apply_run_id={result['apply_run_id']}")
            print(f"run_dir={result['run_dir']}")
            return 0
        if args.command == "transition":
            event = transition_task_state(Path(args.run_dir), args.task_id, args.to, args.actor, args.evidence)
            print("apply_run_status=transitioned")
            print(f"event_sequence={event['sequence']}")
            print(f"task_id={args.task_id}")
            print(f"state={args.to}")
            return 0
        if args.command == "dispatch":
            result = prepare_dispatch_packet(Path(args.run_dir), args.task_id, args.role, args.actor, args.evidence)
            event = result["event"]
            print("apply_run_status=dispatch_packet_ready")
            print(f"event_sequence={event['sequence']}")
            print(f"task_id={args.task_id}")
            print(f"role={args.role}")
            print(f"packet_path={result['packet_path']}")
            print(f"packet_sha256={result['packet_sha256']}")
            return 0
        if args.command == "record-agent":
            event = record_agent_status(
                Path(args.run_dir),
                args.task_id,
                args.role,
                args.agent_id,
                args.status,
                args.actor,
                args.evidence,
                args.summary,
            )
            print("apply_run_status=agent_recorded")
            print(f"event_sequence={event['sequence']}")
            print(f"task_id={args.task_id}")
            print(f"role={args.role}")
            print(f"agent_id={args.agent_id}")
            print(f"agent_status={args.status}")
            return 0
        if args.command == "reconcile":
            result = reconcile_external_superpowers(Path(args.run_dir))
            print(f"apply_run_status={result['state']}")
            print(f"mode={result['mode']}")
            if "event_sequence" in result:
                print(f"event_sequence={result['event_sequence']}")
            return 0
        if args.command == "recover-lock":
            event = recover_stale_writer_lock(Path(args.run_dir), args.task_id, args.to, args.actor, args.evidence)
            print("apply_run_status=recovered")
            print(f"event_sequence={event['sequence']}")
            print(f"task_id={args.task_id}")
            print(f"state={args.to}")
            return 0
        if args.command == "finalize":
            event = finalize_apply_run(Path(args.run_dir), args.actor, args.evidence)
            print("apply_run_status=finalized")
            print(f"event_sequence={event['sequence']}")
            return 0
        errors = validate_apply_run(Path(args.run_dir), Path(args.root) if args.root else None)
    except Exception as exc:
        print("apply_run_status=failed", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1
    if errors:
        print("apply_run_status=failed")
        for error in errors:
            print(f"error={error}")
        return 1
    print("apply_run_status=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
