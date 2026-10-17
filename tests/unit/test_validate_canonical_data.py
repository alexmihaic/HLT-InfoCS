import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
_SPEC = importlib.util.spec_from_file_location(
    "validate_canonical_data", ROOT / "scripts" / "validate_canonical_data.py"
)
validate_canonical_data = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validate_canonical_data)


class CanonicalDataDiagnosticsTests(unittest.TestCase):
    def test_public_diagnostics_never_expose_identifiers_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "schemas", root / "schemas")
            records = root / "data" / "records" / "bdns"
            records.mkdir(parents=True)
            (records / "r-infocs%3Abdns%3A987654-0123456789abcdef.json").write_text(
                '{"source": {"id": "bdns", "official_id": "987654"}, "title": "SECRETO"}',
                encoding="utf-8",
            )
            health = root / "data" / "health"
            health.mkdir(parents=True)
            (health / "bdns.json").write_text('{"source_id": "bdns", "status": "x"}', encoding="utf-8")

            with self.assertRaises(validate_canonical_data.CanonicalDataError) as raised:
                validate_canonical_data.validate_canonical_data(root)

        message = str(raised.exception)
        self.assertIn("records/bdns#1: SchemaValidationError(", message)
        self.assertIn("health/bdns#1: SchemaValidationError(", message)
        for leaked in ("987654", "0123456789abcdef", "infocs", "SECRETO", "r-", ".json", directory):
            self.assertNotIn(leaked, message)


if __name__ == "__main__":
    unittest.main()
