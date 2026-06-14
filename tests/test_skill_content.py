from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "plugins/codexqb/skills/codexqb"


def read_simple_yaml_scalar(text: str, key: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(f"{key}:"):
            continue
        value = stripped.split(":", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value
    return None


class SkillContentTests(unittest.TestCase):
    def test_skill_references_repo_aware_intake(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/repo-aware-intake.md", skill)
        self.assertIn("repo-aware", skill.lower())

    def test_openai_yaml_semantics_are_concise_and_quote_tolerant(self) -> None:
        yaml_text = (SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        display_name = read_simple_yaml_scalar(yaml_text, "display_name")
        short_description = read_simple_yaml_scalar(yaml_text, "short_description")
        default_prompt = read_simple_yaml_scalar(yaml_text, "default_prompt")

        self.assertEqual(display_name, "CodexQB")
        self.assertIsNotNone(short_description)
        self.assertLessEqual(len(short_description or ""), 80)
        self.assertIsNotNone(default_prompt)
        self.assertIn("$codexqb", default_prompt or "")
        self.assertLessEqual(len(default_prompt or ""), 220)

        for sample in [
            "display_name: CodexQB",
            'display_name: "CodexQB"',
            "display_name: 'CodexQB'",
        ]:
            self.assertEqual(read_simple_yaml_scalar(sample, "display_name"), "CodexQB")

    def test_language_contract_is_documented(self) -> None:
        required_phrases = [
            "CodexQB asks intake questions in the user's language when practical.",
            "Generated Planner-docs artifacts are English by default unless the user explicitly requests another body language.",
            "Required document headings remain English for validator stability.",
        ]
        checked_files = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs/USAGE.md",
            SKILL_ROOT / "SKILL.md",
        ]
        for path in checked_files:
            text = path.read_text(encoding="utf-8")
            for phrase in required_phrases:
                self.assertIn(phrase, text, path.name)

        for path in [
            SKILL_ROOT / "references/First-Planner.md",
            SKILL_ROOT / "references/Second-Planner.md",
            SKILL_ROOT / "references/Third-Planner.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("English by default unless the user explicitly requests another body language", text, path.name)
            self.assertIn("Required document headings remain English", text, path.name)

    def test_repo_aware_intake_keeps_stable_four_fields(self) -> None:
        intake = (SKILL_ROOT / "references/repo-aware-intake.md").read_text(encoding="utf-8")
        for field in ["PROJECT_NAME", "PROJECT_INTENT", "TARGET_END_STATE", "KNOWN_CONSTRAINTS"]:
            self.assertIn(field, intake)
        for number in range(1, 5):
            self.assertIn(f"Question {number} / 4", intake)
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

    def test_autopsy_planner_is_wired_into_skill_and_step2(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        second = (SKILL_ROOT / "references/Second-Planner.md").read_text(encoding="utf-8")
        autopsy = (SKILL_ROOT / "references/Autopsy-Planner.md").read_text(encoding="utf-8")

        self.assertIn("references/Autopsy-Planner.md", skill)
        self.assertIn("Step 1.5", skill)
        self.assertIn("Planner-docs/Autopsy.md", second)
        self.assertIn("Autopsy.md is not a replacement for Main-Planing.md", second)

        required_headings = [
            "# Project Autopsy",
            "## 1. Executive Summary",
            "## 2. Reviewed Sources",
            "## 3. Project Areas and Ownership Boundaries",
            "## 4. Feature Inventory",
            "## 5. Placeholder, Stub, and Skeleton Analysis",
            "## 6. Technical Debt and Maintenance Risks",
            "## 7. Broken or Missing Integrations",
            "## 8. Test, CI, and Validation Gaps",
            "## 9. Security, Secret, and Governance Findings",
            "## 10. Operational Readiness and Observability",
            "## 11. Alignment Analysis with the Main Plan",
            "## 12. Autopsy Feedback for Step 2",
            "## 13. Priority Fix and Planning Signals",
        ]
        for heading in required_headings:
            self.assertIn(heading, autopsy)

    def test_validator_guidance_does_not_assume_global_skill_path(self) -> None:
        checked_files = [
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "references/workflow-quality.md",
            SKILL_ROOT / "references/Second-Planner.md",
            SKILL_ROOT / "references/Third-Planner.md",
        ]
        for path in checked_files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("~/.codex/skills/codexqb/scripts/validate_planner_docs.py", text, path.name)
            self.assertIn("bundled validator", text, path.name)
            self.assertIn("plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py", text, path.name)
            self.assertIn("equivalent all-file validation", text, path.name)

    def test_fourth_planner_external_skills_are_optional(self) -> None:
        fourth = (SKILL_ROOT / "references/Fourth-Planner.md").read_text(encoding="utf-8")
        self.assertIn("if installed/available", fourth.lower())
        self.assertIn("superpowers:executing-plans", fourth)
        self.assertIn("codex-security", fourth)
        self.assertIn("continue using the audit", fourth)

    def test_fourth_planner_runs_queue_continuously_with_stop_gates(self) -> None:
        fourth = (SKILL_ROOT / "references/Fourth-Planner.md").read_text(encoding="utf-8")
        self.assertIn("Build an ordered implementation queue", fourth)
        self.assertIn("Execute the queue continuously", fourth)
        self.assertIn("instead of stopping", fourth)
        self.assertIn("Stop only when one of these stop gates is hit", fourth)
        self.assertIn("token/context budget too low to continue safely", fourth)

    def test_fourth_planner_has_mechanical_per_slice_loop(self) -> None:
        fourth = (SKILL_ROOT / "references/Fourth-Planner.md").read_text(encoding="utf-8")
        for phrase in [
            "For each implementation slice:",
            "Name the active phase/sub-plan",
            "Read AGENTS.md",
            "Run git status",
            "Inspect relevant files before editing",
            "focused failing test",
            "smallest change",
            "Run targeted validation",
            "Run the repo-level gate",
            "Summarize:",
            "scope would exceed the selected sub-plan",
        ]:
            self.assertIn(phrase, fourth)

    def test_validate_script_covers_archive_and_secret_hygiene(self) -> None:
        validate_script = (REPO_ROOT / "scripts/validate.sh").read_text(encoding="utf-8")
        for phrase in [
            "tracked_secret_hygiene_failed",
            "openrouter_api_key",
            "OPENROUTER_API_KEY",
            "git\", \"archive\"",
            "archive_hygiene_failed",
            "__MACOSX",
            ".local",
        ]:
            self.assertIn(phrase, validate_script)

    def test_archive_hygiene_pattern_matches_forbidden_paths(self) -> None:
        pattern = re.compile(
            r"(^|/)(\.git|__pycache__|\.env|artifacts|logs|tmp|__MACOSX)(/|$)"
            r"|\.pyc$|\.pem$|\.key$|\.local($|\.)"
        )
        forbidden = [
            ".git/config",
            "pkg/__pycache__/module.pyc",
            ".env",
            "artifacts/build.log",
            "logs/run.txt",
            "tmp/cache.txt",
            "__MACOSX/file",
            "keys/prod.pem",
            "keys/prod.key",
            "settings.local",
            "settings.local.json",
        ]
        allowed = [
            "README.md",
            "docs/MAINTAINING.md",
            "plugins/codexqb/skills/codexqb/SKILL.md",
        ]
        for path in forbidden:
            self.assertRegex(path, pattern)
        for path in allowed:
            self.assertNotRegex(path, pattern)


if __name__ == "__main__":
    unittest.main()
