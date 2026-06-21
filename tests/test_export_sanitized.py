from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTER = REPO_ROOT / "scripts/export_sanitized.py"


def load_export_module():
    spec = importlib.util.spec_from_file_location("codexqb_export_sanitized", EXPORTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load export_sanitized from {EXPORTER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


EXPORT_MODULE = load_export_module()


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, text=True, capture_output=True)


class ExportSanitizedTests(unittest.TestCase):
    def test_default_export_excludes_untracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            git(root, "init")
            (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
            git(root, "add", "README.md")
            (root / "notes.txt").write_text("do not ship sk-" + "A" * 40 + "\n", encoding="utf-8")
            output = root / "CodexQB-sanitized.zip"

            count = EXPORT_MODULE.create_zip(root, output)

            self.assertEqual(count, 1)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertIn("CodexQB/README.md", names)
            self.assertNotIn("CodexQB/notes.txt", names)

    def test_include_untracked_scans_secret_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            git(root, "init")
            (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
            git(root, "add", "README.md")
            (root / "notes.txt").write_text("leaked sk-" + "A" * 40 + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "secret_like_content=notes.txt"):
                EXPORT_MODULE.create_zip(root, root / "CodexQB-sanitized.zip", include_untracked=True)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlink support required")
    def test_export_rejects_symlink_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as outside_dir:
            root = Path(temp_dir)
            outside = Path(outside_dir) / "outside.txt"
            outside.write_text("outside secret\n", encoding="utf-8")
            git(root, "init")
            (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
            (root / "external-link.txt").symlink_to(outside)
            git(root, "add", "README.md", "external-link.txt")

            with self.assertRaisesRegex(ValueError, "symlink_rejected=external-link.txt"):
                EXPORT_MODULE.create_zip(root, root / "CodexQB-sanitized.zip")


if __name__ == "__main__":
    unittest.main()
