"""Pruebas offline del runner manual BOE y barreras del workflow."""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path
import argparse
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.events import EventStore
from infocs.fetch.boe.models import (
    BOEDepartment,
    BOEDiary,
    BOEDocumentLinks,
    BOEFetchResult,
    BOEFetchStatus,
    BOEHeading,
    BOEItem,
    BOESection,
    BOESummary,
)
from infocs.fetch.boe.runner import parse_requested_date, resolve_collection_date, run_boe_collection, runner_exit_code
from infocs.fetch.boe.territorial import load_castellon_registry
from infocs.fetch.boe.workflow_safety import (
    WorkflowSafetyError,
    validate_changed_paths,
    validate_generated_artifacts,
)
from infocs.manifests import ManifestStore, RunStatus, SoftwareMetadata, write_source_health
from infocs.privacy import PrivacyGate
from infocs.publication.review import PublicationReviewConfig
from infocs.store import RecordStore


START = datetime(2026, 9, 18, 7, 0, tzinfo=UTC)
FINISH = datetime(2026, 9, 18, 7, 1, tzinfo=UTC)
RUN_ID = "run-v1-00000000-0000-4000-8000-000000000018"
OFFICIAL_ID = "BOE-A-2099-1801"


def fetched(
    status: BOEFetchStatus = BOEFetchStatus.COMPLETE_SUCCESS,
    *, title: str = "Resolución relativa a Borriana",
) -> BOEFetchResult:
    if status is not BOEFetchStatus.COMPLETE_SUCCESS:
        return BOEFetchResult(status, 503 if status is BOEFetchStatus.SOURCE_FAILURE else 404, reason="synthetic")
    item = BOEItem(
        official_id=OFFICIAL_ID,
        title=title,
        section_code="1",
        section_name="I. Disposiciones generales",
        department_code="9999",
        department_name="MINISTERIO DE EJEMPLO",
        published_on=date(2026, 9, 18),
        documents=BOEDocumentLinks(
            xml_url=f"https://www.boe.es/doc.xml?id={OFFICIAL_ID}",
            html_url=f"https://www.boe.es/doc.html?id={OFFICIAL_ID}",
            pdf_url=f"https://www.boe.es/doc.pdf?id={OFFICIAL_ID}",
        ),
    )
    department = BOEDepartment("9999", "MINISTERIO DE EJEMPLO", (BOEHeading("Avisos", (item,)),), ())
    section = BOESection("1", "I. Disposiciones generales", (department,))
    summary = BOESummary(date(2026, 9, 18), (BOEDiary("1", (section,)),))
    return BOEFetchResult(status, 200, summary=summary)


def review_config(*, approved: bool = True) -> PublicationReviewConfig:
    records = ([{"official_id": OFFICIAL_ID, "decision": "approved", "reason_code": "reviewed_safe"}]
               if approved else [])
    return PublicationReviewConfig.from_mapping({"schema_version": "1", "source_id": "boe", "records": records})


