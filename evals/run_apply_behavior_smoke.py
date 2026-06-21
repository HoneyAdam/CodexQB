#!/usr/bin/env python3
"""Exercise the apply-run controller through its public CLI.

This is a behavioral smoke for the artifact controller, not a product-code
executor and not a real subagent launcher. It uses a disposable repository,
drives the public prepare/transition/validate/finalize commands, writes the
minimum evidence reports a real implementation run must produce, and verifies
that the final artifact state is complete.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
APPLY_RUN = REPO_ROOT / "plugins/codexqb/skills/codexqb/scripts/apply_run.py"


def fail(message: str) -> None:
    print(f"apply_behavior_smoke_failed={message}")
    raise SystemExit(1)


def run_apply(args: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        [sys.executable, APPLY_RUN.as_posix(), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        fail(f"command_failed={' '.join(args)} stdout={completed.stdout.strip()} stderr={completed.stderr.strip()}")
    return completed.stdout


def parse_key(output: str, key: str) -> str:
    prefix = f"{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1]
    fail(f"missing_output_key={key}")
    raise AssertionError("unreachable")


def write_fixture(root: Path) -> None:
    docs = root / "Planner-docs"
    subplans = docs / "Faz-1-Plans"
    subplans.mkdir(parents=True)
    (docs / "Main-Planing.md").write_text("# Main Planing\n\nBehavior smoke fixture.\n", encoding="utf-8")
    (docs / "Sub-Planing-Index.md").write_text("# Sub-Planing Index\n\nOne READY smoke task.\n", encoding="utf-8")
    (subplans / "Faz1.1-smoke-contract.md").write_text(
        "\n".join(
            [
                "# Faz 1.1 - Smoke Contract",
                "",
                "## Implementation Contract",
                "- behavioral acceptance: smoke artifact reaches complete state.",
                "- allowed write paths: src/smoke.py",
                "- forbidden paths: .env",
                "- parent acceptance signal: PAS-SMOKE-1",
                "- depends_on: none",
                "- validation command argv: python3 -m unittest",
                "- security review: not required",
                "- algorithmic invariant: task transition order remains monotonic.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "Sub-Planing-Audit.md").write_text(
        "# Sub-Planing Audit\n\nREADY: Planner-docs/Faz-1-Plans/Faz1.1-smoke-contract.md\n",
        encoding="utf-8",
    )


def write_verified_reports(run_dir: Path, task_id: str, brief_sha256: str) -> None:
    task_dir = run_dir / task_id
    (task_dir / "Implementer-Report.json").write_text(
        json.dumps(
            {
                "status": "DONE",
                "task_id": task_id,
                "brief_sha256": brief_sha256,
                "implementer_agent_id": "smoke-impl",
                "files_changed": ["src/smoke.py"],
                "validation_evidence": [
                    {"id": "VAL-SMOKE", "argv": ["python3", "-m", "unittest"], "exit_code": 0}
                ],
                "diff_sha256": "a" * 64,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (task_dir / "Task-Review.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "brief_sha256": brief_sha256,
                "reviewer_agent_id": "smoke-reviewer",
                "spec_compliance": "pass",
                "task_quality": "approved",
                "security_review": "not_required",
                "evidence": ["CLI behavior smoke reviewed transition trace and validation evidence."],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run_dir / "Final-Review.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "reviewed_task_ids": [task_id],
                "global_validations": [{"id": "VAL-REPO", "argv": ["make", "check"], "exit_code": 0}],
                "evidence": ["CLI behavior smoke validated and finalized the apply run."],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        write_fixture(root)

        output = run_apply(
            ["prepare", "--root", root.as_posix(), "--mode", "direct", "--run-id-suffix", "behavior-smoke"],
            cwd=root,
        )
        run_dir = Path(parse_key(output, "run_dir"))
        progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
        tasks = progress.get("tasks")
        if not isinstance(tasks, list) or len(tasks) != 1:
            fail("expected_one_task")
        task = tasks[0]
        task_id = task["task_id"]
        brief_sha256 = task["brief_sha256"]

        run_apply(["validate", "--run-dir", run_dir.as_posix(), "--root", root.as_posix()], cwd=root)
        actors = {
            "IMPLEMENTING": "smoke-impl",
            "IMPLEMENTED": "smoke-impl",
            "TASK_REVIEW": "smoke-reviewer",
            "VERIFIED": "smoke-reviewer",
        }
        for state in ["IMPLEMENTING", "IMPLEMENTED", "TASK_REVIEW", "VERIFIED"]:
            run_apply(
                [
                    "transition",
                    "--run-dir",
                    run_dir.as_posix(),
                    "--task-id",
                    task_id,
                    "--to",
                    state,
                    "--actor",
                    actors[state],
                    "--evidence",
                    f"behavior smoke reached {state}",
                ],
                cwd=root,
            )

        write_verified_reports(run_dir, task_id, brief_sha256)
        run_apply(["validate", "--run-dir", run_dir.as_posix(), "--root", root.as_posix()], cwd=root)
        run_apply(
            [
                "finalize",
                "--run-dir",
                run_dir.as_posix(),
                "--actor",
                "smoke-controller",
                "--evidence",
                "behavior smoke final review passed",
            ],
            cwd=root,
        )
        run_apply(["validate", "--run-dir", run_dir.as_posix(), "--root", root.as_posix()], cwd=root)

        result = json.loads((run_dir / "Result.json").read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (run_dir / "Events.jsonl").read_text(encoding="utf-8").splitlines()]
        if result.get("status") != "complete":
            fail(f"unexpected_result_status={result.get('status')}")
        if events[-1].get("event_type") != "apply_run_finalized":
            fail("missing_finalize_event")
        if [event.get("sequence") for event in events] != list(range(1, len(events) + 1)):
            fail("non_contiguous_event_sequence")

    print("apply_behavior_smoke=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
