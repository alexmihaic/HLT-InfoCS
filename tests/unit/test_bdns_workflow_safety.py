"""Pruebas offline de los controles de publicación manual de BDNS."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bdns.workflow_safety import (  # noqa: E402
    WorkflowSafetyError,
    validate_changed_entries,
    validate_generated_artifacts,
    validate_inputs,
    validate_remote_boe_commit,
    validate_runner_result,
)
from infocs.fetch.bdns.ingest import BDNS_ATTRIBUTION_REQUIREMENTS  # noqa: E402
from infocs.fetch.bdns.models import BDNSFetchResult, BDNSRequestStatus  # noqa: E402
from infocs.fetch.bdns.parser import parse_bdns_detail, parse_bdns_search  # noqa: E402
from infocs.fetch.bdns.runner import run_bdns_productive_collection  # noqa: E402
from infocs.events import EventStore  # noqa: E402
from infocs.manifests import ManifestStore  # noqa: E402
from infocs.privacy import PrivacyGate  # noqa: E402
from infocs.store import RecordStore  # noqa: E402


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


class BDNSWorkflowSafetyTests(unittest.TestCase):
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

    def test_terminal_stderr_must_be_safe_json_not_human_text(self) -> None:
        diagnostic = (
            '{"run_id":"' + RUN_ID + '","source_id":"bdns",'
            '"status":"failed","error_code":"runner_failure"}'
        )
        self.assertEqual(validate_runner_result("", diagnostic, 1)["status"], "failed")
        with self.assertRaisesRegex(WorkflowSafetyError, "runner_result_not_json"):
            validate_runner_result("", "usage: runner --mode ...", 1)

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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
