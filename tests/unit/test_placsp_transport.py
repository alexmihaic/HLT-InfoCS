"""COLLECTOR-01A: transporte seguro del canal 643. Openers ficticios; ningún socket real."""

from __future__ import annotations

import io
from pathlib import Path
import socket
import ssl
import sys
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.placsp import (
    PRODUCTION_POLICY,
    PROVISIONAL_TWO_ORIGIN_POLICY,
    ROOT_URL,
    PlacspTransport,
    PlacspTransportError,
    UrlPolicyError,
    resolve_next_url,
    validate_feed_url,
)
from infocs.fetch.placsp import transport as transport_module
from infocs.fetch.placsp.config import _FORBIDDEN_CHARS
from ._placsp_helpers import FEED_URL, PAGE2_URL, PAGE3_URL, entry_xml, feed_xml, tombstone_xml

SECONDARY_PAGE2 = PAGE2_URL.replace("contrataciondelsectorpublico.gob.es", "contrataciondelestado.es")


class FakeResponse:
    def __init__(self, body: bytes = b"", *, status: int = 200, content_type: str | None = "application/atom+xml", extra: dict[str, str] | None = None) -> None:
        self._stream = io.BytesIO(body)
        self.status = status
        self.headers: dict[str, str] = {}
        if content_type is not None:
            self.headers["Content-Type"] = content_type
        self.headers.update(extra or {})
        self.read_calls = 0

    def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        return self._stream.read(size)

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class ScriptedOpener:
    def __init__(self, *items: object) -> None:
        self.items = list(items)
        self.requests: list[object] = []

    def __call__(self, request: object, timeout: float) -> object:
        self.requests.append((request, timeout))
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _page(next_url: str | None, key: str = "SYN-1") -> bytes:
    return feed_xml(entries=entry_xml(key), next_url=next_url)


class NoNetworkCase(unittest.TestCase):
    def setUp(self) -> None:
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection", "socket.getaddrinfo"):
            patcher = mock.patch(target, side_effect=AssertionError("no se permiten sockets reales"))
            patcher.start()
            self.addCleanup(patcher.stop)


class UrlPolicyTests(NoNetworkCase):
    def test_accepts_root_and_archive_files(self) -> None:
        for url in (FEED_URL, PAGE2_URL, ROOT_URL):
            self.assertEqual(validate_feed_url(url, PRODUCTION_POLICY), url)
        self.assertEqual(validate_feed_url(SECONDARY_PAGE2, PROVISIONAL_TWO_ORIGIN_POLICY), SECONDARY_PAGE2)
        self.assertEqual(validate_feed_url(FEED_URL.replace(".gob.es/", ".gob.es:443/"), PRODUCTION_POLICY).count(":443"), 1)

    def test_rejects_hostile_urls(self) -> None:
        base = "contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
        file = "licitacionesPerfilesContratanteCompleto3.atom"
        hostile = [
            f"http://{base}{file}",
            f"ftp://{base}{file}",
            f"https://usuario:clave@{base}{file}",
            f"https://usuario@{base}{file}",
            f"https://contrataciondelsectorpublico.gob.es.evil.example/sindicacion/sindicacion_643/{file}",
            f"https://evil.example/sindicacion/sindicacion_643/{file}",
            f"https://127.0.0.1/sindicacion/sindicacion_643/{file}",
            f"https://contrataciondelestado.es/sindicacion/sindicacion_643/{file}",  # segundo origen, política de producción
            f"https://{base}../sindicacion_1044/{file}",
            f"https://{base}%2e%2e/{file}",
            f"https://{base}..%2f{file}",
            f"https://{base}%5c{file}",
            f"https://{base}sub/{file}",
            f"https://{base}/{file}",
            f"https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/{file}",
            f"https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_6430/{file}",
            f"https://{base}licitacionesPerfilesContratanteCompleto3_evil.atom",
            f"https://{base}licitacionesPerfilesContratanteCompleto3.atom.exe",
            f"https://{base}{file}?x=1",
            f"https://{base}{file}#frag",
            f"https://{base}{file}\n",
            f"https://{base}{file} ",
            f"https://{base}{file}\\x",
            f"https://contrataciondelsectorpublico.gob.es:8443/sindicacion/sindicacion_643/{file}",
            "", None, 12,
        ]
        for url in hostile:
            with self.assertRaises(UrlPolicyError, msg=repr(url)):
                validate_feed_url(url, PRODUCTION_POLICY)

    def test_error_codes_do_not_echo_url(self) -> None:
        with self.assertRaises(UrlPolicyError) as raised:
            validate_feed_url("https://usuario:clave-secreta@evil.example/x", PRODUCTION_POLICY)
        self.assertNotIn("secreta", str(raised.exception) + raised.exception.code)

    def test_next_resolution_checks_raw_reference_first(self) -> None:
        relative = "licitacionesPerfilesContratanteCompleto3_20261023_202231.atom"
        self.assertEqual(resolve_next_url(FEED_URL, relative, PRODUCTION_POLICY), PAGE2_URL)
        for reference in ("../sindicacion_1044/x.atom", "/sindicacion/sindicacion_1044/licitacionesPerfilesContratanteCompleto3.atom",
                          "//evil.example/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom",
                          "https://evil.example/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom", "", None):
            with self.assertRaises(UrlPolicyError, msg=repr(reference)):
                resolve_next_url(FEED_URL, reference, PRODUCTION_POLICY)

    def test_provisional_policy_is_flagged_and_not_default(self) -> None:
        self.assertTrue(PROVISIONAL_TWO_ORIGIN_POLICY.provisional)
        self.assertFalse(PRODUCTION_POLICY.provisional)
        self.assertEqual(PRODUCTION_POLICY.hosts, frozenset({"contrataciondelsectorpublico.gob.es"}))


