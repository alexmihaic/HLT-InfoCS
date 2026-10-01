"""Tooling D1 offline: fixtures y filesystem temporal; ninguna fuente real."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import Draft202012Validator
from infocs.events import EventStore
from infocs.fetch.bdns.baseline import (
    BDNSBaselineError, BDNSBaselineTransition, BDNSCutover, canonical, evidence_filename,
    inventory_records, migration_directory, productive_hash_version,
)
from infocs.fetch.bdns.migration import (
    BDNSMigrationBatch, materialize_staged_tree, prepare_baseline_migration,
    stage_batch, validate_batch, validate_migration_entries, validate_staged_tree,
)
from infocs.fetch.bdns.models import BDNSCodeLabel
from infocs.fetch.bdns.runner import run_bdns_productive_collection
from infocs.finalize import finalize_record
from infocs.manifests import ManifestStore
from infocs.models import Record
from infocs.store import RecordStore
from tests.unit.test_bdns_enrichment_gates import enriched_candidate
from tests.unit.test_bdns_normalize import normalized
from tests.unit.test_bdns_runner import FakeTransport, fixture_models

STAMP = datetime(2026, 10, 1, 12, tzinfo=UTC)
MIGRATION_ID = "bdns-v1-v2-11111111-1111-4111-8111-111111111111"
SHA = "a" * 40


class BDNSMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = RecordStore(self.root / "data" / "records")
        self.old = finalize_record(normalized().candidate)
        self.store.write(self.old)
        page, self.detail = fixture_models()
        self.page = replace(page, items=(page.items[0],), page_number=0, page_size=50, offset=0,
            total_pages=1, total_elements=1, number_of_elements=1, first=True, last=True, empty=False)
        self.client = FakeTransport(self.page, self.detail)
        self.stage = self.root / "staging"

    def prepare(self, **changes):
        return prepare_baseline_migration(record_store=self.store, transport=changes.pop("transport", self.client),
            migration_id=MIGRATION_ID, software_git_sha=SHA, clock=lambda: STAMP, **changes)

    def install(self):
        result = self.prepare()
        self.assertEqual(result.status, "prepared", result.safe_reason)
        stage_batch(result.batch, self.stage)
        materialize_staged_tree(self.stage, self.store)
        return result.batch

    def runner(self, client=None):
        stamp = STAMP + timedelta(minutes=10)
        events = EventStore(self.root / "data" / "events")
        return run_bdns_productive_collection(mode="complete_scope", from_date=date(2026, 9, 1), through_date=date(2026, 9, 29),
            started_at=stamp, run_id="run-v1-" + str(uuid.uuid4()), clock=lambda: stamp + timedelta(seconds=10),
            transport=client or self.client, record_store=self.store, event_store=events,
            manifest_store=ManifestStore(self.root / "data" / "manifests"), health_path=self.root / "data" / "health" / "bdns.json")

    def test_inventory_v1_all_and_read_only(self):
        records = inventory_records(self.store)
        self.assertEqual(records, (self.old,))
        self.assertEqual(productive_hash_version(self.store), 1)

    def test_inventory_noncanonical_path_and_invalid_hash_fail(self):
        path = self.store.path_for("bdns", self.old.id)
        raw = path.read_text(encoding="utf-8")
        extra = path.parent / "unexpected.json"
        extra.write_text(raw, encoding="utf-8")
        self.assertEqual(self.prepare().safe_reason, "migration_invalid_inventory")
        extra.unlink()
        payload = self.old.to_dict()
        payload["technical"]["content_hash"] = "0" * 64
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.prepare().safe_reason, "migration_invalid_inventory")

    def test_v2_without_marker_fails_before_source(self):
        self.store.write(finalize_record(enriched_candidate()))
        result = self.prepare()
        self.assertEqual(result.safe_reason, "migration_mixed_hash_versions")
        self.assertEqual(self.client.search_queries, [])
        self.assertEqual(self.client.detail_codes, [])

    def test_fresh_v1_reconstruction_and_counts_all_match(self):
        result = self.prepare()
        self.assertEqual(result.status, "prepared", result.safe_reason)
        for key in ("inventory_count", "fresh_detail_count", "summary_resolved_count", "v1_match_count",
                    "v2_prepared_count", "privacy_allowed_count", "publication_approved_count", "authorization_count", "evidence_count"):
            self.assertEqual(result.to_dict()[key], 1)
        self.assertEqual(result.request_count, 4)
        self.assertEqual(self.client.search_queries[0].numero_convocatoria, self.old.source.official_id)
        self.assertIsNone(self.client.search_queries[0].date_from)
        self.assertEqual(self.store.get(self.old.id, "bdns"), self.old)

    def test_fresh_v1_drift_aborts_all_no_baseline(self):
        result = self.prepare(transport=FakeTransport(self.page, replace(self.detail, title="Cambio oficial sintético")))
        self.assertEqual(result.safe_reason, "migration_v1_source_drift")
        self.assertIsNone(result.batch)
        self.assertEqual(self.store.get(self.old.id, "bdns"), self.old)

    def test_identity_detection_and_observation_timestamp_preserved(self):
        new = self.prepare().batch.prepared[0]
        self.assertEqual(new.id, self.old.id)
        self.assertEqual(new.source, self.old.source)
        self.assertEqual(new.dates.detected_at, self.old.dates.detected_at)
        self.assertEqual(new.dates.last_checked_at, STAMP)
        self.assertEqual(new.technical.content_hash_version, 2)

    def test_missing_summary_cannot_reuse_stored_authority(self):
        page = replace(self.page, items=(replace(self.page.items[0], numero_convocatoria="900002"),))
        result = self.prepare(transport=FakeTransport(page, self.detail))
        self.assertEqual(result.safe_reason, "migration_summary_not_resolved")

    def test_summary_control_and_detail_control_detect_changes(self):
        outer = self
        class Drift(FakeTransport):
            def search(inner, query):
                result = super().search(query)
                if len(inner.search_queries) == 2:
                    return replace(result, payload=replace(outer.page, items=(replace(outer.page.items[0], codigo_invente="CHANGED"),)))
                return result
        self.assertEqual(self.prepare(transport=Drift(self.page, self.detail)).safe_reason, "migration_summary_not_resolved")
        class DetailDrift(FakeTransport):
            def fetch_detail(inner, code):
                result = super().fetch_detail(code)
                return replace(result, payload=replace(outer.detail, purpose="Estado posterior")) if len(inner.detail_codes) == 2 else result
        self.assertEqual(self.prepare(transport=DetailDrift(self.page, self.detail)).safe_reason, "migration_detail_failure")

    def test_extra_search_ids_never_create_extra_records(self):
        page = replace(self.page, items=self.page.items + (replace(self.page.items[0], numero_convocatoria="900002"),),
            total_elements=2, number_of_elements=2)
        result = self.prepare(transport=FakeTransport(page, self.detail))
        self.assertEqual(result.status, "prepared", result.safe_reason)
        self.assertEqual(len(result.batch.prepared), 1)

    def test_privacy_failure_aborts_batch(self):
        detail = replace(self.detail, purpose="Identificador personal 12345678Z")
        result = self.prepare(transport=FakeTransport(self.page, detail))
        self.assertEqual(result.safe_reason, "migration_privacy_blocked")
        self.assertIsNone(result.batch)

    def test_publication_hold_aborts_batch(self):
        from infocs.fetch.bdns.publication import BDNSMetadataPublicationDecision, BDNSMetadataPublicationDecisionType
        from infocs.fetch.bdns.enrichment import prepare_bdns_enriched_record
        original = prepare_bdns_enriched_record
        def hold(*args, **kwargs):
            result = original(*args, **kwargs)
            decision = BDNSMetadataPublicationDecision(BDNSMetadataPublicationDecisionType.HOLD, "publication_source_data_hold")
            return replace(result, authorization=None, safe_reason="publication_source_data_hold",
                publication=replace(result.publication, metadata_publication=decision))
        with patch("infocs.fetch.bdns.migration.prepare_bdns_enriched_record", side_effect=hold):
            result = self.prepare()
        self.assertEqual(result.safe_reason, "migration_publication_blocked")

    def test_enrichment_failure_aborts_batch(self):
        result = self.prepare(transport=FakeTransport(self.page, replace(self.detail, sectors=(BDNSCodeLabel("A", None),))))
        self.assertEqual(result.safe_reason, "migration_enrichment_blocked")

    def test_evidence_schema_roundtrip_and_binding(self):
        batch = self.prepare().batch
        item = batch.evidences[0]
        self.assertEqual(item.record_id, self.old.id)
        self.assertEqual(item.from_content_hash, self.old.technical.content_hash)
        self.assertEqual(item.to_content_hash, batch.prepared[0].technical.content_hash)
        self.assertEqual(BDNSBaselineTransition.from_dict(item.to_dict()), item)
        self.assertEqual(BDNSCutover.from_dict(batch.marker.to_dict()), batch.marker)
        with self.assertRaises(BDNSBaselineError):
            validate_batch(replace(batch, evidences=(replace(item, to_content_hash="0" * 64),)), self.store)

    def test_duplicate_evidence_and_incomplete_batch_fail(self):
        batch = self.prepare().batch
        for changed in (replace(batch, evidences=batch.evidences * 2), replace(batch, prepared=())):
            with self.subTest(count=len(changed.evidences)), self.assertRaises(BDNSBaselineError):
                validate_batch(changed, self.store)

    def test_evidence_without_v2_or_without_marker_fails(self):
        batch = self.install()
        self.store.write(self.old)
        with self.assertRaisesRegex(BDNSBaselineError, "migration_mixed_hash_versions"):
            productive_hash_version(self.store)
        (migration_directory(self.store) / "CUTOVER.json").unlink()
        self.assertEqual(self.prepare().safe_reason, "migration_evidence_conflict")

    def test_v2_without_evidence_fails(self):
        batch = self.install()
        (migration_directory(self.store) / evidence_filename(self.old.id)).unlink()
        self.assertEqual(self.prepare().safe_reason, "migration_evidence_conflict")

    def test_rerun_already_migrated_no_source_calls(self):
        self.install()
        self.client.search_queries.clear()
        self.client.detail_codes.clear()
        result = self.prepare()
        self.assertEqual(result.status, "already_migrated")
        self.assertEqual(result.request_count, 0)
        self.assertEqual(self.client.detail_codes, [])
        self.assertEqual(materialize_staged_tree(self.stage, self.store), "already_migrated")

    def test_no_eventstore_access_any_migration_phase(self):
        with patch.object(EventStore, "__init__", side_effect=AssertionError("migration must not touch Events")), \
             patch.object(EventStore, "write", side_effect=AssertionError("no Event write")), \
             patch.object(EventStore, "list_record", side_effect=AssertionError("no Event read")):
            self.install()
        self.assertFalse(self.root.joinpath("data/events").exists())

    def test_prepare_never_materializes_and_stage_rejects_conflicts(self):
        batch = self.prepare().batch
        stage_batch(batch, self.stage)
        self.assertEqual(self.store.get(self.old.id, "bdns"), self.old)
        with self.assertRaises(BDNSBaselineError):
            stage_batch(batch, self.stage)
        with self.assertRaises(BDNSBaselineError):
            stage_batch(batch, ROOT / "data")

    def test_materialization_rejects_changed_inventory_snapshot(self):
        batch = self.prepare().batch
        stage_batch(batch, self.stage)
        self.store.write(replace(self.old, dates=replace(self.old.dates, last_checked_at=STAMP)))
        with self.assertRaises(BDNSBaselineError):
            materialize_staged_tree(self.stage, self.store)
        self.assertFalse(migration_directory(self.store).exists())

    def test_budget_exhaustion_no_partial_cutover(self):
        times = iter((0, 601))
        result = self.prepare(monotonic=lambda: next(times))
        self.assertEqual(result.safe_reason, "migration_budget_exhausted")
        self.assertIsNone(result.batch)
        self.assertEqual(result.request_count, 0)

    def test_two_record_batch_failure_does_not_return_partial_preparation(self):
        from infocs.fetch.bdns.normalize import normalize_bdns_detail
        summary = replace(self.page.items[0], numero_convocatoria="900002")
        detail = replace(self.detail, codigo_bdns="900002")
        second = finalize_record(normalize_bdns_detail(summary, detail,
            detected_at=self.old.dates.detected_at, last_checked_at=self.old.dates.last_checked_at).candidate)
        self.store.write(second)
        outer = self
        class Pair(FakeTransport):
            def search(inner, query):
                inner.search_queries.append(query)
                page = replace(outer.page, items=(replace(outer.page.items[0], numero_convocatoria=query.numero_convocatoria),))
                from infocs.fetch.bdns.models import BDNSFetchResult, BDNSRequestStatus
                return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=page)
            def fetch_detail(inner, code):
                inner.detail_codes.append(code)
                from infocs.fetch.bdns.models import BDNSFetchResult, BDNSRequestStatus
                detail = replace(outer.detail, codigo_bdns=code, purpose="12345678Z" if code == "900002" else outer.detail.purpose)
                return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=detail)
        result = self.prepare(transport=Pair(self.page, self.detail))
        self.assertEqual(result.inventory_count, 2)
        self.assertEqual(result.v1_match_count, 2)
        self.assertEqual(result.safe_reason, "migration_privacy_blocked")
        self.assertIsNone(result.batch)
        self.assertEqual(len(inventory_records(self.store)), 2)
        self.assertTrue(all(r.technical.content_hash_version == 1 for r in inventory_records(self.store)))

    def test_marker_absent_runner_still_v1(self):
        result = self.runner()
        self.assertEqual(result.status, "complete_success")
        self.assertEqual(self.store.get(self.old.id, "bdns").technical.content_hash_version, 1)

    def test_invalid_marker_runner_stops_before_network(self):
        self.install()
        (migration_directory(self.store) / "CUTOVER.json").write_text("{}", encoding="utf-8")
        self.client.search_queries.clear()
        self.client.detail_codes.clear()
        result = self.runner()
        self.assertEqual(result.request_count, 0)
        self.assertEqual(self.client.search_queries, [])

    def test_marker_with_remaining_v1_runner_stops_before_network(self):
        self.install()
        self.store.write(self.old)
        self.client.search_queries.clear()
        result = self.runner()
        self.assertEqual(result.request_count, 0)
        self.assertEqual(self.client.search_queries, [])

    def test_v2_runner_unchanged_no_event(self):
        self.install()
        result = self.runner()
        self.assertEqual(result.status, "complete_success", result.error_code)
        self.assertEqual(result.metrics.unchanged, 1)
        self.assertEqual(EventStore(self.root / "data/events").list_source("bdns"), ())

    def test_v2_runner_update_event_and_next_preflight_continuity(self):
        batch = self.install()
        client = FakeTransport(self.page, replace(self.detail, purpose="Finalidad oficial modificada"))
        result = self.runner(client)
        self.assertEqual(result.status, "complete_success", result.error_code)
        self.assertEqual(result.metrics.updated, 1)
        events = EventStore(self.root / "data/events")
        event = events.list_source("bdns")[0]
        self.assertEqual(event.type, "update")
        self.assertEqual(event.previous_content_hash, batch.prepared[0].technical.content_hash)
        self.assertEqual(productive_hash_version(self.store, events), 2)
        self.assertEqual(self.store.get(self.old.id, "bdns").dates.detected_at, self.old.dates.detected_at)

    def test_v2_runner_create_new_record_no_transition_evidence(self):
        self.install()
        page = replace(self.page, items=(replace(self.page.items[0], numero_convocatoria="900002"),))
        result = self.runner(FakeTransport(page, replace(self.detail, codigo_bdns="900002")))
        self.assertEqual(result.status, "complete_success", result.error_code)
        self.assertEqual(result.metrics.created, 1)
        events = EventStore(self.root / "data/events")
        self.assertEqual(events.list_source("bdns")[0].type, "create")
        self.assertEqual(len(inventory_records(self.store)), 2)
        self.assertEqual(productive_hash_version(self.store, events), 2)

    def test_structured_result_contains_only_safe_control_metadata(self):
        text = json.dumps(self.prepare().to_dict())
        for forbidden in (self.detail.title, self.detail.purpose, self.detail.electronic_office, self.old.id, self.old.source.official_id):
            self.assertNotIn(forbidden, text)

    def test_exact_git_whitelist_no_events_no_deletions(self):
        batch = self.install()
        root = self.store.root.parent.parent
        entries = [("M", self.store.path_for("bdns", self.old.id).relative_to(root).as_posix()),
            ("A", (migration_directory(self.store) / evidence_filename(self.old.id)).relative_to(root).as_posix()),
            ("A", (migration_directory(self.store) / "CUTOVER.json").relative_to(root).as_posix())]
        self.assertEqual(len(validate_migration_entries(entries, self.store)), 3)
        for extra in (("A", "data/events/bdns/extra.json"), ("D", entries[0][1])):
            with self.assertRaises(BDNSBaselineError):
                validate_migration_entries(entries + [extra], self.store)

    def test_workflow_concurrency_manual_only_and_schemas(self):
        # Guardas de regresión del YAML conocido, sin añadir un parser al runtime.
        # La validación completa de sintaxis se realiza aparte antes de publicar.
        migration = (ROOT / ".github/workflows/bdns-v1-v2-migration.yml").read_text(encoding="utf-8")
        collector = (ROOT / ".github/workflows/bdns-manual.yml").read_text(encoding="utf-8")
        self.assertRegex(migration, r"(?m)^on:\n  workflow_dispatch:\n\n")
        self.assertNotRegex(migration, r"(?m)^  (schedule|push|pull_request):")
        section = r"(?m)^concurrency:\n(?:  .+\n)+"
        self.assertEqual(re.search(section, migration).group(), re.search(section, collector).group())
        self.assertIn("permissions:\n  contents: write\n  actions: write\n\n", migration)
        for name in ("bdns-baseline-transition", "bdns-cutover"):
            Draft202012Validator.check_schema(json.loads((ROOT / "schemas" / (name + ".schema.json")).read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
