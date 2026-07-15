#!/usr/bin/env python3
"""Validate CodexQB's activation metadata as a canonical YAML subset.

The activation policy is security-sensitive.  A permissive or first-match text
parser can disagree with a YAML loader about duplicate keys, quoted booleans,
merge keys, or later documents.  This validator therefore accepts only the
small, canonical structure CodexQB publishes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


DEFAULT_PATH = Path("plugins/codexqb/skills/codexqb/agents/openai.yaml")
CANONICAL_RECORDS = (
    "interface:",
    "  display_name:",
    "  short_description:",
    "  default_prompt:",
    "policy:",
    "  allow_implicit_invocation: false",
)
def parse_string_scalar(value: str) -> str | None:
    value = value.strip()
    if not value.startswith('"') or "\\u" in value.lower():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, str) or not parsed:
        return None
    if any(
        ord(character) < 0x20
        or 0x7F <= ord(character) <= 0x9F
        or 0xD800 <= ord(character) <= 0xDFFF
        for character in parsed
    ):
        return None
    return parsed


def validate_openai_yaml_text(text: str) -> tuple[dict[str, str], list[str]]:
    """Return parsed interface values and fail-closed contract errors."""

    if "\0" in text:
        return {}, ["openai_yaml_nul_rejected"]
    records: list[str] = []
    for line in text.splitlines():
        if "\t" in line:
            return {}, ["openai_yaml_tabs_rejected"]
        line = line.rstrip(" ")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        records.append(line)

    if len(records) != len(CANONICAL_RECORDS):
        return {}, [f"openai_yaml_record_count={len(records)}"]
    if records[0] != CANONICAL_RECORDS[0]:
        return {}, ["openai_yaml_interface_shape_invalid"]
    if records[4] != CANONICAL_RECORDS[4]:
        return {}, ["openai_yaml_policy_shape_invalid"]
    if records[5] != CANONICAL_RECORDS[5]:
        return {}, ["allow_implicit_invocation_must_be_boolean_false"]

    values: dict[str, str] = {}
    for index, key in [(1, "display_name"), (2, "short_description"), (3, "default_prompt")]:
        prefix = f"  {key}:"
        record = records[index]
        if not record.startswith(prefix):
            return {}, [f"openai_yaml_{key}_shape_invalid"]
        raw_value = record[len(prefix) :]
        if raw_value and not raw_value.startswith(" "):
            return {}, [f"openai_yaml_{key}_shape_invalid"]
        parsed = parse_string_scalar(raw_value)
        if parsed is None:
            return {}, [f"openai_yaml_{key}_must_be_string"]
        values[key] = parsed

    errors: list[str] = []
    if values["display_name"] != "CodexQB":
        errors.append("display_name_must_be_CodexQB")
    if len(values["short_description"]) > 80:
        errors.append(f"short_description_too_long={len(values['short_description'])}")
    if "$codexqb" not in values["default_prompt"]:
        errors.append("default_prompt_missing_$codexqb")
    if len(values["default_prompt"]) > 220:
        errors.append(f"default_prompt_too_long={len(values['default_prompt'])}")
    return values, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical CodexQB activation metadata.")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_PATH))
    args = parser.parse_args()
    path = Path(args.path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        print("openai_yaml_semantic_check_failed")
        print("openai_yaml_unreadable")
        return 1
    _values, errors = validate_openai_yaml_text(text)
    if errors:
        print("openai_yaml_semantic_check_failed")
        for error in errors:
            print(error)
        return 1
    print("openai_yaml_semantic_check=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
