#!/usr/bin/env python3
"""Create and validate CodexQB Step 4 apply-run artifacts.

This script manages artifact contracts only. It does not implement code, run
tests, dispatch subagents, commit, push, create PRs, deploy, or mutate external
systems.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
SHELL_METACHAR_RE = re.compile(r"(?:&&|\|\||[;&|<>`]|[$]\(|\n|\r)")
MUTATING_INTENT_RE = re.compile(
    r"\b(?:deploy|release|publish|push|merge|destroy|delete|remove|prune|reset|install|prod|production|live)\b",
    re.IGNORECASE,
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def apply_run_id(mode: str, snapshot: list[dict[str, str]]) -> str:
    return f"apply-{mode}-{snapshot_digest(snapshot)[:12]}"


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
    for match in re.finditer(
        r"\b(READY_WITH_WARNINGS|READY)\b\s*:?\s*`?((?:Planner-docs/)?Faz-\d+-Plans/Faz\d+\.\d+-[a-z0-9-]+\.md)`?",
        text,
        flags=re.IGNORECASE,
    ):
        path = match.group(2)
        if not path.startswith("Planner-docs/"):
            path = f"Planner-docs/{path}"
        items.append({"readiness_status": match.group(1).upper(), "subplan_path": path})
    return items


def audit_text(root: Path) -> str:
    audit = root / "Planner-docs" / "Sub-Planing-Audit.md"
    if not audit.is_file():
        return ""
    return audit.read_text(encoding="utf-8", errors="replace")


def validate_step4_queue(root: Path, mode: str) -> None:
    if mode == "no_action":
        return
    audit = root / "Planner-docs" / "Sub-Planing-Audit.md"
    if not audit.is_file():
        raise ValueError("missing_step4_audit=Planner-docs/Sub-Planing-Audit.md")
    if not extract_ready_queue(root):
        if "NO_ACTION_REQUIRED" in audit_text(root):
            raise ValueError("no_action_required_use_no_action_mode")
        raise ValueError("missing_step4_ready_queue")


def default_tasks(root: Path, mode: str) -> list[dict[str, object]]:
    if mode == "no_action":
        return []
    queue = extract_ready_queue(root)
    tasks: list[dict[str, object]] = []
    for index, item in enumerate(queue, start=1):
        subplan_path = item["subplan_path"]
        subplan = root / subplan_path
        tasks.append(
            {
                "task_id": f"task-{index}",
                "state": "BRIEFED",
                "readiness_status": item["readiness_status"],
                "source_subplan_path": subplan_path,
                "source_subplan_sha256": sha256_bytes(subplan.read_bytes()) if subplan.is_file() else None,
                "finding_ids": [],
                "security_review_required": False,
                "writer_lock": None,
                "validation_commands": [],
                "redispatch_count": 0,
            }
        )
    return tasks


def create_apply_run(
    root: Path,
    mode: str,
    output_dir: Path | None = None,
    commit_policy: str = "none",
    *,
    replace: bool = False,
    resume: bool = False,
) -> dict[str, object]:
    root = root.resolve()
    if mode not in APPLY_MODES:
        raise ValueError(f"unsupported apply mode: {mode}")
    if commit_policy not in COMMIT_POLICIES:
        raise ValueError(f"unsupported commit policy: {commit_policy}")
    if commit_policy != "none":
        raise ValueError("commit_policy defaults to none; other policies require explicit controller approval outside apply_run.py")
    snapshot = collect_snapshot(root)
    run_id = apply_run_id(mode, snapshot)
    run_dir = (output_dir or root / ".codexqb" / "apply-runs" / run_id).resolve()
    if not is_inside(root, run_dir):
        raise ValueError("output_dir must be inside the target repository")
    validate_step4_queue(root, mode)
    if run_dir.exists() and not replace and not resume:
        raise ValueError(f"apply_run_already_exists={run_dir.relative_to(root).as_posix()}")
    if resume:
        return {"apply_run_id": run_id, "run_dir": run_dir.as_posix(), "state": "resumed"}
    run_dir.mkdir(parents=True, exist_ok=True)

    tasks = default_tasks(root, mode)
    run = {
        "apply_run_schema_version": APPLY_RUN_SCHEMA_VERSION,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "handoff_contract_version": HANDOFF_CONTRACT_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "apply_run_id": run_id,
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
        "source_snapshot": snapshot,
        "source_snapshot_digest": snapshot_digest(snapshot),
        "external_superpowers": {
            "required": mode == "external_superpowers",
            "availability": "not_checked",
            "fallback_mode": "subagent_serial",
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
    (run_dir / "Apply-Run.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "Progress.json").write_text(json.dumps(progress, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "Final-Review.json").write_text(json.dumps({"status": "not_started" if mode != "no_action" else "not_required"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "Result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for index, task in enumerate(tasks, start=1):
        task_dir = run_dir / f"task-{index}"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "Brief.md").write_text(
            "\n".join(
                [
                    f"# Task {index} Brief",
                    "",
                    f"- task_id: {task['task_id']}",
                    f"- mode: {mode}",
                    "- commit_policy: none",
                    f"- source_subplan_path: {task.get('source_subplan_path')}",
                    f"- source_subplan_sha256: {task.get('source_subplan_sha256')}",
                    f"- readiness_status: {task.get('readiness_status')}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (task_dir / "Implementer-Report.json").write_text(json.dumps({"status": "PENDING"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (task_dir / "Review-Package.patch").write_text("", encoding="utf-8")
        (task_dir / "Task-Review.json").write_text(json.dumps({"status": "PENDING"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (task_dir / "Fix-Report.json").write_text(json.dumps({"status": "PENDING"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"apply_run_id": run_id, "run_dir": run_dir.as_posix(), "state": result["status"]}


def load_json(path: Path, errors: list[str], label: str) -> object:
    if not path.is_file():
        errors.append(f"missing_{label}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append(f"invalid_json={label}")
        return {}


def command_is_safe(command: object) -> bool:
    if isinstance(command, list):
        return safe_validation_command_item({"argv": command})
    if isinstance(command, str):
        return safe_validation_command_item({"command": command})
    if isinstance(command, dict):
        return safe_validation_command_item(command)
    return False


def validate_task_artifacts(run_dir: Path, task: dict[str, object], errors: list[str]) -> None:
    task_id = str(task.get("task_id", ""))
    state = str(task.get("state", ""))
    if not re.fullmatch(r"task-\d+", task_id):
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

    match = re.fullmatch(r"task-(\d+)", task_id)
    task_dir = (run_dir / task_id).resolve()
    if not match or not is_inside(run_dir, task_dir):
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


def validate_apply_run(run_dir: Path, root: Path | None = None) -> list[str]:
    errors: list[str] = []
    run_dir = run_dir.resolve()
    root = root.resolve() if root else infer_root(run_dir)
    run = load_json(run_dir / "Apply-Run.json", errors, "apply_run_json")
    progress = load_json(run_dir / "Progress.json", errors, "progress_json")
    final_review = load_json(run_dir / "Final-Review.json", errors, "final_review_json")
    load_json(run_dir / "Result.json", errors, "result_json")
    if errors or not isinstance(run, dict) or not isinstance(progress, dict):
        return errors

    if run.get("apply_run_schema_version") != APPLY_RUN_SCHEMA_VERSION:
        errors.append("invalid_apply_run_schema_version")
    if run.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION:
        errors.append("invalid_artifact_schema_version")
    if run.get("handoff_contract_version") != HANDOFF_CONTRACT_VERSION:
        errors.append("invalid_handoff_contract_version")
    if run.get("mode") not in APPLY_MODES:
        errors.append(f"invalid_mode={run.get('mode')}")
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
    external = run.get("external_superpowers", {})
    if run.get("mode") == "external_superpowers":
        if not isinstance(external, dict):
            errors.append("external_superpowers_policy_missing")
        elif external.get("availability") == "unavailable" and external.get("fallback_mode") != "subagent_serial":
            errors.append("external_superpowers_unavailable_requires_subagent_serial_fallback")

    if root is not None and run.get("source_snapshot_digest") != snapshot_digest(collect_snapshot(root)):
        errors.append("source_snapshot_mismatch")

    tasks = progress.get("tasks", [])
    if not isinstance(tasks, list):
        errors.append("progress_tasks_must_be_list")
        tasks = []
    task_ids: set[str] = set()
    if run.get("mode") == "no_action" and tasks:
        errors.append("no_action_must_not_have_tasks")
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
        validate_task_artifacts(run_dir, task, errors)

    locks = progress.get("active_writer_locks", [])
    if isinstance(locks, list) and len(locks) > 1:
        errors.append("only_one_active_writer_lock_permitted")
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
    init = sub.add_parser("init", help="Create an apply-run artifact directory.")
    init.add_argument("--root", default=".")
    init.add_argument("--mode", default="subagent_serial", choices=sorted(APPLY_MODES))
    init.add_argument("--output-dir")
    init.add_argument("--replace", action="store_true")
    init.add_argument("--resume", action="store_true")
    check = sub.add_parser("validate", help="Validate an apply-run artifact directory.")
    check.add_argument("--run-dir", required=True)
    check.add_argument("--root")
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            result = create_apply_run(
                Path(args.root),
                args.mode,
                Path(args.output_dir) if args.output_dir else None,
                replace=args.replace,
                resume=args.resume,
            )
            print("apply_run_status=initialized")
            print(f"apply_run_id={result['apply_run_id']}")
            print(f"run_dir={result['run_dir']}")
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
