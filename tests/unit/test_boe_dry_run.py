"""Pruebas offline del BOE Live Dry Run y su frontera anti-write."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
import ast
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.boe.dry_run import dry_run_boe_date
from infocs.fetch.boe.models import (
    BOEDepartment,
    BOEDiary,
    BOEDocumentLinks,
    BOEFetchResult,
    BOEFetchStatus,
    BOEItem,
    BOESection,
    BOESummary,
)
from infocs.fetch.boe.territorial import load_castellon_registry
from infocs.privacy import PrivacyConfig, PrivacyDecisionType, PrivacyGate
from infocs.store import RecordStore


OBSERVED_AT = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
PUBLICATION_DATE = date(2026, 9, 18)


def make_summary(
    title: str = "Anuncio ficticio en Segorbe",
    *,
    section_code: str = "1",
    official_id: str = "BOE-A-2099-99001",
    department_name: str = "Departamento administrativo ficticio",
) -> BOESummary:
    item = BOEItem(
        official_id=official_id,
        title=title,
        section_code=section_code,
        section_name="Sección ficticia",
        department_code="001",
        department_name=department_name,
        published_on=PUBLICATION_DATE,
        documents=BOEDocumentLinks(
            xml_url="https://www.boe.es/diario_boe/xml.php?id=BOE-A-2099-99001",
            html_url="https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-99001",
            pdf_url="https://www.boe.es/boe/dias/2099/01/01/pdfs/BOE-A-2099-99001.pdf",
        ),
    )
    department = BOEDepartment("001", department_name, (), (item,))
    section = BOESection(section_code, "Sección ficticia", (department,))
    return BOESummary(PUBLICATION_DATE, (BOEDiary("1", (section,)),))


class FakeTransport:
    def __init__(self, result: BOEFetchResult | Exception) -> None:
        self.result = result
        self.calls: list[date] = []

    def fetch_daily_summary(self, publication_date: date) -> BOEFetchResult:
        self.calls.append(publication_date)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def fetch_result(
    status: BOEFetchStatus = BOEFetchStatus.COMPLETE_SUCCESS,
    summary: BOESummary | None = None,
    http_status: int | None = 200,
    reason: str | None = None,
) -> BOEFetchResult:
    return BOEFetchResult(status, http_status, summary=summary, reason=reason)


class BOEDryRunTests(unittest.TestCase):
    def run_dry(
        self,
        result: BOEFetchResult | Exception,
        *,
        summary: BOESummary | None = None,
        gate: PrivacyGate | None = None,
    ):
        transport = FakeTransport(result)
        dry = dry_run_boe_date(
            PUBLICATION_DATE,
            detected_at=OBSERVED_AT,
            last_checked_at=OBSERVED_AT,
            registry=load_castellon_registry(),
            privacy_gate=gate,
            transport=transport,  # type: ignore[arg-type]
        )
        return dry, transport

    def test_allowed_pipeline_is_deterministic_and_reports_identity_checks(self) -> None:
        source = fetch_result(summary=make_summary())
        first, transport = self.run_dry(source)
        second, _ = self.run_dry(source)
        self.assertEqual(transport.calls, [PUBLICATION_DATE])
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.transport_status, "complete_success")
        self.assertEqual(first.metrics.to_dict(), {
            "seen": 1, "included": 1, "excluded": 0, "normalized": 1,
            "finalized": 1, "privacy_allowed": 1, "privacy_quarantined": 0,
            "privacy_rejected": 0, "unprocessed": 0,
        })
        self.assertEqual(dict(first.identity_checks), {
            "official_id_strategy_count": 1,
            "fallback_count": 0,
            "record_id_collision_count": 0,
        })
        self.assertTrue(first.content_hash_stable)
        row = first.items[0].to_dict()
        self.assertEqual(row["identity_strategy"], "official_id")
        self.assertEqual(row["category"], "regulation")
        self.assertEqual(row["authority_name"], "Departamento administrativo ficticio")

    def test_excluded_item_counts_without_candidate(self) -> None:
        result, _ = self.run_dry(
            fetch_result(summary=make_summary("Anuncio estatal genérico"))
        )
        self.assertEqual(result.metrics.seen, 1)
        self.assertEqual(result.metrics.included, 0)
        self.assertEqual(result.metrics.excluded, 1)
        self.assertEqual(result.metrics.normalized, 0)
        self.assertEqual(result.metrics.finalized, 0)
        self.assertEqual(result.items, ())

    def test_quarantine_report_omits_sensitive_title_and_value(self) -> None:
        secret = "12345678Z"
        summary = make_summary(f"Anuncio en Segorbe. DNI personal {secret}")
        result, _ = self.run_dry(fetch_result(summary=summary))
        self.assertEqual(result.metrics.privacy_quarantined, 1)
        row = result.items[0].to_dict()
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertEqual(row["official_id"], "BOE-A-2099-99001")
        self.assertEqual(row["privacy_decision"], "quarantine")
        self.assertNotIn("title", row)
        self.assertNotIn(secret, serialized)

    def test_reject_is_counted_and_redacted_in_audit_view(self) -> None:
        payload = json.loads((ROOT / "config" / "privacy-rules.json").read_text(encoding="utf-8"))
        payload["rules"]["spanish_personal_identifier"]["decision"] = "reject"
        gate = PrivacyGate(PrivacyConfig.from_mapping(payload))
        result, _ = self.run_dry(
            fetch_result(summary=make_summary("Anuncio en Segorbe DNI 12345678Z")), gate=gate
        )
        self.assertEqual(result.metrics.privacy_rejected, 1)
        self.assertEqual(result.items[0].privacy_decision, PrivacyDecisionType.REJECT)
        self.assertNotIn("12345678Z", json.dumps(result.to_dict()))

    def test_no_daily_publication_is_success_without_errors_or_records(self) -> None:
        result, _ = self.run_dry(fetch_result(BOEFetchStatus.NO_DAILY_PUBLICATION, http_status=404))
        self.assertEqual(result.transport_status, "no_daily_publication")
        self.assertEqual(result.http_status, 404)
        self.assertEqual(result.metrics.to_dict(), {
            "seen": 0, "included": 0, "excluded": 0, "normalized": 0,
            "finalized": 0, "privacy_allowed": 0, "privacy_quarantined": 0,
            "privacy_rejected": 0, "unprocessed": 0,
        })
        self.assertEqual(result.errors, ())

    def test_summary_for_different_publication_date_is_contract_failure(self) -> None:
        # La fixture helper usa el 18; procesar la misma respuesta como 19 no
        # está permitido aunque el cuerpo y el transporte sean estructuralmente válidos.
        result = dry_run_boe_date(
            date(2026, 9, 19),
            detected_at=OBSERVED_AT,
            last_checked_at=OBSERVED_AT,
            registry=load_castellon_registry(),
            transport=FakeTransport(fetch_result(summary=make_summary())),  # type: ignore[arg-type]
        )
        self.assertEqual(result.transport_status, "source_failure")
        self.assertEqual(result.errors[0].stage, "parser")
        self.assertEqual(result.errors[0].error_type, "PublicationDateMismatch")
        self.assertEqual(result.metrics.seen, 0)

    def test_transport_failures_and_invalid_request_have_zero_metrics(self) -> None:
        for status in (BOEFetchStatus.SOURCE_FAILURE, BOEFetchStatus.INVALID_REQUEST):
            with self.subTest(status=status.value):
                result, _ = self.run_dry(fetch_result(status, http_status=500, reason="safe_reason"))
                self.assertEqual(result.transport_status, status.value)
                self.assertEqual(result.metrics.seen, 0)
                self.assertEqual(result.errors[0].stage, "transport")

    def test_unexpected_transport_exception_is_reported_without_message(self) -> None:
        secret = "DNI 12345678Z"
        result, _ = self.run_dry(RuntimeError(secret))
        self.assertEqual(result.errors[0].error_type, "RuntimeError")
        self.assertNotIn(secret, json.dumps(result.to_dict()))

    def test_normalizer_failure_is_reported_by_stage_without_record_payload(self) -> None:
        summary = make_summary()
        department = summary.diaries[0].sections[0].departments[0]
        item = department.direct_items[0]
        bad_item = replace(item, department_name="")
        bad_summary = BOESummary(
            summary.publication_date,
            (BOEDiary("1", (BOESection("1", "Sección", (
                BOEDepartment("001", "", (), (bad_item,)),
            )),)),),
        )
        result, _ = self.run_dry(fetch_result(summary=bad_summary))
        self.assertEqual(result.metrics.included, 1)
        self.assertEqual(result.metrics.normalized, 0)
        self.assertEqual(result.errors[0].stage, "normalization")
        self.assertEqual(result.errors[0].official_id, item.official_id)

    def test_privacy_exception_fails_closed_and_does_not_leak_message(self) -> None:
        class BrokenGate(PrivacyGate):
            def evaluate(self, record):  # type: ignore[no-untyped-def]
                raise RuntimeError("sensible DNI 12345678Z")

        result, _ = self.run_dry(
            fetch_result(summary=make_summary()), gate=BrokenGate()
        )
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertEqual(result.metrics.privacy_allowed, 0)
        self.assertEqual(result.metrics.privacy_quarantined, 0)
        self.assertEqual(result.errors[0].stage, "privacy")
        self.assertNotIn("12345678Z", payload)

    def test_generic_province_match_is_flagged_suspicious_not_rewritten(self) -> None:
        result, _ = self.run_dry(
            fetch_result(summary=make_summary("Convocatoria general en Castellón"))
        )
        match = result.items[0].territorial_matches[0]
        self.assertEqual(match["reason"], "province_exact")
        self.assertEqual(match["audit"], "suspicious_match")
        self.assertEqual(match["entity_code"], "12")

    def test_compound_city_variant_is_expected_municipality_12040(self) -> None:
        result, _ = self.run_dry(
            fetch_result(summary=make_summary("Anuncio en Castellón de la Plana"))
        )
        matches = result.items[0].territorial_matches
        city = next(match for match in matches if match["reason"] == "municipality_exact")
        self.assertEqual(city["entity_code"], "12040")
        self.assertEqual(city["audit"], "expected_match")
        self.assertEqual(result.items[0].geography_municipality, "Castelló de la Plana/Castellón de la Plana")

    def test_dry_run_has_no_store_parameter_or_import_and_never_calls_write(self) -> None:
        self.assertNotIn("store", inspect.signature(dry_run_boe_date).parameters)
        module_path = Path(inspect.getsourcefile(dry_run_boe_date) or "")
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        store_imports = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "infocs.store"
        ]
        self.assertEqual(store_imports, [])
        with patch.object(RecordStore, "write", side_effect=AssertionError("write attempted")) as write:
            self.run_dry(fetch_result(summary=make_summary()))
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
