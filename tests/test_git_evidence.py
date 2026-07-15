from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "plugins/codexqb/skills/codexqb/scripts"
GIT_EVIDENCE_PATH = SCRIPTS_DIR / "git_evidence.py"


def load_git_evidence_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("codexqb_git_evidence", GIT_EVIDENCE_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"could not load git_evidence from {GIT_EVIDENCE_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


GIT_EVIDENCE = load_git_evidence_module()
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class GitEvidenceTests(unittest.TestCase):
    def git(self, root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def init_repo(self, root: Path, *, attributes: bool = False) -> Path:
        self.git(root, "init", "-q")
        tracked = root / "tracked.txt"
        tracked.write_text("before\n", encoding="utf-8")
        if attributes:
            (root / ".gitattributes").write_text(
                "*.txt diff=probe filter=probe\n",
                encoding="utf-8",
            )
        self.git(root, "add", ".")
        self.git(
            root,
            "-c",
            "user.name=CodexQB Test",
            "-c",
            "user.email=codexqb-test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        )
        return tracked

    def marker_program(self, root: Path, name: str) -> tuple[Path, Path]:
        marker = root / f"{name}.ran"
        program = root / f"{name}.sh"
        program.write_text(f"#!/bin/sh\ntouch '{marker.as_posix()}'\nexit 0\n", encoding="utf-8")
        program.chmod(0o755)
        return program, marker

    def test_clean_staged_unstaged_and_untracked_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tracked = self.init_repo(root)

            clean = GIT_EVIDENCE.capture_git_workspace_evidence(root)
            self.assertTrue(clean["is_git"])
            self.assertEqual(clean["tracked_paths"], ["tracked.txt"])
            self.assertEqual(clean["staged_diff_sha256"], EMPTY_SHA256)
            self.assertEqual(clean["unstaged_diff_sha256"], EMPTY_SHA256)
            self.assertEqual(clean["untracked_paths_sha256"], EMPTY_SHA256)
            self.assertEqual(clean["untracked_entries_sha256"], EMPTY_SHA256)
            self.assertEqual(clean["status_sha256"], EMPTY_SHA256)

            tracked.write_text("staged\n", encoding="utf-8")
            self.git(root, "add", "tracked.txt")
            staged = GIT_EVIDENCE.capture_git_workspace_evidence(root)
            self.assertEqual([item["path"] for item in staged["staged_changes"]], ["tracked.txt"])
            self.assertNotEqual(staged["staged_diff_sha256"], EMPTY_SHA256)
            self.assertEqual(staged["unstaged_diff_sha256"], EMPTY_SHA256)

            tracked.write_text("unstaged\n", encoding="utf-8")
            (root / "new file.txt").write_text("untracked\n", encoding="utf-8")
            dirty = GIT_EVIDENCE.capture_git_workspace_evidence(root)
            self.assertEqual([item["path"] for item in dirty["unstaged_changes"]], ["tracked.txt"])
            self.assertEqual(dirty["untracked_paths"], ["new file.txt"])
            self.assertEqual([item["path"] for item in dirty["untracked_entries"]], ["new file.txt"])
            self.assertNotEqual(dirty["unstaged_diff_sha256"], EMPTY_SHA256)
            self.assertNotEqual(dirty["untracked_paths_sha256"], EMPTY_SHA256)
            self.assertNotEqual(dirty["untracked_entries_sha256"], EMPTY_SHA256)
            self.assertNotEqual(dirty["status_sha256"], EMPTY_SHA256)

    def test_tracked_and_untracked_content_share_one_descriptor_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.init_repo(root)
            untracked = root / "local.txt"
            untracked.write_text("first\n", encoding="utf-8")
            runtime = root / ".runtime"
            runtime.mkdir()
            (runtime / "excluded.bin").write_bytes(b"x" * 1024)
            self.git(root, "add", ".runtime/excluded.bin")
            self.git(
                root,
                "-c",
                "user.name=CodexQB Test",
                "-c",
                "user.email=codexqb-test@example.invalid",
                "commit",
                "-qm",
                "tracked exclusion",
            )

            def exclude_runtime(path: str) -> bool:
                return path.startswith(".runtime/")

            real_snapshot = GIT_EVIDENCE.snapshot_git_paths_from_anchor
            calls: list[list[str]] = []

            def recording_snapshot(anchor, paths, **kwargs):
                selected = list(paths)
                calls.append(selected)
                return real_snapshot(anchor, selected, **kwargs)

            with mock.patch.object(
                GIT_EVIDENCE,
                "snapshot_git_paths_from_anchor",
                side_effect=recording_snapshot,
            ):
                first = GIT_EVIDENCE.capture_git_workspace_evidence(
                    root,
                    exclude_untracked=exclude_runtime,
                    exclude_tracked=exclude_runtime,
                )

            self.assertEqual(calls, [["local.txt", "tracked.txt"]])
            self.assertEqual(first["untracked_paths"], ["local.txt"])
            self.assertEqual(
                [entry["path"] for entry in first["worktree_entries"]],
                ["tracked.txt"],
            )
            first_entry = first["untracked_entries"][0]
            self.assertEqual(first_entry["kind"], "regular")
            self.assertEqual(first_entry["git_mode"], "100644")
            first_digest = first["untracked_entries_sha256"]

            untracked.write_text("second\n", encoding="utf-8")
            content_changed = GIT_EVIDENCE.capture_git_workspace_evidence(
                root,
                exclude_untracked=exclude_runtime,
                exclude_tracked=exclude_runtime,
            )
            self.assertNotEqual(content_changed["untracked_entries_sha256"], first_digest)

            untracked.chmod(0o755)
            mode_changed = GIT_EVIDENCE.capture_git_workspace_evidence(
                root,
                exclude_untracked=exclude_runtime,
                exclude_tracked=exclude_runtime,
            )
            self.assertEqual(mode_changed["untracked_entries"][0]["git_mode"], "100755")
            self.assertNotEqual(
                mode_changed["untracked_entries_sha256"],
                content_changed["untracked_entries_sha256"],
            )

            untracked.unlink()
            untracked.symlink_to("tracked.txt")
            kind_changed = GIT_EVIDENCE.capture_git_workspace_evidence(
                root,
                exclude_untracked=exclude_runtime,
                exclude_tracked=exclude_runtime,
            )
            self.assertEqual(kind_changed["untracked_entries"][0]["kind"], "symlink")
            self.assertNotEqual(
                kind_changed["untracked_entries_sha256"],
                mode_changed["untracked_entries_sha256"],
            )

    def test_unborn_detached_and_sha256_repositories_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            unborn_root = Path(temp_dir) / "unborn"
            unborn_root.mkdir()
            self.git(unborn_root, "init", "-q")
            (unborn_root / "first.txt").write_text("first\n", encoding="utf-8")
            self.git(unborn_root, "add", "first.txt")

            unborn = GIT_EVIDENCE.capture_git_workspace_evidence(unborn_root)
            self.assertEqual(unborn["head"], "unknown")
            self.assertEqual(unborn["staged_changes"][0]["state"], "add")
            self.assertEqual(unborn["unstaged_diff_sha256"], EMPTY_SHA256)

            self.git(
                unborn_root,
                "-c",
                "user.name=CodexQB Test",
                "-c",
                "user.email=codexqb-test@example.invalid",
                "commit",
                "-qm",
                "fixture",
            )
            self.git(unborn_root, "checkout", "--detach", "-q")
            detached = GIT_EVIDENCE.capture_git_workspace_evidence(unborn_root)
            self.assertEqual(detached["branch"], "unknown")
            self.assertRegex(str(detached["head"]), r"^[0-9a-f]{40}$")

        with tempfile.TemporaryDirectory() as temp_dir:
            sha256_root = Path(temp_dir)
            initialized = subprocess.run(
                ["git", "init", "-q", "--object-format=sha256"],
                cwd=sha256_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if initialized.returncode != 0:
                self.skipTest("installed Git does not support SHA-256 repositories")
            (sha256_root / "tracked.txt").write_text("sha256\n", encoding="utf-8")
            self.git(sha256_root, "add", "tracked.txt")
            self.git(
                sha256_root,
                "-c",
                "user.name=CodexQB Test",
                "-c",
                "user.email=codexqb-test@example.invalid",
                "commit",
                "-qm",
                "fixture",
            )
            evidence = GIT_EVIDENCE.capture_git_workspace_evidence(sha256_root)
            self.assertEqual(evidence["object_format"], "sha256")
            self.assertRegex(str(evidence["head"]), r"^[0-9a-f]{64}$")
            self.assertEqual(evidence["status_sha256"], EMPTY_SHA256)

    def test_repository_controlled_executables_are_never_invoked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tracked = self.init_repo(root, attributes=True)
            external, external_marker = self.marker_program(root, "external-diff")
            textconv, textconv_marker = self.marker_program(root, "textconv")
            clean, clean_marker = self.marker_program(root, "clean-filter")
            fsmonitor, fsmonitor_marker = self.marker_program(root, "fsmonitor")
            inherited, inherited_marker = self.marker_program(root, "inherited-external-diff")
            fake_git, fake_git_marker = self.marker_program(root, "fake-git")
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            (fake_bin / "git").symlink_to(fake_git)
            self.git(root, "config", "diff.external", external.as_posix())
            self.git(root, "config", "diff.probe.textconv", textconv.as_posix())
            self.git(root, "config", "filter.probe.clean", clean.as_posix())
            self.git(root, "config", "core.fsmonitor", fsmonitor.as_posix())
            tracked.write_text("after\n", encoding="utf-8")

            previous = os.environ.get("GIT_EXTERNAL_DIFF")
            previous_path = os.environ.get("PATH")
            os.environ["GIT_EXTERNAL_DIFF"] = inherited.as_posix()
            os.environ["PATH"] = f"{fake_bin}{os.pathsep}{previous_path or ''}"
            try:
                evidence = GIT_EVIDENCE.capture_git_workspace_evidence(root)
            finally:
                if previous is None:
                    os.environ.pop("GIT_EXTERNAL_DIFF", None)
                else:
                    os.environ["GIT_EXTERNAL_DIFF"] = previous
                if previous_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = previous_path

            self.assertEqual([item["path"] for item in evidence["unstaged_changes"]], ["tracked.txt"])
            self.assertNotEqual(evidence["unstaged_diff_sha256"], EMPTY_SHA256)
            for marker in (
                external_marker,
                textconv_marker,
                clean_marker,
                fsmonitor_marker,
                inherited_marker,
                fake_git_marker,
            ):
                self.assertFalse(marker.exists(), marker.name)

    def test_repository_root_replacement_is_detected_while_git_uses_open_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            root = parent / "root"
            replacement = parent / "replacement"
            original_after_swap = parent / "original-after-swap"
            root.mkdir()
            replacement.mkdir()
            self.init_repo(root)
            replacement_tracked = self.init_repo(replacement)
            replacement_tracked.write_text("attacker replacement\n", encoding="utf-8")

            real_popen = subprocess.Popen
            invocation: dict[str, object] = {}

            def swap_before_child_chdir(*args, **kwargs):
                if not invocation:
                    invocation.update(kwargs)
                    root.rename(original_after_swap)
                    replacement.rename(root)
                return real_popen(*args, **kwargs)

            with mock.patch.object(
                GIT_EVIDENCE.subprocess,
                "Popen",
                side_effect=swap_before_child_chdir,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "git_evidence_root_identity_changed",
                ):
                    GIT_EVIDENCE.capture_git_workspace_evidence(root)

            self.assertIsNone(invocation["cwd"])
            self.assertTrue(invocation["pass_fds"])
            self.assertIsNotNone(invocation["preexec_fn"])
            self.assertEqual((root / "tracked.txt").read_text(encoding="utf-8"), "attacker replacement\n")
            self.assertEqual(
                (original_after_swap / "tracked.txt").read_text(encoding="utf-8"),
                "before\n",
            )

    def test_environment_and_command_allowlist_are_fail_closed(self) -> None:
        environment = GIT_EVIDENCE.git_subprocess_environment(
            {
                "PATH": "/usr/bin",
                "GIT_DIR": "/tmp/attacker",
                "git_external_diff": "/tmp/attacker-diff",
                "LANG": "tr_TR.UTF-8",
                "PWD": "/tmp/replaced-root",
                "OLDPWD": "/tmp/old-root",
            }
        )
        self.assertEqual(environment["PATH"], os.defpath)
        self.assertEqual(environment["LANG"], "C")
        self.assertEqual(environment["LC_ALL"], "C")
        self.assertNotIn("GIT_DIR", environment)
        self.assertNotIn("git_external_diff", environment)
        self.assertNotIn("PWD", environment)
        self.assertNotIn("OLDPWD", environment)
        with self.assertRaisesRegex(ValueError, "git_evidence_command_not_allowed"):
            GIT_EVIDENCE.git_command(["diff", "--binary"])

    def test_git_command_output_is_bounded_before_buffering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            noisy_git = root / "noisy-git"
            noisy_git.write_text(
                "#!/bin/sh\n/usr/bin/yes A | /usr/bin/head -c 10000\n",
                encoding="utf-8",
            )
            noisy_git.chmod(0o755)
            with mock.patch.object(
                GIT_EVIDENCE,
                "trusted_git_executable",
                return_value=noisy_git.as_posix(),
            ), mock.patch.object(
                GIT_EVIDENCE,
                "MAX_GIT_COMMAND_OUTPUT_BYTES",
                1024,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "git_evidence_output_limit_exceeded=bounded_probe",
                ):
                    GIT_EVIDENCE.run_git_bytes(
                        root,
                        ("rev-parse", "--show-object-format"),
                        operation="bounded_probe",
                    )

    def test_preexec_git_runner_rejects_multithreaded_parent_before_popen(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            GIT_EVIDENCE.threading,
            "active_count",
            return_value=2,
        ), mock.patch.object(GIT_EVIDENCE.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(
                ValueError,
                "git_evidence_preexec_requires_single_thread",
            ):
                GIT_EVIDENCE.run_git_bytes(
                    Path(temp_dir),
                    ("rev-parse", "--show-object-format"),
                    operation="thread_guard",
                )
            popen.assert_not_called()

    def test_all_post_popen_setup_failures_kill_reap_and_close_pipes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incomplete = mock.Mock()
            incomplete.pid = 4242
            incomplete.stdout = None
            incomplete.stderr = mock.Mock()
            incomplete.wait.return_value = 0

            with mock.patch.object(
                GIT_EVIDENCE.subprocess,
                "Popen",
                return_value=incomplete,
            ), mock.patch.object(
                GIT_EVIDENCE,
                "_terminate_git_process_group",
            ) as terminate:
                with self.assertRaisesRegex(
                    ValueError,
                    "git_evidence_command_unavailable=incomplete_pipe",
                ):
                    GIT_EVIDENCE.run_git_bytes(
                        root,
                        ("rev-parse", "--show-object-format"),
                        operation="incomplete_pipe",
                    )
            terminate.assert_called_once_with(incomplete)
            incomplete.wait.assert_called_once_with(timeout=5)
            incomplete.stderr.close.assert_called_once_with()

            selector_failure = mock.Mock()
            selector_failure.pid = 4343
            selector_failure.stdout = mock.Mock()
            selector_failure.stderr = mock.Mock()
            selector_failure.wait.return_value = 0

            with mock.patch.object(
                GIT_EVIDENCE.subprocess,
                "Popen",
                return_value=selector_failure,
            ), mock.patch.object(
                GIT_EVIDENCE.selectors,
                "DefaultSelector",
                side_effect=OSError("selector unavailable"),
            ), mock.patch.object(
                GIT_EVIDENCE,
                "_terminate_git_process_group",
            ) as terminate:
                with self.assertRaisesRegex(
                    ValueError,
                    "git_evidence_command_unavailable=selector_setup",
                ):
                    GIT_EVIDENCE.run_git_bytes(
                        root,
                        ("rev-parse", "--show-object-format"),
                        operation="selector_setup",
                    )
            terminate.assert_called_once_with(selector_failure)
            selector_failure.wait.assert_called_once_with(timeout=5)
            selector_failure.stdout.close.assert_called_once_with()
            selector_failure.stderr.close.assert_called_once_with()

            interrupted = mock.Mock()
            interrupted.pid = 4444
            interrupted.stdout = mock.Mock()
            interrupted.stderr = mock.Mock()
            interrupted.wait.return_value = 0

            with mock.patch.object(
                GIT_EVIDENCE.subprocess,
                "Popen",
                return_value=interrupted,
            ), mock.patch.object(
                GIT_EVIDENCE.time,
                "monotonic",
                side_effect=KeyboardInterrupt,
            ), mock.patch.object(
                GIT_EVIDENCE,
                "_terminate_git_process_group",
            ) as terminate:
                with self.assertRaises(KeyboardInterrupt):
                    GIT_EVIDENCE.run_git_bytes(
                        root,
                        ("rev-parse", "--show-object-format"),
                        operation="post_popen_interrupt",
                    )
            terminate.assert_called_once_with(interrupted)
            interrupted.wait.assert_called_once_with(timeout=5)
            interrupted.stdout.close.assert_called_once_with()
            interrupted.stderr.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
