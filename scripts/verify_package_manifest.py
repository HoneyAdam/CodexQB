#!/usr/bin/env python3
"""Verify a CodexQB package manifest against a ZIP or extracted directory."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
import re
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO


PACKAGE_MANIFEST_NAME = "PACKAGE-MANIFEST.json"
PACKAGE_PREFIX = "CodexQB/"
PACKAGE_SCHEMA_VERSION = 2
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA_RE = re.compile(r"^[a-f0-9]{40}(?:[a-f0-9]{24})?$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_FILES = 100_000
MAX_PACKAGE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
RUNTIME_CACHE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
REQUIRED_MANIFEST_FIELDS = {
    "package_schema_version",
    "export_mode",
    "release_claim",
    "git_provenance_available",
    "source_inventory",
    "plugin_version",
    "git_commit",
    "git_branch",
    "origin_main_commit",
    "origin_main_ref_status",
    "head_matches_origin_main",
    "working_tree_clean",
    "tracked_only",
    "include_untracked",
    "changelog_mentions_plugin_version",
    "changelog_release_state",
    "release_tag",
    "release_tag_commit",
    "release_tag_matches_head",
    "generated_at",
    "file_count",
    "tree_sha256",
    "files",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_manifest_key")
        result[key] = value
    return result


def parse_manifest(data: bytes) -> tuple[dict[str, object] | None, list[str]]:
    if len(data) > MAX_MANIFEST_BYTES:
        return None, ["package_manifest_too_large"]
    try:
        manifest = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        return None, ["package_manifest_invalid_json"]
    if not isinstance(manifest, dict):
        return None, ["package_manifest_must_be_object"]
    return manifest, []


def safe_manifest_path(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    canonical = path.as_posix()
    if canonical != value:
        return None
    return canonical


def safe_archive_name(value: str) -> tuple[str, bool] | None:
    """Return one canonical package member name and whether it is a directory."""

    if not value or "\x00" in value or "\\" in value:
        return None
    is_directory = value.endswith("/")
    candidate = value[:-1] if is_directory else value
    if not candidate or candidate.endswith("/"):
        return None
    path = PurePosixPath(candidate)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    canonical = path.as_posix()
    if canonical != candidate or not path.parts or path.parts[0] != PACKAGE_PREFIX.rstrip("/"):
        return None
    if not is_directory and len(path.parts) == 1:
        return None
    return canonical, is_directory


def exact_bool(value: object, expected: bool) -> bool:
    return isinstance(value, bool) and value is expected


def portable_path_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def path_has_ancestor_conflict(
    path: str,
    existing: set[str],
    descendant_ancestors: set[str],
) -> bool:
    portable = portable_path_key(path)
    parts = portable.split("/")
    return any(
        "/".join(parts[:depth]) in existing
        for depth in range(1, len(parts))
    ) or portable in descendant_ancestors


def optional_bool(value: object) -> bool:
    return value is None or isinstance(value, bool)


def valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def manifest_entries(manifest: dict[str, object]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    raw_entries = manifest.get("files")
    if not isinstance(raw_entries, list):
        return [], ["package_manifest_files_invalid"]
    if len(raw_entries) > MAX_MANIFEST_FILES:
        return [], ["package_manifest_file_limit_exceeded"]
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    seen_portable: set[str] = set()
    seen_ancestor_prefixes: set[str] = set()
    for index, item in enumerate(raw_entries, start=1):
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "mode"}:
            errors.append(f"package_manifest_file_invalid=index-{index}")
            continue
        path = safe_manifest_path(item.get("path"))
        digest = item.get("sha256")
        mode = item.get("mode")
        if (
            path is None
            or not isinstance(digest, str)
            or SHA256_RE.fullmatch(digest) is None
            or not isinstance(mode, str)
            or mode not in {"0644", "0755"}
        ):
            errors.append(f"package_manifest_file_invalid=index-{index}")
            continue
        if path == PACKAGE_MANIFEST_NAME or path in seen:
            errors.append(f"package_manifest_file_duplicate=index-{index}")
            continue
        portable = portable_path_key(path)
        if portable in seen_portable:
            errors.append(f"package_manifest_file_case_collision=index-{index}")
            continue
        if path_has_ancestor_conflict(path, seen_portable, seen_ancestor_prefixes):
            errors.append(f"package_manifest_file_ancestor_conflict=index-{index}")
            continue
        seen.add(path)
        seen_portable.add(portable)
        portable_parts = portable.split("/")
        seen_ancestor_prefixes.update(
            "/".join(portable_parts[:depth])
            for depth in range(1, len(portable_parts))
        )
        entries.append({"path": path, "sha256": digest, "mode": mode})
    if [item["path"] for item in entries] != sorted(item["path"] for item in entries):
        errors.append("package_manifest_files_not_sorted")
    file_count = manifest.get("file_count")
    if not isinstance(file_count, int) or isinstance(file_count, bool) or file_count != len(entries):
        errors.append("package_manifest_file_count_mismatch")
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if manifest.get("tree_sha256") != sha256_bytes(encoded):
        errors.append("package_manifest_tree_digest_mismatch")
    return entries, errors


def manifest_contract_errors(manifest: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if set(manifest) != REQUIRED_MANIFEST_FIELDS:
        errors.append("package_manifest_fields_invalid")
    schema_version = manifest.get("package_schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != PACKAGE_SCHEMA_VERSION
    ):
        errors.append("package_manifest_schema_version_invalid")
    mode = manifest.get("export_mode")
    if mode not in {"strict_release", "worktree", "source_package"}:
        errors.append("package_manifest_export_mode_invalid")
        return errors

    version = manifest.get("plugin_version")
    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
        errors.append("package_manifest_plugin_version_invalid")
    elif manifest.get("release_tag") != f"v{version}":
        errors.append("package_manifest_release_tag_invalid")
    for field in (
        "release_claim",
        "git_provenance_available",
        "tracked_only",
        "include_untracked",
        "changelog_mentions_plugin_version",
    ):
        if not isinstance(manifest.get(field), bool):
            errors.append(f"package_manifest_boolean_invalid={field}")
    for field in ("head_matches_origin_main", "working_tree_clean", "release_tag_matches_head"):
        if not optional_bool(manifest.get(field)):
            errors.append(f"package_manifest_optional_boolean_invalid={field}")
    if not valid_timestamp(manifest.get("generated_at")):
        errors.append("package_manifest_generated_at_invalid")
    if not isinstance(manifest.get("tree_sha256"), str) or SHA256_RE.fullmatch(
        manifest.get("tree_sha256", "")
    ) is None:
        errors.append("package_manifest_tree_digest_invalid")
    if manifest.get("source_inventory") not in {"git_index", "filesystem"}:
        errors.append("package_manifest_source_inventory_invalid")
    if manifest.get("origin_main_ref_status") not in {"absent", "present", "unavailable"}:
        errors.append("package_manifest_origin_status_invalid")
    if manifest.get("changelog_release_state") not in {
        "released",
        "unreleased",
        "missing",
        "unknown",
    }:
        errors.append("package_manifest_changelog_state_invalid")
    mentions_expected = manifest.get("changelog_release_state") in {"released", "unreleased"}
    if isinstance(manifest.get("changelog_mentions_plugin_version"), bool) and (
        manifest.get("changelog_mentions_plugin_version") is not mentions_expected
    ):
        errors.append("package_manifest_changelog_relationship_invalid")

    if mode == "strict_release":
        expected = {
            "release_claim": True,
            "git_provenance_available": True,
            "source_inventory": "git_index",
            "working_tree_clean": True,
            "tracked_only": True,
            "include_untracked": False,
            "changelog_mentions_plugin_version": True,
            "changelog_release_state": "released",
            "release_tag_matches_head": True,
        }
        for field, value in expected.items():
            actual = manifest.get(field)
            if isinstance(value, bool):
                matches = exact_bool(actual, value)
            else:
                matches = actual == value and type(actual) is type(value)
            if not matches:
                errors.append(f"strict_release_manifest_invalid={field}")
        git_commit = manifest.get("git_commit")
        tag_commit = manifest.get("release_tag_commit")
        if not isinstance(manifest.get("git_branch"), str):
            errors.append("strict_release_manifest_invalid=git_branch")
        if not isinstance(git_commit, str) or GIT_SHA_RE.fullmatch(git_commit) is None:
            errors.append("strict_release_manifest_invalid=git_commit")
        if (
            not isinstance(tag_commit, str)
            or GIT_SHA_RE.fullmatch(tag_commit) is None
            or tag_commit != git_commit
        ):
            errors.append("strict_release_manifest_invalid=release_tag_commit")
        origin_status = manifest.get("origin_main_ref_status")
        origin_commit = manifest.get("origin_main_commit")
        if origin_status not in {"absent", "present"}:
            errors.append("strict_release_manifest_invalid=origin_main_ref_status")
        elif origin_status == "present":
            if (
                not isinstance(origin_commit, str)
                or GIT_SHA_RE.fullmatch(origin_commit) is None
                or origin_commit != git_commit
                or not exact_bool(manifest.get("head_matches_origin_main"), True)
            ):
                errors.append("strict_release_manifest_invalid=origin_main_commit")
        elif origin_commit != "unknown" or manifest.get("head_matches_origin_main") is not None:
            errors.append("strict_release_manifest_invalid=origin_main_absence")
    elif not exact_bool(manifest.get("release_claim"), False):
        errors.append("non_release_package_claim_invalid")
    if mode == "worktree":
        if not exact_bool(manifest.get("git_provenance_available"), True):
            errors.append("worktree_manifest_invalid=git_provenance_available")
        if manifest.get("source_inventory") != "git_index":
            errors.append("worktree_manifest_invalid=source_inventory")
        git_commit = manifest.get("git_commit")
        if not isinstance(git_commit, str) or GIT_SHA_RE.fullmatch(git_commit) is None:
            errors.append("worktree_manifest_invalid=git_commit")
        if not isinstance(manifest.get("git_branch"), str):
            errors.append("worktree_manifest_invalid=git_branch")
        if not isinstance(manifest.get("working_tree_clean"), bool):
            errors.append("worktree_manifest_invalid=working_tree_clean")
        include_untracked = manifest.get("include_untracked")
        if isinstance(include_untracked, bool) and not exact_bool(
            manifest.get("tracked_only"), not include_untracked
        ):
            errors.append("worktree_manifest_invalid=tracked_only")
        origin_status = manifest.get("origin_main_ref_status")
        origin_commit = manifest.get("origin_main_commit")
        if origin_status == "present":
            if (
                not isinstance(origin_commit, str)
                or GIT_SHA_RE.fullmatch(origin_commit) is None
                or not isinstance(manifest.get("head_matches_origin_main"), bool)
                or manifest.get("head_matches_origin_main") is not (origin_commit == git_commit)
            ):
                errors.append("worktree_manifest_invalid=origin_main_commit")
        elif origin_status == "absent":
            if origin_commit != "unknown" or manifest.get("head_matches_origin_main") is not None:
                errors.append("worktree_manifest_invalid=origin_main_absence")
        else:
            errors.append("worktree_manifest_invalid=origin_main_ref_status")
        tag_commit = manifest.get("release_tag_commit")
        if tag_commit == "unknown":
            if manifest.get("release_tag_matches_head") is not None:
                errors.append("worktree_manifest_invalid=release_tag_matches_head")
        elif (
            not isinstance(tag_commit, str)
            or GIT_SHA_RE.fullmatch(tag_commit) is None
            or not isinstance(manifest.get("release_tag_matches_head"), bool)
            or manifest.get("release_tag_matches_head") is not (tag_commit == git_commit)
        ):
            errors.append("worktree_manifest_invalid=release_tag_commit")
    if mode == "source_package":
        expected = {
            "source_inventory": "filesystem",
            "tracked_only": False,
            "include_untracked": True,
        }
        for field, value in expected.items():
            actual = manifest.get(field)
            if isinstance(value, bool):
                matches = exact_bool(actual, value)
            else:
                matches = actual == value and type(actual) is type(value)
            if not matches:
                errors.append(f"source_package_manifest_invalid={field}")
        git_provenance = manifest.get("git_provenance_available")
        if exact_bool(git_provenance, False):
            unavailable_expected = {
                "git_commit": "unknown",
                "git_branch": "unknown",
                "origin_main_commit": "unknown",
                "origin_main_ref_status": "unavailable",
                "head_matches_origin_main": None,
                "working_tree_clean": None,
                "release_tag_commit": "unknown",
                "release_tag_matches_head": None,
            }
            for field, value in unavailable_expected.items():
                actual = manifest.get(field)
                if actual != value or type(actual) is not type(value):
                    errors.append(f"source_package_manifest_invalid={field}")
        elif exact_bool(git_provenance, True):
            git_commit = manifest.get("git_commit")
            if not isinstance(git_commit, str) or GIT_SHA_RE.fullmatch(git_commit) is None:
                errors.append("source_package_manifest_invalid=git_commit")
            if not isinstance(manifest.get("git_branch"), str):
                errors.append("source_package_manifest_invalid=git_branch")
            if not isinstance(manifest.get("working_tree_clean"), bool):
                errors.append("source_package_manifest_invalid=working_tree_clean")
            origin_status = manifest.get("origin_main_ref_status")
            origin_commit = manifest.get("origin_main_commit")
            if origin_status == "present":
                if (
                    not isinstance(origin_commit, str)
                    or GIT_SHA_RE.fullmatch(origin_commit) is None
                    or not isinstance(manifest.get("head_matches_origin_main"), bool)
                    or manifest.get("head_matches_origin_main") is not (origin_commit == git_commit)
                ):
                    errors.append("source_package_manifest_invalid=origin_main_commit")
            elif origin_status in {"absent", "unavailable"}:
                if origin_commit != "unknown" or manifest.get("head_matches_origin_main") is not None:
                    errors.append("source_package_manifest_invalid=origin_main_absence")
            else:
                errors.append("source_package_manifest_invalid=origin_main_ref_status")
            tag_commit = manifest.get("release_tag_commit")
            if tag_commit != "unknown" and (
                not isinstance(tag_commit, str) or GIT_SHA_RE.fullmatch(tag_commit) is None
            ):
                errors.append("source_package_manifest_invalid=release_tag_commit")
            if tag_commit == "unknown":
                if manifest.get("release_tag_matches_head") is not None:
                    errors.append("source_package_manifest_invalid=release_tag_matches_head")
            elif not isinstance(manifest.get("release_tag_matches_head"), bool):
                errors.append("source_package_manifest_invalid=release_tag_matches_head")
            elif manifest.get("release_tag_matches_head") is not (tag_commit == git_commit):
                errors.append("source_package_manifest_invalid=release_tag_commit_relationship")
        else:
            errors.append("source_package_manifest_invalid=git_provenance_available")
    return errors


def zip_member_sha256(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info, "r") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def archive_entry_has_ancestor_conflict(
    portable: str,
    is_directory: bool,
    member_types: dict[str, bool],
    descendant_ancestors: set[str],
) -> bool:
    parts = portable.split("/")
    return any(
        member_types.get("/".join(parts[:depth])) is False
        for depth in range(1, len(parts))
    ) or (not is_directory and portable in descendant_ancestors)


def verify_zip(path: Path | BinaryIO) -> list[str]:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                errors.append("package_zip_duplicate_entry")
            if len(infos) > MAX_MANIFEST_FILES + 1:
                return [*errors, "package_zip_entry_limit_exceeded"]
            if sum(info.file_size for info in infos) > MAX_PACKAGE_UNCOMPRESSED_BYTES:
                return [*errors, "package_zip_uncompressed_size_exceeded"]
            normalized_names: set[str] = set()
            portable_names: set[str] = set()
            member_types: dict[str, bool] = {}
            member_ancestor_prefixes: set[str] = set()
            actual_files: set[str] = set()
            for info in infos:
                safe_name = safe_archive_name(info.filename)
                if safe_name is None:
                    errors.append("package_zip_entry_path_invalid")
                    continue
                normalized, is_directory = safe_name
                portable = portable_path_key(normalized)
                if normalized in normalized_names or portable in portable_names:
                    errors.append("package_zip_entry_collision")
                if archive_entry_has_ancestor_conflict(
                    portable,
                    is_directory,
                    member_types,
                    member_ancestor_prefixes,
                ):
                    errors.append("package_zip_entry_ancestor_conflict")
                normalized_names.add(normalized)
                portable_names.add(portable)
                member_types[portable] = is_directory
                portable_parts = portable.split("/")
                member_ancestor_prefixes.update(
                    "/".join(portable_parts[:depth])
                    for depth in range(1, len(portable_parts))
                )
                if info.is_dir() is not is_directory:
                    errors.append("package_zip_entry_type_invalid")
                unix_mode = info.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                permissions = stat.S_IMODE(unix_mode)
                expected_type = stat.S_IFDIR if is_directory else stat.S_IFREG
                allowed_permissions = {0o755} if is_directory else {0o644, 0o755}
                if file_type != expected_type or permissions not in allowed_permissions:
                    errors.append("package_zip_entry_type_invalid")
                if normalized == f"{PACKAGE_PREFIX}{PACKAGE_MANIFEST_NAME}" and permissions != 0o644:
                    errors.append("package_zip_manifest_mode_invalid")
                if info.flag_bits & 0x1:
                    errors.append("package_zip_encrypted_entry")
                if not is_directory:
                    relative = normalized[len(PACKAGE_PREFIX) :]
                    if relative != PACKAGE_MANIFEST_NAME:
                        actual_files.add(relative)
            manifest_name = f"{PACKAGE_PREFIX}{PACKAGE_MANIFEST_NAME}"
            if names.count(manifest_name) != 1:
                return [*errors, "package_manifest_missing_or_duplicate"]
            manifest_info = archive.getinfo(manifest_name)
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                return [*errors, "package_manifest_too_large"]
            manifest, parse_errors = parse_manifest(archive.read(manifest_name))
            errors.extend(parse_errors)
            if manifest is None:
                return errors
            entries, entry_errors = manifest_entries(manifest)
            errors.extend(entry_errors)
            errors.extend(manifest_contract_errors(manifest))
            expected_files = {item["path"] for item in entries}
            if actual_files != expected_files:
                errors.append("package_manifest_file_set_mismatch")
            for index, item in enumerate(entries, start=1):
                archive_name = f"{PACKAGE_PREFIX}{item['path']}"
                try:
                    info = archive.getinfo(archive_name)
                except KeyError:
                    continue
                actual_mode = stat.S_IMODE(info.external_attr >> 16)
                if actual_mode != int(item["mode"], 8):
                    errors.append(f"package_file_mode_mismatch=index-{index}")
                if zip_member_sha256(archive, info) != item["sha256"]:
                    errors.append(f"package_file_digest_mismatch=index-{index}")
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return ["package_zip_invalid"]
    return list(dict.fromkeys(errors))


def metadata_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def directory_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode)


def secure_directory_flags() -> int | None:
    if any(not hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")):
        return None
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def secure_regular_flags() -> int | None:
    if any(not hasattr(os, name) for name in ("O_NOFOLLOW", "O_CLOEXEC")):
        return None
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


def open_regular_descriptor(
    root_descriptor: int,
    relative: str,
) -> tuple[int, os.stat_result] | None:
    """Open one regular file through descriptor-anchored, no-follow traversal."""

    directory_flags = secure_directory_flags()
    regular_flags = secure_regular_flags()
    parts = PurePosixPath(relative).parts
    if directory_flags is None or regular_flags is None or not parts:
        return None
    current_descriptor = -1
    result_descriptor = -1
    try:
        current_descriptor = os.dup(root_descriptor)
        for part in parts[:-1]:
            next_descriptor = os.open(
                part,
                directory_flags,
                dir_fd=current_descriptor,
            )
            metadata = os.fstat(next_descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(next_descriptor)
                return None
            os.close(current_descriptor)
            current_descriptor = next_descriptor
        result_descriptor = os.open(
            parts[-1],
            regular_flags,
            dir_fd=current_descriptor,
        )
        opened_metadata = os.fstat(result_descriptor)
        if not stat.S_ISREG(opened_metadata.st_mode):
            os.close(result_descriptor)
            result_descriptor = -1
            return None
        descriptor = result_descriptor
        result_descriptor = -1
        return descriptor, opened_metadata
    except (NotImplementedError, OSError):
        return None
    finally:
        if result_descriptor >= 0:
            os.close(result_descriptor)
        if current_descriptor >= 0:
            os.close(current_descriptor)


def regular_file_bytes(
    root_descriptor: int,
    relative: str,
    maximum_bytes: int,
) -> tuple[bytes, str, tuple[int, int, int, int, int]] | None:
    opened = open_regular_descriptor(root_descriptor, relative)
    if opened is None:
        return None
    descriptor, before = opened
    if before.st_size > maximum_bytes:
        os.close(descriptor)
        return None
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            data = handle.read(maximum_bytes + 1)
            after = os.fstat(handle.fileno())
    except OSError:
        return None
    if (
        len(data) > maximum_bytes
        or len(data) != after.st_size
        or metadata_identity(before) != metadata_identity(after)
    ):
        return None
    return data, f"{stat.S_IMODE(after.st_mode):04o}", metadata_identity(after)


def regular_file_sha256(
    root_descriptor: int,
    relative: str,
    maximum_bytes: int,
) -> tuple[str | None, int, str | None, tuple[int, int, int, int, int] | None]:
    opened = open_regular_descriptor(root_descriptor, relative)
    if opened is None:
        return None, 0, None, None
    descriptor, before = opened
    if before.st_size > maximum_bytes:
        os.close(descriptor)
        return (
            None,
            0,
            f"{stat.S_IMODE(before.st_mode):04o}",
            metadata_identity(before),
        )
    digest = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            while total <= maximum_bytes:
                chunk = handle.read(min(1024 * 1024, maximum_bytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum_bytes:
                    break
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    except OSError:
        return None, total, None, None
    mode = f"{stat.S_IMODE(after.st_mode):04o}"
    if (
        total > maximum_bytes
        or total != after.st_size
        or metadata_identity(before) != metadata_identity(after)
    ):
        return None, total, mode, metadata_identity(after)
    return digest.hexdigest(), total, mode, metadata_identity(after)


def directory_inventory(
    root_descriptor: int,
) -> tuple[dict[str, tuple[int, int, int, int, int]], int, bool, bool, list[str]]:
    """Inventory a package tree without following path-based ancestor swaps."""

    directory_flags = secure_directory_flags()
    if directory_flags is None:
        return {}, 0, True, False, ["package_directory_secure_open_unavailable"]
    file_identities: dict[str, tuple[int, int, int, int, int]] = {}
    actual_uncompressed_bytes = 0
    actual_entry_count = 0
    walk_failed = False
    inventory_limit_exceeded = False
    errors: list[str] = []

    def walk(directory_descriptor: int, prefix: str, in_runtime_cache: bool) -> None:
        nonlocal actual_entry_count
        nonlocal actual_uncompressed_bytes
        nonlocal inventory_limit_exceeded
        nonlocal walk_failed
        if inventory_limit_exceeded:
            return
        try:
            with os.scandir(directory_descriptor) as iterator:
                names = [entry.name for entry in iterator]
        except (NotImplementedError, OSError, TypeError):
            walk_failed = True
            return
        for name in names:
            actual_entry_count += 1
            if actual_entry_count > MAX_MANIFEST_FILES + 1:
                inventory_limit_exceeded = True
                return
            relative = f"{prefix}/{name}" if prefix else name
            try:
                metadata = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except (NotImplementedError, OSError):
                walk_failed = True
                continue
            if stat.S_ISLNK(metadata.st_mode):
                errors.append("package_directory_symlink_rejected")
                continue
            if stat.S_ISDIR(metadata.st_mode):
                child_descriptor = -1
                try:
                    child_descriptor = os.open(
                        name,
                        directory_flags,
                        dir_fd=directory_descriptor,
                    )
                    opened_metadata = os.fstat(child_descriptor)
                    if (
                        not stat.S_ISDIR(opened_metadata.st_mode)
                        or directory_identity(metadata) != directory_identity(opened_metadata)
                    ):
                        walk_failed = True
                        continue
                    walk(
                        child_descriptor,
                        relative,
                        in_runtime_cache or name in RUNTIME_CACHE_PARTS,
                    )
                except (NotImplementedError, OSError):
                    walk_failed = True
                finally:
                    if child_descriptor >= 0:
                        os.close(child_descriptor)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                errors.append("package_directory_special_file_rejected")
                continue
            if name == ".DS_Store" or in_runtime_cache:
                continue
            actual_uncompressed_bytes += metadata.st_size
            file_identities[relative] = metadata_identity(metadata)

    walk(root_descriptor, "", False)
    return (
        file_identities,
        actual_uncompressed_bytes,
        walk_failed,
        inventory_limit_exceeded,
        errors,
    )


def verify_directory(root: Path) -> list[str]:
    directory_flags = secure_directory_flags()
    if directory_flags is None:
        return ["package_directory_secure_open_unavailable"]
    try:
        root_descriptor = os.open(root, directory_flags)
    except (NotImplementedError, OSError):
        return ["package_directory_root_invalid"]
    try:
        try:
            root_metadata = os.fstat(root_descriptor)
        except OSError:
            return ["package_directory_root_invalid"]
        if not stat.S_ISDIR(root_metadata.st_mode):
            return ["package_directory_root_invalid"]
        manifest_result = regular_file_bytes(
            root_descriptor,
            PACKAGE_MANIFEST_NAME,
            MAX_MANIFEST_BYTES,
        )
        if manifest_result is None:
            return ["package_manifest_missing_or_invalid"]
        manifest_data, manifest_mode, manifest_identity = manifest_result
        manifest, parse_errors = parse_manifest(manifest_data)
        if manifest is None:
            return parse_errors
        entries, entry_errors = manifest_entries(manifest)
        errors = [*parse_errors, *entry_errors, *manifest_contract_errors(manifest)]
        if manifest_mode != "0644":
            errors.append("package_directory_manifest_mode_invalid")
        expected_files = {item["path"] for item in entries}
        (
            initial_file_identities,
            actual_uncompressed_bytes,
            walk_failed,
            inventory_limit_exceeded,
            inventory_errors,
        ) = directory_inventory(root_descriptor)
        errors.extend(inventory_errors)
        actual_files = set(initial_file_identities) - {PACKAGE_MANIFEST_NAME}
        if initial_file_identities.get(PACKAGE_MANIFEST_NAME) != manifest_identity:
            errors.append("package_manifest_changed_during_verification")
        if walk_failed:
            errors.append("package_directory_inventory_unavailable")
        if inventory_limit_exceeded:
            errors.append("package_directory_entry_limit_exceeded")
        if actual_uncompressed_bytes > MAX_PACKAGE_UNCOMPRESSED_BYTES:
            errors.append("package_directory_size_limit_exceeded")
        if actual_files != expected_files:
            errors.append("package_manifest_file_set_mismatch")
        if (
            actual_uncompressed_bytes <= MAX_PACKAGE_UNCOMPRESSED_BYTES
            and not inventory_limit_exceeded
        ):
            remaining_bytes = MAX_PACKAGE_UNCOMPRESSED_BYTES - len(manifest_data)
            for index, item in enumerate(entries, start=1):
                digest, bytes_read, actual_mode, opened_identity = regular_file_sha256(
                    root_descriptor,
                    item["path"],
                    max(0, remaining_bytes),
                )
                remaining_bytes = max(0, remaining_bytes - bytes_read)
                if digest is None:
                    errors.append(f"package_file_unreadable_or_oversized=index-{index}")
                    continue
                if opened_identity != initial_file_identities.get(item["path"]):
                    errors.append(f"package_file_changed_during_verification=index-{index}")
                if actual_mode != item["mode"]:
                    errors.append(f"package_file_mode_mismatch=index-{index}")
                if digest != item["sha256"]:
                    errors.append(f"package_file_digest_mismatch=index-{index}")
            (
                final_file_identities,
                final_uncompressed_bytes,
                final_walk_failed,
                final_inventory_limit_exceeded,
                final_inventory_errors,
            ) = directory_inventory(root_descriptor)
            errors.extend(final_inventory_errors)
            if final_walk_failed:
                errors.append("package_directory_inventory_unavailable")
            if final_inventory_limit_exceeded:
                errors.append("package_directory_entry_limit_exceeded")
            if (
                final_file_identities != initial_file_identities
                or final_uncompressed_bytes != actual_uncompressed_bytes
            ):
                errors.append("package_directory_changed_during_verification")
        return list(dict.fromkeys(errors))
    finally:
        os.close(root_descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify CodexQB package manifest integrity.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--zip", dest="zip_path")
    group.add_argument("--root")
    args = parser.parse_args(argv)
    errors = verify_zip(Path(args.zip_path)) if args.zip_path else verify_directory(Path(args.root))
    if errors:
        print("package_manifest_verification=failed")
        for error in errors:
            print(error)
        return 1
    print("package_manifest_verification=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
