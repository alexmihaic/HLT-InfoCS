"""Pruebas offline de ingestión BDNS con stores temporales."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bdns.ingest import (  # noqa: E402
    BDNSEventStatus,
    BDNSIngestionStatus,
    BDNSRecordOperation,
    ingest_bdns,
)
from infocs.fetch.bdns.models import BDNSFetchResult, BDNSRequestStatus  # noqa: E402
from infocs.fetch.bdns.parser import parse_bdns_detail, parse_bdns_search  # noqa: E402
from infocs.models import Record, SourceReference  # noqa: E402
from infocs.privacy import PrivacyDecision, PrivacyDecisionType, PrivacyGate  # noqa: E402
from infocs.store import RecordStore  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures" / "bdns"
STARTED = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
OBSERVED = datetime(2026, 9, 27, 10, 0, 2, tzinfo=UTC)
ATTRIBUTION = ROOT / "data" / "records" / "bdns" / "README.md"


def fixture_models(*, title: str | None = None):
    search_payload = json.loads((FIXTURES / "search_success.json").read_text(encoding="utf-8"))
    detail_payload = json.loads(
        (FIXTURES / "detail_success.json").read_text(encoding="utf-8"), parse_float=Decimal
    )
    detail_payload["regiones"] = [{"descripcion": "ES522 - Castellón / Castelló"}]
    if title is not None:
        detail_payload["descripcion"] = title
    return parse_bdns_search(search_payload), parse_bdns_detail(detail_payload)


class FakeTransport:
    def __init__(self, page, details):
        self.page = page
        self.details = list(details)
        self.search_queries = []
        self.detail_codes = []

    def search(self, query):
        self.search_queries.append(query)
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=self.page)

    def fetch_detail(self, numero_convocatoria):
        self.detail_codes.append(numero_convocatoria)
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=self.details.pop(0))


class FixedGate:
    def __init__(self, decision: PrivacyDecision):
        self.decision = decision

    def evaluate(self, record):
        return PrivacyDecision(self.decision.decision, self.decision.record_id)


class BDNSIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = RecordStore(self.root / "records", privacy_gate=PrivacyGate.default())
        self.attribution = self.root / "DATASET.md"
        self.attribution.write_text(ATTRIBUTION.read_text(encoding="utf-8"), encoding="utf-8")

    def run_ingest(self, transport, *, gate=None, attribution_path=None, **kwargs):
        return ingest_bdns(
            record_store=self.store,
            started_at=STARTED,
            transport=transport,
            privacy_gate=gate or PrivacyGate.default(),
            clock=lambda: OBSERVED,
            attribution_path=attribution_path or self.attribution,
            **kwargs,
        )

    def test_publicable_first_observation_writes_one_record_and_defers_event(self) -> None:
        page, detail = fixture_models()
        summaries = tuple(
            replace(page.items[0], numero_convocatoria=f"90000{index}")
            for index in range(1, 4)
        )
        page = replace(page, items=summaries)
        details = tuple(replace(detail, codigo_bdns=summary.numero_convocatoria) for summary in summaries)
        transport = FakeTransport(page, details)
        with (
            patch.object(self.store, "write", wraps=self.store.write) as record_write,
            patch("infocs.events.EventStore.preflight") as event_preflight,
            patch("infocs.events.EventStore.write") as event_write,
            patch("infocs.publication.review.review_publication") as boe_review,
            patch("infocs.fetch.boe.review_queue.BOEReviewQueueStore.update") as queue_update,
        ):
            result = self.run_ingest(transport)

        self.assertEqual(result.status, BDNSIngestionStatus.COMPLETE_SUCCESS)
        self.assertEqual(result.operation, BDNSRecordOperation.CREATE)
        self.assertEqual(result.event_status, BDNSEventStatus.DEFERRED)
        self.assertEqual(result.safe_reason, "BDNS_CREATE_EVENT_DEFERRED")
        self.assertEqual(result.request_count, 2)
        self.assertEqual(result.metrics.search_seen, 3)
        self.assertEqual(result.metrics.records_created, 1)
        self.assertEqual(result.metrics.events_created, 0)
        self.assertEqual(result.metrics.metadata_publishable, 1)
        self.assertTrue(result.record_path.is_file())
        self.assertEqual(transport.detail_codes, [summaries[0].numero_convocatoria])
        safe_report = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn(summaries[0].numero_convocatoria, safe_report)
        self.assertEqual(
            result.to_dict()["record_path"],
            "data/records/bdns/r-<encoded-record-id>.json",
        )
        self.assertEqual(Record.from_json(result.record_path.read_bytes()).technical.content_hash, result.content_hash)
        record_write.assert_called_once()
        for forbidden_path in (event_preflight, event_write, boe_review, queue_update):
            forbidden_path.assert_not_called()

    def test_identical_second_ingestion_is_no_change_without_new_event(self) -> None:
        page, detail = fixture_models()
        self.run_ingest(FakeTransport(page, (detail,)))
        with patch.object(self.store, "write", wraps=self.store.write) as record_write:
            second = self.run_ingest(FakeTransport(page, (detail,)))
        self.assertEqual(second.operation, BDNSRecordOperation.NO_CHANGE)
        self.assertEqual(second.metrics.records_unchanged, 1)
        self.assertEqual(second.metrics.events_created, 0)
        self.assertEqual(second.event_status, BDNSEventStatus.NOT_REQUIRED)
        self.assertIsNone(second.safe_reason)
        record_write.assert_not_called()

    def test_administrative_change_updates_record_and_defers_update_event(self) -> None:
        page, first = fixture_models()
        _, changed = fixture_models(title="Convocatoria sintética actualizada")
        created = self.run_ingest(FakeTransport(page, (first,)))
        updated = self.run_ingest(FakeTransport(page, (changed,)))
        self.assertEqual(created.content_hash != updated.content_hash, True)
        self.assertEqual(updated.operation, BDNSRecordOperation.UPDATE)
        self.assertEqual(updated.metrics.records_updated, 1)
        self.assertEqual(updated.metrics.events_created, 0)
        self.assertEqual(updated.event_status, BDNSEventStatus.DEFERRED)
        self.assertEqual(updated.safe_reason, "BDNS_UPDATE_EVENT_DEFERRED")

    def test_privacy_quarantine_and_reject_never_reach_record_store(self) -> None:
        page, detail = fixture_models(title="DNI sintético 12345678Z")
        quarantine = self.run_ingest(FakeTransport(page, (detail,)))
        self.assertEqual(quarantine.metrics.privacy_quarantine, 1)
        self.assertEqual(quarantine.metrics.records_created, 0)

        page, detail = fixture_models()
        _, parsed = fixture_models()
        # Replace the placeholder with the final source record id using a tiny gate.
        from infocs.finalize import finalize_record
        from infocs.fetch.bdns.normalize import normalize_bdns_detail

        candidate = normalize_bdns_detail(
            page.items[0], parsed, detected_at=STARTED, last_checked_at=OBSERVED
        ).candidate
        record_id = finalize_record(candidate).id
        rejected_gate = FixedGate(PrivacyDecision(PrivacyDecisionType.REJECT, record_id))
        rejected = self.run_ingest(FakeTransport(page, (detail,)), gate=rejected_gate)
        self.assertEqual(rejected.metrics.privacy_reject, 1)
        self.assertEqual(rejected.metrics.records_created, 0)
        self.assertEqual(self.store.list_source("bdns"), ())

    def test_wrong_privacy_identity_and_metadata_hold_never_write(self) -> None:
        page, detail = fixture_models()
        wrong_identity_gate = FixedGate(PrivacyDecision(PrivacyDecisionType.ALLOW, "not-the-record"))
        wrong = self.run_ingest(FakeTransport(page, (detail,)), gate=wrong_identity_gate)
        self.assertEqual(wrong.metrics.records_created, 0)
        self.assertEqual(wrong.metrics.errors, 1)

        from infocs.fetch.bdns.publication import (
            BDNSMetadataPublicationDecision,
            BDNSMetadataPublicationDecisionType,
            BDNSPublicationEvaluation,
            bdns_source_publication_eligibility,
        )
        def hold(record, privacy):
            return BDNSPublicationEvaluation(
                privacy,
                bdns_source_publication_eligibility(),
                BDNSMetadataPublicationDecision(
                    BDNSMetadataPublicationDecisionType.HOLD,
                    "metadata_scope_not_publishable",
                ),
            )

        with patch("infocs.fetch.bdns.ingest.evaluate_bdns_publication", side_effect=hold):
            held = self.run_ingest(FakeTransport(page, (detail,)))
        self.assertEqual(held.metrics.metadata_hold, 1)
        self.assertEqual(held.metrics.records_created, 0)
        self.assertEqual(self.store.list_source("bdns"), ())

    def test_wrong_source_is_rejected_before_record_store(self) -> None:
        page, detail = fixture_models()
        from infocs.fetch.bdns.normalize import normalize_bdns_detail

        original = normalize_bdns_detail

        def wrong_source(*args, **kwargs):
            result = original(*args, **kwargs)
            candidate = replace(
                result.candidate,
                source=SourceReference(id="boe", official_id="BOE-A-2026-99999"),
            )
            return replace(result, candidate=candidate)

        with (
            patch("infocs.fetch.bdns.ingest.normalize_bdns_detail", side_effect=wrong_source),
            patch.object(self.store, "write") as record_write,
        ):
            result = self.run_ingest(FakeTransport(page, (detail,)))
        self.assertEqual(result.metrics.records_created, 0)
        self.assertEqual(result.metrics.errors, 1)
        record_write.assert_not_called()

    def test_attribution_preflight_blocks_write(self) -> None:
        page, detail = fixture_models()
        missing = self.root / "missing.md"
        result = self.run_ingest(FakeTransport(page, (detail,)), attribution_path=missing)
        self.assertEqual(result.status, BDNSIngestionStatus.PERSISTENCE_BLOCKED)
        self.assertEqual(result.safe_reason, "attribution_preflight_failed")
        self.assertEqual(result.metrics.records_created, 0)
        self.assertEqual(self.store.list_source("bdns"), ())

    def test_one_record_limit_is_enforced_and_region_filter_is_fixed(self) -> None:
        page, detail = fixture_models()
        with self.assertRaises(ValueError):
            self.run_ingest(FakeTransport(page, (detail,)), max_persisted_records=2)
        transport = FakeTransport(page, (detail,))
        self.run_ingest(transport)
        self.assertEqual(transport.search_queries[0].region_ids, (56,))
        self.assertLessEqual(transport.search_queries[0].page_size, 3)


if __name__ == "__main__":
    unittest.main()
