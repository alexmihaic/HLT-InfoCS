"""Pruebas mocked del dry-run BDNS; no llaman a red ni a Stores."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bdns.dry_run import BDNSDryRunStatus, run_bdns_dry_run  # noqa: E402
from infocs.fetch.bdns.models import BDNSFetchResult, BDNSRequestStatus  # noqa: E402
from infocs.fetch.bdns.parser import parse_bdns_detail, parse_bdns_search  # noqa: E402
from infocs.privacy import PrivacyGate  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures" / "bdns"
OBSERVED = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def fixture_models():
    search_payload = json.loads((FIXTURES / "search_success.json").read_text(encoding="utf-8"))
    detail_payload = json.loads(
        (FIXTURES / "detail_success.json").read_text(encoding="utf-8"), parse_float=Decimal
    )
    detail_payload["regiones"] = [{"descripcion": "ES522 - Castellón / Castelló"}]
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
        detail = self.details.pop(0)
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=detail)


class BDNSDryRunTests(unittest.TestCase):
    def test_in_scope_record_passes_privacy_and_both_publication_gates_with_no_writes(self) -> None:
        page, detail = fixture_models()
        transport = FakeTransport(page, (detail,))

        with (
            patch("infocs.store.RecordStore.write") as record_write,
            patch("infocs.events.EventStore.write") as event_write,
            patch("infocs.manifests.store.ManifestStore.write") as manifest_write,
            patch("infocs.manifests.health.write_source_health") as health_write,
            patch("infocs.fetch.boe.review_queue.BOEReviewQueueStore.update") as queue_update,
            patch("infocs.publication.review.review_publication") as manual_review,
        ):
            report = run_bdns_dry_run(
                detected_at=OBSERVED,
                last_checked_at=OBSERVED,
                transport=transport,
                privacy_gate=PrivacyGate.default(),
            )

        self.assertEqual(report.status, BDNSDryRunStatus.SUCCESS)
        self.assertEqual(report.request_count, 2)
        self.assertEqual(report.http_statuses, (200, 200))
        self.assertEqual(report.metrics.search_seen, 1)
        self.assertEqual(report.metrics.detail_fetched, 1)
        self.assertEqual(report.metrics.in_scope, 1)
        self.assertEqual(report.metrics.finalized, 1)
        self.assertEqual(report.metrics.privacy_allow, 1)
        self.assertEqual(report.metrics.source_eligible, 1)
        self.assertEqual(report.metrics.metadata_publishable, 1)
        self.assertEqual(report.metrics.errors, 0)
        self.assertEqual(report.territorial_reason_codes, ("exact_castellon_province_region",))
        self.assertEqual(transport.search_queries[0].region_ids, (56,))
        self.assertLessEqual(transport.search_queries[0].page_size, 3)
        self.assertEqual(transport.detail_codes, ["900001"])
        safe_json = json.dumps(report.to_dict(), ensure_ascii=False)
        for forbidden in ("900001", "Convocatoria sintética", "documentos", "sede.example"):
            self.assertNotIn(forbidden, safe_json)
        self.assertEqual(report.to_dict()["writes"], 0)
        for store in (record_write, event_write, manifest_write, health_write, queue_update, manual_review):
            store.assert_not_called()

    def test_quarantined_first_candidate_does_not_stop_search_before_next_allowed(self) -> None:
        page, detail = fixture_models()
        first_summary = replace(page.items[0], numero_convocatoria="900010")
        second_summary = replace(page.items[0], numero_convocatoria="900011")
        summaries = replace(page, items=(first_summary, second_summary))
        quarantined_detail = replace(detail, codigo_bdns="900010", title="DNI sintético 12345678Z")
        allowed_detail = replace(detail, codigo_bdns="900011")
        transport = FakeTransport(summaries, (quarantined_detail, allowed_detail))

        report = run_bdns_dry_run(
            detected_at=OBSERVED,
            last_checked_at=OBSERVED,
            transport=transport,
            privacy_gate=PrivacyGate.default(),
        )

        self.assertEqual(report.status, BDNSDryRunStatus.SUCCESS)
        self.assertEqual(
            report.territorial_reason_codes,
            ("exact_castellon_province_region", "exact_castellon_province_region"),
        )
        self.assertEqual(report.request_count, 3)
        self.assertEqual(report.metrics.privacy_quarantine, 1)
        self.assertEqual(report.metrics.privacy_allow, 1)
        self.assertEqual(report.metrics.metadata_publishable, 1)
        self.assertEqual(transport.detail_codes, ["900010", "900011"])

    def test_filtered_search_stops_on_unresolved_detail_as_contract_drift(self) -> None:
        page, detail = fixture_models()
        unresolved = replace(detail, codigo_bdns="900010", regions=())
        excluded = replace(detail, codigo_bdns="900011", regions=(replace(detail.regions[0], description="ES523 - Valencia / València"),))
        summaries = replace(
            page,
            items=(
                replace(page.items[0], numero_convocatoria="900010"),
                replace(page.items[0], numero_convocatoria="900011"),
            ),
        )
        report = run_bdns_dry_run(
            detected_at=OBSERVED,
            last_checked_at=OBSERVED,
            transport=FakeTransport(summaries, (unresolved, excluded)),
            privacy_gate=PrivacyGate.default(),
        )
        self.assertEqual(report.metrics.unresolved, 1)
        self.assertEqual(report.metrics.out_of_scope, 0)
        self.assertEqual(report.metrics.finalized, 0)
        self.assertEqual(report.metrics.metadata_publishable, 0)
        self.assertEqual(report.status, BDNSDryRunStatus.TERRITORIAL_CONTRACT_DRIFT)
        self.assertEqual(report.request_count, 2)
        self.assertEqual(report.error_stages, ("territorial_contract_drift",))

    def test_filtered_search_stops_on_disjoint_detail_as_contract_drift(self) -> None:
        page, detail = fixture_models()
        excluded = replace(
            detail,
            regions=(replace(detail.regions[0], description="ES523 - Valencia / València"),),
        )
        transport = FakeTransport(page, (excluded,))
        report = run_bdns_dry_run(
            detected_at=OBSERVED,
            last_checked_at=OBSERVED,
            transport=transport,
            privacy_gate=PrivacyGate.default(),
        )
        self.assertEqual(report.status, BDNSDryRunStatus.TERRITORIAL_CONTRACT_DRIFT)
        self.assertEqual(report.territorial_reason_codes, ("exact_disjoint_province_region",))
        self.assertEqual(report.request_count, 2)
        self.assertEqual(transport.detail_codes, [page.items[0].numero_convocatoria])

    def test_no_results_is_valid_and_detail_budget_is_hard_capped(self) -> None:
        page, _ = fixture_models()
        empty_transport = FakeTransport(replace(page, items=()), ())
        empty = run_bdns_dry_run(
            detected_at=OBSERVED,
            last_checked_at=OBSERVED,
            transport=empty_transport,
        )
        self.assertEqual(empty.status, BDNSDryRunStatus.NO_RESULTS)
        self.assertEqual(empty.request_count, 1)

        with self.assertRaises(ValueError):
            run_bdns_dry_run(
                detected_at=OBSERVED,
                last_checked_at=OBSERVED,
                transport=empty_transport,
                max_details=4,
            )
        self.assertEqual(len(empty_transport.search_queries), 1)


if __name__ == "__main__":
    unittest.main()
