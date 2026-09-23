"""Pruebas offline de ingesta incremental BOE y RecordStore canónico."""

from __future__ import annotations

from datetime import UTC, date, datetime
from dataclasses import replace
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

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
    ingest_boe_summary as _ingest_boe_summary,
    load_castellon_registry,
)
from infocs.models import RecordStatus
from infocs.events import EventStore
from infocs.privacy import PrivacyGate, PrivacyGateError
from infocs.publication.review import PublicationReviewConfig
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


def ingest_boe_summary(fetched, **kwargs):  # type: ignore[no-untyped-def]
    """Los tests publican sólo mediante una allowlist sintética explícita."""
    config = kwargs.pop("publication_review_config", None)
    if config is None:
        summary_value = fetched if isinstance(fetched, BOESummary) else fetched.summary
        ids = [] if summary_value is None else [
            entry.official_id for entry in summary_value.items
            if re.fullmatch(r"[A-Z0-9]+-[A-Z]-\d{4}-\d+", entry.official_id)
        ]
        config = PublicationReviewConfig.from_mapping({
            "schema_version": "1",
            "source_id": "boe",
            "records": [
                {"official_id": official_id, "decision": "approved", "reason_code": "reviewed_safe"}
                for official_id in ids
            ],
        })
    return _ingest_boe_summary(fetched, publication_review_config=config, **kwargs)


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
                "publication_approved": 1,
                "publication_hold": 0,
                "publication_rejected": 0,
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

    def test_approved_create_update_are_persisted_once_with_record(self) -> None:
        with TemporaryDirectory() as directory:
            record_store = RecordStore(Path(directory) / "records")
            event_store = EventStore(Path(directory) / "events")
            first = ingest_boe_summary(
                summary(included_item("BOE-A-2099-993")), registry=REGISTRY,
                store=record_store, event_store=event_store,
                detected_at=NOW, last_checked_at=NOW,
            )
            self.assertEqual([event.type for event in first.events], ["create"])
            self.assertEqual(len(event_store.list_record(first.operations[0].record.id)), 1)
            replay = ingest_boe_summary(
                summary(included_item("BOE-A-2099-993")), registry=REGISTRY,
                store=record_store, event_store=event_store,
                detected_at=NOW, last_checked_at=NOW,
            )
            self.assertEqual(replay.operations[0].type.value, "no_change")
            self.assertEqual(replay.events, ())
            self.assertEqual(len(event_store.list_record(first.operations[0].record.id)), 1)

            changed = ingest_boe_summary(
                summary(included_item("BOE-A-2099-993", "Resolución actualizada relativa a Borriana")),
                registry=REGISTRY, store=record_store, event_store=event_store,
                detected_at=NOW, last_checked_at=NOW.replace(hour=10),
            )
            self.assertEqual([event.type for event in changed.events], ["update"])
            self.assertIn("title", changed.events[0].changed_fields)
            self.assertEqual(len(event_store.list_record(first.operations[0].record.id)), 2)

    def test_publication_hold_writes_neither_record_nor_event(self) -> None:
        with TemporaryDirectory() as directory:
            item_value = included_item("BOE-A-2099-994")
            hold_config = PublicationReviewConfig.from_mapping({
                "schema_version": "1", "source_id": "boe", "records": [],
            })
            record_store = RecordStore(Path(directory) / "records")
            event_store = EventStore(Path(directory) / "events")
            result = ingest_boe_summary(
                summary(item_value), registry=REGISTRY, store=record_store,
                event_store=event_store, publication_review_config=hold_config,
                detected_at=NOW, last_checked_at=NOW,
            )
            self.assertEqual(result.metrics.publication_hold, 1)
            self.assertEqual(result.events, ())
            self.assertEqual(record_store.list_source("boe"), ())
            self.assertEqual(event_store.list_source("boe"), ())

    def test_publication_rejected_writes_neither_record_nor_event(self) -> None:
        with TemporaryDirectory() as directory:
            item_value = included_item("BOE-A-2099-996")
            rejected_config = PublicationReviewConfig.from_mapping({
                "schema_version": "1", "source_id": "boe", "records": [{
                    "official_id": item_value.official_id,
                    "decision": "rejected",
                    "reason_code": "privacy_quarantine",
                }],
            })
            record_store = RecordStore(Path(directory) / "records")
            event_store = EventStore(Path(directory) / "events")
            result = ingest_boe_summary(
                summary(item_value), registry=REGISTRY, store=record_store,
                event_store=event_store, publication_review_config=rejected_config,
                detected_at=NOW, last_checked_at=NOW,
            )
            self.assertEqual(result.metrics.publication_rejected, 1)
            self.assertEqual(result.events, ())
            self.assertEqual(record_store.list_source("boe"), ())
            self.assertEqual(event_store.list_source("boe"), ())

    def test_event_preflight_conflict_aborts_before_record_write(self) -> None:
        with TemporaryDirectory() as directory:
            a = included_item("BOE-A-2099-995")
            b = included_item("BOE-A-2099-995", "Resolución corregida relativa a Borriana")
            seed_store = RecordStore(Path(directory) / "seed-records")
            ingest_boe_summary(
                summary(a), registry=REGISTRY, store=seed_store,
                detected_at=NOW, last_checked_at=NOW,
            )
            seed = ingest_boe_summary(
                summary(b), registry=REGISTRY, store=seed_store,
                detected_at=NOW, last_checked_at=NOW.replace(hour=10),
            )
            event_store = EventStore(Path(directory) / "events")
            conflicting = replace(seed.events[0], changed_fields=("description",))
            config = PublicationReviewConfig.from_mapping({
                "schema_version": "1", "source_id": "boe", "records": [{
                    "official_id": "BOE-A-2099-995", "decision": "approved", "reason_code": "reviewed_safe",
                }],
            })
            target_store = RecordStore(Path(directory) / "target-records")
            initial = ingest_boe_summary(
                summary(a), registry=REGISTRY, store=target_store,
                detected_at=NOW, last_checked_at=NOW,
            )
            event_store.write(
                conflicting, record=seed.operations[0].record,
                publication_review_config=config,
            )
            with self.assertRaises(BOEIngestionError):
                ingest_boe_summary(
                    summary(b), registry=REGISTRY, store=target_store,
                    event_store=event_store, detected_at=NOW,
                    last_checked_at=NOW.replace(hour=10),
                )
            current = target_store.get(initial.operations[0].record.id, source_id="boe")
            assert current is not None
            self.assertEqual(current.technical.content_hash, initial.operations[0].record.technical.content_hash)

    def test_update_event_first_failure_recovers_record_write_on_retry(self) -> None:
        with TemporaryDirectory() as directory:
            record_store = RecordStore(Path(directory) / "records")
            event_store = EventStore(Path(directory) / "events")
            a = included_item("BOE-A-2099-997", "Estado A relativo a Borriana")
            b = included_item("BOE-A-2099-997", "Estado B relativo a Borriana")
            initial = ingest_boe_summary(
                summary(a), registry=REGISTRY, store=record_store,
                detected_at=NOW, last_checked_at=NOW,
            )
            record_a = initial.operations[0].record
            original_write = record_store.write
            calls = 0

            def fail_first_write(record):  # type: ignore[no-untyped-def]
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("synthetic RecordStore failure")
                return original_write(record)

            with patch.object(record_store, "write", side_effect=fail_first_write):
                with self.assertRaises(OSError):
                    ingest_boe_summary(
                        summary(b), registry=REGISTRY, store=record_store,
                        event_store=event_store, detected_at=NOW,
                        last_checked_at=NOW.replace(hour=10),
                    )
            stored_after_failure = record_store.get(record_a.id, source_id="boe")
            assert stored_after_failure is not None
            self.assertEqual(stored_after_failure.technical.content_hash, record_a.technical.content_hash)
            first_events = event_store.list_record(record_a.id)
            self.assertEqual(len(first_events), 1)
            transition_id = first_events[0].event_id
            first_observed_at = first_events[0].observed_at

            retried = ingest_boe_summary(
                summary(b), registry=REGISTRY, store=record_store,
                event_store=event_store, detected_at=NOW,
                last_checked_at=NOW.replace(hour=11),
            )
            self.assertEqual(retried.operations[0].type.value, "update")
            self.assertEqual(retried.events[0].event_id, transition_id)
            self.assertEqual(len(event_store.list_record(record_a.id)), 1)
            self.assertEqual(event_store.get(transition_id).observed_at, first_observed_at)  # type: ignore[union-attr]
            current = record_store.get(record_a.id, source_id="boe")
            assert current is not None
            self.assertEqual(current.title, b.title)

    def test_legacy_record_first_failure_demonstrates_lost_update_event(self) -> None:
        """Reproduce controladamente el orden anterior Record→Event, no el flujo nuevo."""
        class FailingEventStore(EventStore):
            def write(self, event, **kwargs):  # type: ignore[no-untyped-def]
                raise OSError("synthetic EventStore failure")

        with TemporaryDirectory() as directory:
            record_store = RecordStore(Path(directory) / "records")
            a = included_item("BOE-A-2099-999", "Estado A relativo a Borriana")
            b = included_item("BOE-A-2099-999", "Estado B relativo a Borriana")
            ingest_boe_summary(summary(a), registry=REGISTRY, store=record_store, detected_at=NOW, last_checked_at=NOW)
            # El orquestador 03E escribía el Record antes de entregar el Event al store.
            legacy_result = ingest_boe_summary(
                summary(b), registry=REGISTRY, store=record_store,
                detected_at=NOW, last_checked_at=NOW.replace(hour=10),
            )
            event = legacy_result.events[0]
            record_b = legacy_result.operations[0].record
            config = PublicationReviewConfig.from_mapping({
                "schema_version": "1", "source_id": "boe", "records": [{
                    "official_id": b.official_id, "decision": "approved", "reason_code": "reviewed_safe",
                }],
            })
            with self.assertRaises(OSError):
                FailingEventStore(Path(directory) / "legacy-events").write(
                    event, record=record_b, publication_review_config=config,
                )

            recovered_store = EventStore(Path(directory) / "legacy-events")
            rerun = ingest_boe_summary(
                summary(b), registry=REGISTRY, store=record_store,
                event_store=recovered_store, detected_at=NOW,
                last_checked_at=NOW.replace(hour=11),
            )
            self.assertEqual(rerun.operations[0].type.value, "no_change")
            self.assertEqual(rerun.events, ())
            self.assertEqual(recovered_store.list_source("boe"), ())

    def test_create_event_first_failure_recovers_record_write_on_retry(self) -> None:
        with TemporaryDirectory() as directory:
            record_store = RecordStore(Path(directory) / "records")
            event_store = EventStore(Path(directory) / "events")
            observed = summary(included_item("BOE-A-2099-998"))
            original_write = record_store.write
            calls = 0

            def fail_first_write(record):  # type: ignore[no-untyped-def]
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("synthetic RecordStore failure")
                return original_write(record)

            with patch.object(record_store, "write", side_effect=fail_first_write):
                with self.assertRaises(OSError):
                    ingest_boe_summary(
                        observed, registry=REGISTRY, store=record_store,
                        event_store=event_store, detected_at=NOW,
                        last_checked_at=NOW.replace(hour=10),
                    )
            self.assertEqual(record_store.list_source("boe"), ())
            events_after_failure = event_store.list_source("boe")
            self.assertEqual(len(events_after_failure), 1)
            event_id = events_after_failure[0].event_id

            retried = ingest_boe_summary(
                observed, registry=REGISTRY, store=record_store,
                event_store=event_store, detected_at=NOW,
                last_checked_at=NOW.replace(hour=11),
            )
            self.assertEqual(retried.operations[0].type.value, "create")
            self.assertEqual(len(record_store.list_source("boe")), 1)
            self.assertEqual(len(event_store.list_source("boe")), 1)
            self.assertEqual(event_store.list_source("boe")[0].event_id, event_id)

    def test_privacy_quarantine_is_per_record_and_safe_record_is_written(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            event_store = EventStore(Path(directory) / "events")
            result = ingest_boe_summary(
                summary(
                    included_item("BOE-A-2099-990"),
                    included_item("BOE-A-2099-991", "Resolución relativa a Borriana. DNI 12345678Z"),
                ),
                registry=REGISTRY, store=store, event_store=event_store,
                detected_at=NOW, last_checked_at=NOW,
            )
            self.assertEqual(result.metrics.privacy_allowed, 1)
            self.assertEqual(result.metrics.privacy_quarantined, 1)
            self.assertEqual(result.metrics.privacy_rejected, 0)
            self.assertEqual(result.metrics.created, 1)
            self.assertEqual(len(store.list_source("boe")), 1)
            self.assertEqual(len(event_store.list_source("boe")), 1)
            self.assertEqual(event_store.list_source("boe")[0].record_id, result.operations[0].record.id)
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
                    summary(included_item("BOE-A-2099-992", "Resolución relativa a Borriana. DNI 12345678Z")),
                    registry=REGISTRY, store=store, detected_at=NOW, last_checked_at=NOW,
                    privacy_gate=gate,
                )
            self.assertNotIn("12345678Z", str(raised.exception))
            self.assertNotIn("12345678Z", repr(raised.exception))
            self.assertTrue(raised.exception.__suppress_context__)
            self.assertEqual(tuple(Path(directory).iterdir()), ())


if __name__ == "__main__":
    unittest.main()
