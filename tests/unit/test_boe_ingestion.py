"""Pruebas offline de ingesta incremental BOE y RecordStore canónico."""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.boe import (
    BOEDepartment,
    BOEDiary,
    BOEDocumentLinks,
    BOEFetchResult,
    BOEFetchStatus,
    BOE_COLLECTION_SEMANTICS,
    BOECollectionSemantics,
    BOEHeading,
    BOEIngestionError,
    BOEIngestionStatus,
    BOEItem,
    BOESection,
    BOESummary,
    ingest_boe_summary,
    load_castellon_registry,
)
from infocs.models import RecordStatus
from infocs.privacy import PrivacyGate, PrivacyGateError
from infocs.store import RecordStore


NOW = datetime(2026, 9, 23, 9, 0, tzinfo=UTC)
REGISTRY = load_castellon_registry()


def item(
    official_id: str,
    *,
    title: str,
    published_on: date = date(2026, 9, 23),
) -> BOEItem:
    return BOEItem(
        official_id=official_id,
        title=title,
        section_code="1",
        section_name="I. Disposiciones generales",
        department_code="9999",
        department_name="MINISTERIO DE EJEMPLO",
        published_on=published_on,
        documents=BOEDocumentLinks(
            xml_url=f"https://www.boe.es/diario_boe/xml.php?id={official_id}",
            html_url=f"https://www.boe.es/diario_boe/txt.php?id={official_id}",
            pdf_url=f"https://www.boe.es/boe/dias/2026/09/23/pdfs/{official_id}.pdf",
        ),
    )


def summary(*items: BOEItem) -> BOESummary:
    department = BOEDepartment(
        code="9999",
        name="MINISTERIO DE EJEMPLO",
        headings=(BOEHeading(name="Anuncios ficticios", items=tuple(items)),),
        direct_items=(),
    )
    section = BOESection(code="1", name="I. Disposiciones generales", departments=(department,))
    return BOESummary(
        publication_date=date(2026, 9, 23),
        diaries=(BOEDiary(number="1", sections=(section,)),),
    )


def included_item(official_id: str, title: str = "Resolución relativa a Borriana") -> BOEItem:
    return item(official_id, title=title)


