"""Pruebas offline de la barrera de ingestión BOP 05E."""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bop_castellon import (  # noqa: E402
    BOPAnnouncement,
    BOPFetchResult,
    BOPFetchStatus,
    BOPIngestionStatus,
    BOPIssue,
    ingest_bop_fetch_result,
)
from infocs.manifests import (  # noqa: E402
    CollectionMode,
    HealthStatus,
    RequestedScope,
    RunManifest,
    RunMetrics,
    RunStatus,
    SoftwareMetadata,
    derive_source_health,
)
from infocs.manifests.model import MANIFEST_VERSION  # noqa: E402
from infocs.privacy import PrivacyConfig, PrivacyGate  # noqa: E402


DETECTED = datetime(2026, 9, 26, 10, 15, tzinfo=UTC)
CHECKED = datetime(2026, 9, 26, 10, 16, tzinfo=UTC)
RUN_ID = "run-v1-00000000-0000-4000-8000-000000000005"


def fetch_result(*announcements: BOPAnnouncement) -> BOPFetchResult:
    issue = BOPIssue("200001", date(2026, 9, 24), "115", "B260924", tuple(announcements))
    return BOPFetchResult(BOPFetchStatus.COMPLETE_SUCCESS, "2026-09-24", issue=issue)


def announcement(portal_id: str, title: str = "Anuncio sintético") -> BOPAnnouncement:
    return BOPAnnouncement(
        portal_id,
        title,
        f"https://bop.dipcas.es/PortalBOP/api/descargarAnuncio?idAnuncio={portal_id}&idioma=es",
    )


def reject_gate() -> PrivacyGate:
    payload = json.loads((ROOT / "config" / "privacy-rules.json").read_text(encoding="utf-8"))
    payload["rules"]["iban"]["decision"] = "reject"
    return PrivacyGate(PrivacyConfig.from_mapping(payload))


