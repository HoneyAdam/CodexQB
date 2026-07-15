#!/usr/bin/env python3
"""Validate CodexQB Apply artifacts against their intended Draft 2020-12 definitions."""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = REPO_ROOT / "plugins/codexqb/skills/codexqb/references/apply-run-schema.json"
MAX_SCHEMA_INPUT_BYTES = 16 * 1024 * 1024
ARTIFACT_DEFINITIONS = {
    ".codexqb-apply-run.json": "ApplyRunMarker",
    "Apply-Run.json": "ApplyRun",
    "Progress.json": "Progress",
    "Events.jsonl[]": "Event",
    "Writer-Lock.json": "WriterLock",
    "Dispatch-Packet.json": "DispatchPacket",
    "Agent-Run-*.json": "AgentRun",
    "Change-Set-*.json": "ChangeSet",
    "Validation-Receipt-*.json": "ValidationReceipt",
    "Review-Receipt-*.json": "ReviewReceipt",
    "Review-Report-*.json": "ReviewReport",
    "Implementer-Report.json": "ImplementerReport",
    "Task-Review.json": "TaskReview",
    "Fix-Report.json": "FixReport",
    "Final-Review.json": "FinalReview",
    "Result.json": "Result",
}
REQUIRED_RUN_ARTIFACTS = frozenset(
    {
        ".codexqb-apply-run.json",
        "Apply-Run.json",
        "Progress.json",
        "Events.jsonl",
        "Final-Review.json",
        "Result.json",
    }
)
REQUIRED_TASK_JSON_ARTIFACTS = frozenset(
    {
        "Implementer-Report.json",
        "Task-Review.json",
        "Fix-Report.json",
        "Review-Report-spec.json",
        "Review-Report-quality.json",
        "Review-Report-security.json",
        "Review-Report-final.json",
    }
)
SAFE_DIAGNOSTIC_ARTIFACT_NAMES = REQUIRED_RUN_ARTIFACTS | REQUIRED_TASK_JSON_ARTIFACTS | {
    "Writer-Lock.json"
}


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("schema_json_duplicate_key")
        value[key] = item
    return value


