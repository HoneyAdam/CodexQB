#!/usr/bin/env python3
"""Shared safety checks for CodexQB local helper scripts.

The helpers in this directory are artifact validators and preview compilers,
not executors. This module keeps command, path, and secret checks consistent
across planner validation, Goal previews, apply-run artifacts, and sanitized
exports.
"""

from __future__ import annotations

import fnmatch
import re
import shlex
from pathlib import Path


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openrouter_api_key", re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b", re.IGNORECASE)),
    ("openai_api_key", re.compile(r"\bsk-(?!or-v1-)[A-Za-z0-9_-]{20,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("github_legacy_pat", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"BEGIN (?:RSA|OPENSSH|DSA|EC|PRIVATE) KEY", re.IGNORECASE)),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)

SHELL_METACHAR_RE = re.compile(r"(?:&&|\|\||[;&|<>`]|[$]\(|\n|\r)")
MUTATING_COMMAND_INTENT_RE = re.compile(
    r"\b(?:deploy|release|publish|push|merge|destroy|delete|remove|prune|reset|checkout|apply|install|upgrade|"
    r"migrate|seed|prod|production|live|remote|clean)\b",
    re.IGNORECASE,
)
MUTATING_EXECUTABLES = {
    "rm",
    "rmdir",
    "mv",
    "cp",
    "chmod",
    "chown",
    "sudo",
    "su",
    "ssh",
    "scp",
    "rsync",
    "curl",
    "wget",
    "kubectl",
    "terraform",
    "docker",
    "gh",
    "git",
    "bash",
    "sh",
    "zsh",
}

SAFE_PYTHON_MODULES = {"pytest", "unittest", "compileall"}
SAFE_MAKE_TARGETS = {"check", "test", "lint", "typecheck", "smoke", "ci-local", "build"}
SAFE_JS_SCRIPTS = {"test", "lint", "typecheck", "build", "check"}
SAFE_RUFF_COMMANDS = {"check"}


def secret_findings(text: str) -> list[str]:
    return [name for name, pattern in SECRET_PATTERNS if pattern.search(text)]


def has_secret_like(text: str) -> bool:
    return bool(secret_findings(text))


def path_is_inside(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _strip_value(value: str) -> str:
    return value.strip().strip("`").strip("'\"")


def _path_parts(value: str) -> tuple[str, ...]:
    return Path(value).parts


def is_safe_repo_path(value: str, *, allow_glob: bool = False, allow_home: bool = False) -> bool:
    target = _strip_value(value)
    if not target:
        return False
    if target.startswith("~"):
        return allow_home and not any(part == ".." for part in _path_parts(target))
    path = Path(target)
    if path.is_absolute():
        return False
    if any(part == ".." for part in path.parts):
        return False
    if not allow_glob and any(char in target for char in "*?[]"):
        return False
    return True


def unsafe_path_in_arg(value: str) -> bool:
    raw = _strip_value(value)
    candidates = [raw]
    if "=" in raw:
        candidates.append(raw.split("=", 1)[1])
    for candidate in candidates:
        if not candidate or candidate in {".", "./", "./..."}:
            continue
        if candidate.startswith(("http://", "https://")):
            return True
        if candidate.startswith("~"):
            return True
        path = Path(candidate)
        if path.is_absolute():
            return True
        if any(part == ".." for part in path.parts):
            return True
    return False


def glob_patterns_overlap(left: str, right: str) -> bool:
    left = _strip_value(left)
    right = _strip_value(right)
    if left == right:
        return True
    if fnmatch.fnmatch(left, right) or fnmatch.fnmatch(right, left):
        return True
    left_prefix = re.split(r"[*?\[]", left, maxsplit=1)[0].rstrip("/")
    right_prefix = re.split(r"[*?\[]", right, maxsplit=1)[0].rstrip("/")
    if left_prefix and right.startswith(left_prefix + "/"):
        return True
    if right_prefix and left.startswith(right_prefix + "/"):
        return True
    return False


def parse_legacy_command(command: str) -> list[str] | None:
    command = command.strip().strip("`")
    if len(command.split()) < 2:
        return None
    if SHELL_METACHAR_RE.search(command):
        return None
    try:
        return shlex.split(command)
    except ValueError:
        return None


def safe_validation_argv(argv: object, *, allow_uv: bool = True) -> bool:
    if not isinstance(argv, list) or len(argv) < 2:
        return False
    normalized: list[str] = []
    for item in argv:
        if not isinstance(item, str):
            return False
        value = item.strip()
        if not value or SHELL_METACHAR_RE.search(value):
            return False
        if any(pattern.search(value) for _, pattern in SECRET_PATTERNS):
            return False
        if unsafe_path_in_arg(value):
            return False
        normalized.append(value)

    executable = Path(normalized[0]).name
    if executable in MUTATING_EXECUTABLES:
        return False
    if MUTATING_COMMAND_INTENT_RE.search(" ".join(normalized)):
        return False

    if executable in {"python", "python3"}:
        return len(normalized) >= 3 and normalized[1] == "-m" and normalized[2] in SAFE_PYTHON_MODULES
    if executable == "pytest":
        return True
    if executable == "uv":
        return allow_uv and len(normalized) >= 4 and normalized[1] == "run" and safe_validation_argv(
            normalized[2:], allow_uv=False
        )
    if executable == "make":
        return len(normalized) >= 2 and all(arg in SAFE_MAKE_TARGETS for arg in normalized[1:])
    if executable == "npm":
        return len(normalized) >= 3 and normalized[1] == "run" and normalized[2] in SAFE_JS_SCRIPTS
    if executable in {"pnpm", "yarn"}:
        if len(normalized) >= 3 and normalized[1] == "run":
            return normalized[2] in SAFE_JS_SCRIPTS
        return len(normalized) >= 2 and normalized[1] in SAFE_JS_SCRIPTS
    if executable == "cargo":
        return len(normalized) >= 2 and normalized[1] == "test"
    if executable == "go":
        return len(normalized) >= 2 and normalized[1] == "test"
    if executable == "ruff":
        return len(normalized) >= 2 and normalized[1] in SAFE_RUFF_COMMANDS
    if executable == "mypy":
        return True
    return False


def exact_validation_command(command: str) -> bool:
    argv = parse_legacy_command(command)
    return bool(argv and safe_validation_argv(argv))


def safe_validation_command_item(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    argv = item.get("argv")
    if argv is not None:
        return safe_validation_argv(argv)
    command = item.get("command")
    return isinstance(command, str) and exact_validation_command(command)
