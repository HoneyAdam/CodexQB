#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TRUSTED_GIT="$(PATH=/bin:/usr/bin command -v git || true)"
if [[ -z "$TRUSTED_GIT" ]]; then
  echo "trusted_git_executable_unavailable"
  exit 1
fi
export CODEXQB_TRUSTED_GIT="$TRUSTED_GIT"
GIT_TOP_LEVEL="$("$TRUSTED_GIT" rev-parse --show-toplevel 2>/dev/null || true)"
IS_EXACT_GIT_ROOT=0
if [[ -n "$GIT_TOP_LEVEL" && "$(cd "$GIT_TOP_LEVEL" && pwd -P)" == "$(pwd -P)" ]]; then
  IS_EXACT_GIT_ROOT=1
fi
TMPDIR_VALIDATE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_VALIDATE"' EXIT
export CODEXQB_TRUST_ROOT="$TMPDIR_VALIDATE/codexqb-trust"
mkdir -m 700 "$CODEXQB_TRUST_ROOT"

python3 -m json.tool .agents/plugins/marketplace.json >/dev/null
python3 -m json.tool plugins/codexqb/.codex-plugin/plugin.json >/dev/null

required_files=(
  ".agents/plugins/marketplace.json"
  "plugins/codexqb/.codex-plugin/plugin.json"
  "plugins/codexqb/skills/codexqb/SKILL.md"
  "plugins/codexqb/skills/codexqb/agents/openai.yaml"
  "plugins/codexqb/skills/codexqb/scripts/safety_contracts.py"
  "plugins/codexqb/skills/codexqb/scripts/artifact_io.py"
  "plugins/codexqb/skills/codexqb/scripts/evidence_contracts.py"
  "plugins/codexqb/skills/codexqb/scripts/repository_evidence.py"
  "plugins/codexqb/skills/codexqb/scripts/git_evidence.py"
  "plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py"
  "plugins/codexqb/skills/codexqb/scripts/goal_run.py"
  "plugins/codexqb/skills/codexqb/scripts/apply_run.py"
  "plugins/codexqb/skills/codexqb/references/First-Planner.md"
  "plugins/codexqb/skills/codexqb/references/Autopsy-Planner.md"
  "plugins/codexqb/skills/codexqb/references/Second-Planner.md"
  "plugins/codexqb/skills/codexqb/references/Third-Planner.md"
  "plugins/codexqb/skills/codexqb/references/Fourth-Planner.md"
  "plugins/codexqb/skills/codexqb/references/goal-compiler.md"
  "plugins/codexqb/skills/codexqb/references/apply-orchestrator.md"
  "plugins/codexqb/skills/codexqb/references/apply-run-schema.json"
  "plugins/codexqb/skills/codexqb/references/apply/controller.md"
  "plugins/codexqb/skills/codexqb/references/apply/implementer.md"
  "plugins/codexqb/skills/codexqb/references/apply/task-reviewer.md"
  "plugins/codexqb/skills/codexqb/references/apply/security-reviewer.md"
  "plugins/codexqb/skills/codexqb/references/apply/fixer.md"
  "plugins/codexqb/skills/codexqb/references/apply/final-reviewer.md"
  "plugins/codexqb/skills/codexqb/references/goal-specs/step15.md"
  "plugins/codexqb/skills/codexqb/references/goal-specs/step2.md"
  "plugins/codexqb/skills/codexqb/references/goal-specs/step3.md"
  "plugins/codexqb/skills/codexqb/references/goal-specs/step4.md"
  "plugins/codexqb/skills/codexqb/references/handoffs/run-step2.md"
  "plugins/codexqb/skills/codexqb/references/handoffs/run-step3.md"
  "plugins/codexqb/skills/codexqb/references/handoffs/run-step4.md"
  "plugins/codexqb/skills/codexqb/references/repo-aware-intake.md"
  "plugins/codexqb/skills/codexqb/references/workflow-quality.md"
  "plugins/codexqb/skills/codexqb/references/vibecoding-principles.md"
  "plugins/codexqb/skills/codexqb/references/subagent-playbook.md"
  "plugins/codexqb/skills/codexqb/references/planning-ledger.md"
  "plugins/codexqb/skills/codexqb/references/project-ontology.md"
  "plugins/codexqb/skills/codexqb/references/project-comprehension-methods.md"
  "plugins/codexqb/skills/codexqb/references/probe-policy.md"
  "plugins/codexqb/skills/codexqb/references/assessment-and-budget.md"
  "plugins/codexqb/skills/codexqb/references/engineering-principles.md"
  "evals/run_apply_behavior_smoke.py"
  "evals/run_downstream_goal_apply_dry_run.py"
  "evals/run_goal_apply_metric_checks.py"
  "evals/run_fixture_corpus_checks.py"
  "evals/run_fixture_checks.py"
  "requirements-ci.txt"
  "scripts/export_sanitized.py"
  "scripts/validate_openai_yaml.py"
  "scripts/verify_package_manifest.py"
  "scripts/validate_apply_schema.py"
  "tests/test_package_manifest.py"
  "tests/test_apply_schema.py"
  "tests/test_apply_inventory.py"
  "tests/test_evidence_contracts.py"
  "tests/test_repository_evidence.py"
  "tests/test_git_evidence.py"
  "README.md"
  "CHANGELOG.md"
  "docs/INSTALLATION.md"
  "docs/USAGE.md"
  "docs/MAINTAINING.md"
  "docs/FEEDBACK-CLOSURE-AUDIT.md"
  "docs/release-audits/0.3.0-feedback-closure.md"
  "LICENSE"
)