class TransportSafetyTests(NoNetworkCase):
    def test_success_uses_safe_request_headers(self) -> None:
        opener = ScriptedOpener(FakeResponse(b"<x/>"))
        fetched = PlacspTransport(opener=opener, timeout_seconds=7).fetch_page(FEED_URL)
        request, timeout = opener.requests[0]
        self.assertEqual((fetched.body, fetched.status, timeout), (b"<x/>", 200, 7))
        self.assertEqual((request.get_method(), request.full_url), ("GET", FEED_URL))
        names = {name.lower() for name in dict(request.header_items())}
        self.assertEqual(names, {"accept", "user-agent"})  # sin Authorization, Cookie ni credenciales
        self.assertEqual(request.get_header("Accept"), "application/atom+xml")

    def test_invalid_url_never_reaches_opener(self) -> None:
        opener = ScriptedOpener()
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=opener).fetch_page("https://evil.example/x")
        self.assertEqual((raised.exception.reason, opener.requests), ("invalid_request_url", []))

    def test_secondary_host_is_disabled_for_real_use(self) -> None:
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(policy=PROVISIONAL_TWO_ORIGIN_POLICY)  # sin opener inyectado: uso real
        self.assertEqual(raised.exception.reason, "provisional_policy_disabled")
        with self.assertRaises(PlacspTransportError):
            PlacspTransport().fetch_page(SECONDARY_PAGE2)
        PlacspTransport(policy=PROVISIONAL_TWO_ORIGIN_POLICY, opener=ScriptedOpener(FakeResponse(b"<x/>"))).fetch_page(SECONDARY_PAGE2)

    def test_redirects_are_rejected(self) -> None:
        for error in (HTTPError(FEED_URL, 302, "Found", {}, None), HTTPError(FEED_URL, 308, "Perm", {}, None)):
            with self.assertRaises(PlacspTransportError) as raised:
                PlacspTransport(opener=ScriptedOpener(error)).fetch_page(FEED_URL)
            self.assertEqual(raised.exception.reason, "redirect_rejected")
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=ScriptedOpener(FakeResponse(b"", status=301))).fetch_page(FEED_URL)
        self.assertEqual(raised.exception.reason, "redirect_rejected")

    def test_default_opener_does_not_follow_redirects(self) -> None:
        handler = transport_module._NoRedirectHandler()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/"))

    def test_mime_must_be_atom_xml(self) -> None:
        for content_type in ("text/html", "application/json", "application/xml", None, "application/atom+xml.evil"):
            with self.assertRaises(PlacspTransportError, msg=str(content_type)) as raised:
                PlacspTransport(opener=ScriptedOpener(FakeResponse(b"<x/>", content_type=content_type))).fetch_page(FEED_URL)
            self.assertEqual(raised.exception.reason, "mime_incompatible")
        PlacspTransport(opener=ScriptedOpener(FakeResponse(b"<x/>", content_type="Application/Atom+XML; charset=UTF-8"))).fetch_page(FEED_URL)

    def test_content_encoding_is_rejected(self) -> None:
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=ScriptedOpener(FakeResponse(b"<x/>", extra={"Content-Encoding": "gzip"}))).fetch_page(FEED_URL)
        self.assertEqual(raised.exception.reason, "content_encoding_unsupported")

    def test_declared_length_is_checked_before_reading(self) -> None:
        response = FakeResponse(b"x" * 10, extra={"Content-Length": "999999"})
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=ScriptedOpener(response), max_response_bytes=1000).fetch_page(FEED_URL)
        self.assertEqual((raised.exception.reason, response.read_calls), ("body_too_large", 0))
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=ScriptedOpener(FakeResponse(b"x", extra={"Content-Length": "abc"}))).fetch_page(FEED_URL)
        self.assertEqual(raised.exception.reason, "invalid_content_length")

    def test_body_limit_is_enforced_while_reading(self) -> None:
        response = FakeResponse(b"x" * 5000, extra={"Content-Length": "10"})  # cabecera mentirosa
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=ScriptedOpener(response), max_response_bytes=1000).fetch_page(FEED_URL)
        self.assertEqual(raised.exception.reason, "body_too_large")
        exact = FakeResponse(b"x" * 1000)
        self.assertEqual(len(PlacspTransport(opener=ScriptedOpener(exact), max_response_bytes=1000).fetch_page(FEED_URL).body), 1000)

    def test_failure_codes_without_retries(self) -> None:
        cases = [
            (HTTPError(FEED_URL, 404, "x", {}, None), "http_failure"),
            (HTTPError(FEED_URL, 429, "x", {}, None), "rate_limited"),
            (HTTPError(FEED_URL, 503, "x", {}, None), "server_error"),
            (TimeoutError(), "timeout"),
            (socket.timeout(), "timeout"),
            (URLError("sin red"), "network_failure"),
            (ssl.SSLError("tls"), "network_failure"),
            (ConnectionResetError(), "network_failure"),
        ]
        for error, reason in cases:
            opener = ScriptedOpener(error, FakeResponse(b"<x/>"))
            with self.assertRaises(PlacspTransportError) as raised:
                PlacspTransport(opener=opener).fetch_page(FEED_URL)
            self.assertEqual(raised.exception.reason, reason)
            self.assertEqual(len(opener.requests), 1, "sin reintentos automáticos")
            self.assertNotIn("contrataciondelsectorpublico", str(raised.exception))

    def test_invalid_configuration(self) -> None:
        for kwargs in ({"timeout_seconds": 0}, {"max_response_bytes": 0}, {"max_pages": 0}):
            with self.assertRaises(ValueError):
                PlacspTransport(**kwargs)