class BOEIngestionTests(unittest.TestCase):
    def test_boe_declares_incremental_feed_not_snapshot(self) -> None:
        self.assertEqual(BOE_COLLECTION_SEMANTICS, BOECollectionSemantics.INCREMENTAL_FEED)
        self.assertEqual(BOECollectionSemantics.SNAPSHOT.value, "snapshot")
        with TemporaryDirectory() as directory:
            result = ingest_boe_summary(
                summary(), registry=REGISTRY, store=RecordStore(directory),
                detected_at=NOW, last_checked_at=NOW,
            )
            self.assertEqual(result.collection_semantics, BOECollectionSemantics.INCREMENTAL_FEED)

    def test_create_and_excluded_metrics_and_event_are_in_memory(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            result = ingest_boe_summary(
                summary(
                    included_item("BOE-A-2099-1"),
                    item("BOE-A-2099-2", title="Resolución estatal sin territorio"),
                ),
                registry=REGISTRY,
                store=store,
                detected_at=NOW,
                last_checked_at=NOW,
            )
            self.assertEqual(result.status, BOEIngestionStatus.COMPLETE_SUCCESS)
            self.assertEqual(result.metrics.to_dict(), {
                "seen": 2,
                "included": 1,
                "created": 1,
                "updated": 0,
                "unchanged": 0,
                "excluded": 1,
                "privacy_allowed": 1,
                "privacy_quarantined": 0,
                "privacy_rejected": 0,
            })
            self.assertEqual([operation.type.value for operation in result.operations], ["create"])
            self.assertEqual([event.type for event in result.events], ["create"])
            self.assertEqual(len(store.list_source("boe")), 1)
            self.assertFalse((Path(directory) / "events").exists())

    def test_same_day_is_idempotent_and_produces_no_change(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            first = ingest_boe_summary(
                summary(included_item("BOE-A-2099-3")),
                registry=REGISTRY,
                store=store,
                detected_at=NOW,
                last_checked_at=NOW,
            )
            second = ingest_boe_summary(
                summary(included_item("BOE-A-2099-3")),
                registry=REGISTRY,
                store=store,
                detected_at=NOW,
                last_checked_at=NOW,
            )
            self.assertEqual([event.type for event in first.events], ["create"])
            self.assertEqual(second.events, ())
            self.assertEqual([operation.type.value for operation in second.operations], ["no_change"])
            self.assertEqual(second.metrics.unchanged, 1)
            self.assertEqual(len(store.list_source("boe")), 1)
            stored = store.list_source("boe")[0]
            self.assertEqual(stored.technical.content_hash, first.operations[0].record.technical.content_hash)
            self.assertEqual(stored.id, first.operations[0].record.id)

    def test_changed_content_updates_record_and_reports_diff_paths(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            first = included_item("BOE-A-2099-4")
            ingest_boe_summary(
                summary(first), registry=REGISTRY, store=store,
                detected_at=NOW, last_checked_at=NOW,
            )
            changed = included_item("BOE-A-2099-4", "Resolución corregida relativa a Borriana")
            result = ingest_boe_summary(
                summary(changed), registry=REGISTRY, store=store,
                detected_at=NOW, last_checked_at=NOW,
            )
            self.assertEqual(result.metrics.updated, 1)
            self.assertEqual(result.metrics.created, 0)
            self.assertEqual([operation.type.value for operation in result.operations], ["update"])
            self.assertIn("title", result.operations[0].changed_fields)
            self.assertEqual(result.events[0].type, "update")
            self.assertIn("title", result.events[0].changed_fields)
            self.assertEqual(store.list_source("boe")[0].title, changed.title)

    def test_different_day_absence_does_not_mark_previous_record_missing(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            first = ingest_boe_summary(
                summary(included_item("BOE-A-2099-5")),
                registry=REGISTRY, store=store, detected_at=NOW, last_checked_at=NOW,
            )
            second = ingest_boe_summary(
                summary(included_item("BOE-A-2099-6")),
                registry=REGISTRY, store=store,
                detected_at=NOW.replace(day=24), last_checked_at=NOW.replace(day=24),
            )
            self.assertEqual([event.type for event in first.events], ["create"])
            self.assertEqual([event.type for event in second.events], ["create"])
            self.assertEqual(len(store.list_source("boe")), 2)
            previous = store.get(first.operations[0].record.id, source_id="boe")
            assert previous is not None
            self.assertEqual(previous.status, RecordStatus.ACTIVE)
            self.assertNotIn("missing_from_source", [event.type for event in second.events])

    def test_no_daily_publication_is_success_without_writes_or_missing(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            created = ingest_boe_summary(
                summary(included_item("BOE-A-2099-7")), registry=REGISTRY,
                store=store, detected_at=NOW, last_checked_at=NOW,
            )
            result = ingest_boe_summary(
                BOEFetchResult(BOEFetchStatus.NO_DAILY_PUBLICATION, 404, reason="daily_summary_not_found"),
                registry=REGISTRY, store=store,
                detected_at=NOW, last_checked_at=NOW,
            )
            self.assertEqual(result.status, BOEIngestionStatus.NO_DAILY_PUBLICATION)
            self.assertEqual(result.metrics.to_dict(), {key: 0 for key in result.metrics.to_dict()})
            self.assertEqual(result.operations, ())
            self.assertEqual(result.events, ())
            self.assertEqual(len(store.list_source("boe")), 1)
            self.assertEqual(store.list_source("boe")[0].id, created.operations[0].record.id)

    def test_source_failure_and_invalid_request_do_not_write(self) -> None:
        for fetch_status, http_status, expected in (
            (BOEFetchStatus.SOURCE_FAILURE, 500, BOEIngestionStatus.SOURCE_FAILURE),
            (BOEFetchStatus.INVALID_REQUEST, 400, BOEIngestionStatus.INVALID_REQUEST),
        ):
            with self.subTest(status=fetch_status), TemporaryDirectory() as directory:
                store = RecordStore(directory)
                result = ingest_boe_summary(
                    BOEFetchResult(fetch_status, http_status, reason="controlled_test_failure"),
                    registry=REGISTRY, store=store,
                    detected_at=NOW, last_checked_at=NOW,
                )
                self.assertEqual(result.status, expected)
                self.assertEqual(result.metrics.to_dict(), {key: 0 for key in result.metrics.to_dict()})
                self.assertEqual(result.operations, ())
                self.assertEqual(store.list_source("boe"), ())
                self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_contract_error_aborts_batch_before_any_write(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            invalid = item("", title="Resolución relativa a Borriana")
            with self.assertRaises(BOEIngestionError) as raised:
                ingest_boe_summary(
                    summary(included_item("BOE-A-2099-8"), invalid),
                    registry=REGISTRY, store=store,
                    detected_at=NOW, last_checked_at=NOW,
                )
            self.assertEqual(store.list_source("boe"), ())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_generated_events_validate_and_no_event_is_persisted(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            result = ingest_boe_summary(
                summary(included_item("BOE-A-2099-9")), registry=REGISTRY,
                store=store, detected_at=NOW, last_checked_at=NOW,
            )
            event_schema = json.loads((ROOT / "schemas" / "event.schema.json").read_text(encoding="utf-8"))
            for event in result.events:
                Draft202012Validator(event_schema, format_checker=FormatChecker()).validate(event.to_dict())
            self.assertFalse((Path(directory) / "events").exists())

    def test_privacy_quarantine_is_per_record_and_safe_record_is_written(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            result = ingest_boe_summary(
                summary(
                    included_item("BOE-A-2099-PRIV-SAFE"),
                    included_item("BOE-A-2099-PRIV-SENSITIVE", "Resolución relativa a Borriana. DNI 12345678Z"),
                ),
                registry=REGISTRY, store=store, detected_at=NOW, last_checked_at=NOW,
            )
            self.assertEqual(result.metrics.privacy_allowed, 1)
            self.assertEqual(result.metrics.privacy_quarantined, 1)
            self.assertEqual(result.metrics.privacy_rejected, 0)
            self.assertEqual(result.metrics.created, 1)
            self.assertEqual(len(store.list_source("boe")), 1)
            self.assertEqual(result.events[0].type, "create")
            result_text = repr(result) + str(result.metrics.to_dict())
            self.assertNotIn("12345678Z", result_text)

    def test_privacy_engine_failure_aborts_before_any_write(self) -> None:
        class FailingGate(PrivacyGate):
            def evaluate(self, record):  # type: ignore[no-untyped-def]
                raise PrivacyGateError("internal failure near DNI 12345678Z")

        with TemporaryDirectory() as directory:
            gate = FailingGate()
            store = RecordStore(directory, privacy_gate=gate)
            with self.assertRaises(BOEIngestionError) as raised:
                ingest_boe_summary(
                    summary(included_item("BOE-A-2099-PRIV-FAIL", "Resolución relativa a Borriana. DNI 12345678Z")),
                    registry=REGISTRY, store=store, detected_at=NOW, last_checked_at=NOW,
                    privacy_gate=gate,
                )
            self.assertNotIn("12345678Z", str(raised.exception))
            self.assertNotIn("12345678Z", repr(raised.exception))
            self.assertTrue(raised.exception.__suppress_context__)
            self.assertEqual(tuple(Path(directory).iterdir()), ())


if __name__ == "__main__":
    unittest.main()
