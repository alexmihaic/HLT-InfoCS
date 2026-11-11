"""Pruebas offline de los controles de publicación manual de BDNS."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bdns.workflow_safety import (  # noqa: E402
    WorkflowSafetyError,
    resolve_scheduled_parameters,
    scheduled_through_date,
    validate_changed_entries,
    validate_generated_artifacts,
    validate_inputs,
    validate_remote_boe_commit,
    validate_runner_result,
    write_runner_summary,
    stage_validated_artifacts,
    validate_committed_artifacts,
)
from infocs.fetch.bdns.ingest import BDNS_ATTRIBUTION_REQUIREMENTS, ingest_bdns  # noqa: E402
from infocs.fetch.bdns.models import BDNSFetchResult, BDNSRequestStatus  # noqa: E402
from infocs.fetch.bdns.parser import parse_bdns_detail, parse_bdns_search  # noqa: E402
from infocs.fetch.bdns.runner import run_bdns_productive_collection  # noqa: E402
from infocs.events import EventStore  # noqa: E402
from infocs.manifests import ManifestStore  # noqa: E402
from infocs.manifests import (  # noqa: E402
    CollectionMode,
    RunManifest,
    RunMetrics,
    RunStatus,
    RequestedScope,
    SoftwareMetadata,
)
from infocs.privacy import PrivacyGate  # noqa: E402
from infocs.store import RecordStore  # noqa: E402
from tests.unit.test_bdns_runner import fixture_models  # noqa: E402


RUN_ID = "run-v1-12345678-1234-4234-9234-123456789abc"
FIXTURES = ROOT / "tests" / "fixtures" / "bdns"
STARTED_AT = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)


class _FixtureTransport:
    def __init__(self, page, detail) -> None:
        self.page = page
        self.detail = detail

    def search(self, _query):
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=self.page)

    def fetch_detail(self, _code):
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=self.detail)


class TerminalPublicationGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # A real disposable Git repository, deliberately without commits.
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True, capture_output=True)
        (self.root / "schemas").mkdir()
        for name in ("record", "event", "run-manifest", "source-health"):
            shutil.copyfile(ROOT / "schemas" / f"{name}.schema.json", self.root / "schemas" / f"{name}.schema.json")
        self.records = RecordStore(self.root / "data" / "records")
        self.events = EventStore(self.root / "data" / "events")
        self.manifests = ManifestStore(self.root / "data" / "manifests")
        self.health = self.root / "data" / "health" / "bdns.json"
        attribution = self.records.root / "bdns" / "README.md"
        attribution.parent.mkdir(parents=True)
        attribution.write_text("\n".join(BDNS_ATTRIBUTION_REQUIREMENTS), encoding="utf-8")
        page, self.detail = fixture_models()
        self.page = replace(page, items=(page.items[0], replace(page.items[0], numero_convocatoria="900002")),
            page_number=0, page_size=50, offset=0, total_pages=1, total_elements=2,
            number_of_elements=2, first=True, last=True, empty=False)
        self.addCleanup(patch.stopall)
        patch("socket.create_connection", side_effect=AssertionError("offline_network_forbidden")).start()

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in (self.root / "data").rglob("*") if p.is_file()}

    def changes(self, before):
        return tuple(("M" if path in before else "A", path)
            for path, value in self.snapshot().items() if path.endswith(".json") and before.get(path) != value)

    def seed(self):
        result = ingest_bdns(record_store=self.records, event_store=self.events,
            transport=_FixtureTransport(self.page, self.detail), started_at=STARTED_AT - timedelta(days=1),
            clock=lambda: STARTED_AT - timedelta(days=1))
        self.assertEqual(result.status.value, "complete_success")

    def collect(self, *, fail_at=2, detail=None, max_details=250, run_id=RUN_ID):
        page = self.page
        first = detail or self.detail
        class Transport:
            def search(self, query):
                return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=page)
            def fetch_detail(self, code):
                position = 1 if code == page.items[0].numero_convocatoria else 2
                if position == fail_at:
                    return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, 500)
                return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=replace(first, codigo_bdns=code))
        return run_bdns_productive_collection(mode="incremental_update", from_date=date(2026, 9, 1),
            through_date=date(2026, 9, 29), started_at=STARTED_AT, run_id=run_id,
            clock=lambda: STARTED_AT + timedelta(seconds=10), transport=Transport(),
            record_store=self.records, event_store=self.events, manifest_store=self.manifests,
            health_path=self.health, max_details=max_details)

    def assert_terminal_blocked(self, before, result):
        entries = self.changes(before)
        self.assertEqual(result.status, "source_failure")
        generated = self.snapshot()
        safe = validate_runner_result(json.dumps(result.to_dict()), "", 1)
        with self.assertRaisesRegex(WorkflowSafetyError, "terminal_data_publication_forbidden"):
            validate_generated_artifacts(self.root, entries, safe)
        with patch("infocs.fetch.bdns.workflow_safety._working_tree_entries", return_value=entries):
            with self.assertRaisesRegex(WorkflowSafetyError, "terminal_data_publication_forbidden"):
                stage_validated_artifacts(self.root, safe)
        self.assertFalse((self.root / ".git" / "index").exists())
        # Commit metadata/diff is simulated: no commit is created by these tests.
        with patch("infocs.fetch.bdns.workflow_safety._git_name_status", return_value=entries):
            with self.assertRaisesRegex(WorkflowSafetyError, "terminal_data_publication_forbidden"):
                validate_committed_artifacts(self.root, "synthetic-commit", safe)
        self.assertEqual(self.snapshot(), generated)
        summary = self.root / "summary.md"
        write_runner_summary(summary, safe, 1)
        self.assertIn("Los contadores describen el procesamiento", summary.read_text(encoding="utf-8"))

    def test_identical_first_then_failure_blocks_freshness_including_future_ingest(self):
        self.seed()
        before = self.snapshot()
        def observe_with_freshness(**kwargs):
            result = ingest_bdns(**kwargs)
            record = self.records.list_source("bdns")[0]
            self.records.write(replace(record, dates=replace(record.dates,
                last_checked_at=STARTED_AT + timedelta(seconds=10))))
            return result
        # main has no freshness writes yet. Simulate only this prospective effect
        # of #25 through the runner's existing ingestion seam.
        with patch("infocs.fetch.bdns.runner.ingest_bdns", side_effect=observe_with_freshness):
            result = self.collect()
        self.assertEqual(result.metrics.unchanged, 1)
        self.assertEqual(result.metrics.events_updated, 0)
        self.assert_terminal_blocked(before, result)

    def test_material_update_then_failure_blocks_record_and_event(self):
        self.seed()
        before = self.snapshot()
        result = self.collect(detail=replace(self.detail, title="Rectificación sintética"))
        self.assertEqual((result.metrics.updated, result.metrics.events_updated), (1, 1))
        self.assert_terminal_blocked(before, result)

    def test_creation_then_failure_blocks_new_record_and_event(self):
        before = self.snapshot()
        result = self.collect()
        self.assertEqual((result.metrics.created, result.metrics.events_created), (1, 1))
        self.assert_terminal_blocked(before, result)

    def test_failure_before_items_allows_only_coherent_observability(self):
        before = self.snapshot()
        result = self.collect(fail_at=1)
        entries = self.changes(before)
        self.assertEqual(result.manifest.status.value, "failed")
        self.assertTrue(all(path.startswith("data/manifests/bdns/") or path == "data/health/bdns.json" for _, path in entries))
        self.assertEqual(len(validate_generated_artifacts(self.root, entries, result.to_dict())), 2)
        self.assertEqual(result.manifest.metrics.created, 0)
        self.assertEqual(result.manifest.metrics.events_created, 0)
        with patch("infocs.fetch.bdns.workflow_safety._git_name_status", return_value=entries):
            self.assertEqual(len(validate_committed_artifacts(self.root, "synthetic-commit", result.to_dict())), 2)
        payload = json.loads(self.health.read_text(encoding="utf-8"))
        self.health.write_text(json.dumps({**payload,
            "last_run_id": "run-v1-22222222-2222-4222-8222-222222222222"},
            sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkflowSafetyError, "health_manifest_history_mismatch"):
            validate_generated_artifacts(self.root, entries, result.to_dict())

    def test_complete_and_partial_results_keep_existing_rules_and_checkpoint(self):
        from infocs.fetch.bdns.runner import resolve_incremental_window
        checkpoint = replace(BDNSWorkflowSafetyTests._incremental_checkpoint(),
            run_id="run-v1-33333333-3333-4333-8333-333333333333",
            started_at="2026-09-28T06:00:00Z", finished_at="2026-09-28T06:01:00Z",
            requested_scope=RequestedScope("bdns_incremental_update",
                "region=56;from=2026-09-01;to=2026-09-28;temporal_policy=fecha-recepcion-provisional-v1"))
        self.manifests.write(checkpoint)
        before = self.snapshot()
        run_id = "run-v1-11111111-1111-4111-8111-111111111111"
        partial = self.collect(fail_at=0, max_details=1, run_id=run_id)
        self.assertEqual(partial.status, "partial_success")
        safe = validate_runner_result(json.dumps(partial.to_dict()), "", 2)
        self.assertEqual(len(validate_generated_artifacts(self.root, self.changes(before), safe)), 4)
        window = resolve_incremental_window(self.manifests.list_source("bdns"), through_date=date(2026, 9, 29),
            initial_from_date=None, overlap_days=14)
        self.assertEqual(window[0], date(2026, 9, 14))
        checkpoint_bytes = self.manifests.path_for(checkpoint).read_bytes()
        failed = self.collect(run_id="run-v1-44444444-4444-4444-8444-444444444444")
        self.assertEqual(failed.manifest.status.value, "failed")
        self.assertEqual(self.manifests.path_for(checkpoint).read_bytes(), checkpoint_bytes)
        window = resolve_incremental_window(self.manifests.list_source("bdns"), through_date=date(2026, 9, 29),
            initial_from_date=None, overlap_days=14)
        self.assertEqual(window[0], date(2026, 9, 14))
        before = self.snapshot()
        complete = self.collect(fail_at=0)
        self.assertEqual(complete.status, "complete_success")
        safe = validate_runner_result(json.dumps(complete.to_dict()), "", 0)
        self.assertEqual(len(validate_generated_artifacts(self.root, self.changes(before), safe)), 4)

    def test_all_terminal_statuses_reject_record_and_event_injection(self):
        for status in ("source_failure", "territorial_contract_drift", "persistence_blocked", "failed"):
            for path in ("data/records/bdns/r-synthetic.json",
                         "data/events/bdns/r-synthetic/evt-v1-" + "a" * 64 + ".json"):
                with self.subTest(status=status, path=path):
                    result = dict(run_id=RUN_ID, source_id="bdns", status=status, error_code="runner_failure")
                    with self.assertRaisesRegex(WorkflowSafetyError, "terminal_data_publication_forbidden"):
                        validate_generated_artifacts(self.root, (("A", path),), result)

    def test_publication_entrypoints_require_a_valid_runner_result(self):
        for result in ({}, {"status": "unknown"}, {"status": "source_failure"}):
            with self.subTest(result=result), self.assertRaises(WorkflowSafetyError):
                stage_validated_artifacts(self.root, result)
            with self.subTest(result=result), self.assertRaises(WorkflowSafetyError):
                validate_committed_artifacts(self.root, "synthetic-commit", result)

    def test_terminal_cannot_hide_generated_data_counters_in_observability(self):
        before = self.snapshot()
        result = self.collect()
        entries = tuple(entry for entry in self.changes(before)
            if entry[1].startswith("data/manifests/") or entry[1].startswith("data/health/"))
        with self.assertRaisesRegex(WorkflowSafetyError, "terminal_generated_data_counters"):
            validate_generated_artifacts(self.root, entries, result.to_dict())

    def test_recovery_from_last_published_snapshot_does_not_duplicate_events(self):
        before = self.snapshot()
        result = self.collect()
        self.assert_terminal_blocked(before, result)
        with tempfile.TemporaryDirectory() as directory:
            clean = Path(directory)
            for path, content in before.items():
                target = clean / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            self.records = RecordStore(clean / "data" / "records")
            self.events = EventStore(clean / "data" / "events")
            self.manifests = ManifestStore(clean / "data" / "manifests")
            self.health = clean / "data" / "health" / "bdns.json"
            recovered = self.collect(fail_at=0)
            again = self.collect(fail_at=0, run_id="run-v1-22222222-2222-4222-8222-222222222222")
            self.assertEqual(recovered.status, "complete_success")
            self.assertEqual(again.metrics.events_created, 0)
            self.assertEqual(len(self.records.list_source("bdns")), 2)
            self.assertEqual(len(self.events.list_source("bdns")), 2)


class BDNSWorkflowSafetyTests(unittest.TestCase):
    @staticmethod
    def _incremental_checkpoint() -> RunManifest:
        return RunManifest(
            manifest_version="1.0",
            run_id="run-v1-12345678-1234-4234-9234-123456789abc",
            source_id="bdns",
            collection_mode=CollectionMode.INCREMENTAL_FEED,
            started_at="2026-09-30T06:00:00Z",
            finished_at="2026-09-30T06:01:00Z",
            status=RunStatus.SUCCESS,
            requested_scope=RequestedScope(
                "bdns_incremental_update",
                "region=56;from=2026-09-14;to=2026-09-29;temporal_policy=fecha-recepcion-provisional-v1",
            ),
            metrics=RunMetrics(),
            software_metadata=SoftwareMetadata("0.2.0", "1"),
        )

    def test_scheduled_through_date_uses_madrid_calendar_across_utc_midnight(self) -> None:
        now = datetime(2026, 9, 30, 22, 30, tzinfo=UTC)
        self.assertEqual(scheduled_through_date(now), date(2026, 9, 30))
        with self.assertRaisesRegex(WorkflowSafetyError, "scheduled_clock_must_be_timezone_aware"):
            scheduled_through_date(datetime(2026, 9, 30, 22, 30))

    def test_scheduled_run_fails_closed_without_compatible_checkpoint(self) -> None:
        with self.assertRaisesRegex(WorkflowSafetyError, "compatible_incremental_checkpoint_required"):
            resolve_scheduled_parameters((), now=datetime(2026, 9, 30, 10, tzinfo=UTC))

    def test_scheduled_parameters_use_incremental_mode_and_yesterday_with_checkpoint(self) -> None:
        parameters = resolve_scheduled_parameters(
            (self._incremental_checkpoint(),),
            now=datetime(2026, 9, 30, 10, tzinfo=UTC),
        )
        self.assertEqual(parameters, {"run_class": "incremental_update", "through_date": "2026-09-29"})
        self.assertNotIn("from_date", parameters)

    def test_manual_scope_inputs_validate_dates_and_modes_before_requests(self) -> None:
        validate_inputs("complete_scope", "2026-01-01", "2026-01-31")
        for values in (
            ("unknown", "2026-01-01", "2026-01-31"),
            ("discovery", "2026-02-30", "2026-03-01"),
            ("incremental_update", "2026-02-01", "2026-01-31"),
        ):
            with self.subTest(values=values), self.assertRaises(WorkflowSafetyError):
                validate_inputs(*values)

    def test_result_exit_mapping_is_machine_checked(self) -> None:
        payload = (
            '{"run_id":"' + RUN_ID + '","source_id":"bdns",'
            '"status":"partial_success","metrics":{"seen":1},'
            '"request_count":2,"http_statuses":[200,200],"error_code":"run_budget_exhausted"}'
        )
        result = validate_runner_result(payload, "", 2)
        self.assertEqual(result["status"], "partial_success")
        with self.assertRaisesRegex(WorkflowSafetyError, "runner_status_exit_mismatch"):
            validate_runner_result(payload, "", 0)

    def test_safe_item_failure_diagnostics_and_summary(self) -> None:
        result = dict(run_id=RUN_ID, source_id="bdns", status="source_failure",
            error_code="item_ingestion_failure", safe_detail_reason="enrichment_invalid_url",
            failure_position=1, safe_field_class="regulatory_bases")
        self.assertEqual(validate_runner_result(json.dumps(result), "", 1), result)
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            write_runner_summary(summary, result, 1)
            text = summary.read_text(encoding="utf-8")
            self.assertIn("enrichment_invalid_url", text)
            self.assertIn("Failure position: 1", text)
            self.assertNotIn(RUN_ID, text)
            self.assertNotIn("https://", text)

    def test_unknown_detail_field_class_and_bad_position_fail_closed(self) -> None:
        result = dict(run_id=RUN_ID, source_id="bdns", status="source_failure",
            error_code="item_ingestion_failure", safe_detail_reason="enrichment_invalid_url",
            failure_position=1, safe_field_class="regulatory_bases")
        for key, value in (("safe_detail_reason", "private_title"),
                           ("safe_field_class", "https://example.org/private.pdf"),
                           ("failure_position", 0), ("failure_position", True),
                           ("failure_position", "1")):
            with self.subTest(key=key, value=value), self.assertRaises(WorkflowSafetyError):
                validate_runner_result(json.dumps({**result, key:value}), "", 1)
        with self.assertRaises(WorkflowSafetyError):
            validate_runner_result(json.dumps({**result, "status":"complete_success", "error_code":None}), "", 0)

    def test_terminal_stderr_must_be_safe_json_not_human_text(self) -> None:
        diagnostic = (
            '{"run_id":"' + RUN_ID + '","source_id":"bdns",'
            '"status":"failed","error_code":"runner_failure"}'
        )
        self.assertEqual(validate_runner_result("", diagnostic, 1)["status"], "failed")
        with self.assertRaisesRegex(WorkflowSafetyError, "runner_result_not_json"):
            validate_runner_result("", "usage: runner --mode ...", 1)

    def test_success_non_error_diagnostic_and_neutral_summary(self) -> None:
        code = "electronic_office_dropped_invalid_url"
        result = dict(run_id=RUN_ID, source_id="bdns", status="complete_success", error_code=None,
            metrics={"errors": 0}, request_count=3, http_statuses=[200], safe_diagnostics={code: 2})
        self.assertEqual(validate_runner_result(json.dumps(result), "", 0), result)
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            write_runner_summary(summary, result, 0)
            text = summary.read_text(encoding="utf-8")
            self.assertIn("electronic_office descartado por no cumplir el contrato de URL: 2", text)
            self.assertNotIn("Failure position", text)
            self.assertNotIn(RUN_ID, text)
            self.assertNotIn("https://", text)
        failure = dict(run_id=RUN_ID, source_id="bdns", status="source_failure", error_code="item_ingestion_failure",
            safe_detail_reason="enrichment_invalid_url", safe_field_class="extracts", failure_position=2,
            safe_diagnostics={code: 1})
        self.assertEqual(validate_runner_result(json.dumps(failure), "", 1), failure)
        self.assertEqual(validate_runner_result(json.dumps({**result, "safe_diagnostics": {code: 0}}), "", 0)["safe_diagnostics"], {code: 0})

    def test_non_error_diagnostics_reject_arbitrary_keys_counts_and_payload(self) -> None:
        code = "electronic_office_dropped_invalid_url"
        result = dict(run_id=RUN_ID, source_id="bdns", status="complete_success", error_code=None,
            metrics={"errors": 0}, request_count=3, http_statuses=[200])
        invalid = ({"unknown_source_value": 1}, {code: -1}, {code: True}, {code: 1.5},
            {code: "https://example.invalid/private"}, {code: {"raw": "private"}}, [code], None,
            {code: 1, "record_id": 1})
        for value in invalid:
            with self.subTest(shape=type(value).__name__), self.assertRaisesRegex(WorkflowSafetyError, "runner_safe_diagnostics_invalid"):
                validate_runner_result(json.dumps({**result, "safe_diagnostics": value}), "", 0)

    def test_only_canonical_bdns_json_paths_and_non_deletions_are_allowed(self) -> None:
        allowed = (
            ("A", "data/records/bdns/r-example.json"),
            ("A", "data/events/bdns/r-example/evt-v1-" + "a" * 64 + ".json"),
            ("A", "data/manifests/bdns/2026/09/" + RUN_ID + ".json"),
            ("M", "data/health/bdns.json"),
        )
        self.assertEqual(len(validate_changed_entries(allowed)), 4)
        for entry in (
            ("D", "data/records/bdns/r-example.json"),
            ("A", "data/records/boe/r-example.json"),
            ("A", "site/dist/index.html"),
            ("A", "data/records/bdns/README.md"),
            ("M", "data/health/boe.json"),
        ):
            with self.subTest(entry=entry), self.assertRaises(WorkflowSafetyError):
                validate_changed_entries((entry,))

    def test_remote_race_requires_automatic_boe_commit_and_data_only_paths(self) -> None:
        self.assertEqual(
            validate_remote_boe_commit(
                "data(boe): collect 2026-09-29",
                (("M", "data/health/boe.json"), ("A", "data/manifests/boe/2026/09/run.json")),
            ),
            ("data/health/boe.json", "data/manifests/boe/2026/09/run.json"),
        )
        for subject, entries in (
            ("docs: update project", (("M", "data/health/boe.json"),)),
            ("data(boe): collect 2026-09-29", (("M", "docs/PROJECT_STATE.md"),)),
            ("data(boe): collect 2026-09-29", (("D", "data/records/boe/r-old.json"),)),
            ("data(boe): collect 2026-09-29", (("M", "data/records/bdns/r-other.json"),)),
        ):
            with self.subTest(subject=subject, entries=entries), self.assertRaises(WorkflowSafetyError):
                validate_remote_boe_commit(subject, entries)

    def test_full_generated_bdns_artifact_set_validates_offline(self) -> None:
        search_payload = json.loads((FIXTURES / "search_success.json").read_text(encoding="utf-8"))
        detail_payload = json.loads(
            (FIXTURES / "detail_success.json").read_text(encoding="utf-8"), parse_float=Decimal
        )
        detail_payload["regiones"] = [{"descripcion": "ES522 - Castellón / Castelló"}]
        page = parse_bdns_search(search_payload)
        detail = parse_bdns_detail(detail_payload)
        page = replace(
            page,
            items=(page.items[0],),
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

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "schemas").mkdir()
            for schema in ("record.schema.json", "event.schema.json", "run-manifest.schema.json", "source-health.schema.json"):
                shutil.copyfile(ROOT / "schemas" / schema, root / "schemas" / schema)
            attribution = root / "data" / "records" / "bdns" / "README.md"
            attribution.parent.mkdir(parents=True)
            attribution.write_text("\n".join(BDNS_ATTRIBUTION_REQUIREMENTS), encoding="utf-8")
            gate = PrivacyGate.default()
            result = run_bdns_productive_collection(
                mode="complete_scope",
                from_date=date(2026, 9, 1),
                through_date=date(2026, 9, 29),
                started_at=STARTED_AT,
                run_id=RUN_ID,
                clock=lambda: STARTED_AT.replace(second=10),
                transport=_FixtureTransport(page, detail),
                record_store=RecordStore(root / "data" / "records", privacy_gate=gate),
                event_store=EventStore(root / "data" / "events"),
                manifest_store=ManifestStore(root / "data" / "manifests"),
                health_path=root / "data" / "health" / "bdns.json",
                privacy_gate=gate,
            )
            paths = []
            for directory in (
                root / "data" / "records" / "bdns",
                root / "data" / "events" / "bdns",
                root / "data" / "manifests" / "bdns",
            ):
                paths.extend(path.relative_to(root).as_posix() for path in directory.rglob("*.json"))
            paths.append("data/health/bdns.json")
            entries = tuple(("A", path) for path in paths)
            self.assertEqual(result.status, "complete_success")
            self.assertEqual(len(validate_generated_artifacts(root, entries, result.to_dict())), 4)
            with_diagnostic = {**result.to_dict(), "safe_diagnostics": {"electronic_office_dropped_invalid_url": 1}}
            validated = validate_runner_result(json.dumps(with_diagnostic), "", 0)
            self.assertEqual(len(validate_generated_artifacts(root, entries, validated)), 4)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
