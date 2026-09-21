"""Comprobaciones mínimas del contrato de bootstrap."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import infocs


class BootstrapStructureTests(unittest.TestCase):
    def test_package_is_importable(self) -> None:
        self.assertEqual(infocs.__version__, "0.0.0")

    def test_required_foundation_files_exist(self) -> None:
        for relative_path in (
            "AGENTS.md",
            "pyproject.toml",
            ".gitignore",
            "docs/INFOCS_SPEC_v1.md",
            "docs/ARCHITECTURE.md",
            "docs/DECISIONS.md",
            "docs/IMPLEMENTATION_PLAN.md",
        ):
            with self.subTest(relative_path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())