for path in "${required_files[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing_required_file=$path"
    exit 1
  fi
done

if [[ -f "PACKAGE-MANIFEST.json" ]]; then
  python3 scripts/verify_package_manifest.py --root .
elif [[ "$IS_EXACT_GIT_ROOT" != "1" ]]; then
  echo "package_manifest_missing_for_gitless_tree"
  exit 1
fi

python3 scripts/validate_openai_yaml.py

python3 - <<'PY'
from pathlib import Path
import sys

needles = ("project-" + "planner", "Project " + "Planner", "$" + "project-" + "planner")
ignored_parts = {
    ".git",
    "__MACOSX",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "artifacts",
    "build",
    "dist",
    "logs",
    "tmp",
}
blocked_suffixes = {".key", ".pem", ".pyc", ".zip"}
findings: list[str] = []
for path in Path(".").rglob("*"):
    if not path.is_file():
        continue
    if ignored_parts.intersection(path.parts):
        continue
    if path.suffix in blocked_suffixes:
        continue
    if path.name == ".DS_Store" or path.name.startswith(".env"):
        continue
    if path.name.endswith(".local") or ".local." in path.name:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for needle in needles:
        if needle in text:
            findings.append(f"{path}: contains stale invocation text")
            break

if findings:
    print("stale_invocation_references_found")
    for finding in findings:
        print(finding)
    sys.exit(1)
PY

python3 - <<'PY'
from pathlib import Path
import os
import subprocess
import sys

safety_dir = Path("plugins/codexqb/skills/codexqb/scripts").resolve()
sys.path.insert(0, safety_dir.as_posix())
from safety_contracts import literal_secret_match_locations, secret_match_locations  # noqa: E402

GIT = os.environ["CODEXQB_TRUSTED_GIT"]