class BOERunnerTests(unittest.TestCase):
    def run_in_temp(self, response: BOEFetchResult, *, approved: bool = True, record_store=None, run_id=RUN_ID, transport=None):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        gate = PrivacyGate.default()
        stores = {
            "record_store": record_store or RecordStore(root / "records", privacy_gate=gate),
            "event_store": EventStore(root / "events"),
            "manifest_store": ManifestStore(root / "manifests"),
            "health_path": root / "health" / "boe.json",
            "review_queue_path": root / "review" / "boe" / "pending.json",
            "privacy_gate": gate,
        }
        transport = transport or SimpleNamespace(fetch_daily_summary=lambda requested_date: response)
        result = run_boe_collection(
            date(2026, 9, 18),
            started_at=START,
            run_id=run_id,
            clock=lambda: FINISH,
            transport=transport,
            review_config=review_config(approved=approved),
            software_metadata=SoftwareMetadata("0.1.0", source_contract_version="1"),
            **stores,
        )
        return root, result, stores

    def test_success_persists_record_event_manifest_and_derived_health(self) -> None:
        root, result, stores = self.run_in_temp(fetched())
        self.assertEqual(result.status.value, "complete_success")
        self.assertEqual(len(stores["record_store"].list_source("boe")), 1)
        self.assertEqual(len(stores["event_store"].list_source("boe")), 1)
        manifest = stores["manifest_store"].get(RUN_ID)
        self.assertEqual(manifest.status, RunStatus.SUCCESS)
        self.assertEqual(manifest.metrics.created, 1)
        health = json.loads((root / "health" / "boe.json").read_text(encoding="utf-8"))
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["last_run_id"], RUN_ID)

    def test_no_publication_writes_manifest_and_healthy_health_only(self) -> None:
        root, result, stores = self.run_in_temp(fetched(BOEFetchStatus.NO_DAILY_PUBLICATION))
        manifest = stores["manifest_store"].get(RUN_ID)
        self.assertEqual(result.status.value, "no_daily_publication")
        self.assertEqual(manifest.status, RunStatus.NO_PUBLICATION)
        self.assertEqual(manifest.metrics.seen, 0)
        self.assertEqual(stores["record_store"].list_source("boe"), ())
        self.assertEqual(stores["event_store"].list_source("boe"), ())
        self.assertEqual(json.loads((root / "health" / "boe.json").read_text())["status"], "healthy")

    def test_source_failure_writes_failed_manifest_and_degraded_health_without_data(self) -> None:
        root, result, stores = self.run_in_temp(fetched(BOEFetchStatus.SOURCE_FAILURE))
        manifest = stores["manifest_store"].get(RUN_ID)
        self.assertEqual(result.status.value, "source_failure")
        self.assertEqual(manifest.status, RunStatus.FAILED)
        self.assertEqual(manifest.metrics.errors, 1)
        self.assertEqual(stores["record_store"].list_source("boe"), ())
        self.assertEqual(stores["event_store"].list_source("boe"), ())
        self.assertEqual(json.loads((root / "health" / "boe.json").read_text())["status"], "degraded")

    def test_unexpected_transport_exception_still_writes_safe_failed_observability(self) -> None:
        class BrokenTransport:
            def fetch_daily_summary(self, requested_date):
                raise RuntimeError("private payload DNI 12345678Z")

        root, _, stores = self.run_in_temp(fetched(), transport=BrokenTransport())
        manifest_path = stores["manifest_store"].path_for(stores["manifest_store"].get(RUN_ID))
        self.assertEqual(stores["manifest_store"].get(RUN_ID).status, RunStatus.FAILED)
        self.assertNotIn("12345678Z", manifest_path.read_text(encoding="utf-8"))
        self.assertTrue((root / "health" / "boe.json").is_file())

    def test_publication_hold_writes_observability_but_no_record_or_event(self) -> None:
        root, result, stores = self.run_in_temp(fetched(), approved=False)
        self.assertEqual(result.metrics.privacy_allowed, 1)
        self.assertEqual(result.metrics.publication_hold, 1)
        self.assertEqual(stores["manifest_store"].get(RUN_ID).metrics.publication_hold, 1)
        self.assertEqual(stores["record_store"].list_source("boe"), ())
        self.assertEqual(stores["event_store"].list_source("boe"), ())
        pending_path = root / "review" / "boe" / "pending.json"
        payload = json.loads(pending_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["records"][0]["official_id"], OFFICIAL_ID)
        self.assertEqual(payload["records"][0]["reason_code"], "not_in_allowlist")
        self.assertNotIn("Resolución relativa a Borriana", pending_path.read_text(encoding="utf-8"))

    def test_privacy_quarantine_never_enters_review_queue(self) -> None:
        root, result, stores = self.run_in_temp(
            fetched(title="Resolución relativa a Borriana con DNI 12345678Z"), approved=False,
        )
        queue_path = root / "review" / "boe" / "pending.json"
        self.assertEqual(result.metrics.privacy_quarantined, 1)
        self.assertEqual(result.metrics.publication_hold, 0)
        self.assertEqual(stores["record_store"].list_source("boe"), ())
        self.assertEqual(stores["event_store"].list_source("boe"), ())
        self.assertEqual(json.loads(queue_path.read_text(encoding="utf-8"))["records"], [])
        self.assertNotIn("12345678Z", queue_path.read_text(encoding="utf-8"))

    def test_approved_no_change_writes_no_new_event(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            gate = PrivacyGate.default()
            record_store = RecordStore(root / "records", privacy_gate=gate)
            self.run_in_temp(fetched(), record_store=record_store, run_id="run-v1-00000000-0000-4000-8000-000000000017")
            _, result, stores = self.run_in_temp(fetched(), record_store=record_store)
            self.assertEqual(result.metrics.unchanged, 1)
            self.assertEqual(result.events, ())
            self.assertEqual(len(stores["event_store"].list_source("boe")), 0)


class RunnerContractTests(unittest.TestCase):
    def test_date_input_is_strict(self) -> None:
        self.assertEqual(parse_requested_date("2026-09-18"), date(2026, 9, 18))
        for invalid in ("20260918", "2026-9-18", "2026-02-30", "today", "2026-09-18..19"):
            with self.subTest(invalid=invalid), self.assertRaises(argparse.ArgumentTypeError):
                parse_requested_date(invalid)

    def test_today_uses_europe_madrid_date_from_single_aware_timestamp(self) -> None:
        from infocs.fetch.boe.runner import BOERunnerError

        just_before_madrid_midnight = datetime(2026, 9, 22, 21, 59, tzinfo=UTC)
        at_madrid_midnight = datetime(2026, 9, 22, 22, 0, tzinfo=UTC)
        self.assertEqual(
            resolve_collection_date(date_value=None, use_today=True, now=just_before_madrid_midnight),
            date(2026, 9, 22),
        )
        self.assertEqual(
            resolve_collection_date(date_value=None, use_today=True, now=at_madrid_midnight),
            date(2026, 9, 23),
        )
        with self.assertRaises(BOERunnerError):
            resolve_collection_date(date_value="2026-09-23", use_today=True, now=at_madrid_midnight)

    def test_resolved_date_is_exposed_as_safe_github_step_output(self) -> None:
        from unittest.mock import patch
        from infocs.fetch.boe.runner import _write_requested_date_output

        with TemporaryDirectory() as directory:
            output_path = Path(directory) / "github-output.txt"
            with patch.dict("os.environ", {"GITHUB_OUTPUT": str(output_path)}):
                _write_requested_date_output(date(2026, 9, 23))
            self.assertEqual(output_path.read_text(encoding="utf-8"), "requested_date=2026-09-23\n")

    def test_failed_status_has_nonzero_workflow_exit_code(self) -> None:
        self.assertEqual(runner_exit_code(RunStatus.FAILED), 1)
        self.assertEqual(runner_exit_code(RunStatus.SUCCESS), 0)
        self.assertEqual(runner_exit_code(RunStatus.NO_PUBLICATION), 0)

    def test_workflow_has_manual_and_timezone_aware_schedule_without_push_trigger(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "boe-manual.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("required: true", workflow)
        self.assertIn("schedule:", workflow)
        self.assertIn("cron: '17 12 * * *'", workflow)
        self.assertIn("timezone: 'Europe/Madrid'", workflow)
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("actions/checkout@v7", workflow)
        self.assertIn("actions/setup-python@v7", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertNotIn("push:", workflow)

    def test_workflow_path_allowlist_is_fail_closed(self) -> None:
        self.assertEqual(
            validate_changed_paths(["data/manifests/boe/2026/09/run-v1-abc.json", "data/health/boe.json"]),
            ("data/health/boe.json", "data/manifests/boe/2026/09/run-v1-abc.json"),
        )
        self.assertEqual(
            validate_changed_paths(["data/review/boe/pending.json"]),
            ("data/review/boe/pending.json",),
        )
        for path in ("src/infocs/runner.py", "data/records/../secret.json", r"data\records\x.json", "data/records/note.txt"):
            with self.subTest(path=path), self.assertRaises(WorkflowSafetyError):
                validate_changed_paths([path])

    def test_health_materialization_is_json_with_final_newline(self) -> None:
        from infocs.manifests import HealthStatus, SourceHealth

        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "health" / "boe.json"
            health = SourceHealth("boe", HealthStatus.UNKNOWN, 0)
            write_source_health(path, health)
            raw = path.read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            self.assertEqual(json.loads(raw), health.to_dict())
            self.assertEqual([item.name for item in path.parent.iterdir()], ["boe.json"])

    def test_generated_artifact_validator_checks_schema_and_canonical_health_path(self) -> None:
        from infocs.manifests import HealthStatus, SourceHealth

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "schemas").mkdir()
            shutil.copy2(ROOT / "schemas" / "source-health.schema.json", root / "schemas" / "source-health.schema.json")
            shutil.copy2(ROOT / "schemas" / "review-queue.schema.json", root / "schemas" / "review-queue.schema.json")
            health = SourceHealth("boe", HealthStatus.UNKNOWN, 0)
            path = root / "data" / "health" / "boe.json"
            write_source_health(path, health)
            self.assertEqual(
                validate_generated_artifacts(root, ["data/health/boe.json"]),
                ("data/health/boe.json",),
            )
            with self.assertRaises(WorkflowSafetyError):
                validate_generated_artifacts(root, ["data/health/other.json"])

    def test_generated_review_queue_requires_canonical_path_and_schema(self) -> None:
        from infocs.fetch.boe.review_queue import BOEReviewQueueStore, ReviewQueueEntry, ReviewQueueObservation

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "schemas").mkdir()
            shutil.copy2(ROOT / "schemas" / "review-queue.schema.json", root / "schemas" / "review-queue.schema.json")
            queue_path = root / "data" / "review" / "boe" / "pending.json"
            entry = ReviewQueueEntry(
                "boe", OFFICIAL_ID, f"https://www.boe.es/doc.html?id={OFFICIAL_ID}", "2026-09-18", RUN_ID,
                ("municipality_exact",), ("12040",), "hold", "territorial_review_required",
            )
            BOEReviewQueueStore(queue_path).update((ReviewQueueObservation("boe", OFFICIAL_ID, entry),))
            self.assertEqual(
                validate_generated_artifacts(root, ["data/review/boe/pending.json"]),
                ("data/review/boe/pending.json",),
            )
            with self.assertRaises(WorkflowSafetyError):
                validate_generated_artifacts(root, ["data/review/other/pending.json"])


if __name__ == "__main__":
    unittest.main()