class BOPIngestionBarrierTests(unittest.TestCase):
    def test_safe_allow_runs_normalize_finalize_privacy_then_source_hold(self) -> None:
        result = ingest_bop_fetch_result(
            fetch_result(announcement("100001")),
            detected_at=DETECTED,
            last_checked_at=CHECKED,
        )

        self.assertIs(result.status, BOPIngestionStatus.COMPLETE_SUCCESS)
        self.assertTrue(result.technical_success)
        self.assertEqual(result.reason_code, "reuse_policy_unresolved")
        self.assertEqual(result.metrics.seen, 1)
        self.assertEqual(result.metrics.normalized, 1)
        self.assertEqual(result.metrics.finalized, 1)
        self.assertEqual(result.metrics.privacy_allow, 1)
        self.assertEqual(result.metrics.source_hold, 1)
        self.assertEqual(result.metrics.persistence_blocked, 1)
        self.assertEqual(result.metrics.records_written, 0)
        self.assertEqual(result.metrics.events_written, 0)
        self.assertEqual(result.metrics.manual_reviews, 0)
        self.assertEqual(result.metrics.review_queue_items, 0)

    def test_quarantine_and_reject_keep_privacy_precedence(self) -> None:
        result = ingest_bop_fetch_result(
            fetch_result(
                announcement("100001", "Aviso sintético DNI 12345678Z"),
                announcement("100002", "Aviso sintético IBAN ES9121000418450200051332"),
            ),
            detected_at=DETECTED,
            last_checked_at=CHECKED,
            privacy_gate=reject_gate(),
        )

        self.assertIs(result.status, BOPIngestionStatus.COMPLETE_SUCCESS)
        self.assertEqual(result.metrics.privacy_quarantine, 1)
        self.assertEqual(result.metrics.privacy_reject, 1)
        self.assertEqual(result.metrics.privacy_allow, 0)
        self.assertEqual(result.metrics.source_hold, 0)
        self.assertEqual(result.metrics.persistence_blocked, 2)
        self.assertIsNone(result.reason_code)

    def test_mixed_batch_allows_reach_source_hold_and_privacy_stops_do_not(self) -> None:
        result = ingest_bop_fetch_result(
            fetch_result(
                announcement("100001"),
                announcement("100002", "Aviso sintético DNI 12345678Z"),
                announcement("100003", "Aviso sintético IBAN ES9121000418450200051332"),
            ),
            detected_at=DETECTED,
            last_checked_at=CHECKED,
            privacy_gate=reject_gate(),
        )

        self.assertEqual(result.metrics.seen, 3)
        self.assertEqual(result.metrics.normalized, 3)
        self.assertEqual(result.metrics.finalized, 3)
        self.assertEqual(result.metrics.privacy_allow, 1)
        self.assertEqual(result.metrics.privacy_quarantine, 1)
        self.assertEqual(result.metrics.privacy_reject, 1)
        self.assertEqual(result.metrics.source_hold, 1)
        self.assertEqual(result.metrics.persistence_blocked, 3)
        self.assertEqual(result.metrics.records_written, 0)
        self.assertEqual(result.metrics.events_written, 0)
        self.assertEqual(result.metrics.manual_reviews, 0)

    def test_no_publication_and_fetch_failure_map_to_operational_status(self) -> None:
        no_pub = BOPFetchResult(BOPFetchStatus.NO_PUBLICATION, "2026-09-27")
        failed = BOPFetchResult(BOPFetchStatus.SOURCE_FAILURE, "2026-09-24", reason="network_error")

        no_pub_result = ingest_bop_fetch_result(no_pub, detected_at=DETECTED, last_checked_at=CHECKED)
        failed_result = ingest_bop_fetch_result(failed, detected_at=DETECTED, last_checked_at=CHECKED)

        self.assertIs(no_pub_result.status, BOPIngestionStatus.NO_PUBLICATION)
        self.assertTrue(no_pub_result.technical_success)
        self.assertIs(failed_result.status, BOPIngestionStatus.SOURCE_FAILURE)
        self.assertFalse(failed_result.technical_success)
        self.assertEqual(failed_result.reason_code, "source_failure")

    def test_result_and_logging_surface_contain_only_safe_aggregate_metadata(self) -> None:
        result = ingest_bop_fetch_result(
            fetch_result(announcement("100099", "Título sensible sintético")),
            detected_at=DETECTED,
            last_checked_at=CHECKED,
        )
        serialized = json.dumps(result.to_dict(), sort_keys=True)
        for forbidden in ("Título sensible", "100099", "descargarAnuncio", "document_url", "authority"):
            self.assertNotIn(forbidden, serialized)

    def test_bop_hold_never_calls_record_event_review_or_queue_writers(self) -> None:
        with (
            patch("infocs.store.RecordStore.write") as record_write,
            patch("infocs.events.EventStore.write") as event_write,
            patch("infocs.publication.review.review_publication") as manual_review,
            patch("infocs.publication.review.PublicationReviewConfig.from_file") as review_config_load,
            patch("infocs.fetch.boe.review_queue.BOEReviewQueueStore.update") as queue_update,
        ):
            result = ingest_bop_fetch_result(
                fetch_result(announcement("100001")),
                detected_at=DETECTED,
                last_checked_at=CHECKED,
            )

        self.assertEqual(result.metrics.persistence_blocked, 1)
        record_write.assert_not_called()
        event_write.assert_not_called()
        manual_review.assert_not_called()
        review_config_load.assert_not_called()
        queue_update.assert_not_called()

    def test_privacy_stops_before_source_policy(self) -> None:
        from infocs.fetch.bop_castellon import publication as bop_publication

        original = bop_publication.bop_source_publication_eligibility
        with patch.object(bop_publication, "bop_source_publication_eligibility", wraps=original) as source_policy:
            result = ingest_bop_fetch_result(
                fetch_result(
                    announcement("100001", "Aviso sintético DNI 12345678Z"),
                    announcement("100002", "Aviso sintético IBAN ES9121000418450200051332"),
                ),
                detected_at=DETECTED,
                last_checked_at=CHECKED,
                privacy_gate=reject_gate(),
            )

        self.assertEqual(result.metrics.privacy_quarantine, 1)
        self.assertEqual(result.metrics.privacy_reject, 1)
        source_policy.assert_not_called()

    def test_policy_blocked_success_fits_manifest_without_bop_content(self) -> None:
        # RunManifest v1 expresa el resultado agregado como publicación retenida;
        # el motivo source-wide permanece en el resultado seguro de ingestión.
        metrics = RunMetrics(
            seen=1,
            included=1,
            normalized=1,
            finalized=1,
            privacy_allowed=1,
            publication_hold=1,
        )
        manifest = RunManifest(
            manifest_version=MANIFEST_VERSION,
            run_id=RUN_ID,
            source_id="bop_castellon",
            collection_mode=CollectionMode.INCREMENTAL_FEED,
            started_at=DETECTED.isoformat(),
            finished_at=CHECKED.isoformat(),
            status=RunStatus.SUCCESS,
            requested_scope=RequestedScope("date", "2026-09-24"),
            metrics=metrics,
            software_metadata=SoftwareMetadata("0.1.0", source_contract_version="1"),
        )

        payload = manifest.to_dict()
        encoded = json.dumps(payload, sort_keys=True)
        self.assertEqual(manifest.status, RunStatus.SUCCESS)
        self.assertEqual(payload["metrics"]["publication_hold"], 1)
        health = derive_source_health((manifest,), source_id="bop_castellon")
        self.assertIs(health.status, HealthStatus.HEALTHY)
        for forbidden in ("100001", "Anuncio sintético", "descargarAnuncio", "title", "document_url"):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
