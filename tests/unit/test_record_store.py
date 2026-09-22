"""Pruebas aisladas del almacenamiento canónico en directorios temporales."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.boe import (
    BOEDocumentLinks,
    BOEItem,
    BOETerritorialDecision,
    BOETerritorialDecisionStatus,
    BOETerritorialField,
    BOETerritorialMatch,
    BOETerritorialMatchReason,
    normalize_boe_item,
)
from infocs.finalize import finalize_record
from infocs.models import Record
from infocs.store import RecordStore
from datetime import UTC, date, datetime


def record() -> Record:
    item = BOEItem(
        official_id="BOE-A-2099-STORE",
        title="Resolución relativa a Borriana",
        section_code="1",
        section_name="I. Disposiciones generales",
        department_code="9999",
        department_name="MINISTERIO DE EJEMPLO",
        published_on=date(2099, 1, 1),
        documents=BOEDocumentLinks(
            xml_url="https://www.boe.es/diario_boe/xml.php?id=BOE-A-2099-STORE",
            html_url="https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-STORE",
            pdf_url="https://www.boe.es/boe/dias/2099/01/01/pdfs/BOE-A-2099-STORE.pdf",
        ),
    )
    decision = BOETerritorialDecision(
        BOETerritorialDecisionStatus.INCLUDE,
        (
            BOETerritorialMatch(
                BOETerritorialMatchReason.MUNICIPALITY_EXACT,
                "12031",
                "Borriana",
                BOETerritorialField.TITLE,
                "Borriana",
                "fixture",
            ),
        ),
    )
    candidate = normalize_boe_item(
        item, decision,
        detected_at=datetime(2099, 1, 2, 10, tzinfo=UTC),
        last_checked_at=datetime(2099, 1, 2, 10, tzinfo=UTC),
    )
    assert candidate is not None
    return finalize_record(candidate)


class RecordStoreTests(unittest.TestCase):
    def test_write_is_canonical_atomic_and_round_trips_valid_record(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            current = record()
            path = store.write(current)
            self.assertEqual(path, store.path_for(current.source.id, current.id))
            self.assertTrue(path.is_file())
            self.assertTrue(path.read_bytes().endswith(b"\n"))
            self.assertEqual(Record.from_json(path.read_bytes()), current)
            self.assertEqual(store.get(current.id), current)
            self.assertTrue(store.exists(current.id, source_id="boe"))
            self.assertEqual(store.list_source("boe"), (current,))
            self.assertEqual(tuple(path.parent.glob("*.tmp")), ())
            self.assertEqual(tuple(path.parent.glob(".*.tmp")), ())

    def test_same_record_path_is_stable_across_replacement(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            current = record()
            first_path = store.write(current)
            second_path = store.write(current)
            self.assertEqual(first_path, second_path)
            self.assertEqual(len(tuple(first_path.parent.glob("r-*.json"))), 1)

    def test_external_ids_are_encoded_and_cannot_escape_root(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            path = store.path_for("../outside", "../../escape\\record")
            root = Path(directory).resolve()
            self.assertIn(root, path.parents)
            self.assertNotIn("..", path.name)
            self.assertNotIn("/", path.name)
            self.assertNotIn("\\", path.name)
            self.assertEqual(path, store.path_for("../outside", "../../escape\\record"))

    def test_store_does_not_create_project_data_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "records"
            store = RecordStore(root)
            self.assertFalse(root.exists())
            self.assertEqual(store.list_source("boe"), ())
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
