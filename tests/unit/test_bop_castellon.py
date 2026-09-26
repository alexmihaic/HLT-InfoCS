"""Pruebas offline del flujo JSF y la lista de anuncios BOP Castellón."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import socket
import sys
from urllib.error import URLError
from urllib.parse import parse_qs
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bop_castellon import BOPFetchStatus, BOPTransport  # noqa: E402
from infocs.fetch.bop_castellon.parser import (  # noqa: E402
    BOPContractError,
    diagnose_announcement_structure,
    parse_announcements_page,
    parse_portal_date,
    parse_search_partial_response,
    parse_selection_redirect,
    parse_view_state,
    update_view_state_from_partial,
)


FIXTURES = ROOT / "tests" / "fixtures" / "bop_castellon"
SEARCH_XML = (FIXTURES / "search_partial.xml").read_text(encoding="utf-8")
SELECTION_XML = (FIXTURES / "selection_partial.xml").read_text(encoding="utf-8")
ANNOUNCEMENTS_HTML = (FIXTURES / "announcements_page.html").read_text(encoding="utf-8")
REAL_STRUCTURE_HTML = (FIXTURES / "announcements_real_structure.html").read_text(encoding="utf-8")
PAIRING_EDGE_HTML = (FIXTURES / "announcement_pairing_edge_case.html").read_text(encoding="utf-8")
EMPTY_XML = (FIXTURES / "no_publication_partial.xml").read_text(encoding="utf-8")
GET_HTML = b'''<!doctype html><html><body>
<form id="buscadorForm" method="post" action="/PortalBOP/boletinesAntiguos/">
<input type="hidden" name="buscadorForm" value="buscadorForm" />
<input type="hidden" name="javax.faces.ViewState" value="initial-fake-state" />
<input type="hidden" name="javax.faces.ClientWindow" value="fake-window" />
</form></body></html>'''


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, content_type: str = "text/html;charset=UTF-8") -> None:
        self.status = status
        self.body = body
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self.read_size: int | None = None

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_size = size
        return self.body[:size] if size >= 0 else self.body


class FakeSession:
    def __init__(self, responses: list[FakeResponse] | None = None, error: Exception | None = None) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.requests = []
        self.timeouts = []

    def open(self, request, timeout: float):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError("No fake response configured")
        return self.responses.pop(0)


def success_responses() -> list[FakeResponse]:
    return [
        FakeResponse(GET_HTML),
        FakeResponse(SEARCH_XML.encode(), content_type="text/xml;charset=UTF-8"),
        FakeResponse(SELECTION_XML.encode(), content_type="text/xml;charset=UTF-8"),
        FakeResponse(ANNOUNCEMENTS_HTML.encode()),
    ]


class BOPParserTests(unittest.TestCase):
    def test_search_matches_issue_and_extracts_dynamic_source_for_correct_card(self) -> None:
        selection = parse_search_partial_response(
            SEARCH_XML,
            date(2026, 9, 24),
            current_view_state="initial-state",
        )
        assert selection is not None
        self.assertEqual(selection.issue.portal_id, "26878")
        self.assertEqual(selection.issue.published_date, date(2026, 9, 24))
        self.assertEqual(selection.issue.issue_number, "115")
        self.assertEqual(selection.issue.issue_code, "B260924")
        self.assertEqual(selection.form_id, "buscadorReducidaForm")
        self.assertEqual(selection.source_component, "buscadorReducidaForm:j_idt75:1:j_idt76")
        self.assertIn(";jsessionid=synthetic-session", selection.action_url)
        self.assertEqual(dict(selection.hidden_fields)["javax.faces.ViewState"], "fresh-search-state")

    def test_another_card_has_another_source_and_requested_date_must_match(self) -> None:
        selection = parse_search_partial_response(
            SEARCH_XML,
            date(2026, 9, 22),
            current_view_state="initial-state",
        )
        assert selection is not None
        self.assertEqual(selection.issue.portal_id, "26877")
        self.assertEqual(selection.issue.issue_number, "114")
        self.assertEqual(selection.source_component, "buscadorReducidaForm:j_idt75:0:j_idt76")

    def test_search_date_without_an_issue_is_no_publication(self) -> None:
        self.assertIsNone(
            parse_search_partial_response(
                EMPTY_XML,
                date(2026, 9, 23),
                current_view_state="initial-state",
            )
        )

    def test_portal_date_is_typed_and_contract_format_is_strict(self) -> None:
        self.assertEqual(parse_portal_date("24/09/2026"), date(2026, 9, 24))
        for value in ("24-09-2026", "2026-09-24", "24/9/2026", "31/02/2026"):
            with self.subTest(value=value), self.assertRaises(BOPContractError):
                parse_portal_date(value)

    def test_partial_viewstate_replaces_current_value_when_present(self) -> None:
        self.assertEqual(
            update_view_state_from_partial(SEARCH_XML, "old-state"),
            "fresh-search-state",
        )
        self.assertEqual(
            update_view_state_from_partial("<partial-response><changes/></partial-response>", "old-state"),
            "old-state",
        )
        ambiguous = "<partial-response><changes><update id='a:javax.faces.ViewState'>a</update><update id='b:javax.faces.ViewState'>b</update></changes></partial-response>"
        with self.assertRaisesRegex(BOPContractError, "view_state_update_ambiguous"):
            update_view_state_from_partial(ambiguous, "old")

    def test_missing_search_updates_or_selection_card_fail_contract(self) -> None:
        with self.assertRaisesRegex(BOPContractError, "result_update_missing"):
            parse_search_partial_response("<partial-response><changes/></partial-response>", date(2026, 9, 24), current_view_state="x")
        without_cards = SEARCH_XML.replace('<update id="buscadorReducidaForm">', '<update id="unrelated">')
        with self.assertRaisesRegex(BOPContractError, "selection_component_missing"):
            parse_search_partial_response(without_cards, date(2026, 9, 24), current_view_state="x")
        unsafe_action = SEARCH_XML.replace(
            "/PortalBOP/boletinesAntiguos/;jsessionid=synthetic-session",
            "https://example.invalid/PortalBOP/selection",
        )
        with self.assertRaisesRegex(BOPContractError, "selection_action_unsafe"):
            parse_search_partial_response(unsafe_action, date(2026, 9, 24), current_view_state="x")

    def test_viewstate_is_read_only_from_target_form(self) -> None:
        html = '''<form id="other"><input type="hidden" name="javax.faces.ViewState" value="wrong" /></form>
        <form id="buscadorForm"><input type="hidden" name="javax.faces.ViewState" value="fresh" />
        <input type="hidden" name="x" value="y" /></form>'''
        token, hidden = parse_view_state(html)
        self.assertEqual(token, "fresh")
        self.assertEqual(hidden["x"], "y")
        with self.assertRaisesRegex(BOPContractError, "view_state_missing"):
            parse_view_state('<form id="buscadorForm"></form>')

    def test_selection_redirect_supports_relative_and_official_absolute_urls(self) -> None:
        relative = '<partial-response><redirect url="/PortalBOP/buscador/"/></partial-response>'
        absolute = '<partial-response><redirect url="https://bop.dipcas.es/PortalBOP/buscador/"/></partial-response>'
        base = "https://bop.dipcas.es/PortalBOP/boletinesAntiguos/"
        self.assertEqual(parse_selection_redirect(relative, response_url=base), "https://bop.dipcas.es/PortalBOP/buscador/")
        self.assertEqual(parse_selection_redirect(absolute, response_url=base), "https://bop.dipcas.es/PortalBOP/buscador/")

    def test_selection_redirect_rejects_external_missing_and_invalid_xml(self) -> None:
        base = "https://bop.dipcas.es/PortalBOP/boletinesAntiguos/"
        with self.assertRaisesRegex(BOPContractError, "navigation_unsafe"):
            parse_selection_redirect('<partial-response><redirect url="https://example.invalid/PortalBOP/x"/></partial-response>', response_url=base)
        with self.assertRaisesRegex(BOPContractError, "navigation_unsafe"):
            parse_selection_redirect('<partial-response><redirect url="http://bop.dipcas.es/PortalBOP/x"/></partial-response>', response_url=base)
        with self.assertRaisesRegex(BOPContractError, "navigation_instruction_missing"):
            parse_selection_redirect("<partial-response><changes/></partial-response>", response_url=base)
        with self.assertRaisesRegex(BOPContractError, "invalid_selection_partial_xml"):
            parse_selection_redirect("<partial-response>", response_url=base)

    def test_announcements_are_structurally_paired_ordered_and_official(self) -> None:
        items = parse_announcements_page(ANNOUNCEMENTS_HTML)
        self.assertEqual([item.portal_id for item in items], ["100001", "100002", "100003"])
        self.assertEqual(
            [item.title for item in items],
            ["Anuncio sintético A", "Anuncio sintético B", "Anuncio sintético C"],
        )
        self.assertEqual(items[0].document_url, "https://bop.dipcas.es/PortalBOP/api/descargarAnuncio?idAnuncio=100001&idioma=es")
        self.assertEqual(len(items), 3)  # el enlace general usa otra clase y queda fuera de las parejas
        self.assertEqual(items, parse_announcements_page(ANNOUNCEMENTS_HTML))

    def test_sanitized_public_dom_structure_preserves_local_announcement_pairs(self) -> None:
        """Captured DOM sample: synthetic text/IDs, with its observed structure retained."""
        items = parse_announcements_page(REAL_STRUCTURE_HTML)
        self.assertEqual(
            [item.portal_id for item in items],
            ["100001", "100002", "100003", "100004", "100005", "100006"],
        )
        self.assertEqual(
            [item.title for item in items],
            [
                "ANUNCIO SINTETICO A",
                "ANUNCIO SINTETICO B",
                "ANUNCIO SINTETICO C",
                "ANUNCIO SINTETICO D",
                "ANUNCIO SINTETICO E",
                "ANUNCIO SINTETICO F",
            ],
        )
        self.assertTrue(all(item.document_url.startswith("https://bop.dipcas.es/PortalBOP/api/descargarAnuncio?") for item in items))
        self.assertNotIn("200001", [item.portal_id for item in items])  # link general del boletín excluido

    def test_sanitized_public_dom_structure_rejects_ambiguous_and_duplicate_pairs(self) -> None:
        no_title = REAL_STRUCTURE_HTML.replace(
            'class="titulo4" aria-hidden="true" id="fixture-accessibility-id-2"',
            'class="titulo5" aria-hidden="true" id="fixture-accessibility-id-2"',
        )
        with self.assertRaisesRegex(BOPContractError, "announcement_pairing_invalid"):
            parse_announcements_page(no_title)

        duplicate = REAL_STRUCTURE_HTML.replace("idAnuncio=100002", "idAnuncio=100001")
        with self.assertRaisesRegex(BOPContractError, "duplicate_announcement_id"):
            parse_announcements_page(duplicate)

    def test_structure_diagnostic_is_safe_and_reports_local_sibling_distance(self) -> None:
        html = '''<form><input name="javax.faces.ViewState" value="SECRET_VIEWSTATE" /></form>
        <div id="busquedaBoletinesForm:resultadoBusquedaBoletines">
          <div class="i4t-include-secciones-dentro-tab">
            <span class="linkDownloadFileCurrentAnuncioIcon"><a href="https://bop.dipcas.es/PortalBOP/api/descargarAnuncio?idAnuncio=987654&amp;token=SECRET_TOKEN">PDF</a></span>
            <br /><br /><span class="titulo4">PRIVATE TITLE</span>
            <span class="linkDownloadFileCurrentBoletinIcon"><a href="https://bop.dipcas.es/PortalBOP/api/descargarBoletin?idBoletin=765432">PDF</a></span>
          </div><span class="titulo3">PRIVATE HEADING</span>
        </div>'''
        diagnostic = diagnose_announcement_structure(html)
        encoded = json.dumps(diagnostic, ensure_ascii=False)
        self.assertNotIn("PRIVATE TITLE", encoded)
        self.assertNotIn("PRIVATE HEADING", encoded)
        self.assertNotIn("987654", encoded)
        self.assertNotIn("765432", encoded)
        self.assertNotIn("SECRET_VIEWSTATE", encoded)
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("https://", encoded)
        self.assertEqual(diagnostic["global"], {
            "announcement_download_components": 1,
            "idAnuncio_links": 1,
            "titulo4": 1,
            "titulo3": 1,
            "bulletin_download_components": 1,
        })
        component = diagnostic["components"][0]
        self.assertEqual(component["tag"], "span")
        self.assertIn("linkDownloadFileCurrentAnuncioIcon", component["classes"])
        self.assertTrue(component["next_compatible_titulo4"])
        self.assertEqual(component["distance_element_siblings"], 3)
        self.assertEqual([node["tag"] for node in component["intermediate_structure"]], ["br", "br"])

    def test_pairing_failure_diagnostic_names_ambiguity_without_content(self) -> None:
        html = '''<div id="busquedaBoletinesForm:resultadoBusquedaBoletines">
          <div class="i4t-include-secciones-dentro-tab">
            <span class="linkDownloadFileCurrentAnuncioIcon"><a href="/PortalBOP/api/descargarAnuncio?idAnuncio=987654">PDF</a></span>
            <div class="layout-wrapper"><span class="titulo4">TITLE ONE</span><span class="titulo4">TITLE TWO</span></div>
          </div></div>'''
        with self.assertRaisesRegex(BOPContractError, "announcement_pairing_invalid") as raised:
            parse_announcements_page(html)
        encoded = json.dumps(raised.exception.diagnostic, ensure_ascii=False)
        self.assertNotIn("TITLE ONE", encoded)
        self.assertNotIn("TITLE TWO", encoded)
        self.assertNotIn("987654", encoded)
        self.assertEqual(raised.exception.diagnostic["failure"]["reason_code"], "multiple_title_candidates")
        self.assertEqual(raised.exception.diagnostic["failure"]["component_index"], 0)
        self.assertEqual(raised.exception.diagnostic["failure"]["candidate_title_count"], 2)

    def test_edge_fixture_pairs_title_after_interstitial_script(self) -> None:
        items = parse_announcements_page(PAIRING_EDGE_HTML)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].portal_id, "100099")
        self.assertEqual(items[0].title, "ANUNCIO SINTETICO EDGE")

    def test_single_announcement_pair_is_parsed_without_global_position_matching(self) -> None:
        single = '''<div id="busquedaBoletinesForm:resultadoBusquedaBoletines">
          <div class="i4t-include-secciones-dentro-tab">
            <span class="titulo2">Grupo sintético</span><br />
            <span class="linkDownloadFileCurrentAnuncioIcon"><a href="/PortalBOP/api/descargarAnuncio?idAnuncio=200001">PDF</a></span>
            <span class="titulo4">Anuncio único sintético</span>
          </div></div>'''
        result = parse_announcements_page(single)
        self.assertEqual([(item.portal_id, item.title) for item in result], [("200001", "Anuncio único sintético")])

    def test_announcements_missing_container_empty_list_duplicate_or_bad_ids_fail(self) -> None:
        with self.assertRaisesRegex(BOPContractError, "announcements_container_invalid"):
            parse_announcements_page("<html><body></body></html>")
        empty = '<div id="busquedaBoletinesForm:resultadoBusquedaBoletines"></div>'
        with self.assertRaisesRegex(BOPContractError, "announcements_empty_unexpected"):
            parse_announcements_page(empty)
        duplicate = ANNOUNCEMENTS_HTML.replace("idAnuncio=100002", "idAnuncio=100001")
        with self.assertRaisesRegex(BOPContractError, "duplicate_announcement_id"):
            parse_announcements_page(duplicate)
        malformed = ANNOUNCEMENTS_HTML.replace("idAnuncio=100002&amp;idioma", "sinId&amp;idioma")
        with self.assertRaisesRegex(BOPContractError, "announcement_link_cardinality_invalid"):
            parse_announcements_page(malformed)

    def test_malformed_local_announcement_pairs_fail_closed(self) -> None:
        no_title = ANNOUNCEMENTS_HTML.replace(
            '<span class="titulo4">Anuncio sintético B</span>',
            '<span class="titulo5">Anuncio sintético B</span>',
        )
        with self.assertRaisesRegex(BOPContractError, "announcement_pairing_invalid"):
            parse_announcements_page(no_title)

        multiple_ids = ANNOUNCEMENTS_HTML.replace(
            '</a>\n          </span><span class="titulo4">Anuncio sintético A</span>',
            '</a><a href="/PortalBOP/api/descargarAnuncio?idAnuncio=100004">otro documento</a>'
            '\n          </span><span class="titulo4">Anuncio sintético A</span>',
        )
        with self.assertRaisesRegex(BOPContractError, "announcement_link_cardinality_invalid"):
            parse_announcements_page(multiple_ids)

    def test_announcements_untrusted_link_and_unpaired_structure_are_rejected(self) -> None:
        unsafe = ANNOUNCEMENTS_HTML.replace("https://bop.dipcas.es/PortalBOP/api/descargarAnuncio?idAnuncio=100003&amp;idioma=es", "https://example.invalid/api/descargarAnuncio?idAnuncio=100003&amp;idioma=es")
        with self.assertRaises(BOPContractError):
            parse_announcements_page(unsafe)
        unpaired = '<div id="busquedaBoletinesForm:resultadoBusquedaBoletines"><span class="titulo4">Sintético</span></div>'
        with self.assertRaisesRegex(BOPContractError, "announcement_structure_invalid"):
            parse_announcements_page(unpaired)


class BOPTransportTests(unittest.TestCase):
    def _transport(self, session: FakeSession, jars: list[object]) -> BOPTransport:
        def factory(jar):  # type: ignore[no-untyped-def]
            jars.append(jar)
            return session

        return BOPTransport(opener_factory=factory)

    def test_end_to_end_is_get_search_post_selection_post_and_announcement_get(self) -> None:
        session = FakeSession(success_responses())
        jars: list[object] = []
        result = self._transport(session, jars).fetch_issue("2026-09-24")
        self.assertEqual(result.status, BOPFetchStatus.COMPLETE_SUCCESS)
        self.assertEqual(result.issue.portal_id, "26878")
        self.assertEqual(result.issue.published_date, date(2026, 9, 24))
        self.assertEqual(result.issue.issue_number, "115")
        self.assertEqual(result.issue.issue_code, "B260924")
        self.assertEqual([a.portal_id for a in result.issue.announcements], ["100001", "100002", "100003"])
        self.assertEqual(len(jars), 1)  # una CookieJar para los cuatro pasos
        self.assertEqual(len(session.requests), 4)
        self.assertEqual([r.get_method() for r in session.requests], ["GET", "POST", "POST", "GET"])
        self.assertEqual(session.requests[0].full_url, "https://bop.dipcas.es/PortalBOP/boletinesAntiguos/")
        self.assertEqual(session.requests[1].full_url, session.requests[0].full_url)
        self.assertEqual(session.requests[2].full_url, "https://bop.dipcas.es/PortalBOP/boletinesAntiguos/;jsessionid=synthetic-session")
        self.assertEqual(session.requests[3].full_url, "https://bop.dipcas.es/PortalBOP/buscador/")
        search_fields = parse_qs(session.requests[1].data.decode(), keep_blank_values=True)
        self.assertEqual(search_fields["buscadorForm:fechaInicialAntiguo_input"], ["24/09/2026"])
        self.assertEqual(search_fields["buscadorForm:fechaFinalAntiguo_input"], ["24/09/2026"])

        selection_request = session.requests[2]
        selection_fields = parse_qs(selection_request.data.decode(), keep_blank_values=True)
        source = "buscadorReducidaForm:j_idt75:1:j_idt76"
        self.assertEqual(selection_fields["buscadorReducidaForm"], ["buscadorReducidaForm"])
        self.assertEqual(selection_fields["javax.faces.partial.ajax"], ["true"])
        self.assertEqual(selection_fields["javax.faces.source"], [source])
        self.assertEqual(selection_fields["javax.faces.partial.execute"], ["@all"])
        self.assertEqual(selection_fields[source], [source])
        self.assertEqual(selection_fields["javax.faces.ViewState"], ["fresh-search-state"])
        self.assertNotIn("javax.faces.partial.render", selection_fields)
        self.assertNotIn("javax.faces.behavior.event", selection_fields)
        self.assertNotIn("javax.faces.partial.event", selection_fields)
        self.assertEqual(selection_request.get_header("Faces-request"), "partial/ajax")
        self.assertEqual(session.timeouts, [20.0] * 4)

    def test_transport_returns_only_safe_diagnostic_for_pairing_failure(self) -> None:
        edge_html = '''<div id="busquedaBoletinesForm:resultadoBusquedaBoletines">
          <div class="i4t-include-secciones-con-titulo3">
            <span class="linkDownloadFileCurrentAnuncioIcon"><a href="/PortalBOP/api/descargarAnuncio?idAnuncio=987654&amp;token=PRIVATE">PDF</a></span>
            <div class="layout-wrapper"><span class="titulo4">PRIVATE TITLE</span></div>
          </div></div>'''
        responses = success_responses()[:3] + [FakeResponse(edge_html.encode())]
        result = self._transport(FakeSession(responses), []).fetch_issue("2026-09-24")
        self.assertEqual(result.status, BOPFetchStatus.SOURCE_FAILURE)
        self.assertEqual(result.reason, "announcement_pairing_invalid")
        safe = json.dumps(result.diagnostic, ensure_ascii=False)
        self.assertNotIn("PRIVATE TITLE", safe)
        self.assertNotIn("987654", safe)
        self.assertNotIn("PRIVATE", safe)
        self.assertEqual(result.diagnostic["failure"]["reason_code"], "title_not_adjacent")

    def test_invalid_date_performs_no_network_request(self) -> None:
        session = FakeSession()
        jars: list[object] = []
        result = self._transport(session, jars).fetch_issue("2026-02-30")
        self.assertEqual(result.status, BOPFetchStatus.INVALID_REQUEST)
        self.assertEqual(session.requests, [])
        self.assertEqual(jars, [])

    def test_no_publication_stops_after_valid_search_response(self) -> None:
        session = FakeSession([
            FakeResponse(GET_HTML),
            FakeResponse(EMPTY_XML.encode(), content_type="text/xml;charset=UTF-8"),
        ])
        result = self._transport(session, []).fetch_issue(date(2026, 9, 23))
        self.assertEqual(result.status, BOPFetchStatus.NO_PUBLICATION)
        self.assertEqual(len(session.requests), 2)
        self.assertIsNone(result.issue)

    def test_selection_failure_redirect_absent_and_final_empty_list_fail_closed(self) -> None:
        base = [
            FakeResponse(GET_HTML),
            FakeResponse(SEARCH_XML.encode(), content_type="text/xml"),
        ]
        cases = [
            (base + [FakeResponse(b"<broken", content_type="text/xml")], "invalid_selection_partial_xml", 3),
            (base + [FakeResponse(b"<partial-response><changes/></partial-response>", content_type="text/xml")], "navigation_instruction_missing", 3),
            (base + [FakeResponse(b'<partial-response><redirect url="https://example.invalid/x"/></partial-response>', content_type="text/xml")], "navigation_unsafe", 3),
            (base + [FakeResponse(SELECTION_XML.encode(), content_type="text/xml"), FakeResponse(b'<div id="busquedaBoletinesForm:resultadoBusquedaBoletines"></div>')], "announcements_empty_unexpected", 4),
        ]
        for responses, reason, request_count in cases:
            with self.subTest(reason=reason):
                session = FakeSession(responses)
                result = self._transport(session, []).fetch_issue(date(2026, 9, 24))
                self.assertEqual(result.status, BOPFetchStatus.SOURCE_FAILURE)
                self.assertEqual(result.reason, reason)
                self.assertEqual(len(session.requests), request_count)

    def test_network_timeout_http_mime_and_size_failures_are_safe(self) -> None:
        for error, expected in ((TimeoutError(), "timeout"), (socket.timeout(), "timeout"), (URLError("private detail"), "network_failure")):
            result = self._transport(FakeSession(error=error), []).fetch_issue(date(2026, 9, 24))
            self.assertEqual(result.status, BOPFetchStatus.SOURCE_FAILURE)
            self.assertEqual(result.reason, expected)
        session = FakeSession([FakeResponse(GET_HTML, status=503)])
        self.assertEqual(self._transport(session, []).fetch_issue(date(2026, 9, 24)).http_status, 503)
        bad_mime = FakeSession([FakeResponse(GET_HTML), FakeResponse(SEARCH_XML.encode(), content_type="text/html")])
        self.assertEqual(self._transport(bad_mime, []).fetch_issue(date(2026, 9, 24)).reason, "mime_incompatible")
        oversized = FakeSession([FakeResponse(b"12345")])
        result = BOPTransport(max_get_bytes=4, opener_factory=lambda jar: oversized).fetch_issue(date(2026, 9, 24))
        self.assertEqual(result.reason, "body_too_large")


if __name__ == "__main__":
    unittest.main()
