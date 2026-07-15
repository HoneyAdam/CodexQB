from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.test_export_sanitized import (
    EXPORT_MODULE,
    git,
    git_commit_all,
    write_minimal_codexqb_tree,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "scripts/verify_package_manifest.py"
MANIFEST_MEMBER = "CodexQB/PACKAGE-MANIFEST.json"


def load_verifier_module():
    spec = importlib.util.spec_from_file_location("codexqb_verify_package_manifest", VERIFIER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load package verifier from {VERIFIER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFY_MODULE = load_verifier_module()


def create_source_package(base: Path, *, git_checkout: bool = False) -> tuple[Path, Path]:
    root = base / "source"
    root.mkdir()
    if git_checkout:
        git(root, "init")
    write_minimal_codexqb_tree(root)
    if git_checkout:
        git_commit_all(root)
    output = base / "CodexQB-source-package.zip"
    EXPORT_MODULE.create_zip(root, output, source_package=True)
    return root, output


def extracted_package(base: Path) -> tuple[Path, Path]:
    _root, output = create_source_package(base)
    extracted = base / "extracted"
    with zipfile.ZipFile(output) as archive:
        archive.extractall(extracted)
        for info in archive.infolist():
            if info.is_dir():
                continue
            (extracted / info.filename).chmod(stat.S_IMODE(info.external_attr >> 16))
    return output, extracted / "CodexQB"


def rewrite_zip(
    source: Path,
    destination: Path,
    *,
    replacements: dict[str, bytes] | None = None,
    appended: list[tuple[zipfile.ZipInfo, bytes]] | None = None,
) -> None:
    replacements = replacements or {}
    appended = appended or []
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as rewritten:
        for info in original.infolist():
            rewritten.writestr(info, replacements.get(info.filename, original.read(info.filename)))
        for info, data in appended:
            rewritten.writestr(info, data)


def manifest_bytes_with_mutation(source: Path, mutate) -> bytes:
    with zipfile.ZipFile(source) as archive:
        manifest = json.loads(archive.read(MANIFEST_MEMBER).decode("utf-8"))
    mutate(manifest)
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


class PackageManifestTests(unittest.TestCase):
    def test_source_package_verifies_as_zip_and_extracted_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output, extracted = extracted_package(Path(temp_dir))

            self.assertEqual(VERIFY_MODULE.verify_zip(output), [])
            self.assertEqual(VERIFY_MODULE.verify_directory(extracted), [])

    def test_source_package_with_available_git_provenance_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _root, output = create_source_package(Path(temp_dir), git_checkout=True)

            self.assertEqual(VERIFY_MODULE.verify_zip(output), [])

    def test_extracted_runtime_caches_are_ignored_but_cache_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _output, extracted = extracted_package(Path(temp_dir))
            cache = extracted / ".pytest_cache/nested"
            cache.mkdir(parents=True)
            (cache / "state.txt").write_text("runtime cache\n", encoding="utf-8")
            pycache = extracted / "scripts/__pycache__"
            pycache.mkdir(parents=True)
            (pycache / "module.pyc").write_bytes(b"runtime bytecode")
            (extracted / ".DS_Store").write_bytes(b"finder metadata")

            self.assertEqual(VERIFY_MODULE.verify_directory(extracted), [])

            if hasattr(Path, "symlink_to"):
                (cache / "escape").symlink_to(extracted / "README.md")
                self.assertIn(
                    "package_directory_symlink_rejected",
                    VERIFY_MODULE.verify_directory(extracted),
                )

    def test_tampered_zip_file_digest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            _root, output = create_source_package(base)
            tampered = base / "tampered.zip"
            rewrite_zip(
                output,
                tampered,
                replacements={"CodexQB/README.md": b"tampered\n"},
            )

            errors = VERIFY_MODULE.verify_zip(tampered)
            self.assertTrue(any(error.startswith("package_file_digest_mismatch=") for error in errors))

    def test_deeply_nested_manifest_is_rejected_without_recursion_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            output, extracted = extracted_package(base)
            depth = 1_000_000
            nested = ("[" * depth + "0" + "]" * depth).encode("ascii")

            tampered = base / "deep-manifest.zip"
            rewrite_zip(
                output,
                tampered,
                replacements={MANIFEST_MEMBER: nested},
            )
            self.assertIn(
                "package_manifest_invalid_json",
                VERIFY_MODULE.verify_zip(tampered),
            )

            manifest_path = extracted / "PACKAGE-MANIFEST.json"
            manifest_path.write_bytes(nested)
            manifest_path.chmod(0o644)
            self.assertIn(
                "package_manifest_invalid_json",
                VERIFY_MODULE.verify_directory(extracted),
            )

    def test_extracted_tamper_extra_and_missing_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _output, extracted = extracted_package(Path(temp_dir))
            readme = extracted / "README.md"
            readme.write_text("tampered\n", encoding="utf-8")
            (extracted / "unexpected.txt").write_text("extra\n", encoding="utf-8")

            errors = VERIFY_MODULE.verify_directory(extracted)
            self.assertIn("package_manifest_file_set_mismatch", errors)
            self.assertTrue(any(error.startswith("package_file_digest_mismatch=") for error in errors))

            readme.unlink()
            self.assertIn(
                "package_manifest_file_set_mismatch",
                VERIFY_MODULE.verify_directory(extracted),
            )

    def test_tree_digest_duplicate_and_non_release_claim_tampering_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _output, extracted = extracted_package(Path(temp_dir))
            manifest_path = extracted / "PACKAGE-MANIFEST.json"
            original = json.loads(manifest_path.read_text(encoding="utf-8"))

            bad_tree = copy.deepcopy(original)
            bad_tree["tree_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(bad_tree), encoding="utf-8")
            self.assertIn(
                "package_manifest_tree_digest_mismatch",
                VERIFY_MODULE.verify_directory(extracted),
            )

            duplicate = copy.deepcopy(original)
            duplicate["files"].append(copy.deepcopy(duplicate["files"][0]))
            duplicate["file_count"] += 1
            manifest_path.write_text(json.dumps(duplicate), encoding="utf-8")
            duplicate_errors = VERIFY_MODULE.verify_directory(extracted)
            self.assertTrue(
                any(error.startswith("package_manifest_file_duplicate=") for error in duplicate_errors)
            )

            false_release = copy.deepcopy(original)
            false_release["release_claim"] = True
            manifest_path.write_text(json.dumps(false_release), encoding="utf-8")
            self.assertIn(
                "non_release_package_claim_invalid",
                VERIFY_MODULE.verify_directory(extracted),
            )

    def test_manifest_paths_reject_noncanonical_backslash_unicode_and_ancestor_collisions(self) -> None:
        self.assertIsNone(VERIFY_MODULE.safe_manifest_path("a//b"))
        self.assertIsNone(VERIFY_MODULE.safe_manifest_path("..\\escaped.txt"))
        digest = hashlib.sha256(b"x").hexdigest()
        manifest = {
            "files": [
                {"path": "a", "sha256": digest, "mode": "0644"},
                {"path": "a/b", "sha256": digest, "mode": "0644"},
                {"path": "é.txt", "sha256": digest, "mode": "0644"},
                {"path": "e\u0301.txt", "sha256": digest, "mode": "0644"},
            ],
            "file_count": 4,
            "tree_sha256": "0" * 64,
        }

        _entries, errors = VERIFY_MODULE.manifest_entries(manifest)
        self.assertTrue(any(error.startswith("package_manifest_file_ancestor_conflict=") for error in errors))
        self.assertTrue(any(error.startswith("package_manifest_file_case_collision=") for error in errors))

    def test_zip_traversal_and_symlink_members_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            _root, output = create_source_package(base)

            traversal_info = zipfile.ZipInfo("../../escaped/")
            traversal_info.external_attr = (stat.S_IFDIR | 0o755) << 16
            traversal = base / "traversal.zip"
            rewrite_zip(output, traversal, appended=[(traversal_info, b"")])
            self.assertIn("package_zip_entry_path_invalid", VERIFY_MODULE.verify_zip(traversal))

            symlink_info = zipfile.ZipInfo("CodexQB/link")
            symlink_info.create_system = 3
            symlink_info.external_attr = (stat.S_IFLNK | 0o777) << 16
            symlink = base / "symlink.zip"
            rewrite_zip(output, symlink, appended=[(symlink_info, b"README.md")])
            self.assertIn("package_zip_entry_type_invalid", VERIFY_MODULE.verify_zip(symlink))

    def test_zip_rejects_unsafe_regular_file_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            _root, output = create_source_package(base)
            tampered = base / "unsafe-mode.zip"
            with zipfile.ZipFile(output) as original, zipfile.ZipFile(
                tampered,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as rewritten:
                for original_info in original.infolist():
                    info = copy.copy(original_info)
                    if info.filename == "CodexQB/README.md":
                        info.external_attr = (stat.S_IFREG | 0o4777) << 16
                    rewritten.writestr(info, original.read(original_info.filename))

            self.assertIn(
                "package_zip_entry_type_invalid",
                VERIFY_MODULE.verify_zip(tampered),
            )

    def test_manifest_binds_safe_file_modes_in_zip_and_extracted_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            output, extracted = extracted_package(base)
            tampered = base / "safe-but-wrong-mode.zip"
            with zipfile.ZipFile(output) as original, zipfile.ZipFile(
                tampered,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as rewritten:
                for original_info in original.infolist():
                    info = copy.copy(original_info)
                    if info.filename == "CodexQB/README.md":
                        info.external_attr = (stat.S_IFREG | 0o755) << 16
                    rewritten.writestr(info, original.read(original_info.filename))

            self.assertTrue(
                any(
                    error.startswith("package_file_mode_mismatch=")
                    for error in VERIFY_MODULE.verify_zip(tampered)
                )
            )

            (extracted / "README.md").chmod(0o755)
            self.assertTrue(
                any(
                    error.startswith("package_file_mode_mismatch=")
                    for error in VERIFY_MODULE.verify_directory(extracted)
                )
            )

    def test_extra_standalone_pyc_is_not_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _output, extracted = extracted_package(Path(temp_dir))
            (extracted / "standalone.pyc").write_bytes(b"executable bytecode")

            self.assertIn(
                "package_manifest_file_set_mismatch",
                VERIFY_MODULE.verify_directory(extracted),
            )

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlink support required")
    def test_descriptor_walk_rejects_ancestor_symlink_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            _output, extracted = extracted_package(base)
            replacement = base / "replacement-plugins"
            shutil.copytree(extracted / "plugins", replacement)
            original_plugins = base / "original-plugins"
            real_open = VERIFY_MODULE.os.open
            fired = False

            def swap_before_directory_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal fired
                if not fired and dir_fd is not None and path == "plugins":
                    fired = True
                    (extracted / "plugins").rename(original_plugins)
                    (extracted / "plugins").symlink_to(
                        replacement,
                        target_is_directory=True,
                    )
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with mock.patch.object(
                VERIFY_MODULE.os,
                "open",
                side_effect=swap_before_directory_open,
            ):
                errors = VERIFY_MODULE.verify_directory(extracted)

            self.assertTrue(fired)
            self.assertNotEqual(errors, [])
            self.assertTrue(
                "package_directory_inventory_unavailable" in errors
                or "package_directory_symlink_rejected" in errors
            )

    def test_real_directory_swap_cannot_hide_an_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            _output, extracted = extracted_package(base)
            replacement = base / "replacement-plugins"
            shutil.copytree(extracted / "plugins", replacement)
            (replacement / "evil.py").write_text("print('unexpected')\n", encoding="utf-8")
            original_plugins = base / "original-plugins"
            real_digest = VERIFY_MODULE.regular_file_sha256
            fired = False

            def swap_before_hash(root_descriptor, relative, maximum_bytes):
                nonlocal fired
                if not fired:
                    fired = True
                    (extracted / "plugins").rename(original_plugins)
                    replacement.rename(extracted / "plugins")
                return real_digest(root_descriptor, relative, maximum_bytes)

            with mock.patch.object(
                VERIFY_MODULE,
                "regular_file_sha256",
                side_effect=swap_before_hash,
            ):
                errors = VERIFY_MODULE.verify_directory(extracted)

            self.assertTrue(fired)
            self.assertIn("package_directory_changed_during_verification", errors)

    def test_ancestor_checks_remain_linear_at_manifest_limit(self) -> None:
        digest = hashlib.sha256(b"x").hexdigest()
        entries = [
            {
                "path": f"flat/{index:06d}.txt",
                "sha256": digest,
                "mode": "0644",
            }
            for index in range(VERIFY_MODULE.MAX_MANIFEST_FILES)
        ]
        encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
        manifest = {
            "files": entries,
            "file_count": len(entries),
            "tree_sha256": hashlib.sha256(encoded).hexdigest(),
        }

        started = time.monotonic()
        parsed, errors = VERIFY_MODULE.manifest_entries(manifest)
        elapsed = time.monotonic() - started

        self.assertEqual(errors, [])
        self.assertEqual(len(parsed), VERIFY_MODULE.MAX_MANIFEST_FILES)
        self.assertLess(elapsed, 5.0)

        class IterationForbiddenDict(dict):
            def __iter__(self):
                raise AssertionError("archive ancestor checks must not scan prior entries")

        self.assertFalse(
            VERIFY_MODULE.archive_entry_has_ancestor_conflict(
                "codexqb/new.txt",
                False,
                IterationForbiddenDict({"codexqb/old.txt": False}),
                {"codexqb"},
            )
        )

    def test_extracted_directory_enforces_cumulative_size_limit_without_unbounded_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _output, extracted = extracted_package(Path(temp_dir))
            packaged_files = [
                path
                for path in extracted.rglob("*")
                if path.is_file()
            ]
            actual_total = sum(path.stat().st_size for path in packaged_files)
            largest_file = max(path.stat().st_size for path in packaged_files)
            self.assertGreater(actual_total, largest_file)
            patched_limit = actual_total - 1
            with (
                mock.patch.object(
                    VERIFY_MODULE,
                    "MAX_PACKAGE_UNCOMPRESSED_BYTES",
                    patched_limit,
                ),
                mock.patch.object(
                    VERIFY_MODULE,
                    "regular_file_sha256",
                    wraps=VERIFY_MODULE.regular_file_sha256,
                ) as digest_mock,
            ):
                errors = VERIFY_MODULE.verify_directory(extracted)

            self.assertIn("package_directory_size_limit_exceeded", errors)
            self.assertEqual(digest_mock.call_count, 0)

    def test_boolean_type_tricks_and_forged_strict_provenance_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _root, output = create_source_package(Path(temp_dir))
            with zipfile.ZipFile(output) as archive:
                manifest = json.loads(archive.read(MANIFEST_MEMBER).decode("utf-8"))

            type_trick = copy.deepcopy(manifest)
            type_trick["package_schema_version"] = True
            type_trick["file_count"] = True
            type_trick["release_claim"] = 1
            type_errors = [
                *VERIFY_MODULE.manifest_entries(type_trick)[1],
                *VERIFY_MODULE.manifest_contract_errors(type_trick),
            ]
            self.assertIn("package_manifest_schema_version_invalid", type_errors)
            self.assertIn("package_manifest_file_count_mismatch", type_errors)
            self.assertIn("non_release_package_claim_invalid", type_errors)

            forged = copy.deepcopy(manifest)
            forged.update(
                {
                    "export_mode": "strict_release",
                    "release_claim": True,
                    "git_provenance_available": True,
                    "source_inventory": "git_index",
                    "working_tree_clean": True,
                    "tracked_only": True,
                    "include_untracked": False,
                    "changelog_mentions_plugin_version": True,
                    "changelog_release_state": "released",
                    "release_tag_matches_head": True,
                    "git_commit": "unknown",
                    "release_tag_commit": "unknown",
                    "origin_main_ref_status": "unavailable",
                }
            )
            forged_errors = VERIFY_MODULE.manifest_contract_errors(forged)
            self.assertIn("strict_release_manifest_invalid=git_commit", forged_errors)
            self.assertIn("strict_release_manifest_invalid=release_tag_commit", forged_errors)
            self.assertIn("strict_release_manifest_invalid=origin_main_ref_status", forged_errors)


if __name__ == "__main__":
    unittest.main()
