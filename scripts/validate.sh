#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TMPDIR_VALIDATE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_VALIDATE"' EXIT

python3 -m json.tool .agents/plugins/marketplace.json >/dev/null
python3 -m json.tool plugins/codexqb/.codex-plugin/plugin.json >/dev/null

required_files=(
  ".agents/plugins/marketplace.json"
  "plugins/codexqb/.codex-plugin/plugin.json"
  "plugins/codexqb/skills/codexqb/SKILL.md"
  "plugins/codexqb/skills/codexqb/agents/openai.yaml"
  "plugins/codexqb/skills/codexqb/scripts/safety_contracts.py"
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
  "scripts/export_sanitized.py"
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

python3 - <<'PY'
from pathlib import Path
import sys

path = Path("plugins/codexqb/skills/codexqb/agents/openai.yaml")
text = path.read_text(encoding="utf-8")

def scalar(key: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(f"{key}:"):
            continue
        value = stripped.split(":", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value
    return None

display_name = scalar("display_name")
short_description = scalar("short_description")
default_prompt = scalar("default_prompt")

errors: list[str] = []
if display_name != "CodexQB":
    errors.append(f"display_name={display_name!r}")
if short_description is None:
    errors.append("missing short_description")
elif len(short_description) > 80:
    errors.append(f"short_description_too_long={len(short_description)}")
if default_prompt is None:
    errors.append("missing default_prompt")
else:
    if "$codexqb" not in default_prompt:
        errors.append("default_prompt_missing_$codexqb")
    if len(default_prompt) > 220:
        errors.append(f"default_prompt_too_long={len(default_prompt)}")

if errors:
    print("openai_yaml_semantic_check_failed")
    for error in errors:
        print(error)
    sys.exit(1)
PY

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
import re
import subprocess
import sys

def in_git_checkout() -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
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
    tracked = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True).stdout
    paths = [Path(item.decode("utf-8")) for item in tracked.split(b"\0") if item]
    failure_label = "tracked_secret_hygiene_failed"
else:
    paths = package_paths()
    failure_label = "package_secret_hygiene_failed"
    print("package_secret_hygiene_mode=filesystem")

secret_patterns = [
    ("openrouter_api_key", re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b")),
    ("openai_api_key", re.compile(r"\bsk-(?!or-v1-)[A-Za-z0-9_-]{20,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("github_legacy_pat", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"BEGIN (?:RSA|OPENSSH|DSA|EC|PRIVATE) KEY")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
]
openrouter_env = re.compile(r"\bOPENROUTER_API_KEY\s*=\s*([^\s#]+)", re.IGNORECASE)
allowed_openrouter_values = {
    "$OPENROUTER_API_KEY",
    "<redacted>",
    "redacted",
    "your_openrouter_api_key",
}

findings: list[str] = []
for path in paths:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue

    for line_number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in secret_patterns:
            if pattern.search(line):
                findings.append(f"{path}:{line_number}: {name}")

        match = openrouter_env.search(line)
        if match:
            value = match.group(1).strip().strip("'\"")
            if value and value not in allowed_openrouter_values:
                findings.append(f"{path}:{line_number}: openrouter_env_value")

if findings:
    print(failure_label)
    for finding in findings:
        print(finding)
    sys.exit(1)
PY

python3 - <<'PY'
import io
from pathlib import Path
import re
import subprocess
import sys
import tarfile

bad = re.compile(
    r"(^|/)(\.git|__pycache__|\.env|artifacts|logs|tmp|__MACOSX)(/|$)"
    r"|\.pyc$|\.pem$|\.key$|\.local($|\.)"
)

def in_git_checkout() -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
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
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], check=True, capture_output=True).stdout
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

python3 scripts/export_sanitized.py --root . --output "$TMPDIR_VALIDATE/CodexQB-sanitized.zip" --include-untracked --allow-dirty --allow-head-mismatch >/dev/null
CODEXQB_SANITIZED_ZIP="$TMPDIR_VALIDATE/CodexQB-sanitized.zip" python3 - <<'PY'
import os
import re
import sys
import zipfile
from pathlib import Path

safety_dir = Path("plugins/codexqb/skills/codexqb/scripts").resolve()
sys.path.insert(0, safety_dir.as_posix())
from safety_contracts import has_secret_like  # noqa: E402

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
        if has_secret_like(text):
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