class PaginationTests(NoNetworkCase):
    def _transport(self, *bodies: bytes, policy=PROVISIONAL_TWO_ORIGIN_POLICY, **kwargs):
        opener = ScriptedOpener(*(FakeResponse(body) for body in bodies))
        return PlacspTransport(policy=policy, opener=opener, **kwargs), opener

    def test_follows_next_until_absent(self) -> None:
        transport, opener = self._transport(_page(SECONDARY_PAGE2, "SYN-1"), _page(PAGE3_URL, "SYN-2"), _page(None, "SYN-3"))
        chain = transport.fetch_chain(FEED_URL)
        self.assertEqual([len(page.entries) for _, page in chain], [1, 1, 1])
        self.assertEqual([request.full_url for request, _ in opener.requests], [FEED_URL, SECONDARY_PAGE2, PAGE3_URL])

    def test_production_policy_rejects_second_origin_link(self) -> None:
        # El feed real enlaza a contrataciondelestado.es: con la política de producción la cadena se detiene.
        opener = ScriptedOpener(FakeResponse(_page(SECONDARY_PAGE2)), FakeResponse(_page(None)))
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=opener).fetch_chain(FEED_URL)
        self.assertEqual((raised.exception.reason, len(opener.requests)), ("pagination_unsafe", 1))

    def test_hostile_next_references_are_unsafe(self) -> None:
        file = "licitacionesPerfilesContratanteCompleto3.atom"
        hostile = [
            f"https://evil.example/sindicacion/sindicacion_643/{file}",
            "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/../sindicacion_1044/x.atom",
            f"https://usuario:clave@contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/{file}",
            f"http://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/{file}",
            f"https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/{file}?redir=1",
            f"https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/{file}",
            f"https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/%2e%2e/{file}",
        ]
        for href in hostile:
            opener = ScriptedOpener(FakeResponse(_page(href)), FakeResponse(_page(None)))
            with self.assertRaises(PlacspTransportError, msg=href) as raised:
                PlacspTransport(opener=opener).fetch_chain(FEED_URL)
            self.assertEqual((raised.exception.reason, len(opener.requests)), ("pagination_unsafe", 1), href)
            self.assertNotIn("evil", str(raised.exception))

    def test_cycles_are_detected(self) -> None:
        transport, _ = self._transport(_page(SECONDARY_PAGE2, "SYN-1"), _page(FEED_URL.replace("sectorpublico.gob", "estado"), "SYN-2"))
        with self.assertRaises(PlacspTransportError) as raised:
            transport.fetch_chain(FEED_URL.replace("contrataciondelsectorpublico.gob.es", "contrataciondelestado.es"))
        self.assertEqual(raised.exception.reason, "pagination_loop")
        transport, opener = self._transport(_page(FEED_URL.replace("contrataciondelsectorpublico.gob.es", "contrataciondelestado.es")))
        with self.assertRaises(PlacspTransportError) as raised:
            transport.fetch_chain(FEED_URL.replace("contrataciondelsectorpublico.gob.es", "contrataciondelestado.es"))
        self.assertEqual((raised.exception.reason, len(opener.requests)), ("pagination_loop", 1))

    def test_page_budget(self) -> None:
        transport, opener = self._transport(_page(SECONDARY_PAGE2), _page(PAGE3_URL.replace("sectorpublico.gob", "estado")), _page(None), max_pages=2)
        with self.assertRaises(PlacspTransportError) as raised:
            transport.fetch_chain(FEED_URL)
        self.assertEqual((raised.exception.reason, len(opener.requests)), ("too_many_pages", 2))

    def test_parse_failure_aborts_whole_chain_without_partial_results(self) -> None:
        transport, _ = self._transport(_page(SECONDARY_PAGE2), b"<feed")
        with self.assertRaises(PlacspTransportError) as raised:
            transport.fetch_chain(FEED_URL)
        self.assertEqual(raised.exception.reason, "parse_invalid_xml")

    def test_ambiguous_next_aborts(self) -> None:
        other = '<link href="https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3_20250101_000000.atom" rel="next"/>'
        page = feed_xml(entries=entry_xml(), extra_links=other)
        transport, _ = self._transport(page)
        with self.assertRaises(PlacspTransportError) as raised:
            transport.fetch_chain(FEED_URL)
        self.assertEqual(raised.exception.reason, "parse_pagination_ambiguous")

    def test_xml_base_cannot_widen_permissions(self) -> None:
        page = feed_xml(entries=entry_xml(), root_attrs='xml:base="https://evil.example/sindicacion/sindicacion_643/"', next_url="licitacionesPerfilesContratanteCompleto3_20261023_202231.atom")
        opener = ScriptedOpener(FakeResponse(page), FakeResponse(_page(None)))
        PlacspTransport(opener=opener).fetch_chain(FEED_URL)
        self.assertEqual(opener.requests[1][0].full_url, PAGE2_URL)  # resuelto contra la URL real, no contra xml:base

    def test_no_partial_state_is_exposed(self) -> None:
        self.assertFalse(any(name in dir(PlacspTransport) for name in ("write", "save", "persist", "run", "main")))


