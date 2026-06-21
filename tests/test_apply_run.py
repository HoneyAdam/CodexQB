from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
APPLY_RUN = REPO_ROOT / "plugins/codexqb/skills/codexqb/scripts/apply_run.py"


def load_apply_module():
    spec = importlib.util.spec_from_file_location("codexqb_apply_run", APPLY_RUN)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load apply_run from {APPLY_RUN}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


APPLY_MODULE = load_apply_module()


class ApplyRunTests(unittest.TestCase):
    def write_apply_fixture(self, root: Path) -> None:
        docs = root / "Planner-docs"
        (docs / "Faz-1-Plans").mkdir(parents=True)
        (docs / "Main-Planing.md").write_text("# Main Planing\n", encoding="utf-8")
        (docs / "Sub-Planing-Index.md").write_text("# Sub-Planing Index\n", encoding="utf-8")
        (docs / "Faz-1-Plans" / "Faz1.1-local-contract.md").write_text("# Faz 1.1 - Local Contract\n", encoding="utf-8")
        (docs / "Sub-Planing-Audit.md").write_text(
            "# Sub-Planing Audit\n\nREADY: Planner-docs/Faz-1-Plans/Faz1.1-local-contract.md\n",
            encoding="utf-8",
        )

    def mark_task_verified(self, run_dir: Path, security: str = "not_required") -> None:
        progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
        task = progress["tasks"][0]
        task["state"] = "VERIFIED"
        task["brief_sha256"] = "a" * 64
        task["security_review_required"] = security == "pass"
        progress["verified_task_ids"] = [task["task_id"]]
        (run_dir / "Progress.json").write_text(json.dumps(progress), encoding="utf-8")
        (run_dir / "task-1" / "Implementer-Report.json").write_text(
            json.dumps(
                {
                    "status": "DONE",
                    "task_id": task["task_id"],
                    "brief_sha256": "a" * 64,
                    "implementer_agent_id": "impl-1",
                    "files_changed": ["src/example.py"],
                    "validation_evidence": [{"id": "VAL-01", "argv": ["python3", "-m", "unittest"], "exit_code": 0}],
                    "diff_sha256": "b" * 64,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "task-1" / "Task-Review.json").write_text(
            json.dumps(
                {
                    "task_id": task["task_id"],
                    "brief_sha256": "a" * 64,
                    "reviewer_agent_id": "review-1",
                    "spec_compliance": "pass",
                    "task_quality": "approved",
                    "security_review": security,
                    "evidence": ["reviewed diff and validation evidence"],
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "Final-Review.json").write_text(
            json.dumps(
                {
                    "status": "pass",
                    "reviewed_task_ids": [task["task_id"]],
                    "global_validations": [{"id": "VAL-REPO", "argv": ["make", "check"], "exit_code": 0}],
                    "evidence": ["repo gate passed"],
                }
            ),
            encoding="utf-8",
        )

    def test_init_subagent_serial_creates_safe_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_apply_fixture(root)

            result = APPLY_MODULE.create_apply_run(root, "subagent_serial")
            run_dir = Path(result["run_dir"])

            self.assertTrue((run_dir / "Apply-Run.json").is_file())
            self.assertTrue((run_dir / "Progress.json").is_file())
            self.assertTrue((run_dir / "Final-Review.json").is_file())
            self.assertTrue((run_dir / "Result.json").is_file())
            self.assertTrue((run_dir / "task-1" / "Brief.md").is_file())
            self.assertTrue((run_dir / "task-1" / "Implementer-Report.json").is_file())
            self.assertTrue((run_dir / "task-1" / "Review-Package.patch").is_file())
            self.assertTrue((run_dir / "task-1" / "Task-Review.json").is_file())
            self.assertTrue((run_dir / "task-1" / "Fix-Report.json").is_file())
            run = json.loads((run_dir / "Apply-Run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["apply_run_schema_version"], 1)
            self.assertEqual(run["mode"], "subagent_serial")
            self.assertEqual(run["commit_policy"], "none")
            self.assertFalse(run["push_allowed"])
            self.assertFalse(run["pr_allowed"])
            self.assertEqual(run["max_writer_agents"], 1)
            self.assertEqual(run["max_subagent_depth"], 1)
            self.assertFalse(run["safety"]["executes_implementation"])
            self.assertFalse(run["safety"]["allows_commit_push_pr_deploy"])
            progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
            self.assertEqual(
                progress["tasks"][0]["source_subplan_path"],
                "Planner-docs/Faz-1-Plans/Faz1.1-local-contract.md",
            )
            brief = (run_dir / "task-1" / "Brief.md").read_text(encoding="utf-8")
            self.assertIn("Planner-docs/Faz-1-Plans/Faz1.1-local-contract.md", brief)
            self.assertEqual(APPLY_MODULE.validate_apply_run(run_dir), [])

    def test_no_action_mode_has_no_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = APPLY_MODULE.create_apply_run(Path(temp_dir), "no_action")
            run_dir = Path(result["run_dir"])
            progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
            run = json.loads((run_dir / "Apply-Run.json").read_text(encoding="utf-8"))
            self.assertEqual(progress["tasks"], [])
            self.assertEqual(run["mode"], "no_action")

    def test_apply_run_rejects_output_dir_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(ValueError):
                APPLY_MODULE.create_apply_run(Path(temp_dir), "direct", Path(outside))

    def test_apply_run_requires_step4_audit_for_action_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "missing_step4_audit"):
                APPLY_MODULE.create_apply_run(Path(temp_dir), "direct")

    def test_apply_run_rejects_unsafe_queue_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_apply_fixture(root)
            result = APPLY_MODULE.create_apply_run(root, "direct")
            run_dir = Path(result["run_dir"])
            progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
            progress["tasks"][0]["validation_commands"] = [
                {"argv": ["sh", "-c", "touch /tmp/codexqb-owned"]}
            ]
            (run_dir / "Progress.json").write_text(json.dumps(progress), encoding="utf-8")
            errors = APPLY_MODULE.validate_apply_run(run_dir)
            self.assertIn("unsafe_validation_command=task-1", errors)

    def test_apply_run_enforces_review_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_apply_fixture(root)
            result = APPLY_MODULE.create_apply_run(root, "direct")
            run_dir = Path(result["run_dir"])
            progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
            progress["tasks"][0]["state"] = "TASK_REVIEW"
            (run_dir / "Progress.json").write_text(json.dumps(progress), encoding="utf-8")
            review = {
                "spec_compliance": "fail",
                "task_quality": "needs_fixes",
                "blocking_findings": ["missing acceptance behavior"],
                "re_review_required": True,
            }
            (run_dir / "task-1" / "Task-Review.json").write_text(json.dumps(review), encoding="utf-8")
            errors = APPLY_MODULE.validate_apply_run(run_dir)
            self.assertIn("re_review_requires_fix_report=task-1", errors)

    def test_apply_run_rejects_non_ready_p0_p1_and_policy_violations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_apply_fixture(root)
            result = APPLY_MODULE.create_apply_run(root, "subagent_serial")
            run_dir = Path(result["run_dir"])
            run = json.loads((run_dir / "Apply-Run.json").read_text(encoding="utf-8"))
            run["max_writer_agents"] = 2
            run["max_subagent_depth"] = 2
            (run_dir / "Apply-Run.json").write_text(json.dumps(run), encoding="utf-8")
            progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
            progress["tasks"][0]["readiness_status"] = "BLOCKED"
            progress["tasks"][0]["finding_ids"] = ["P1"]
            (run_dir / "Progress.json").write_text(json.dumps(progress), encoding="utf-8")

            errors = APPLY_MODULE.validate_apply_run(run_dir)

            self.assertIn("only_one_writer_permitted", errors)
            self.assertIn("recursive_subagents_rejected", errors)
            self.assertIn("non_ready_queue_item=task-1:BLOCKED", errors)
            self.assertIn("p0_p1_queue_item_rejected=task-1", errors)

    def test_apply_run_requires_security_review_and_final_review_for_verified_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_apply_fixture(root)
            result = APPLY_MODULE.create_apply_run(root, "subagent_serial")
            run_dir = Path(result["run_dir"])
            progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
            progress["tasks"][0]["state"] = "VERIFIED"
            progress["tasks"][0]["security_review_required"] = True
            (run_dir / "Progress.json").write_text(json.dumps(progress), encoding="utf-8")
            (run_dir / "task-1" / "Implementer-Report.json").write_text(json.dumps({"status": "DONE"}), encoding="utf-8")
            (run_dir / "task-1" / "Task-Review.json").write_text(
                json.dumps({"spec_compliance": "pass", "task_quality": "approved", "security_review": "not_required"}),
                encoding="utf-8",
            )

            errors = APPLY_MODULE.validate_apply_run(run_dir)

            self.assertIn("required_security_review_must_pass=task-1", errors)
            self.assertIn("final_review_required", errors)

            self.mark_task_verified(run_dir, security="pass")
            self.assertEqual(APPLY_MODULE.validate_apply_run(run_dir), [])

    def test_apply_run_snapshot_mismatch_blocks_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "Planner-docs"
            (docs / "Faz-1-Plans").mkdir(parents=True)
            (docs / "Faz-1-Plans" / "Faz1.1-local-contract.md").write_text("# Faz 1.1 - Local Contract\n", encoding="utf-8")
            (docs / "Sub-Planing-Audit.md").write_text(
                "READY: Planner-docs/Faz-1-Plans/Faz1.1-local-contract.md\n",
                encoding="utf-8",
            )
            result = APPLY_MODULE.create_apply_run(root, "direct")
            run_dir = Path(result["run_dir"])
            (docs / "Sub-Planing-Audit.md").write_text("changed\n", encoding="utf-8")

            errors = APPLY_MODULE.validate_apply_run(run_dir, root)

            self.assertIn("source_snapshot_mismatch", errors)

    def test_apply_run_verified_task_is_not_redispatched(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_apply_fixture(root)
            result = APPLY_MODULE.create_apply_run(root, "direct")
            run_dir = Path(result["run_dir"])
            progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
            progress["tasks"][0]["state"] = "VERIFIED"
            progress["tasks"][0]["redispatch_count"] = 1
            (run_dir / "Progress.json").write_text(json.dumps(progress), encoding="utf-8")

            errors = APPLY_MODULE.validate_apply_run(run_dir)

            self.assertIn("verified_task_not_redispatched=task-1", errors)

    def test_external_superpowers_unavailable_requires_safe_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_apply_fixture(root)
            result = APPLY_MODULE.create_apply_run(root, "external_superpowers")
            run_dir = Path(result["run_dir"])
            run = json.loads((run_dir / "Apply-Run.json").read_text(encoding="utf-8"))
            run["external_superpowers"]["availability"] = "unavailable"
            run["external_superpowers"]["fallback_mode"] = "direct"
            (run_dir / "Apply-Run.json").write_text(json.dumps(run), encoding="utf-8")

            errors = APPLY_MODULE.validate_apply_run(run_dir)

            self.assertIn("external_superpowers_unavailable_requires_subagent_serial_fallback", errors)
            run["external_superpowers"]["fallback_mode"] = "subagent_serial"
            (run_dir / "Apply-Run.json").write_text(json.dumps(run), encoding="utf-8")
            self.assertEqual(APPLY_MODULE.validate_apply_run(run_dir), [])

    def test_apply_run_rejects_task_id_traversal_and_no_action_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            no_action = APPLY_MODULE.create_apply_run(Path(temp_dir), "no_action")
            run_dir = Path(no_action["run_dir"])
            progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
            progress["tasks"] = [{"task_id": "../../outside-task", "state": "BRIEFED", "readiness_status": "READY"}]
            (run_dir / "Progress.json").write_text(json.dumps(progress), encoding="utf-8")

            errors = APPLY_MODULE.validate_apply_run(run_dir)

            self.assertIn("no_action_must_not_have_tasks", errors)
            self.assertIn("invalid_task_id=../../outside-task", errors)

    def test_apply_run_does_not_overwrite_existing_progress_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_apply_fixture(root)
            first = APPLY_MODULE.create_apply_run(root, "direct")

            with self.assertRaises(ValueError):
                APPLY_MODULE.create_apply_run(root, "direct")

            resumed = APPLY_MODULE.create_apply_run(root, "direct", resume=True)
            self.assertEqual(resumed["run_dir"], first["run_dir"])

    def test_verified_task_requires_evidence_bearing_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_apply_fixture(root)
            result = APPLY_MODULE.create_apply_run(root, "direct")
            run_dir = Path(result["run_dir"])
            progress = json.loads((run_dir / "Progress.json").read_text(encoding="utf-8"))
            progress["tasks"][0]["state"] = "VERIFIED"
            (run_dir / "Progress.json").write_text(json.dumps(progress), encoding="utf-8")
            (run_dir / "task-1" / "Implementer-Report.json").write_text(json.dumps({"status": "DONE"}), encoding="utf-8")
            (run_dir / "task-1" / "Task-Review.json").write_text(
                json.dumps({"spec_compliance": "pass", "task_quality": "approved", "security_review": "not_required"}),
                encoding="utf-8",
            )
            (run_dir / "Final-Review.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")

            errors = APPLY_MODULE.validate_apply_run(run_dir)

            self.assertIn("verified_requires_files_changed=task-1", errors)
            self.assertIn("verified_requires_validation_evidence=task-1", errors)
            self.assertIn("verified_requires_review_evidence=task-1", errors)


if __name__ == "__main__":
    unittest.main()
