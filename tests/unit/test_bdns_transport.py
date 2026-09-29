from __future__ import annotations

from decimal import Decimal
from datetime import date
from http.client import HTTPResponse
import json
from pathlib import Path
import socket
import sys
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bdns.config import (
    BDNS_ACCEPT,
    BDNS_MAX_RESPONSE_BYTES,
    BDNS_SEARCH_URL,
    BDNS_USER_AGENT,
    detail_url_for,
    search_url_for,
)
from infocs.fetch.bdns.models import BDNSSearchQuery, BDNSRequestStatus
from infocs.fetch.bdns.transport import BDNSTransport


FIXTURES = ROOT / "tests" / "fixtures" / "bdns"


class FakeResponse:
    def __init__(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.status = status
        self.body = body
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self.read_limit = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):  # type: ignore[no-untyped-def]
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_limit = size
        return self.body[:size] if size >= 0 else self.body


class FakeOpener:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, request, timeout: float):  # type: ignore[no-untyped-def]
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return self.response


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class BDNSUrlTests(unittest.TestCase):
    def test_search_query_uses_only_documented_encoded_parameters(self) -> None:
        query = BDNSSearchQuery(
            page=2,
            page_size=10,
            order="descripcion",
            direction="asc",
            numero_convocatoria="900 001/á",
        )
        url = search_url_for(query)
        self.assertTrue(url.startswith(BDNS_SEARCH_URL + "?"))
        self.assertEqual(
            parse_qs(urlsplit(url).query),
            {
                "page": ["2"],
                "pageSize": ["10"],
                "order": ["descripcion"],
                "direccion": ["asc"],
                "numeroConvocatoria": ["900 001/á"],
            },
        )

    def test_detail_query_is_exactly_numConv(self) -> None:
        self.assertEqual(parse_qs(urlsplit(detail_url_for("900001")).query), {"numConv": ["900001"]})

    def test_region_filter_uses_documented_regiones_parameter(self) -> None:
        query = BDNSSearchQuery(page=0, page_size=3, region_ids=(56,))
        self.assertEqual(
            parse_qs(urlsplit(search_url_for(query)).query),
            {
                "page": ["0"],
                "pageSize": ["3"],
                "order": ["fechaRecepcion"],
                "direccion": ["desc"],
                "regiones": ["56"],
            },
        )

    def test_temporal_filters_use_documented_ddmmyyyy_parameters(self) -> None:
        query = BDNSSearchQuery(
            region_ids=(56,),
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 29),
        )
        self.assertEqual(
            parse_qs(urlsplit(search_url_for(query)).query),
            {
                "page": ["0"],
                "pageSize": ["25"],
                "order": ["fechaRecepcion"],
                "direccion": ["desc"],
                "regiones": ["56"],
                "fechaDesde": ["01/09/2026"],
                "fechaHasta": ["29/09/2026"],
            },
        )

    def test_invalid_temporal_range_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            search_url_for(BDNSSearchQuery(date_from=date(2026, 9, 2), date_to=date(2026, 9, 1)))

    def test_invalid_region_filter_is_rejected_before_any_network_call(self) -> None:
        for region_ids in ((0,), (-1,), (True,), (56, 56), [56]):
            with self.subTest(region_ids=region_ids):
                with self.assertRaises(ValueError):
                    search_url_for(BDNSSearchQuery(region_ids=region_ids))

    def test_invalid_query_rejected_before_any_network_call(self) -> None:
        opener = FakeOpener(FakeResponse(200, fixture_bytes("search_success.json")))
        transport = BDNSTransport(opener=opener)
        result = transport.search(BDNSSearchQuery(page=-1))
        self.assertEqual(result.status, BDNSRequestStatus.INVALID_REQUEST)
        self.assertEqual(opener.calls, [])


