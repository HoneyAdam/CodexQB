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
import zipfile
from pathlib import Path


IGNORED_PARTS = {
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
BLOCKED_SUFFIXES = {".pyc", ".pem", ".key", ".zip"}
BLOCKED_RE = re.compile(r"(^|/)(\.git|__pycache__|\.env|artifacts|logs|tmp|__MACOSX)(/|$)|\.pyc$|\.pem$|\.key$|\.local($|\.)")


def should_include(path: Path, root: Path, output: Path) -> bool:
    if not path.is_file():
        return False
    if path.resolve() == output.resolve():
        return False
    rel = path.relative_to(root)
    if IGNORED_PARTS.intersection(rel.parts):
        return False
    if path.name == ".DS_Store" or path.name.startswith(".env"):
        return False
    if path.suffix in BLOCKED_SUFFIXES:
        return False
    if path.name.endswith(".local") or ".local." in path.name:
        return False
    return not BLOCKED_RE.search(rel.as_posix())


def create_zip(root: Path, output: Path) -> int:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in root.rglob("*") if should_include(path, root, output))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            rel = path.relative_to(root).as_posix()
            archive.write(path, f"CodexQB/{rel}")
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create CodexQB-sanitized.zip from the current worktree.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="CodexQB-sanitized.zip")
    args = parser.parse_args()
    count = create_zip(Path(args.root), Path(args.output))
    print(f"sanitized_export=created")
    print(f"file_count={count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
