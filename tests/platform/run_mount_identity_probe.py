#!/usr/bin/env python3
"""Run the real mount-identity probe without masking unsupported platforms."""

from __future__ import annotations

import getpass
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTOR_PATH = REPO_ROOT / "plugins/codexqb/skills/codexqb/scripts/doctor.py"


def _load_doctor():
    spec = importlib.util.spec_from_file_location("codexqb_doctor_platform", DOCTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("doctor_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DOCTOR = _load_doctor()


def _contains_private_runtime_data(report: Mapping[str, object]) -> bool:
    encoded = json.dumps(report, sort_keys=True)
    forbidden_values = {os.fspath(Path.home()), os.fspath(Path.cwd())}
    try:
        user_name = getpass.getuser()
    except (ImportError, KeyError, OSError):
        user_name = ""
    if len(user_name) >= 3:
        forbidden_values.add(user_name)

    for key, value in os.environ.items():
        upper = key.upper()
        if not any(marker in upper for marker in ("SECRET", "TOKEN", "PASSWORD")):
            continue
        if len(value) >= 8:
            forbidden_values.add(value)
    return any(value and value in encoded for value in forbidden_values)


def evaluate_report(report: Mapping[str, object]) -> tuple[bool, str]:
    if report.get("schema") != DOCTOR.REPORT_SCHEMA:
        return False, "invalid_schema"
    if report.get("version") != DOCTOR.REPORT_VERSION:
        return False, "invalid_version"
    if _contains_private_runtime_data(report):
        return False, "private_runtime_data_exposed"

    mount = report.get("mount_identity")
    operations = report.get("operations")
    if not isinstance(mount, dict) or not isinstance(operations, dict):
        return False, "invalid_report_shape"
    if "identity" in mount or "diagnostics" in mount:
        return False, "raw_mount_data_exposed"

    providers = mount.get("providers")
    if not isinstance(providers, list):
        return False, "invalid_provider_shape"
    for provider in providers:
        if not isinstance(provider, dict):
            return False, "invalid_provider_shape"
        if "identity" in provider or "diagnostics" in provider:
            return False, "raw_provider_data_exposed"

    status = report.get("status")
    assurance = mount.get("selected_assurance")
    supported = operations.get("supported")
    blocked = operations.get("blocked")
    if not isinstance(supported, list) or not isinstance(blocked, list):
        return False, "invalid_operation_shape"

    if status == "ready":
        if assurance not in DOCTOR.HIGH_ASSURANCE:
            return False, "ready_without_high_assurance"
        if report.get("error_code") is not None:
            return False, "ready_with_error"
        if supported != list(DOCTOR.OPERATIONS) or blocked:
            return False, "ready_operation_policy_mismatch"
        if not any(provider.get("status") == "available" for provider in providers):
            return False, "ready_without_available_provider"
        return True, "ready"

    if status == "expected_unsupported":
        if report.get("error_code") != DOCTOR.EXTERNAL_MOUNT_ERROR:
            return False, "unsupported_error_code_mismatch"
        if supported or blocked != list(DOCTOR.OPERATIONS):
            return False, "unsupported_operation_policy_mismatch"
        advertised_failure = any(
            provider.get("supported") is True
            and (
                provider.get("provider") in DOCTOR.HIGH_ASSURANCE_PROVIDERS
                or provider.get("assurance") in DOCTOR.HIGH_ASSURANCE
            )
            for provider in providers
        )
        if advertised_failure:
            return False, "advertised_provider_probe_failed"
        return True, "expected_unsupported"

    if status == "probe_failed":
        return False, "advertised_provider_probe_failed"
    return False, "unknown_status"


def main() -> int:
    report = DOCTOR.build_live_report()
    accepted, result = evaluate_report(report)
    mount = report.get("mount_identity", {})
    assurance = mount.get("selected_assurance", "unavailable") if isinstance(mount, dict) else "unavailable"
    print(f"codexqb_platform_probe status={result} assurance={assurance}")
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
