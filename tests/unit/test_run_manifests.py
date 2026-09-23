"""Pruebas offline de RunManifest, ManifestStore, SourceHealth y adaptador BOE."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.boe.ingest import BOEIngestionMetrics, BOEIngestionResult, BOEIngestionStatus
from infocs.fetch.boe.manifest import manifest_from_boe_result
from infocs.manifests import (
    CollectionMode,
    ErrorSummary,
    HealthStatus,
    ManifestStore,
    ManifestStoreConflictError,
    ManifestStoreError,
    ManifestValidationError,
    RequestedScope,
    RunManifest,
    RunMetrics,
    RunStatus,
    SoftwareMetadata,
    derive_source_health,
    new_run_id,
)


START = datetime(2026, 9, 23, 8, 0, tzinfo=UTC)
FINISH = datetime(2026, 9, 23, 8, 1, tzinfo=UTC)
SOFTWARE = SoftwareMetadata("0.1.0", source_contract_version="1")
RUN_A = "run-v1-00000000-0000-4000-8000-000000000001"
RUN_B = "run-v1-00000000-0000-4000-8000-000000000002"
RUN_C = "run-v1-00000000-0000-4000-8000-000000000003"


def manifest(
    run_id: str = RUN_A,
    *,
    status: RunStatus = RunStatus.SUCCESS,
    started_at: datetime = START,
    finished_at: datetime = FINISH,
    metrics: RunMetrics | None = None,
    error: ErrorSummary | None = None,
    source_id: str = "boe",
) -> RunManifest:
    if metrics is None:
        metrics = success_metrics() if status is RunStatus.SUCCESS else RunMetrics(errors=1) if status is RunStatus.FAILED else RunMetrics()
    if error is None and status is RunStatus.FAILED:
        error = ErrorSummary("transport", "source_failure", "La ejecución de la fuente no produjo un resultado utilizable.")
    if status is RunStatus.PARTIAL and error is None:
        error = ErrorSummary("parser", "incomplete_result", "La ejecución terminó parcialmente.")
        if metrics.errors == 0:
            metrics = RunMetrics(errors=1)
    return RunManifest(
        manifest_version="1.0",
        run_id=run_id,
        source_id=source_id,
        collection_mode=CollectionMode.INCREMENTAL_FEED,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        status=status,
        requested_scope=RequestedScope("date", "2026-09-23"),
        metrics=metrics,
        software_metadata=SOFTWARE,
        error_summary=error,
    )


def success_metrics(**overrides: int) -> RunMetrics:
    values = {
        "seen": 4,
        "included": 3,
        "excluded": 1,
        "normalized": 3,
        "finalized": 3,
        "privacy_allowed": 2,
        "privacy_quarantined": 1,
        "privacy_rejected": 0,
        "publication_approved": 1,
        "publication_hold": 1,
        "publication_rejected": 0,
        "created": 1,
        "updated": 0,
        "unchanged": 0,
        "events_created": 1,
        "events_updated": 0,
        "errors": 0,
    }
    values.update(overrides)
    return RunMetrics(**values)


class RunManifestModelTests(unittest.TestCase):
    def test_success_no_publication_and_failed_are_valid(self) -> None:
        success = manifest()
        no_publication = manifest(RUN_B, status=RunStatus.NO_PUBLICATION)
        failed = manifest(RUN_C, status=RunStatus.FAILED)
        self.assertEqual(success.status, RunStatus.SUCCESS)
        self.assertEqual(no_publication.metrics, RunMetrics())
        self.assertIsNotNone(failed.error_summary)

    def test_partial_status_is_supported_with_error_summary(self) -> None:
        partial = manifest(status=RunStatus.PARTIAL)
        self.assertEqual(partial.status, RunStatus.PARTIAL)

    def test_timestamps_are_aware_ordered_and_canonical_utc(self) -> None:
        offset_start = "2026-09-23T10:00:00+02:00"
        value = RunManifest.from_mapping({
            **manifest().to_dict(),
            "started_at": offset_start,
            "finished_at": "2026-09-23T10:01:00+02:00",
        })
        self.assertEqual(value.started_at, "2026-09-23T08:00:00Z")
        self.assertEqual(value.finished_at, "2026-09-23T08:01:00Z")
        with self.assertRaises(ManifestValidationError):
            RunManifest.from_mapping({**manifest().to_dict(), "started_at": "2026-09-23T08:00:00"})
        with self.assertRaises(ManifestValidationError):
            RunManifest.from_mapping({**manifest().to_dict(), "finished_at": "2026-09-23T07:59:00Z"})

    def test_run_id_is_uuid4_occurrence_not_scope_identity(self) -> None:
        first, second = new_run_id(), new_run_id()
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("run-v1-"))
        self.assertIn("-4", first)
        self.assertEqual(manifest(first).requested_scope, manifest(second).requested_scope)

    def test_negative_and_boolean_metrics_are_rejected(self) -> None:
        with self.assertRaises(ManifestValidationError):
            RunMetrics(seen=-1)
        with self.assertRaises(ManifestValidationError):
            RunMetrics(seen=True)  # type: ignore[arg-type]

    def test_success_metric_invariants_are_enforced(self) -> None:
        with self.assertRaises(ManifestValidationError):
            manifest(metrics=success_metrics(excluded=0))
        with self.assertRaises(ManifestValidationError):
            manifest(metrics=success_metrics(publication_approved=2))
        with self.assertRaises(ManifestValidationError):
            manifest(metrics=success_metrics(events_created=0))

    def test_error_summary_accepts_only_public_safe_templates(self) -> None:
        with self.assertRaises(ManifestValidationError):
            ErrorSummary("transport", "source_failure", "DNI 12345678Z")
        with self.assertRaises(ManifestValidationError):
            ErrorSummary("transport", "source_failure", "x" * 201)

    def test_deterministic_serialization_and_round_trip(self) -> None:
        first = manifest()
        second = RunManifest.from_mapping(json.loads(first.canonical_json()))
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertTrue(first.canonical_json().startswith('{"collection_mode"'))

    def test_scope_date_format_is_validated(self) -> None:
        with self.assertRaises(ManifestValidationError):
            RequestedScope("date", "23-09-2026")
        with self.assertRaises(ManifestValidationError):
            RequestedScope("date", r"C:\Users\local")

    def test_software_metadata_rejects_local_paths(self) -> None:
        with self.assertRaises(ManifestValidationError):
            SoftwareMetadata(r"C:\Users\local\collector.py")


class ManifestStoreTests(unittest.TestCase):
    def test_path_layout_write_and_same_run_idempotency(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ManifestStore(temporary)
            value = manifest()
            path = store.path_for(value)
            self.assertIn(Path("boe/2026/09"), path.relative_to(Path(temporary)).parents)
            self.assertTrue(store.write(value))
            self.assertFalse(store.write(value))
            self.assertEqual(store.get(RUN_A).canonical_json(), value.canonical_json())
            self.assertTrue(store.exists(RUN_A))
            self.assertTrue(path.read_bytes().endswith(b"\n"))
            self.assertEqual(tuple(path.parent.glob("*.tmp")), ())

    def test_same_run_id_with_different_content_is_a_contract_conflict(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ManifestStore(temporary)
            store.write(manifest())
            altered = manifest(finished_at=FINISH + timedelta(seconds=1))
            with self.assertRaises(ManifestStoreConflictError):
                store.write(altered)

    def test_path_traversal_and_invalid_run_id_do_not_escape_store(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ManifestStore(temporary)
            self.assertIsNone(store.get("../../outside"))
            with self.assertRaises(ManifestValidationError):
                manifest("run-v1-../../outside")
            with self.assertRaises(ManifestStoreError):
                store.list_source("../boe")

    def test_list_source_has_stable_chronological_order(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ManifestStore(temporary)
            late = manifest(RUN_C, started_at=START + timedelta(days=2), finished_at=FINISH + timedelta(days=2))
            early = manifest(RUN_A)
            middle = manifest(RUN_B, started_at=START + timedelta(days=1), finished_at=FINISH + timedelta(days=1))
            store.write(late)
            store.write(early)
            store.write(middle)
            self.assertEqual([item.run_id for item in store.list_source("boe")], [RUN_A, RUN_B, RUN_C])
            self.assertEqual(store.list_source("other"), ())

    def test_store_rejects_noncanonical_or_invalid_payload_on_read(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ManifestStore(temporary)
            value = manifest()
            path = store.path_for(value)
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(value.to_dict()) + "\n\n", encoding="utf-8")
            with self.assertRaises(ManifestStoreError):
                store.get(RUN_A)


class SourceHealthTests(unittest.TestCase):
    def test_no_manifests_is_unknown(self) -> None:
        health = derive_source_health((), source_id="boe")
        self.assertEqual(health.status, HealthStatus.UNKNOWN)
        self.assertEqual(health.to_dict(), {"source_id": "boe", "status": "unknown", "consecutive_failures": 0})

    def test_success_and_no_publication_are_healthy_successful_attempts(self) -> None:
        success = manifest(status=RunStatus.SUCCESS)
        no_publication = manifest(RUN_B, status=RunStatus.NO_PUBLICATION, started_at=START + timedelta(days=1), finished_at=FINISH + timedelta(days=1))
        health = derive_source_health([success, no_publication], source_id="boe")
        self.assertEqual(health.status, HealthStatus.HEALTHY)
        self.assertEqual(health.last_run_id, RUN_B)
        self.assertEqual(health.last_success_at, no_publication.finished_at)
        self.assertEqual(health.consecutive_failures, 0)

    def test_one_failure_after_success_is_degraded_and_keeps_last_success(self) -> None:
        success = manifest()
        failed = manifest(RUN_B, status=RunStatus.FAILED, started_at=START + timedelta(days=1), finished_at=FINISH + timedelta(days=1))
        health = derive_source_health([failed, success], source_id="boe")
        self.assertEqual(health.status, HealthStatus.DEGRADED)
        self.assertEqual(health.consecutive_failures, 1)
        self.assertEqual(health.last_success_at, success.finished_at)
        self.assertEqual(health.last_error_code, "source_failure")

    def test_three_consecutive_failures_are_failing(self) -> None:
        runs = [
            manifest(run_id, status=RunStatus.FAILED, started_at=START + timedelta(days=index), finished_at=FINISH + timedelta(days=index))
            for index, run_id in enumerate((RUN_A, RUN_B, RUN_C))
        ]
        health = derive_source_health(runs, source_id="boe")
        self.assertEqual(health.status, HealthStatus.FAILING)
        self.assertEqual(health.consecutive_failures, 3)

    def test_success_resets_failure_streak(self) -> None:
        failed = manifest(RUN_A, status=RunStatus.FAILED)
        success = manifest(RUN_B, started_at=START + timedelta(days=1), finished_at=FINISH + timedelta(days=1))
        health = derive_source_health([failed, success], source_id="boe")
        self.assertEqual((health.status, health.consecutive_failures), (HealthStatus.HEALTHY, 0))

    def test_derivation_is_independent_of_input_filesystem_order(self) -> None:
        runs = [
            manifest(RUN_A, status=RunStatus.FAILED),
            manifest(RUN_B, status=RunStatus.FAILED, started_at=START + timedelta(days=1), finished_at=FINISH + timedelta(days=1)),
        ]
        self.assertEqual(derive_source_health(runs, source_id="boe"), derive_source_health(reversed(runs), source_id="boe"))

    def test_health_regenerates_from_manifest_store(self) -> None:
        first = manifest(RUN_A)
        second = manifest(RUN_B, status=RunStatus.FAILED, started_at=START + timedelta(days=1), finished_at=FINISH + timedelta(days=1))
        with TemporaryDirectory() as temporary:
            store = ManifestStore(temporary)
            store.write(second)
            store.write(first)
            derived = derive_source_health(store.list_source("boe"), source_id="boe")
            self.assertEqual(derived.status, HealthStatus.DEGRADED)
            self.assertEqual(derived.last_run_id, RUN_B)

    def test_health_rejects_mixed_sources(self) -> None:
        with self.assertRaises(ManifestValidationError):
            derive_source_health([manifest(source_id="other")], source_id="boe")


class BOEManifestAdapterTests(unittest.TestCase):
    def build(self, result: BOEIngestionResult):
        return manifest_from_boe_result(
            result,
            requested_date=date(2026, 9, 23),
            run_id=RUN_A,
            started_at=START,
            finished_at=FINISH,
            software_metadata=SOFTWARE,
        )

    def test_success_maps_existing_privacy_publication_and_event_metrics(self) -> None:
        source_metrics = BOEIngestionMetrics(
            seen=4, included=3, excluded=1, created=1, updated=0, unchanged=0,
            privacy_allowed=2, privacy_quarantined=1, privacy_rejected=0,
            publication_approved=1, publication_hold=1, publication_rejected=0,
        )
        result = BOEIngestionResult(
            BOEIngestionStatus.COMPLETE_SUCCESS,
            source_metrics,
            events=(SimpleNamespace(type="create"),),
        )
        value = self.build(result)
        self.assertEqual(value.status, RunStatus.SUCCESS)
        self.assertEqual(value.collection_mode, CollectionMode.INCREMENTAL_FEED)
        self.assertEqual(value.requested_scope.to_dict(), {"type": "date", "value": "2026-09-23"})
        self.assertEqual(value.metrics, success_metrics())

    def test_no_publication_maps_to_successful_zero_metrics(self) -> None:
        result = BOEIngestionResult(BOEIngestionStatus.NO_DAILY_PUBLICATION, BOEIngestionMetrics())
        value = self.build(result)
        self.assertEqual(value.status, RunStatus.NO_PUBLICATION)
        self.assertEqual(value.metrics, RunMetrics())
        self.assertIsNone(value.error_summary)

    def test_no_publication_with_processing_counts_is_rejected(self) -> None:
        invalid = BOEIngestionResult(
            BOEIngestionStatus.NO_DAILY_PUBLICATION,
            BOEIngestionMetrics(seen=1),
        )
        with self.assertRaises(ValueError):
            self.build(invalid)

    def test_source_failure_uses_safe_summary_not_raw_error(self) -> None:
        result = BOEIngestionResult(
            BOEIngestionStatus.SOURCE_FAILURE,
            BOEIngestionMetrics(),
            error="DNI 12345678Z IBAN ES9121000418450200051332 secret raw response",
        )
        value = self.build(result)
        serialized = value.canonical_json()
        self.assertEqual(value.status, RunStatus.FAILED)
        self.assertEqual(value.metrics.errors, 1)
        self.assertNotIn("12345678Z", serialized)
        self.assertNotIn("ES9121000418450200051332", serialized)
        self.assertNotIn("raw response", serialized)

    def test_invalid_request_maps_to_failed_with_stable_error_code(self) -> None:
        value = self.build(BOEIngestionResult(BOEIngestionStatus.INVALID_REQUEST, BOEIngestionMetrics()))
        self.assertEqual(value.status, RunStatus.FAILED)
        self.assertEqual(value.error_summary.error_code, "invalid_request")

    def test_update_events_count_separately_and_unchanged_has_no_event(self) -> None:
        source_metrics = BOEIngestionMetrics(
            seen=1, included=1, updated=1,
            privacy_allowed=1, publication_approved=1,
        )
        value = self.build(BOEIngestionResult(
            BOEIngestionStatus.COMPLETE_SUCCESS,
            source_metrics,
            events=(SimpleNamespace(type="update"),),
        ))
        self.assertEqual(value.metrics.events_updated, 1)
        self.assertEqual(value.metrics.events_created, 0)

    def test_no_change_is_counted_without_new_event(self) -> None:
        source_metrics = BOEIngestionMetrics(
            seen=1, included=1, unchanged=1,
            privacy_allowed=1, publication_approved=1,
        )
        value = self.build(BOEIngestionResult(BOEIngestionStatus.COMPLETE_SUCCESS, source_metrics))
        self.assertEqual(value.metrics.unchanged, 1)
        self.assertEqual(value.metrics.events_created + value.metrics.events_updated, 0)


if __name__ == "__main__":
    unittest.main()