def in_git_checkout() -> bool:
    return subprocess.run(
        [GIT, "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def package_paths() -> list[Path]:
    ignored_parts = {
        ".git",
        "__MACOSX",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "artifacts",
        "build",
        "dist",
        "logs",
        "tmp",
    }
    paths: list[Path] = []
    for path in Path(".").rglob("*"):
        if not path.is_file():
            continue
        if ignored_parts.intersection(path.parts):
            continue
        if path.name == ".DS_Store":
            continue
        paths.append(path)
    return paths


if in_git_checkout():
    tracked = subprocess.run([GIT, "ls-files", "-z"], check=True, capture_output=True).stdout
    paths = [Path(item.decode("utf-8")) for item in tracked.split(b"\0") if item]
    failure_label = "tracked_secret_hygiene_failed"
else:
    paths = package_paths()
    failure_label = "package_secret_hygiene_failed"
    print("package_secret_hygiene_mode=filesystem")

# Shared provider labels include openrouter_api_key. Canonical placeholders such
# as OPENROUTER_API_KEY=${OPENROUTER_API_KEY} are handled by the shared policy.

findings: list[str] = []
for path in paths:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue

    scanner = literal_secret_match_locations if path.suffix.lower() in {".py", ".sh", ".json"} else secret_match_locations
    for name, offset in scanner(text):
        line_number = text.count("\n", 0, offset) + 1
        findings.append(f"{path}:{line_number}: {name}")

if findings:
    print(failure_label)
    for finding in findings:
        print(finding)
    sys.exit(1)
PY

python3 - <<'PY'
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

GIT = os.environ["CODEXQB_TRUSTED_GIT"]

bad = re.compile(
    r"(^|/)(\.git|__pycache__|\.env|artifacts|logs|tmp|__MACOSX)(/|$)"
    r"|\.pyc$|\.pem$|\.key$|\.local($|\.)"
)

def in_git_checkout() -> bool:
    return subprocess.run(
        [GIT, "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def package_offenders() -> list[str]:
    ignored_parts = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "build",
        "dist",
    }
    offenders: list[str] = []
    for path in Path(".").rglob("*"):
        if not path.is_file():
            continue
        if ignored_parts.intersection(path.parts):
            continue
        rel = path.as_posix()
        if bad.search(rel):
            offenders.append(rel)
    return offenders


if in_git_checkout():
    archive = subprocess.run([GIT, "archive", "--format=tar", "HEAD"], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        offenders = [member.name for member in tar.getmembers() if bad.search(member.name)]
    failure_label = "archive_hygiene_failed"
else:
    offenders = package_offenders()
    failure_label = "package_hygiene_failed"
    print("package_hygiene_mode=filesystem")

if offenders:
    print(failure_label)
    for offender in offenders:
        print(offender)
    sys.exit(1)
PY

if [[ "$IS_EXACT_GIT_ROOT" == "1" ]]; then
  python3 scripts/export_sanitized.py --root . --output "$TMPDIR_VALIDATE/CodexQB-sanitized.zip" --include-untracked --allow-dirty --allow-head-mismatch >/dev/null
else
  python3 scripts/export_sanitized.py --root . --output "$TMPDIR_VALIDATE/CodexQB-sanitized.zip" --source-package >/dev/null
fi
python3 scripts/verify_package_manifest.py --zip "$TMPDIR_VALIDATE/CodexQB-sanitized.zip"
CODEXQB_SANITIZED_ZIP="$TMPDIR_VALIDATE/CodexQB-sanitized.zip" python3 - <<'PY'
import os
import re
import sys
import zipfile
from pathlib import Path

safety_dir = Path("plugins/codexqb/skills/codexqb/scripts").resolve()
sys.path.insert(0, safety_dir.as_posix())
from safety_contracts import literal_secret_match_locations, secret_match_locations  # noqa: E402

bad = re.compile(
    r"(^|/)(\.git|\.codexqb|__pycache__|\.env|artifacts|logs|tmp|__MACOSX)(/|$)"
    r"|\.pyc$|\.pem$|\.key$|\.local($|\.)"
)
archive_path = Path(os.environ["CODEXQB_SANITIZED_ZIP"])
offenders: list[str] = []
secret_offenders: list[str] = []
with zipfile.ZipFile(archive_path) as archive:
    names = set(archive.namelist())
    if "CodexQB/PACKAGE-MANIFEST.json" not in names:
        offenders.append("missing_package_manifest")
    for info in archive.infolist():
        name = info.filename
        if bad.search(name):
            offenders.append(name)
            continue
        if info.is_dir():
            continue
        data = archive.read(info)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        scanner = (
            literal_secret_match_locations
            if Path(name).suffix.lower() in {".py", ".sh", ".json"}
            else secret_match_locations
        )
        if scanner(text):
            secret_offenders.append(name)

if offenders or secret_offenders:
    print("sanitized_zip_hygiene_failed")
    for offender in offenders:
        print(f"blocked_path={offender}")
    for offender in secret_offenders:
        print(f"secret_like_content={offender}")
    sys.exit(1)
print("sanitized_zip_hygiene=passed")
PY

if [[ "${CODEXQB_VALIDATE_SKIP_UNITTESTS:-0}" == "1" ]]; then
  echo "unit_tests_skipped=1"
else
  python3 -m unittest discover -s tests -v
fi

if [[ "${CODEXQB_VALIDATE_SKIP_BEHAVIOR_SMOKE:-0}" == "1" ]]; then
  echo "behavior_smokes_skipped=1"
else
  # evals/run_apply_behavior_smoke.py prints apply_behavior_smoke=passed on success.
  python3 evals/run_apply_behavior_smoke.py
  # evals/run_downstream_goal_apply_dry_run.py prints downstream_goal_apply_dry_run=passed on success.
  python3 evals/run_downstream_goal_apply_dry_run.py
fi
# evals/run_goal_apply_metric_checks.py prints goal_apply_metric_checks=passed on success.
python3 evals/run_goal_apply_metric_checks.py
python3 evals/run_fixture_corpus_checks.py