class QueryPolicyTests(NoNetworkCase):
    """FIX 3: política provisional de cero queries y fragmentos, con motivo estable."""

    BASE = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"

    def test_any_query_or_fragment_has_one_stable_reason(self) -> None:
        for suffix in ("?", "?x=1", "?a=1&b=2", "#", "#frag", "?x=1#f"):
            with self.assertRaises(UrlPolicyError, msg=suffix) as raised:
                validate_feed_url(self.BASE + suffix, PRODUCTION_POLICY)
            self.assertEqual(raised.exception.code, "url_query_or_fragment", suffix)
        for encoded in ("%3f", "%3F", "%23"):
            with self.assertRaises(UrlPolicyError) as raised:
                validate_feed_url(self.BASE + encoded, PRODUCTION_POLICY)
            self.assertEqual(raised.exception.code, "url_encoded_hazard")

    def test_next_with_query_is_rejected_with_same_reason(self) -> None:
        for reference in ("licitacionesPerfilesContratanteCompleto3_20261023_202231.atom?x=1", "licitacionesPerfilesContratanteCompleto3_20261023_202231.atom#a", "?x=1"):
            with self.assertRaises(UrlPolicyError) as raised:
                resolve_next_url(self.BASE, reference, PRODUCTION_POLICY)
            self.assertEqual(raised.exception.code, "url_query_or_fragment")

    def test_chain_aborts_on_next_with_query(self) -> None:
        href = PAGE2_URL + "?page=2"
        opener = ScriptedOpener(FakeResponse(_page(href)), FakeResponse(_page(None)))
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=opener).fetch_chain(FEED_URL)
        self.assertEqual((raised.exception.reason, len(opener.requests)), ("pagination_unsafe", 1))
        self.assertNotIn("page=2", str(raised.exception))


