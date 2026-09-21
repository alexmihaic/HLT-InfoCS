"""Pruebas offline del transporte y parser del sumario diario BOE."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.boe import BOEContractError, BOEFetchStatus, BOETransport, parse_boe_summary
from infocs.fetch.boe.config import BOE_ACCEPT, BOE_USER_AGENT, validate_boe_url


FIXTURE = ROOT / "collectors" / "boe" / "fixtures" / "summary_20240529_minimal.json"


def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.status = status
        self.body = body
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self.read_limit: int | None = None

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_limit = size
        return self.body if size < 0 else self.body[:size]


class FakeOpener:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.request = None
        self.timeout = None

    def __call__(self, request, timeout: float):  # type: ignore[no-untyped-def]
        self.request = request
        self.timeout = timeout
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def json_response(data: dict, *, status: int = 200, content_type: str = "application/json") -> FakeResponse:
    return FakeResponse(status, json.dumps(data).encode("utf-8"), content_type)


class BOEParserTests(unittest.TestCase):
    def test_real_truncated_fixture_preserves_documented_fields_and_status_type(self) -> None:
        raw = payload()
        self.assertIsInstance(raw["status"]["code"], str)
        self.assertEqual(raw["status"]["code"], "200")

        summary = parse_boe_summary(raw)
        self.assertEqual(summary.publication_date.isoformat(), "2024-05-29")
        self.assertEqual(summary.diaries[0].number, "130")
        item = summary.items[0]
        self.assertEqual(item.official_id, "BOE-A-2024-10761")
        self.assertEqual(item.section_code, "1")
        self.assertEqual(item.section_name, "I. Disposiciones generales")
        self.assertEqual(item.department_code, "9562")
        self.assertEqual(item.heading_name, "Tratados internacionales")
        self.assertEqual(item.documents.pdf_size_bytes, 263064)
        self.assertEqual(item.documents.pdf_first_page, 61912)
        self.assertTrue(item.documents.xml_url.endswith("BOE-A-2024-10761"))

    def test_optional_fields_are_absent_not_invented(self) -> None:
        raw = payload()
        item = raw["data"]["sumario"]["diario"][0]["seccion"][0]["departamento"][0]["epigrafe"][0]["item"]
        item.pop("control")
        for field in ("szBytes", "szKBytes", "pagina_inicial", "pagina_final"):
            item["url_pdf"].pop(field)

        parsed = parse_boe_summary(raw).items[0]
        self.assertIsNone(parsed.control)
        self.assertIsNone(parsed.documents.pdf_size_bytes)
        self.assertIsNone(parsed.documents.pdf_last_page)

    def test_multiple_diaries_sections_and_direct_items_preserve_collection_order(self) -> None:
        raw = payload()
        diary = raw["data"]["sumario"]["diario"][0]
        direct = deepcopy(diary["seccion"][0]["departamento"][0]["epigrafe"][0]["item"])
        direct["identificador"] = "BOE-A-2024-90001"
        diary["seccion"][0]["departamento"][0]["item"] = direct

        second_section = deepcopy(diary["seccion"][0])
        second_section["codigo"] = "2A"
        second_section["nombre"] = "II. Autoridades y personal"
        second_section["departamento"][0]["epigrafe"][0]["item"]["identificador"] = "BOE-A-2024-90002"
        diary["seccion"].append(second_section)

        second_diary = deepcopy(diary)
        second_diary["numero"] = "131"
        second_diary["seccion"][0]["departamento"][0]["item"]["identificador"] = "BOE-A-2024-90003"
        raw["data"]["sumario"]["diario"].append(second_diary)

        summary = parse_boe_summary(raw)
        self.assertEqual(tuple(diary.number for diary in summary.diaries), ("130", "131"))
        self.assertEqual(tuple(section.code for section in summary.diaries[0].sections), ("1", "2A"))
        self.assertEqual(summary.items[0].official_id, "BOE-A-2024-90001")
        self.assertEqual(summary.items[1].official_id, "BOE-A-2024-10761")

    def test_non_success_status_and_incomplete_structure_are_rejected(self) -> None:
        non_success = payload()
        non_success["status"]["code"] = "500"
        with self.assertRaises(BOEContractError):
            parse_boe_summary(non_success)

        incomplete = payload()
        del incomplete["data"]["sumario"]
        with self.assertRaises(BOEContractError):
            parse_boe_summary(incomplete)


class BOETransportTests(unittest.TestCase):
    def fetch(self, response: FakeResponse | None = None, error: Exception | None = None, **options):
        opener = FakeOpener(response, error)
        transport = BOETransport(opener=opener, **options)
        return transport.fetch_daily_summary("20240529"), opener

    def test_200_valid_json_is_complete_success_with_required_headers(self) -> None:
        result, opener = self.fetch(json_response(payload()))
        self.assertEqual(result.status, BOEFetchStatus.COMPLETE_SUCCESS)
        self.assertIsNotNone(result.summary)
        self.assertEqual(opener.request.get_header("Accept"), BOE_ACCEPT)
        self.assertEqual(opener.request.get_header("User-agent"), BOE_USER_AGENT)
        self.assertEqual(opener.timeout, 15.0)

    def test_200_with_payload_failure_or_invalid_json_is_source_failure(self) -> None:
        non_success = payload()
        non_success["status"]["code"] = "500"
        for response, reason in (
            (json_response(non_success), "invalid_payload"),
            (FakeResponse(200, b"not-json"), "invalid_json"),
            (json_response(payload(), content_type="text/html"), "mime_incompatible"),
        ):
            with self.subTest(reason=reason):
                result, _ = self.fetch(response)
                self.assertEqual(result.status, BOEFetchStatus.SOURCE_FAILURE)
                self.assertEqual(result.reason, reason)
                self.assertIsNone(result.summary)

    def test_http_statuses_have_explicit_non_reconciliation_semantics(self) -> None:
        cases = (
            (404, BOEFetchStatus.NO_DAILY_PUBLICATION, "daily_summary_not_found"),
            (400, BOEFetchStatus.INVALID_REQUEST, "invalid_request"),
            (500, BOEFetchStatus.SOURCE_FAILURE, "http_failure"),
            (302, BOEFetchStatus.SOURCE_FAILURE, "http_failure"),
        )
        for status, expected, reason in cases:
            with self.subTest(status=status):
                result, _ = self.fetch(FakeResponse(status, b""))
                self.assertEqual(result.status, expected)
                self.assertEqual(result.reason, reason)
                self.assertIsNone(result.summary)

    def test_body_limit_host_allowlist_and_timeout_fail_safely(self) -> None:
        result, opener = self.fetch(json_response(payload()), max_response_bytes=20)
        self.assertEqual(result.status, BOEFetchStatus.SOURCE_FAILURE)
        self.assertEqual(result.reason, "body_too_large")
        self.assertIsNone(result.summary)
        self.assertIsNone(opener.response.read_limit)

        with self.assertRaises(ValueError):
            validate_boe_url("https://example.test/not-boe")
        with self.assertRaises(ValueError):
            validate_boe_url("http://www.boe.es/datosabiertos/api/boe/sumario/20240529")

        timeout_result, _ = self.fetch(error=TimeoutError())
        self.assertEqual(timeout_result.status, BOEFetchStatus.SOURCE_FAILURE)
        self.assertEqual(timeout_result.reason, "network_failure")
