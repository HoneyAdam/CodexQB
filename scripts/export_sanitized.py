#!/usr/bin/env python3
"""Create a sanitized CodexQB source zip from the current worktree.

Unlike `git archive`, this includes uncommitted repository-scope changes so the
package gate can be run before a commit. It still excludes local/runtime/cache
content and never reads outside the repository.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path


SAFETY_DIR = Path(__file__).resolve().parents[1] / "plugins/codexqb/skills/codexqb/scripts"
if str(SAFETY_DIR) not in sys.path:
    sys.path.insert(0, str(SAFETY_DIR))

from safety_contracts import has_secret_like, path_is_inside  # noqa: E402


IGNORED_PARTS = {
    ".git",
    ".codexqb",
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
BLOCKED_SUFFIXES = {".pyc", ".pem", ".key", ".zip"}
BLOCKED_RE = re.compile(
    r"(^|/)(\.git|\.codexqb|__pycache__|\.env|artifacts|logs|tmp|__MACOSX)(/|$)|"
    r"\.pyc$|\.pem$|\.key$|\.local($|\.)"
)


def run_git(root: Path, args: list[str]) -> list[str] | None:
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
        return None
    if completed.returncode != 0:
        return None
    return [line for line in completed.stdout.splitlines() if line.strip()]


def candidate_paths(root: Path, *, include_untracked: bool) -> list[Path]:
    tracked = run_git(root, ["ls-files", "--cached"])
    if tracked is None:
        return sorted(path for path in root.rglob("*"))
    rels = set(tracked)
    if include_untracked:
        rels.update(run_git(root, ["ls-files", "--others", "--exclude-standard"]) or [])
    return sorted(root / rel for rel in rels)


def should_include(path: Path, root: Path, output: Path, errors: list[str]) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        errors.append(f"path_outside_repo={path}")
        return False
    if path.is_symlink():
        errors.append(f"symlink_rejected={rel.as_posix()}")
        return False
    resolved = path.resolve()
    if not path_is_inside(root, resolved):
        errors.append(f"path_outside_repo={rel.as_posix()}")
        return False
    if resolved == output.resolve():
        return False
    if not path.is_file():
        return False
    if IGNORED_PARTS.intersection(rel.parts):
        return False
    if path.name == ".DS_Store" or path.name.startswith(".env"):
        return False
    if path.suffix in BLOCKED_SUFFIXES:
        return False
    if path.name.endswith(".local") or ".local." in path.name:
        return False
    if BLOCKED_RE.search(rel.as_posix()):
        return False
    try:
        data = path.read_bytes()
    except OSError as exc:
        errors.append(f"read_error={rel.as_posix()}:{exc}")
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    if text and has_secret_like(text):
        errors.append(f"secret_like_content={rel.as_posix()}")
        return False
    return True


def create_zip(root: Path, output: Path, *, include_untracked: bool = False) -> int:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    files = [
        path
        for path in candidate_paths(root, include_untracked=include_untracked)
        if should_include(path, root, output, errors)
    ]
    if errors:
        raise ValueError(";".join(errors))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            rel = path.relative_to(root).as_posix()
            archive.write(path, f"CodexQB/{rel}")
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create CodexQB-sanitized.zip from the current worktree.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="CodexQB-sanitized.zip")
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Include untracked, non-ignored files after symlink and secret scanning.",
    )
    args = parser.parse_args()
    count = create_zip(Path(args.root), Path(args.output), include_untracked=args.include_untracked)
    print(f"sanitized_export=created")
    print(f"file_count={count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