class BackslashTests(NoNetworkCase):
    """FIX 4: la barra invertida se rechaza directamente, no solo por otros controles de ruta."""

    BASE = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
    FILE = "licitacionesPerfilesContratanteCompleto3.atom"

    def test_character_class_matches_backslash_directly(self) -> None:
        for char in ("\\", "@", " ", "\t", "\n", "\r", "\x00", "\x7f"):
            self.assertIsNotNone(_FORBIDDEN_CHARS.search(char), repr(char))
        for char in ("/", ":", ".", "_", "-", "%", "a", "Z", "0", "~"):
            self.assertIsNone(_FORBIDDEN_CHARS.search(char), repr(char))

    def test_backslash_urls_are_rejected_by_character_check_first(self) -> None:
        urls = [
            self.BASE + self.FILE + "\\",
            self.BASE + "\\" + self.FILE,
            self.BASE + "..\\" + self.FILE,
            self.BASE + "\\..\\" + self.FILE,
            self.BASE + "%2e%2e\\" + self.FILE,
            self.BASE + "..\\%2f" + self.FILE,
            self.BASE + "..%5c" + "\\" + self.FILE,
            "https:\\\\contrataciondelsectorpublico.gob.es\\sindicacion\\sindicacion_643\\" + self.FILE,
        ]
        for url in urls:
            with self.assertRaises(UrlPolicyError, msg=url) as raised:
                validate_feed_url(url, PRODUCTION_POLICY)
            self.assertEqual(raised.exception.code, "url_forbidden_characters", url)

    def test_encoded_backslash_and_traversal_are_rejected_by_hazard_check(self) -> None:
        for fragment in ("%5c", "%5C", "..%5c", "%2e%2e%5c", "%2f", "%252e"):
            with self.assertRaises(UrlPolicyError, msg=fragment) as raised:
                validate_feed_url(self.BASE + fragment + self.FILE, PRODUCTION_POLICY)
            self.assertEqual(raised.exception.code, "url_encoded_hazard", fragment)

    def test_next_reference_with_backslash(self) -> None:
        for reference in ("..\\x.atom", "licitacionesPerfilesContratanteCompleto3_20261023_202231.atom\\", "\\\\evil.example\\x"):
            with self.assertRaises(UrlPolicyError) as raised:
                resolve_next_url(self.BASE + self.FILE, reference, PRODUCTION_POLICY)
            self.assertEqual(raised.exception.code, "next_unsafe")
        opener = ScriptedOpener(FakeResponse(_page("licitacionesPerfilesContratanteCompleto3_20261023_202231.atom\\")))
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=opener).fetch_chain(FEED_URL)
        self.assertEqual(raised.exception.reason, "pagination_unsafe")


