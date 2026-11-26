"""Manual recheck simulations. All writable stores contain synthetic data."""

from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.events import EventStore
from infocs.fetch.bdns.ingest import ingest_bdns, observe_bdns_record
from infocs.fetch.bdns.migration import prepare_baseline_migration, stage_batch, materialize_staged_tree
from infocs.fetch.bdns.models import BDNSFetchResult, BDNSRequestStatus
from infocs.fetch.bdns.recheck import OfflineBDNSTransport, run_offline_recheck
from infocs.fetch.bdns.transport import BDNSTransport
from infocs.privacy import PrivacyDecision, PrivacyDecisionType
from infocs.store import RecordStore
from tests.unit.test_bdns_ingest import fixture_models, STARTED, OBSERVED
from tests.unit.test_bdns_runner import FakeTransport


def success(payload):
    return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=payload)


class FixtureReader:
    def __init__(self, pages, details):
        self.pages = pages
        self.details = details

    def search(self, query):
        return success(self.pages[query.numero_convocatoria])

    def fetch_detail(self, code):
        return success(self.details[code])


class BDNSRecheckTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.records = RecordStore(self.root / "data" / "records")
        self.events = EventStore(self.root / "data" / "events")
        self.codes = ("900001", "900002", "900003")
        self.pages = {}
        self.details = {}
        page, detail = fixture_models()
        for code in self.codes:
            summary = replace(page.items[0], numero_convocatoria=code)
            self.pages[code] = replace(page, items=(summary,), page_number=0, page_size=50,
                offset=0, total_pages=1, total_elements=1, number_of_elements=1,
                first=True, last=True, empty=False)
            self.details[code] = replace(detail, codigo_bdns=code)
            result = ingest_bdns(record_store=self.records, event_store=self.events,
                transport=FakeTransport(self.pages[code], self.details[code]),
                started_at=STARTED, clock=lambda: OBSERVED)
            self.assertEqual(result.status.value, "complete_success")
        batch = prepare_baseline_migration(record_store=self.records,
            transport=FixtureReader(self.pages, self.details),
            migration_id="bdns-v1-v2-11111111-1111-4111-8111-111111111111",
            software_git_sha="a" * 40, clock=lambda: OBSERVED + timedelta(minutes=1))
        self.assertEqual(batch.status, "prepared", batch.safe_reason)
        stage = self.root / "baseline-stage"
        stage_batch(batch.batch, stage)
        materialize_staged_tree(stage, self.records)
        checkpoint = self.root / "data" / "manifests" / "bdns" / "checkpoint.json"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_text('{"synthetic_checkpoint":"unchanged"}', encoding="utf-8")
        self.before = self.snapshot()
        self.when = OBSERVED + timedelta(minutes=2)
        self.network_guard = patch("socket.create_connection", side_effect=AssertionError("network_forbidden"))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in (self.root / "data").rglob("*") if p.is_file()}

    def steps(self, code, detail=None):
        value = self.details[code] if detail is None else detail
        return (("detail", success(value)), ("search", success(self.pages[code])),
            ("search", success(self.pages[code])), ("detail", success(value)))

    def run_batch(self, steps=None, **kwargs):
        scripted = steps if steps is not None else sum((self.steps(code) for code in self.codes), ())
        self.transport = OfflineBDNSTransport(scripted)
        return run_offline_recheck(identifiers=kwargs.pop("identifiers", self.codes),
            workspace=self.workspace, record_store=kwargs.pop("record_store", self.records),
            event_store=kwargs.pop("event_store", self.events), transport=self.transport,
            started_at=STARTED, clock=lambda: self.when, **kwargs)

    def output_records(self, result):
        return RecordStore(result.validated_root / "data" / "records").list_source("bdns")

    def assert_counts(self, result):
        self.assertEqual(result.accepted, result.identical + result.modified)
        self.assertEqual(result.attempted, result.accepted + result.rejected)
        self.assertEqual(result.selected, result.attempted + result.not_attempted)
        self.assertLessEqual(result.requests_used, 16)
        self.assertEqual(self.snapshot(), self.before)

    def test_three_successes_freshness_and_safe_structured_output(self):
        result = self.run_batch()
        self.assertEqual((result.status, result.accepted, result.identical, result.requests_used),
            ("complete", 3, 3, 12))
        self.assertEqual([item.position for item in result.items], [1, 2, 3])
        old = self.records.list_source("bdns")
        for before, after in zip(old, self.output_records(result)):
            self.assertEqual(after, replace(before, dates=replace(before.dates, last_checked_at=self.when)))
        self.assertEqual(EventStore(result.validated_root / "data" / "events").list_source("bdns"),
            self.events.list_source("bdns"))
        safe = json.dumps(result.to_dict())
        for code in self.codes:
            self.assertNotIn(code, safe)
        self.assertNotIn(str(self.root), safe)
        self.assertFalse((result.validated_root / "data" / "manifests").exists())
        self.assertFalse((result.validated_root / "data" / "health").exists())
        self.assert_counts(result)

    def test_rectification_and_repetition_preserve_single_update(self):
        changed = replace(self.details[self.codes[1]], application_end_date=date(2027, 2, 1))
        steps = self.steps(self.codes[0]) + self.steps(self.codes[1], changed) + self.steps(self.codes[2])
        first = self.run_batch(steps)
        self.assertEqual((first.modified, first.identical), (1, 2))
        records = RecordStore(first.validated_root / "data" / "records")
        events = EventStore(first.validated_root / "data" / "events")
        updates = [e for e in events.list_source("bdns") if e.type == "update"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].changed_fields, ("source_data.bdns.application.end_date",))
        second = self.run_batch(steps, record_store=records, event_store=events)
        self.assertEqual((second.modified, second.identical), (0, 3))
        self.assertEqual(EventStore(second.validated_root / "data" / "events").list_source("bdns"),
            events.list_source("bdns"))
        self.assert_counts(first)
        self.assert_counts(second)

    def test_second_failure_stops_third_and_preserves_both(self):
        steps = self.steps(self.codes[0]) + (("detail", BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, 500)),)
        result = self.run_batch(steps)
        self.assertEqual((result.status, result.accepted, result.rejected, result.not_attempted, result.requests_used),
            ("partial", 1, 1, 1, 5))
        output = self.output_records(result)
        self.assertEqual(output[1:], self.records.list_source("bdns")[1:])
        self.assert_counts(result)
        # A fresh invocation can recover from the coherent partial candidate.
        recovered = self.run_batch(record_store=RecordStore(result.validated_root / "data" / "records"),
            event_store=EventStore(result.validated_root / "data" / "events"))
        self.assertEqual(recovered.status, "complete")
        self.assert_counts(recovered)

    def test_partial_response_is_rejected_without_freshness_or_events(self):
        detail = replace(self.details[self.codes[0]], documents=())
        result = self.run_batch(self.steps(self.codes[0], detail))
        self.assertEqual((result.status, result.reason, result.rejected, result.not_attempted),
            ("failed", "incomplete_response", 1, 2))
        self.assertIsNone(result.validated_root)
        self.assert_counts(result)

    def test_budget_limits_include_control_reads_and_never_overrun(self):
        for limit, counts in ((1, (1, 0, 1, 2)), (4, (1, 1, 0, 2)), (5, (2, 1, 1, 1)), (12, (3, 3, 0, 0))):
            with self.subTest(limit=limit):
                result = self.run_batch(max_requests=limit)
                self.assertEqual((result.attempted, result.accepted, result.rejected, result.not_attempted), counts)
                self.assertEqual(result.requests_used, limit)
                self.assert_counts(result)

    def test_wrong_response_identity_and_429_stop_without_retry(self):
        cases = (("identity", success(replace(self.details[self.codes[0]], codigo_bdns="999999"))),
            ("rate_limited", BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, 429)))
        for label, response in cases:
            with self.subTest(label=label):
                result = self.run_batch((("detail", response),))
                self.assertEqual((result.accepted, result.rejected, result.not_attempted, result.requests_used), (0, 1, 2, 1))
                self.assertIsNone(result.validated_root)
                if label == "rate_limited":
                    self.assertEqual(result.reason, label)
                self.assert_counts(result)

    def test_preflight_duplicates_missing_limits_and_live_transport(self):
        for identifiers in (("900001", "900001"), ("999999",), ("900001",) * 4):
            with self.subTest(identifiers=identifiers):
                result = self.run_batch(identifiers=identifiers)
                self.assertEqual((result.status, result.attempted, result.requests_used), ("blocked", 0, 0))
        for args in ({"max_records": 4}, {"max_requests": 17}, {"max_requests": True}):
            self.assertEqual(self.run_batch(**args).status, "blocked")
        result = run_offline_recheck(identifiers=self.codes, workspace=self.workspace,
            record_store=self.records, event_store=self.events, transport=BDNSTransport(),
            started_at=STARTED, clock=lambda: self.when)
        self.assertEqual((result.status, result.requests_used), ("blocked", 0))
        self.assertEqual(self.snapshot(), self.before)

    def test_non_temporary_store_and_incompatible_normalizer_rejected_before_read(self):
        result = self.run_batch(record_store=RecordStore(ROOT / "data" / "records"))
        self.assertEqual((result.status, result.requests_used), ("blocked", 0))
        old = self.records.list_source("bdns")[0]
        self.records.write(replace(old, provenance=replace(old.provenance, normalizer_version="9.0.0")))
        changed_input = self.snapshot()
        result = self.run_batch()
        self.assertEqual((result.status, result.requests_used), ("blocked", 0))
        self.assertEqual(self.snapshot(), changed_input)

    def test_privacy_rejection_does_not_expose_candidate(self):
        from infocs.privacy import PrivacyGate
        class RejectGate(PrivacyGate):
            def evaluate(self, record):
                if record.title == "Candidato sintético rechazado":
                    return PrivacyDecision(PrivacyDecisionType.REJECT, record.id)
                return super().evaluate(record)
        detail = replace(self.details[self.codes[0]], title="Candidato sintético rechazado")
        result = self.run_batch(self.steps(self.codes[0], detail), privacy_gate=RejectGate.default())
        self.assertEqual((result.status, result.accepted, result.rejected, result.not_attempted), ("failed", 0, 1, 2))
        self.assertIsNone(result.validated_root)
        self.assert_counts(result)

    def test_concurrent_batch_is_rejected_by_lock(self):
        nested = []
        def observe(**kwargs):
            nested.append(self.run_batch())
            return observe_bdns_record(**kwargs)
        with patch("infocs.fetch.bdns.recheck.observe_bdns_record", side_effect=observe):
            result = self.run_batch()
        self.assertEqual(result.status, "complete")
        self.assertTrue(all(r.reason == "batch_busy" and r.requests_used == 0 for r in nested))
        self.assert_counts(result)

    def test_writer_ignoring_lock_invalidates_output(self):
        def observe(**kwargs):
            result = observe_bdns_record(**kwargs)
            old = self.records.list_source("bdns")[0]
            self.records.write(replace(old, dates=replace(old.dates, last_checked_at=self.when)))
            return result
        with patch("infocs.fetch.bdns.recheck.observe_bdns_record", side_effect=observe):
            result = self.run_batch()
        self.assertEqual((result.status, result.reason), ("blocked", "input_changed"))
        self.assertIsNone(result.validated_root)

    def test_terminal_event_record_failure_has_no_validated_output_and_retry_recovers(self):
        changed = replace(self.details[self.codes[1]], application_end_date=date(2027, 2, 1))
        steps = self.steps(self.codes[0]) + self.steps(self.codes[1], changed) + self.steps(self.codes[2])
        original_write = RecordStore.write
        def fail_update(store, record):
            if record.source.official_id == self.codes[1]:
                raise OSError("synthetic persistence fault with private text")
            return original_write(store, record)
        with patch.object(RecordStore, "write", new=fail_update):
            result = self.run_batch(steps)
        self.assertEqual((result.status, result.accepted, result.rejected, result.not_attempted), ("blocked", 1, 1, 1))
        self.assertEqual(result.reason, "candidate_validation_failed")
        self.assertIsNone(result.validated_root)
        self.assertNotIn("private text", json.dumps(result.to_dict()))
        self.assert_counts(result)
        recovered = self.run_batch(steps)
        self.assertEqual((recovered.status, recovered.modified), ("complete", 1))
        updates = [e for e in EventStore(recovered.validated_root / "data" / "events").list_source("bdns") if e.type == "update"]
        self.assertEqual(len(updates), 1)
        self.assert_counts(recovered)


if __name__ == "__main__":
    unittest.main()
