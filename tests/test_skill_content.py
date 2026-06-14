from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "plugins/codexqb/skills/codexqb"


class SkillContentTests(unittest.TestCase):
    def test_skill_references_repo_aware_intake(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/repo-aware-intake.md", skill)
        self.assertIn("repo-aware", skill.lower())

    def test_repo_aware_intake_keeps_stable_four_fields(self) -> None:
        intake = (SKILL_ROOT / "references/repo-aware-intake.md").read_text(encoding="utf-8")
        for field in ["PROJECT_NAME", "PROJECT_INTENT", "TARGET_END_STATE", "KNOWN_CONSTRAINTS"]:
            self.assertIn(field, intake)
        for number in range(1, 5):
            self.assertIn(f"Soru {number} / 4", intake)
        self.assertIn("Use plain text only", intake)
        self.assertIn("Pre-Intake Scan", intake)

    def test_first_planner_required_placeholders_remain_stable(self) -> None:
        first_planner = (SKILL_ROOT / "references/First-Planner.md").read_text(encoding="utf-8")
        headings = re.findall(r"^([A-Z_]+):$", first_planner, flags=re.MULTILINE)
        required = ["PROJECT_NAME", "PROJECT_INTENT", "TARGET_END_STATE", "KNOWN_CONSTRAINTS"]
        for field in required:
            self.assertIn(field, headings)
        positions = [headings.index(field) for field in required]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("INTAKE_EVIDENCE_SUMMARY:", first_planner)


if __name__ == "__main__":
    unittest.main()