class ChainIntegrityTests(NoNetworkCase):
    """FIX 1: la cadena nunca devuelve una lectura incompleta como éxito."""

    def _transport(self, *bodies: bytes, **kwargs):
        opener = ScriptedOpener(*(FakeResponse(body) for body in bodies))
        return PlacspTransport(policy=PROVISIONAL_TWO_ORIGIN_POLICY, opener=opener, **kwargs), opener

    def test_discarded_entry_in_single_page_aborts(self) -> None:
        bad = feed_xml(entries=entry_xml("SYN-OK") + entry_xml("SYN-BAD", cpv="NOPE"), next_url=None)
        transport, _ = self._transport(bad)
        with self.assertRaises(PlacspTransportError) as raised:
            transport.fetch_chain(FEED_URL)
        self.assertEqual((raised.exception.reason, str(raised.exception)), ("parse_entries_discarded", "parse_entries_discarded"))
        self.assertNotIn("SYN", repr(raised.exception) + str(raised.exception))

    def test_issue_in_last_page_aborts_whole_chain(self) -> None:
        last = feed_xml(entries=entry_xml("SYN-3") + entry_xml("SYN-X", nuts="es522"), next_url=None)
        transport, opener = self._transport(_page(SECONDARY_PAGE2, "SYN-1"), _page(PAGE3_URL, "SYN-2"), last)
        result = None
        with self.assertRaises(PlacspTransportError) as raised:
            result = transport.fetch_chain(FEED_URL)
        self.assertEqual((raised.exception.reason, len(opener.requests), result), ("parse_entries_discarded", 3, None))

    def test_invalid_tombstone_aborts_chain(self) -> None:
        bad = feed_xml(entries=entry_xml("SYN-1"), tombstones=tombstone_xml("T", "ANULADA", when="mañana"), next_url=None)
        transport, _ = self._transport(bad)
        with self.assertRaises(PlacspTransportError) as raised:
            transport.fetch_chain(FEED_URL)
        self.assertEqual(raised.exception.reason, "parse_tombstones_discarded")

    def test_successful_chain_contains_only_complete_pages(self) -> None:
        transport, _ = self._transport(_page(SECONDARY_PAGE2, "SYN-1"), _page(None, "SYN-2"))
        chain = transport.fetch_chain(FEED_URL)
        self.assertTrue(all(page.complete for _, page in chain))


class DotSegmentTests(NoNetworkCase):
    """`urljoin` normaliza los segmentos punto; la referencia cruda se rechaza antes."""

    BASE = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
    FILE = "licitacionesPerfilesContratanteCompleto3_20261023_202231.atom"

    def test_relative_and_absolute_dot_segments_are_rejected(self) -> None:
        references = [
            "./" + self.FILE,
            "." + "/" + self.FILE,
            self.BASE + "./" + self.FILE,
            self.BASE + "." ,
            self.BASE + "././" + self.FILE,
            "https://contrataciondelsectorpublico.gob.es/sindicacion/./sindicacion_643/" + self.FILE,
            self.BASE + "../sindicacion_643/" + self.FILE,
            "../sindicacion_643/" + self.FILE,
        ]
        for reference in references:
            with self.assertRaises(UrlPolicyError, msg=reference) as raised:
                resolve_next_url(self.BASE + "licitacionesPerfilesContratanteCompleto3.atom", reference, PRODUCTION_POLICY)
            self.assertEqual(raised.exception.code, "next_unsafe", reference)

    def test_dot_segments_combined_with_escapes_are_rejected(self) -> None:
        for reference in ("./%2e/" + self.FILE, ".%2e/" + self.FILE, self.BASE + "./%2e%2e/" + self.FILE,
                          self.BASE + ".%2f" + self.FILE, "./" + self.FILE + "%00", ".\\" + self.FILE):
            with self.assertRaises(UrlPolicyError, msg=reference):
                resolve_next_url(self.BASE + "licitacionesPerfilesContratanteCompleto3.atom", reference, PRODUCTION_POLICY)

    def test_absolute_validation_also_rejects_dot_segment(self) -> None:
        with self.assertRaises(UrlPolicyError) as raised:
            validate_feed_url(self.BASE + "./" + self.FILE, PRODUCTION_POLICY)
        self.assertEqual(raised.exception.code, "url_path_not_allowed")

    def test_legitimate_references_still_resolve(self) -> None:
        current = self.BASE + "licitacionesPerfilesContratanteCompleto3.atom"
        self.assertEqual(resolve_next_url(current, self.FILE, PRODUCTION_POLICY), self.BASE + self.FILE)
        self.assertEqual(resolve_next_url(current, self.BASE + self.FILE, PRODUCTION_POLICY), self.BASE + self.FILE)
        self.assertEqual(resolve_next_url(current, "/sindicacion/sindicacion_643/" + self.FILE, PRODUCTION_POLICY), self.BASE + self.FILE)

    def test_chain_aborts_on_dot_segment_next(self) -> None:
        opener = ScriptedOpener(FakeResponse(_page("./" + self.FILE)), FakeResponse(_page(None)))
        with self.assertRaises(PlacspTransportError) as raised:
            PlacspTransport(opener=opener).fetch_chain(FEED_URL)
        self.assertEqual((raised.exception.reason, len(opener.requests)), ("pagination_unsafe", 1))


if __name__ == "__main__":
    unittest.main()
