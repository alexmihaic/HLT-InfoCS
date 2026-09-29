"""Pruebas offline del runner operativo BDNS; todo I/O va a temporales."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.events import EventStore  # noqa: E402
from infocs.fetch.bdns.models import BDNSFetchResult, BDNSRequestStatus  # noqa: E402
from infocs.fetch.bdns.parser import parse_bdns_detail, parse_bdns_search  # noqa: E402
from infocs.fetch.bdns.runner import (  # noqa: E402
    BDNSRunMode,
    BDNSRunnerStatus,
    main,
    resolve_incremental_window,
    runner_exit_code,
    run_bdns_productive_collection,
)
from infocs.manifests import ManifestStore, RunStatus  # noqa: E402
from infocs.privacy import PrivacyGate  # noqa: E402
from infocs.store import RecordStore  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures" / "bdns"
START = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)


def fixture_models():
    search_payload = json.loads((FIXTURES / "search_success.json").read_text(encoding="utf-8"))
    detail_payload = json.loads(
        (FIXTURES / "detail_success.json").read_text(encoding="utf-8"), parse_float=Decimal
    )
    detail_payload["regiones"] = [{"descripcion": "ES522 - Castellón / Castelló"}]
    return parse_bdns_search(search_payload), parse_bdns_detail(detail_payload)


class FakeTransport:
    def __init__(self, page, detail, *, status=BDNSRequestStatus.SUCCESS):
        self.page = page
        self.detail = detail
        self.search_queries = []
        self.detail_codes = []
        self.status = status

    def search(self, query):
        self.search_queries.append(query)
        return BDNSFetchResult(self.status, 200, payload=self.page)

    def fetch_detail(self, code):
        self.detail_codes.append(code)
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=self.detail)


class BDNSRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.gate = PrivacyGate.default()
        self.records = RecordStore(root / "records", privacy_gate=self.gate)
        self.events = EventStore(root / "events")
        self.manifests = ManifestStore(root / "manifests")
        self.health = root / "health" / "bdns.json"
        self.page, self.detail = fixture_models()

    def run_runner(self, transport, *, mode=BDNSRunMode.DISCOVERY, **kwargs):
        from_date = kwargs.pop("from_date", date(2026, 9, 1))
        run_id = kwargs.pop("run_id", "run-v1-11111111-1111-4111-8111-111111111111")
        return run_bdns_productive_collection(
            mode=mode,
            from_date=from_date,
            through_date=date(2026, 9, 29),
            started_at=START,
            run_id=run_id,
            clock=lambda: START.replace(second=10),
            transport=transport,
            record_store=self.records,
            event_store=self.events,
            manifest_store=self.manifests,
            health_path=self.health,
            privacy_gate=self.gate,
            **kwargs,
        )

    def test_complete_scope_persists_record_and_event_and_validates_final_control(self) -> None:
        summaries = tuple(
            replace(self.page.items[0], numero_convocatoria=f"90000{index}")
            for index in (1, 2)
        )
        page = replace(
            self.page,
            items=summaries,
            page_number=0,
            page_size=50,
            offset=0,
            total_pages=1,
            total_elements=2,
            number_of_elements=2,
            first=True,
            last=True,
            empty=False,
        )
        class MultiDetailTransport(FakeTransport):
            def fetch_detail(inner, code):
                inner.detail_codes.append(code)
                return BDNSFetchResult(
                    BDNSRequestStatus.SUCCESS,
                    200,
                    payload=replace(self.detail, codigo_bdns=code),
                )

        transport = MultiDetailTransport(page, self.detail)
        result = self.run_runner(transport, mode=BDNSRunMode.COMPLETE_SCOPE)
        self.assertEqual(result.status, BDNSRunnerStatus.COMPLETE_SUCCESS)
        self.assertEqual(result.request_count, 4)  # search + 2 details + control read
        self.assertEqual(result.metrics.seen, 2)
        self.assertEqual(result.metrics.included, 2)
        self.assertEqual(result.metrics.created, 2)
        self.assertEqual(result.metrics.events_created, 2)
        self.assertEqual(result.manifest.status, RunStatus.SUCCESS)
        self.assertEqual(len(self.records.list_source("bdns")), 2)
        self.assertEqual(len(self.events.list_source("bdns")), 2)
        self.assertEqual(len(transport.search_queries), 2)
        self.assertEqual(transport.search_queries[0].region_ids, (56,))
        self.assertEqual(transport.search_queries[0].date_from, date(2026, 9, 1))
        health = json.loads(self.health.read_text(encoding="utf-8"))
        self.assertEqual(health["source_id"], "bdns")
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["last_run_id"], result.run_id)
        report = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn(self.detail.title, report)
        self.assertNotIn(self.detail.codigo_bdns, report)
        self.assertNotIn("document", report.casefold())

    def test_budget_exhaustion_is_partial_and_not_an_incremental_checkpoint(self) -> None:
        summaries = tuple(
            replace(self.page.items[0], numero_convocatoria=f"9010{index:02}")
            for index in range(50)
        )
        page = replace(
            self.page,
            items=summaries,
            page_number=0,
            page_size=50,
            offset=0,
            total_pages=1,
            total_elements=50,
            number_of_elements=50,
            first=True,
            last=True,
            empty=False,
        )
        transport = FakeTransport(page, replace(self.detail, codigo_bdns=summaries[0].numero_convocatoria))
        result = self.run_runner(transport, max_details=1)
        self.assertEqual(result.status, BDNSRunnerStatus.PARTIAL_SUCCESS)
        self.assertEqual(result.manifest.status, RunStatus.PARTIAL)
        self.assertEqual(result.error_code, "run_budget_exhausted")
        self.assertEqual(json.loads(self.health.read_text())["status"], "degraded")
        self.assertEqual(result.metrics.seen, 50)
        self.assertEqual(result.metrics.created, 1)
        self.assertEqual(len(transport.detail_codes), 1)
        window = resolve_incremental_window(
            self.manifests.list_source("bdns"),
            through_date=date(2026, 9, 30),
            initial_from_date=date(2026, 9, 1),
            overlap_days=7,
        )
        self.assertEqual(window, (date(2026, 9, 1), date(2026, 9, 30)))

    def test_cli_exit_codes_distinguish_complete_partial_and_failed(self) -> None:
        self.assertEqual(runner_exit_code(BDNSRunnerStatus.COMPLETE_SUCCESS), 0)
        self.assertEqual(runner_exit_code(BDNSRunnerStatus.NO_RESULTS), 0)
        self.assertEqual(runner_exit_code(BDNSRunnerStatus.PARTIAL_SUCCESS), 2)
        self.assertEqual(runner_exit_code(BDNSRunnerStatus.SOURCE_FAILURE), 1)
        self.assertEqual(runner_exit_code(BDNSRunnerStatus.TERRITORIAL_CONTRACT_DRIFT), 1)
        self.assertEqual(runner_exit_code(BDNSRunnerStatus.PERSISTENCE_BLOCKED), 1)
        self.assertEqual(runner_exit_code("unknown_status"), 1)

    def test_invalid_cli_invocation_uses_terminal_exit_code_one(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            main([])
        self.assertEqual(raised.exception.code, 1)

    def test_control_read_that_finishes_after_wall_clock_budget_is_partial(self) -> None:
        elapsed = {"seconds": 0}
        page = replace(
            self.page,
            items=(self.page.items[0],),
            page_number=0,
            page_size=50,
            offset=0,
            total_pages=1,
            total_elements=1,
            number_of_elements=1,
            first=True,
            last=True,
            empty=False,
        )

        class SlowControlTransport(FakeTransport):
            def search(inner, query=None):
                result = super(SlowControlTransport, inner).search(query)
                if len(inner.search_queries) == 2:
                    elapsed["seconds"] = 601
                return result

        transport = SlowControlTransport(page, self.detail)
        result = self.run_runner(
            transport,
            time_budget_seconds=600,
            monotonic=lambda: elapsed["seconds"],
        )
        self.assertEqual(result.status, BDNSRunnerStatus.PARTIAL_SUCCESS, result.error_code)
        self.assertEqual(result.manifest.status, RunStatus.PARTIAL)
        self.assertEqual(result.error_code, "run_budget_exhausted")

    def test_empty_scope_is_success_only_after_stable_control_read(self) -> None:
        empty = replace(
            self.page,
            items=(),
            page_number=0,
            page_size=50,
            offset=0,
            total_pages=0,
            total_elements=0,
            number_of_elements=0,
            first=True,
            last=True,
            empty=True,
        )
        transport = FakeTransport(empty, self.detail, status=BDNSRequestStatus.NO_RESULTS)
        result = self.run_runner(transport)
        self.assertEqual(result.status, BDNSRunnerStatus.NO_RESULTS)
        self.assertEqual(result.request_count, 2)
        self.assertEqual(result.manifest.status, RunStatus.SUCCESS)
        self.assertEqual(result.metrics.to_manifest_metrics().errors, 0)

    def test_existing_complete_incremental_manifest_advances_window_with_overlap(self) -> None:
        # Build a safe successful manifest through a no-results incremental run.
        empty = replace(
            self.page,
            items=(), page_number=0, page_size=50, offset=0, total_pages=0,
            total_elements=0, number_of_elements=0, first=True, last=True, empty=True,
        )
        self.run_runner(
            FakeTransport(empty, self.detail, status=BDNSRequestStatus.NO_RESULTS),
            mode=BDNSRunMode.INCREMENTAL_UPDATE,
            from_date=date(2026, 9, 1),
        )
        window = resolve_incremental_window(
            self.manifests.list_source("bdns"),
            through_date=date(2026, 10, 5),
            initial_from_date=None,
            overlap_days=3,
        )
        self.assertEqual(window, (date(2026, 9, 26), date(2026, 10, 5)))

    def test_update_creates_update_event_and_manifest_counts_match(self) -> None:
        page = replace(
            self.page,
            items=(self.page.items[0],),
            page_number=0,
            page_size=50,
            offset=0,
            total_pages=1,
            total_elements=1,
            number_of_elements=1,
            first=True,
            last=True,
            empty=False,
        )
        self.run_runner(FakeTransport(page, self.detail))
        changed_detail = replace(self.detail, title="Convocatoria sintética actualizada")
        second = self.run_runner(
            FakeTransport(page, changed_detail),
            run_id="run-v1-22222222-2222-4222-8222-222222222222",
        )
        self.assertEqual(second.metrics.updated, 1)
        self.assertEqual(second.metrics.events_created, 0)
        self.assertEqual(second.metrics.events_updated, 1)
        self.assertEqual(second.manifest.metrics.updated, 1)
        self.assertEqual(second.manifest.metrics.events_updated, 1)
        self.assertEqual(len(self.events.list_source("bdns")), 2)

    def test_final_control_drift_is_partial_and_does_not_become_checkpoint(self) -> None:
        page = replace(
            self.page,
            items=(self.page.items[0],),
            page_number=0,
            page_size=50,
            offset=0,
            total_pages=1,
            total_elements=1,
            number_of_elements=1,
            first=True,
            last=True,
            empty=False,
        )

        class DriftTransport(FakeTransport):
            def search(inner, query):
                inner.search_queries.append(query)
                if len(inner.search_queries) == 1:
                    return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=page)
                drifted = replace(page, total_elements=2, number_of_elements=2)
                return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=drifted)

        result = self.run_runner(
            DriftTransport(page, self.detail),
            mode=BDNSRunMode.INCREMENTAL_UPDATE,
            from_date=date(2026, 9, 1),
        )
        self.assertEqual(result.status, BDNSRunnerStatus.PARTIAL_SUCCESS)
        self.assertEqual(result.error_code, "scope_drift")
        self.assertEqual(result.manifest.status, RunStatus.PARTIAL)
        self.assertEqual(result.metrics.created, 1)
        next_window = resolve_incremental_window(
            self.manifests.list_source("bdns"),
            through_date=date(2026, 9, 30),
            initial_from_date=date(2026, 9, 1),
            overlap_days=5,
        )
        self.assertEqual(next_window, (date(2026, 9, 1), date(2026, 9, 30)))


if __name__ == "__main__":
    unittest.main()
