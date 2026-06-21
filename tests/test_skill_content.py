from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
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
        self.assertIn("vibecoding", (short_description or "").lower())
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
            "Generated Planner-docs artifacts are English by default unless the user explicitly requests another content language.",
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
            self.assertIn("English by default unless the user explicitly requests another content language", text, path.name)
            self.assertIn("Required document headings remain English", text, path.name)

        for path in [REPO_ROOT / "README.md", REPO_ROOT / "docs/USAGE.md", REPO_ROOT / "docs/MAINTAINING.md"]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("PLANNER_DOC_LANGUAGE", text, path.name)

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
        fourth = (SKILL_ROOT / "references/handoffs/run-step4.md").read_text(encoding="utf-8")
        self.assertIn("if installed/available", fourth.lower())
        self.assertIn("superpowers:executing-plans", fourth)
        self.assertIn("codex-security", fourth)
        self.assertIn("continue using the audit", fourth)

    def test_fourth_planner_runs_queue_continuously_with_stop_gates(self) -> None:
        fourth = (SKILL_ROOT / "references/handoffs/run-step4.md").read_text(encoding="utf-8")
        self.assertIn("Build an ordered implementation queue", fourth)
        self.assertIn("Default Goal batch", fourth)
        self.assertIn("instead of stopping", fourth)
        self.assertIn("Stop only when one of these stop gates is hit", fourth)
        self.assertIn("token/context budget too low to continue safely", fourth)

    def test_fourth_planner_has_mechanical_per_slice_loop(self) -> None:
        fourth = (SKILL_ROOT / "references/handoffs/run-step4.md").read_text(encoding="utf-8")
        for phrase in [
            "For each implementation slice:",
            "Name the active phase/sub-plan",
            "Read AGENTS.md",
            "Run git status",
            "Inspect relevant files before editing",
            "focused failing test",
            "smallest change",
            "Run targeted validation",
            "If targeted validation fails and the source is unclear, stop",
            "Run the repo-level gate",
            "Do not batch unrelated sub-plans in one diff",
            "Summarize:",
            "scope would exceed the selected sub-plan",
        ]:
            self.assertIn(phrase, fourth)

    def test_step3_direct_guidance_starts_with_preflight(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        step3 = skill.split("## Step 3 Handoff", 1)[1].split("## Step 4 Handoff", 1)[0]
        self.assertIn("--mode step3-preflight --strict", step3)
        self.assertIn("Then, after `Planner-docs/Sub-Planing-Audit.md` is written", step3)
        self.assertLess(step3.index("--mode step3-preflight --strict"), step3.index("--mode step3 --strict"))

    def test_step4_documents_apply_modes_and_review_loop(self) -> None:
        fourth = (SKILL_ROOT / "references/handoffs/run-step4.md").read_text(encoding="utf-8")
        for phrase in [
            "Step 4 apply modes:",
            "`direct`",
            "`subagent_serial`",
            "`external_superpowers`",
            "`no_action`",
            "fresh-slice implementer",
            "`DONE_WITH_CONCERNS`",
            "`NEEDS_CONTEXT`",
            "`BLOCKED`",
            "`spec_verdict: pass|fail`",
            "`quality_verdict: pass|fail|with_fixes`",
            "fix only the active slice and re-run spec review",
            "fix only the active slice and re-run the relevant review",
            "final review",
                "Do not commit, push, open PRs, deploy, or mutate external systems unless the user explicitly opts into that action",
        ]:
            self.assertIn(phrase, fourth)

    def test_apply_role_templates_and_durable_controller_contract_are_wired(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        apply_ref = (SKILL_ROOT / "references/apply-orchestrator.md").read_text(encoding="utf-8")
        apply_schema = json.loads((SKILL_ROOT / "references/apply-run-schema.json").read_text(encoding="utf-8"))
        validate_script = (REPO_ROOT / "scripts/validate.sh").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        usage = (REPO_ROOT / "docs/USAGE.md").read_text(encoding="utf-8")
        maintaining = (REPO_ROOT / "docs/MAINTAINING.md").read_text(encoding="utf-8")
        self.assertEqual(apply_schema["$id"], "https://codexqb.local/schemas/apply-run-schema.json")
        self.assertIn("anyOf", apply_schema)
        schema_defs = apply_schema["$defs"]
        for name in [
            "ApplyRun",
            "WorkspaceBaseline",
            "Progress",
            "DispatchPacket",
            "AgentRun",
            "ImplementerReport",
            "TaskReview",
            "FixReport",
            "FinalReview",
            "Result",
        ]:
            self.assertIn(name, schema_defs)
        self.assertEqual(schema_defs["ApplyRun"]["properties"]["apply_run_schema_version"]["const"], 1)
        self.assertEqual(schema_defs["ApplyRun"]["properties"]["artifact_schema_version"]["const"], 3)
        self.assertEqual(schema_defs["ApplyRun"]["properties"]["handoff_contract_version"]["const"], 2)
        step4_readiness = schema_defs["ApplyRun"]["properties"]["step4_readiness"]
        self.assertIn("validator_output_sha256", step4_readiness["required"])
        self.assertIn("execution_queue_state", step4_readiness["required"])
        apply_spec_inputs = schema_defs["ApplyRun"]["properties"]["apply_spec_inputs"]
        self.assertIn("workspace_baseline", apply_spec_inputs["required"])
        self.assertEqual(apply_spec_inputs["properties"]["workspace_baseline"]["$ref"], "#/$defs/WorkspaceBaseline")
        self.assertIn("workspace_baseline", schema_defs["ApplyRun"]["required"])
        for name in ["workspace_requested", "workspace_detected", "workspace_verified", "workspace_mode", "worktree_path", "base_branch", "working_branch", "dirty_state"]:
            self.assertIn(name, schema_defs["ApplyRun"]["required"])
        self.assertIn("user_approval", schema_defs["ApplyRun"]["required"])
        self.assertEqual(schema_defs["ApplyRun"]["properties"]["workspace_baseline"]["$ref"], "#/$defs/WorkspaceBaseline")
        self.assertEqual(
            schema_defs["ApplyRun"]["properties"]["workspace_mode"]["enum"],
            ["non_git_unsafe", "unverified_current_worktree", "verified_isolated_worktree"],
        )
        self.assertEqual(schema_defs["ApplyRun"]["properties"]["dirty_state"]["enum"], ["clean", "dirty", "non_git", "unknown"])
        self.assertEqual(schema_defs["ApplyRun"]["properties"]["user_approval"]["type"], "boolean")
        workspace_baseline = schema_defs["WorkspaceBaseline"]
        self.assertIn("git_status_porcelain_sha256", workspace_baseline["required"])
        self.assertIn("untracked_inventory_sha256", workspace_baseline["required"])
        self.assertIn("workspace_file_inventory_sha256", workspace_baseline["required"])
        self.assertIn("implementation_contract", schema_defs["Task"]["required"])
        self.assertIn("validation_command_ids", schema_defs["Task"]["required"])
        self.assertEqual(schema_defs["Task"]["properties"]["implementation_contract"]["type"], "object")
        self.assertEqual(schema_defs["Task"]["properties"]["validation_commands"]["items"]["$ref"], "#/$defs/PlannedValidationCommand")
        self.assertEqual(schema_defs["Task"]["properties"]["validation_command_ids"]["items"]["pattern"], "^VAL-[A-Za-z0-9_.:-]+$")
        self.assertEqual(
            schema_defs["ImplementerReport"]["properties"]["validation_evidence"]["items"]["$ref"],
            "#/$defs/ValidationEvidence",
        )
        self.assertEqual(
            schema_defs["FinalReview"]["properties"]["global_validations"]["items"]["$ref"],
            "#/$defs/ValidationEvidence",
        )
        self.assertEqual(schema_defs["DispatchPacket"]["properties"]["spawn_tool"]["const"], "multi_agent_v1.spawn_agent")
        self.assertIn("references/apply-run-schema.json", skill)
        self.assertIn("plugins/codexqb/skills/codexqb/references/apply-run-schema.json", validate_script)
        self.assertIn("references/apply-run-schema.json", maintaining)
        role_files = [
            "controller.md",
            "implementer.md",
            "task-reviewer.md",
            "security-reviewer.md",
            "fixer.md",
            "final-reviewer.md",
        ]
        for name in role_files:
            rel = f"references/apply/{name}"
            path = SKILL_ROOT / rel
            self.assertTrue(path.is_file(), rel)
            text = path.read_text(encoding="utf-8")
            self.assertIn("model_profile", text, rel)
            self.assertIn(rel, skill)
            self.assertIn(f"plugins/codexqb/skills/codexqb/{rel}", validate_script)
        for phrase in [
            "Events.jsonl",
            "Writer-Lock.json",
            "apply_run.py prepare",
            "apply_run.py dispatch",
            "apply_run.py record-agent",
            "apply_run.py transition",
            "apply_run.py recover-lock",
            "apply_run.py finalize",
            "strict Step 4 validation",
            "validator output hash",
            "Dispatch-Packet.json",
            "Agent-Run-<role>-<nn>.json",
            "multi_agent_v1.spawn_agent",
            "record-agent --status spawned",
            "append-only transition truth",
            "agent_profiles",
            "security_strong",
            "allow-non-git-unsafe",
            "non_git_unsafe",
            "allow-unverified-git-worktree",
            "dirty_state",
            "working_branch",
            "security_reviewer_agent_id",
            "that identity must differ from `implementer_agent_id`",
        ]:
            self.assertIn(phrase, apply_ref)
        self.assertIn("security_reviewer_agent_id", schema_defs["TaskReview"]["properties"])
        for phrase in [
            "prepare --root",
            "dispatch --run-dir",
            "record-agent --run-dir",
            "transition --run-dir",
            "recover-lock --run-dir",
            "finalize --run-dir",
            "Events.jsonl",
            "strict Step 4 validation",
            "missing dispatch packets",
            "missing spawned/completed agent lifecycle records",
            "agent profile drift",
            "apply-run-schema.json",
            "security_reviewer_agent_id",
            "implementer_agent_id",
            "validation_command_ids",
        ]:
            self.assertIn(phrase, readme)
            self.assertIn(phrase, usage)

    def test_validate_script_covers_archive_and_secret_hygiene(self) -> None:
        validate_script = (REPO_ROOT / "scripts/validate.sh").read_text(encoding="utf-8")
        for phrase in [
            "tracked_secret_hygiene_failed",
            "package_secret_hygiene_failed",
            "package_secret_hygiene_mode=filesystem",
            "openrouter_api_key",
            "OPENROUTER_API_KEY",
            "git\", \"archive\"",
            "archive_hygiene_failed",
            "package_hygiene_failed",
            "package_hygiene_mode=filesystem",
            "CODEXQB_VALIDATE_SKIP_UNITTESTS",
            "__MACOSX",
            ".local",
            "safety_contracts.py",
            "goal-compiler.md",
            "apply-orchestrator.md",
            "sanitized_zip_hygiene=passed",
            "sanitized_zip_hygiene_failed",
            "PACKAGE-MANIFEST.json",
            "CODEXQB_VALIDATE_SKIP_BEHAVIOR_SMOKE",
            "evals/run_apply_behavior_smoke.py",
            "evals/run_downstream_goal_apply_dry_run.py",
            "downstream_goal_apply_dry_run=passed",
            "evals/run_goal_apply_metric_checks.py",
            "goal_apply_metric_checks=passed",
            "apply_behavior_smoke=passed",
            "docs/FEEDBACK-CLOSURE-AUDIT.md",
            "docs/release-audits/0.3.0-feedback-closure.md",
        ]:
            self.assertIn(phrase, validate_script)

        closure_audit = (REPO_ROOT / "docs/FEEDBACK-CLOSURE-AUDIT.md").read_text(encoding="utf-8")
        for phrase in [
            "Release Blocker Items",
            "Goal Compiler Items",
            "Apply Orchestrator Items",
            "Subagent Methodology Items",
            "Eval And Release Evidence",
            "Remaining",
            "goal_apply_metric_checks=passed",
            "downstream_goal_apply_dry_run=passed",
        ]:
            self.assertIn(phrase, closure_audit)
        matrix = (REPO_ROOT / "docs/release-audits/0.3.0-feedback-closure.md").read_text(encoding="utf-8")
        for phrase in [
            "Allowed status values",
            "contract implemented",
            "artifact validated",
            "behavior smoke passed",
            "live Codex behavior observed",
            "FB-001",
            "FB-006",
            "FB-007",
            "FB-012",
            "collect_step2_planning_horizon",
            "contract_driven_work_steps",
            "0.3.0 feature-complete candidate",
        ]:
            self.assertIn(phrase, matrix)

    def test_shared_safety_contracts_are_wired(self) -> None:
        safety = SKILL_ROOT / "scripts/safety_contracts.py"
        self.assertTrue(safety.is_file())
        for path in [
            REPO_ROOT / "scripts/export_sanitized.py",
            SKILL_ROOT / "scripts/validate_planner_docs.py",
            SKILL_ROOT / "scripts/goal_run.py",
            SKILL_ROOT / "scripts/apply_run.py",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("safety_contracts", text, path.as_posix())

    def test_plugin_metadata_reflects_030_goal_apply_release(self) -> None:
        plugin_text = (REPO_ROOT / "plugins/codexqb/.codex-plugin/plugin.json").read_text(encoding="utf-8")
        self.assertIn('"version": "0.3.0"', plugin_text)
        for phrase in [
            "project comprehension",
            "evidence",
            "traceability",
            "vibecoding",
            "ontology",
            "ledger",
            "gate",
            "semantic",
            "adaptive",
            "goal",
            "apply",
        ]:
            self.assertIn(phrase, plugin_text.lower())

        yaml_text = (SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        default_prompt = read_simple_yaml_scalar(yaml_text, "default_prompt") or ""
        short_description = read_simple_yaml_scalar(yaml_text, "short_description") or ""
        self.assertIn("$codexqb", default_prompt)
        self.assertIn("comprehension", default_prompt.lower())
        self.assertIn("evidence", default_prompt.lower())
        self.assertLessEqual(len(short_description), 80)
        self.assertLessEqual(len(default_prompt), 220)

    def test_second_planner_keeps_security_and_ontology_out_of_scope_clean(self) -> None:
        second = (SKILL_ROOT / "references/Second-Planner.md").read_text(encoding="utf-8")
        scope = second.split("## 4. Scope", 1)[1].split("## 5. Out of Scope", 1)[0]
        out_of_scope = second.split("## 5. Out of Scope", 1)[1].split("## 6. Current Repository Evidence", 1)[0]

        self.assertIn("secure coding and secure-by-design expectations where relevant", scope)
        self.assertIn("ontology, lifecycle, or invariant consistency where relevant", scope)
        self.assertNotIn("secure coding and secure-by-design expectations where relevant", out_of_scope)
        self.assertNotIn("ontology, lifecycle, or invariant consistency where relevant", out_of_scope)

    def test_autopsy_sensitive_discovery_is_file_name_only(self) -> None:
        autopsy = (SKILL_ROOT / "references/Autopsy-Planner.md").read_text(encoding="utf-8")
        normal_scan = next(line for line in autopsy.splitlines() if line.strip().startswith("- rg \"TODO|FIXME"))
        sensitive_scan = next(line for line in autopsy.splitlines() if "secret|token|credential" in line and "rg -l" in line)

        self.assertNotIn("secret|token|credential", normal_scan)
        self.assertIn("rg -l", sensitive_scan)
        self.assertIn("file-name-only", autopsy)

    def test_project_comprehension_reference_and_prompts_are_wired(self) -> None:
        ref = SKILL_ROOT / "references/project-comprehension-methods.md"
        self.assertTrue(ref.is_file())
        ref_text = ref.read_text(encoding="utf-8")
        for phrase in [
            "question-driven comprehension",
            "why/how/what hypotheses",
            "Evidence Register",
            "Domain-to-Code Trace Map",
            "Architecture Reflexion",
            "QAW/ATAM-lite",
            "Goal/Question/Evidence",
        ]:
            self.assertIn(phrase, ref_text)

        checked_files = [
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "references/Autopsy-Planner.md",
            SKILL_ROOT / "references/Second-Planner.md",
            SKILL_ROOT / "references/Third-Planner.md",
            SKILL_ROOT / "references/Fourth-Planner.md",
        ]
        for path in checked_files:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Project-Comprehension.md", text, path.name)
            self.assertIn("project-comprehension-methods.md", text, path.name)

    def test_goal_run_contract_uses_canonical_handoff_sources(self) -> None:
        handoff_root = SKILL_ROOT / "references/handoffs"
        for name in ["run-step2.md", "run-step3.md", "run-step4.md"]:
            path = handoff_root / name
            self.assertTrue(path.is_file(), name)
            text = path.read_text(encoding="utf-8")
            self.assertIn("contract_version: 2", text)
            self.assertIn("Goal Run Contract", text)
            self.assertIn("Resume / Recovery Protocol", text)
            for phrase in [
                "Outcome",
                "Inputs",
                "Boundaries",
                "Source precedence",
                "Validation gates",
                "Stop gates",
                "Context budget",
                "Subagent policy",
            ]:
                self.assertIn(phrase, text, name)

        references = {
            "SKILL.md": SKILL_ROOT / "SKILL.md",
            "Second-Planner.md": SKILL_ROOT / "references/Second-Planner.md",
            "Third-Planner.md": SKILL_ROOT / "references/Third-Planner.md",
            "Fourth-Planner.md": SKILL_ROOT / "references/Fourth-Planner.md",
        }
        for name, path in references.items():
            text = path.read_text(encoding="utf-8")
            self.assertIn("references/handoffs/", text, name)
            self.assertNotIn("Goal Run Contract:\n- Outcome:", text, name)

    def test_step2_adaptive_horizon_and_step3_handoff_do_not_regress(self) -> None:
        step2_handoff = (SKILL_ROOT / "references/handoffs/run-step2.md").read_text(encoding="utf-8")
        second = (SKILL_ROOT / "references/Second-Planner.md").read_text(encoding="utf-8")

        self.assertIn("active planning horizon", step2_handoff)
        self.assertIn("deferred roadmap cards", step2_handoff)
        self.assertIn("Planning modes", step2_handoff)
        self.assertNotIn("Do not stop until all phases are covered", step2_handoff)

        self.assertIn("exact canonical Step 3 handoff from `references/handoffs/run-step3.md`", second)
        self.assertNotIn("Use $codexqb. Run Step 3 according to references/Third-Planner.md.", second)
        self.assertNotIn("Do not stop until all phases and sub-plans have been reviewed.", (SKILL_ROOT / "references/handoffs/run-step3.md").read_text(encoding="utf-8"))

    def test_comprehension_validator_contract_is_documented(self) -> None:
        validator = (SKILL_ROOT / "scripts/validate_planner_docs.py").read_text(encoding="utf-8")
        for phrase in [
            "COMPREHENSION_HEADINGS",
            "Project-Comprehension.md",
            "ALLOWED_EVIDENCE_TYPES",
            "ALLOWED_CONFIDENCE_VALUES",
            "ALLOWED_CLAIM_TYPES",
            "ALLOWED_ARCHITECTURE_STATUSES",
            "ALLOWED_ONTOLOGY_QUESTION_STATUSES",
            "markdown_headings",
            "validate_optional_comprehension_doc",
            "NOT_APPLICABLE",
            "NO_UNRESOLVED_HYPOTHESES",
        ]:
            self.assertIn(phrase, validator)

    def test_planning_ledger_v3_is_documented_and_legacy_remains_supported(self) -> None:
        ledger_ref = (SKILL_ROOT / "references/planning-ledger.md").read_text(encoding="utf-8")
        validator = (SKILL_ROOT / "scripts/validate_planner_docs.py").read_text(encoding="utf-8")
        for phrase in ["Plan Snapshot Registry", "Sub-Plan Status Matrix", "Ledger v3", "legacy v1", "Planning Evidence", "Implementation Evidence", "Superseded By", "Updated At"]:
            self.assertIn(phrase, ledger_ref)
        self.assertIn("LEDGER_V3_HEADINGS", validator)
        self.assertIn("LEDGER_V2_HEADINGS", validator)
        self.assertIn("LEDGER_LEGACY_HEADINGS", validator)
        self.assertIn("ALLOWED_LEDGER_STATUSES", validator)

    def test_ci_and_export_sanitized_are_hardened(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("push:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertNotIn("branches: [main]", workflow)
        self.assertIn("matrix:", workflow)
        self.assertIn('python-version: ["3.12", "3.13"]', workflow)
        self.assertIn("python-version: ${{ matrix.python-version }}", workflow)
        self.assertIn("scripts/export_sanitized.py", makefile)
        self.assertIn("check-fast", makefile)
        self.assertIn("check-behavior", makefile)
        self.assertIn("check-release", makefile)
        self.assertIn("export-sanitized-worktree", makefile)
        export_script = (REPO_ROOT / "scripts/export_sanitized.py").read_text(encoding="utf-8")
        self.assertIn("CodexQB-sanitized.zip", export_script)
        self.assertIn("IGNORED_PARTS", export_script)
        self.assertIn("BLOCKED_SUFFIXES", export_script)
        self.assertIn("PACKAGE-MANIFEST.json", export_script)
        self.assertIn("working_tree_dirty", export_script)
        self.assertIn("head_mismatch_origin_main", export_script)

    def test_fixture_corpus_infrastructure_is_present(self) -> None:
        runner = REPO_ROOT / "evals/run_fixture_corpus_checks.py"
        wrapper = REPO_ROOT / "evals/run_fixture_checks.py"
        apply_smoke = REPO_ROOT / "evals/run_apply_behavior_smoke.py"
        downstream_smoke = REPO_ROOT / "evals/run_downstream_goal_apply_dry_run.py"
        metric_smoke = REPO_ROOT / "evals/run_goal_apply_metric_checks.py"
        self.assertTrue(runner.is_file())
        self.assertTrue(wrapper.is_file())
        self.assertTrue(apply_smoke.is_file())
        self.assertTrue(downstream_smoke.is_file())
        self.assertTrue(metric_smoke.is_file())
        runner_text = runner.read_text(encoding="utf-8")
        smoke_text = apply_smoke.read_text(encoding="utf-8")
        downstream_text = downstream_smoke.read_text(encoding="utf-8")
        metric_text = metric_smoke.read_text(encoding="utf-8")
        self.assertIn("fixture_corpus_checks=passed", runner_text)
        self.assertIn("apply_behavior_smoke=passed", smoke_text)
        self.assertIn("apply_run_finalized", smoke_text)
        for phrase in [
            "downstream_goal_apply_dry_run=passed",
            "step3-preflight",
            "subagent_serial",
            "Use only this fresh task context",
            "Structured Implementation Contract",
        ]:
            self.assertIn(phrase, downstream_text)
        for phrase in [
            "goal_apply_metric_checks=passed",
            "static_step4_handoff",
            "dynamic_step4_goal_direct",
            "dynamic_step4_goal_subagent_serial",
            "apply_direct_brief",
            "apply_subagent_dispatch_message",
        ]:
            self.assertIn(phrase, metric_text)
        self.assertNotIn("fixture_eval_checks=passed", runner_text)
        fixture_root = REPO_ROOT / "evals/fixtures"
        for fixture in [
            "adaptive-wave-planning",
            "clean-layered-service",
            "drifted-architecture",
            "distributed-domain-feature",
            "hidden-coupling-signal",
            "stale-ledger",
            "runtime-only-behavior",
            "security-boundary-risk",
            "dynamic-step2-goal",
            "dynamic-step3-goal",
            "dynamic-step4-goal",
            "apply-happy-path",
            "apply-review-fix-rereview",
            "apply-security-gate",
            "apply-interrupted-resume",
            "apply-stale-snapshot",
            "apply-run-id-collision",
            "apply-no-action",
            "export-untracked-secret",
            "export-external-symlink",
        ]:
            self.assertTrue((fixture_root / fixture / "expected.json").is_file(), fixture)

        validate_script = (REPO_ROOT / "scripts/validate.sh").read_text(encoding="utf-8")
        self.assertIn("python3 evals/run_fixture_corpus_checks.py", validate_script)
        self.assertIn("python3 evals/run_downstream_goal_apply_dry_run.py", validate_script)
        self.assertIn("--allow-dirty --allow-head-mismatch", validate_script)

    def test_probe_policy_and_schema_versions_are_documented(self) -> None:
        probe = SKILL_ROOT / "references/probe-policy.md"
        self.assertTrue(probe.is_file())
        probe_text = probe.read_text(encoding="utf-8")
        for phrase in ["Tier 0", "Tier 1", "Tier 2", "Tier 3", "approval", "timeout", "cleanup"]:
            self.assertIn(phrase, probe_text)

        for path in [REPO_ROOT / "README.md", REPO_ROOT / "docs/USAGE.md", REPO_ROOT / "docs/MAINTAINING.md"]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("artifact_schema_version: 3", text, path.name)
            self.assertIn("handoff_contract_version: 2", text, path.name)
            self.assertIn("fixture corpus", text.lower(), path.name)

    def test_local_skill_sync_docs_exclude_python_caches(self) -> None:
        install = (REPO_ROOT / "docs/INSTALLATION.md").read_text(encoding="utf-8")
        maintaining = (REPO_ROOT / "docs/MAINTAINING.md").read_text(encoding="utf-8")
        for text in [install, maintaining]:
            self.assertIn("--exclude '__pycache__/'", text)
            self.assertIn("--exclude '*.pyc'", text)
            self.assertIn("diff -ru -x __pycache__", text)

    def test_validate_script_runs_without_git_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir) / "CodexQB"

            def ignore(_dir: str, names: list[str]) -> set[str]:
                ignored = {
                    ".git",
                    "__pycache__",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                    "CodexQB-sanitized.zip",
                }
                return ignored.intersection(names)

            shutil.copytree(REPO_ROOT, package_root, ignore=ignore)
            env = os.environ.copy()
            env["CODEXQB_VALIDATE_SKIP_UNITTESTS"] = "1"
            result = subprocess.run(
                ["bash", "scripts/validate.sh"],
                cwd=package_root,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("package_secret_hygiene_mode=filesystem", result.stdout)
            self.assertIn("package_hygiene_mode=filesystem", result.stdout)
            self.assertIn("unit_tests_skipped=1", result.stdout)

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

    def test_autopsy_validator_mode_is_documented(self) -> None:
        validator = (SKILL_ROOT / "scripts/validate_planner_docs.py").read_text(encoding="utf-8")
        autopsy = (SKILL_ROOT / "references/Autopsy-Planner.md").read_text(encoding="utf-8")
        maintaining = (REPO_ROOT / "docs/MAINTAINING.md").read_text(encoding="utf-8")
        self.assertIn('"autopsy"', validator)
        self.assertIn("--mode autopsy --strict", autopsy)
        self.assertIn("--mode autopsy --strict", maintaining)

    def test_vibecoding_and_subagent_references_are_wired(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        usage = (REPO_ROOT / "docs/USAGE.md").read_text(encoding="utf-8")

        expected_refs = [
            "vibecoding-principles.md",
            "subagent-playbook.md",
            "planning-ledger.md",
            "project-ontology.md",
            "assessment-and-budget.md",
            "engineering-principles.md",
        ]
        for ref in expected_refs:
            self.assertTrue((SKILL_ROOT / "references" / ref).is_file(), ref)
            self.assertIn(ref, skill, ref)

        for text_blob in [skill, readme, usage]:
            self.assertIn("vibecoding-first", text_blob.lower())
            self.assertIn("subagent", text_blob.lower())

    def test_planning_ledger_and_ontology_are_documented(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        usage = (REPO_ROOT / "docs/USAGE.md").read_text(encoding="utf-8")
        second = (SKILL_ROOT / "references/Second-Planner.md").read_text(encoding="utf-8")
        fourth = (SKILL_ROOT / "references/Fourth-Planner.md").read_text(encoding="utf-8")

        for artifact in ["Planner-docs/Planing-Ledger.md", "Planner-docs/Project-Ontology.md"]:
            self.assertIn(artifact, skill)
            self.assertIn(artifact, usage)

        self.assertIn("Planing-Ledger.md", second)
        self.assertIn("Project-Ontology.md", second)
        self.assertIn("Planing-Ledger.md", fourth)

    def test_prompt_secret_scans_do_not_print_secret_values(self) -> None:
        prompt_paths = list((SKILL_ROOT / "references").glob("*.md")) + [SKILL_ROOT / "SKILL.md"]
        for path in prompt_paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('rg -n "sk-', text, path.name)
        workflow_quality = (SKILL_ROOT / "references/workflow-quality.md").read_text(encoding="utf-8")
        self.assertIn("file-name-only", workflow_quality)

    def test_fourth_planner_mentions_subagent_roles_and_ledger(self) -> None:
        fourth = (SKILL_ROOT / "references/Fourth-Planner.md").read_text(encoding="utf-8")
        for phrase in [
            "explorer maps relevant files and risks",
            "tester/verifier identifies validation path",
            "implementer/worker makes the smallest change",
            "reviewer/security reviews the diff",
            "Only one writer should modify files per slice",
            "Planner-docs/Planing-Ledger.md",
        ]:
            self.assertIn(phrase, fourth)

    def test_validator_supports_optional_ontology_and_ledger_headings(self) -> None:
        validator = (SKILL_ROOT / "scripts/validate_planner_docs.py").read_text(encoding="utf-8")
        for phrase in [
            "ONTOLOGY_HEADINGS",
            "LEDGER_HEADINGS",
            "Project-Ontology.md",
            "Planing-Ledger.md",
            "validate_optional_continuity_docs",
        ]:
            self.assertIn(phrase, validator)


if __name__ == "__main__":
    unittest.main()