class BDNSTransportTests(unittest.TestCase):
    def test_search_success_headers_and_safe_public_access(self) -> None:
        opener = FakeOpener(FakeResponse(200, fixture_bytes("search_success.json")))
        result = BDNSTransport(opener=opener).search(BDNSSearchQuery(page_size=1))
        self.assertEqual(result.status, BDNSRequestStatus.SUCCESS)
        request, timeout = opener.calls[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.get_header("Accept"), BDNS_ACCEPT)
        self.assertEqual(request.get_header("User-agent"), BDNS_USER_AGENT)
        self.assertIsNone(request.get_header("Cookie"))
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(timeout, 15.0)

    def test_empty_search_is_no_results_not_source_failure(self) -> None:
        opener = FakeOpener(FakeResponse(200, fixture_bytes("search_empty.json")))
        result = BDNSTransport(opener=opener).search()
        self.assertEqual(result.status, BDNSRequestStatus.NO_RESULTS)
        self.assertEqual(result.payload.total_elements, 0)

    def test_detail_success_and_external_code_must_match_requested_code(self) -> None:
        opener = FakeOpener(FakeResponse(200, fixture_bytes("detail_success.json")))
        result = BDNSTransport(opener=opener).fetch_detail("900001")
        self.assertEqual(result.status, BDNSRequestStatus.SUCCESS)
        self.assertEqual(result.payload.codigo_bdns, "900001")
        mismatch = BDNSTransport(
            opener=FakeOpener(FakeResponse(200, fixture_bytes("detail_success.json")))
        ).fetch_detail("900009")
        self.assertEqual(mismatch.status, BDNSRequestStatus.SOURCE_FAILURE)
        self.assertEqual(mismatch.reason, "identity_mismatch")

    def test_http_input_rate_limit_server_and_network_failures(self) -> None:
        bad_request = BDNSTransport(opener=FakeOpener(error=HTTPError("https://x.invalid", 400, "", {}, None)))
        self.assertEqual(bad_request.search().status, BDNSRequestStatus.INVALID_REQUEST)
        limited = BDNSTransport(opener=FakeOpener(error=HTTPError("https://x.invalid", 429, "", {}, None)))
        self.assertEqual(limited.search().reason, "rate_limited")
        failed = BDNSTransport(opener=FakeOpener(error=HTTPError("https://x.invalid", 503, "", {}, None)))
        self.assertEqual(failed.search().status, BDNSRequestStatus.SOURCE_FAILURE)
        timed_out = BDNSTransport(opener=FakeOpener(error=socket.timeout()))
        self.assertEqual(timed_out.search().reason, "network_failure")

    def test_mime_invalid_json_and_invalid_contract_are_safe_failures(self) -> None:
        wrong_mime = BDNSTransport(opener=FakeOpener(FakeResponse(200, b"{}", "text/html")))
        self.assertEqual(wrong_mime.search().reason, "mime_incompatible")
        malformed = BDNSTransport(opener=FakeOpener(FakeResponse(200, fixture_bytes("malformed.json"))))
        self.assertEqual(malformed.search().reason, "invalid_json")
        contract = BDNSTransport(opener=FakeOpener(FakeResponse(200, b'{"content":[{}]}')))
        self.assertEqual(contract.search().reason, "invalid_payload")
        self.assertNotIn("campoFuturo", contract.search().reason)

    def test_response_cap_applies_with_and_without_content_length(self) -> None:
        declared = FakeResponse(200, b"{}")
        declared.headers["Content-Length"] = str(BDNS_MAX_RESPONSE_BYTES + 1)
        self.assertEqual(
            BDNSTransport(opener=FakeOpener(declared), max_response_bytes=32).search().reason,
            "body_too_large",
        )
        unknown = FakeResponse(200, b"{" + b" " * 40 + b"}")
        del unknown.headers["Content-Length"]
        self.assertEqual(
            BDNSTransport(opener=FakeOpener(unknown), max_response_bytes=32).search().reason,
            "body_too_large",
        )


if __name__ == "__main__":
    unittest.main()