def load_json(path: Path) -> object:
    data = path.read_bytes()
    if len(data) > MAX_SCHEMA_INPUT_BYTES:
        raise ValueError("schema_json_input_too_large")
    try:
        text = data.decode("utf-8")
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except UnicodeDecodeError as exc:
        raise ValueError("schema_json_not_utf8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("schema_json_invalid") from exc


def load_schema(path: Path = DEFAULT_SCHEMA) -> dict[str, object]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError("apply_schema_must_be_object")
    return value


def import_schema_engine():
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise RuntimeError("jsonschema_validation_dependency_missing") from exc
    return Draft202012Validator


def check_schema_bundle(schema: dict[str, object]) -> list[str]:
    errors: list[str] = []
    validator_class = import_schema_engine()
    try:
        validator_class.check_schema(schema)
    except Exception:
        return ["apply_schema_meta_validation_failed"]
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        return ["apply_schema_definitions_missing"]
    declared_mapping = schema.get("x-codexqb-artifact-definitions")
    if declared_mapping != ARTIFACT_DEFINITIONS:
        errors.append("apply_schema_artifact_mapping_mismatch")
    for definition in ARTIFACT_DEFINITIONS.values():
        if definition not in definitions:
            errors.append(f"apply_schema_definition_missing={definition}")
    return errors


def validator_for_definition(schema: dict[str, object], definition: str):
    validator_class = import_schema_engine()
    return validator_class(
        {
            "$schema": schema.get("$schema"),
            "$defs": schema.get("$defs", {}),
            "$ref": f"#/$defs/{definition}",
        }
    )


def validate_instance(
    schema: dict[str, object],
    definition: str,
    instance: object,
) -> list[str]:
    errors: list[str] = []
    validator = validator_for_definition(schema, definition)
    for error in validator.iter_errors(instance):
        keyword = str(error.validator or "unknown")
        errors.append(
            f"schema_instance_invalid={definition}:{keyword}:depth={len(error.absolute_path)}"
        )
    return sorted(set(errors))


def definition_for_filename(name: str) -> str | None:
    for pattern, definition in ARTIFACT_DEFINITIONS.items():
        candidate = "Events.jsonl[]" if name == "Events.jsonl" else name
        if fnmatch.fnmatchcase(candidate, pattern):
            return definition
    return None


def _load_json_lines(path: Path) -> list[object]:
    data = path.read_bytes()
    if len(data) > MAX_SCHEMA_INPUT_BYTES:
        raise ValueError("schema_jsonl_input_too_large")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("schema_jsonl_not_utf8") from exc
    values: list[object] = []
    for line in text.splitlines():
        if not line.strip():
            raise ValueError("schema_jsonl_blank_line")
        try:
            values.append(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
        except json.JSONDecodeError as exc:
            raise ValueError("schema_jsonl_invalid") from exc
    if not values:
        raise ValueError("schema_jsonl_empty")
    return values


def validate_run_directory(schema: dict[str, object], run_dir: Path) -> list[str]:
    errors: list[str] = []
    if not run_dir.is_dir() or run_dir.is_symlink():
        return ["apply_schema_run_directory_invalid"]
    present_root_names = {
        path.name for path in run_dir.iterdir() if path.is_file() and not path.is_symlink()
    }
    for required in sorted(REQUIRED_RUN_ARTIFACTS - present_root_names):
        errors.append(f"apply_schema_required_artifact_missing={required}")
    progress: object | None = None
    progress_path = run_dir / "Progress.json"
    if progress_path.is_file() and not progress_path.is_symlink():
        try:
            progress = load_json(progress_path)
        except (OSError, ValueError):
            progress = None
    if isinstance(progress, dict):
        tasks = progress.get("tasks")
        if isinstance(tasks, list):
            for task in tasks:
                task_id = task.get("task_id") if isinstance(task, dict) else None
                task_dir = run_dir / str(task_id)
                if not isinstance(task_id, str) or not task_dir.is_dir() or task_dir.is_symlink():
                    errors.append("apply_schema_task_directory_invalid")
                    continue
                for required in REQUIRED_TASK_JSON_ARTIFACTS:
                    candidate = task_dir / required
                    if not candidate.is_file() or candidate.is_symlink():
                        errors.append(f"apply_schema_required_task_artifact_missing={required}")
        active_locks = progress.get("active_writer_locks")
        writer_lock = run_dir / "Writer-Lock.json"
        writer_lock_present = writer_lock.is_file() and not writer_lock.is_symlink()
        if isinstance(active_locks, list):
            if active_locks and not writer_lock_present:
                errors.append("apply_schema_writer_lock_missing")
            if not active_locks and writer_lock_present:
                errors.append("apply_schema_writer_lock_unexpected")
    for path in sorted(run_dir.rglob("*")):
        if path.is_symlink():
            if path.name in SAFE_DIAGNOSTIC_ARTIFACT_NAMES:
                errors.append(f"apply_schema_symlink_artifact={path.name}")
            else:
                errors.append("apply_schema_symlink_entry")
            continue
        if not path.is_file():
            continue
        if path.suffix not in {".json", ".jsonl"}:
            continue
        definition = definition_for_filename(path.name)
        if definition is None:
            errors.append("apply_schema_unmapped_json_artifact")
            continue
        try:
            instances = _load_json_lines(path) if path.suffix == ".jsonl" else [load_json(path)]
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            continue
        for instance in instances:
            errors.extend(validate_instance(schema, definition, instance))
    return sorted(set(errors))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate CodexQB Apply JSON Schema and run artifacts.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--run-dir", action="append", type=Path, default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        schema = load_schema(args.schema)
        errors = check_schema_bundle(schema)
        for run_dir in args.run_dir:
            errors.extend(validate_run_directory(schema, run_dir))
    except OSError:
        print("apply_schema_validation=failed")
        print("error=apply_schema_io_error")
        return 1
    except (RuntimeError, ValueError) as exc:
        print("apply_schema_validation=failed")
        print(f"error={exc}")
        return 1
    if errors:
        print("apply_schema_validation=failed")
        for error in sorted(set(errors)):
            print(f"error={error}")
        return 1
    print("apply_schema_validation=passed")
    print(f"artifact_definition_count={len(ARTIFACT_DEFINITIONS)}")
    print(f"validated_run_count={len(args.run_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
