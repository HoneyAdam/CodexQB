from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GOAL_RUN = REPO_ROOT / "plugins/codexqb/skills/codexqb/scripts/goal_run.py"


def load_goal_module():
    spec = importlib.util.spec_from_file_location("codexqb_goal_run", GOAL_RUN)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load goal_run from {GOAL_RUN}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GOAL_MODULE = load_goal_module()


class GoalRunTests(unittest.TestCase):
    def test_compile_goal_writes_deterministic_step2_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "Planner-docs"
            docs.mkdir()
            (docs / "Main-Planing.md").write_text("# Main Planing\n\n## 1. Executive Summary\n\nExample.\n", encoding="utf-8")

            first = GOAL_MODULE.compile_goal(root, "step2")
            second = GOAL_MODULE.compile_goal(root, "step2")

            self.assertEqual(first["result"]["goal_run_id"], second["result"]["goal_run_id"])
            out_dir = Path(first["output_dir"])
            self.assertIn("Planner-docs/Goal-Runs", out_dir.as_posix())
            self.assertTrue((out_dir / "Goal-Run.json").is_file())
            self.assertTrue((out_dir / "Goal-Prompt.md").is_file())
            self.assertTrue((out_dir / "Goal-Result.json").is_file())

            run = json.loads((out_dir / "Goal-Run.json").read_text(encoding="utf-8"))
            result = json.loads((out_dir / "Goal-Result.json").read_text(encoding="utf-8"))
            prompt = (out_dir / "Goal-Prompt.md").read_text(encoding="utf-8")
            self.assertEqual(run["goal_run_schema_version"], 1)
            self.assertEqual(run["artifact_schema_version"], 3)
            self.assertEqual(run["handoff_contract_version"], 2)
            self.assertEqual(run["stage"], "step2")
            self.assertIn("source_snapshot_digest", run)
            self.assertIn("required_inputs", run)
            self.assertIn("allowed_writes", run)
            self.assertIn("forbidden_writes", run)
            self.assertIn("validation_checkpoints", run)
            self.assertIn("stop_gates", run)
            self.assertFalse(run["safety"]["executes_commands"])
            self.assertFalse(run["safety"]["allows_commit_push_pr_deploy"])
            self.assertEqual(result["status"], "ready")
            self.assertIn("Canonical Handoff", prompt)
            self.assertIn("Goal Compiler Safety", prompt)
            self.assertEqual(prompt, GOAL_MODULE.render_prompt_from_run(run))
            self.assertEqual(GOAL_MODULE.validate_goal_run(root, run), [])

    def test_compile_goal_rejects_output_dir_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(ValueError):
                GOAL_MODULE.compile_goal(Path(temp_dir), "step3", Path(outside))

    def test_compile_goal_supports_all_declared_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for stage in ["step15", "step2", "step3", "step4"]:
                compiled = GOAL_MODULE.compile_goal(root, stage)
                prompt = Path(compiled["output_dir"]) / "Goal-Prompt.md"
                self.assertIn(f"CodexQB Goal Prompt: {stage}", prompt.read_text(encoding="utf-8"))

    def test_goal_run_snapshot_mismatch_blocks_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "Planner-docs"
            docs.mkdir()
            main = docs / "Main-Planing.md"
            main.write_text("# Main Planing\n\ninitial\n", encoding="utf-8")
            compiled = GOAL_MODULE.compile_goal(root, "step2")
            run = json.loads((Path(compiled["output_dir"]) / "Goal-Run.json").read_text(encoding="utf-8"))

            main.write_text("# Main Planing\n\nchanged\n", encoding="utf-8")
            errors = GOAL_MODULE.validate_goal_run(root, run)

            self.assertIn("source_snapshot_mismatch", errors)

    def test_goal_run_rejects_secret_like_content_and_overlapping_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            compiled = GOAL_MODULE.compile_goal(root, "step3")
            run = json.loads((Path(compiled["output_dir"]) / "Goal-Run.json").read_text(encoding="utf-8"))
            run["objective"] = "do not leak sk-" + "A" * 40
            run["allowed_writes"] = ["Planner-docs/Sub-Planing-Audit.md"]
            run["forbidden_writes"] = ["Planner-docs/Sub-Planing-Audit.md"]

            errors = GOAL_MODULE.validate_goal_run(root, run)

            self.assertIn("secret_like_content", errors)
            self.assertIn("overlapping_allowed_forbidden_writes", errors)


if __name__ == "__main__":
    unittest.main()
