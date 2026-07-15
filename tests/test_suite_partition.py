from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts/run_test_suite.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("codexqb_test_suite_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load suite runner from {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner_module()


class TestSuitePartitionTests(unittest.TestCase):
    def test_every_top_level_test_module_has_one_primary_gate(self) -> None:
        suites = RUNNER.primary_suite_stems()
        owners: dict[str, list[str]] = {}
        for suite, stems in suites.items():
            for stem in stems:
                owners.setdefault(stem, []).append(suite)

        discovered = RUNNER.discover_test_stems()
        self.assertEqual(set(owners), discovered)
        self.assertEqual(
            {stem: names for stem, names in owners.items() if len(names) != 1},
            {},
        )

    def test_fast_suite_is_a_platform_and_package_free_unit_subset(self) -> None:
        suites = RUNNER.primary_suite_stems()
        fast = set(RUNNER.suite_stems("fast"))

        self.assertTrue(fast)
        self.assertLessEqual(fast, set(suites["unit"]))
        self.assertTrue(fast.isdisjoint(suites["platform"]))
        self.assertTrue(fast.isdisjoint(suites["package"]))
        self.assertTrue(fast.isdisjoint(suites["schema"]))
        self.assertTrue(fast.isdisjoint(suites["behavior"]))


if __name__ == "__main__":
    unittest.main()
