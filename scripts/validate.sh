#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m json.tool .agents/plugins/marketplace.json >/dev/null
python3 -m json.tool plugins/codexqb/.codex-plugin/plugin.json >/dev/null

required_files=(
  ".agents/plugins/marketplace.json"
  "plugins/codexqb/.codex-plugin/plugin.json"
  "plugins/codexqb/skills/codexqb/SKILL.md"
  "plugins/codexqb/skills/codexqb/agents/openai.yaml"
  "plugins/codexqb/skills/codexqb/scripts/validate_planner_docs.py"
  "plugins/codexqb/skills/codexqb/references/First-Planner.md"
  "plugins/codexqb/skills/codexqb/references/Autopsy-Planner.md"
  "plugins/codexqb/skills/codexqb/references/Second-Planner.md"
  "plugins/codexqb/skills/codexqb/references/Third-Planner.md"
  "plugins/codexqb/skills/codexqb/references/Fourth-Planner.md"
  "plugins/codexqb/skills/codexqb/references/repo-aware-intake.md"
  "plugins/codexqb/skills/codexqb/references/workflow-quality.md"
  "README.md"
  "docs/INSTALLATION.md"
  "docs/USAGE.md"
  "docs/MAINTAINING.md"
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

text = Path("plugins/codexqb/skills/codexqb/agents/openai.yaml").read_text(encoding="utf-8")
required = ("display_name:", "short_description:", "default_prompt:")
missing = [key for key in required if key not in text]
if missing:
    print("openai_yaml_missing_keys=" + ",".join(missing))
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

python3 -m unittest discover -s tests -v
