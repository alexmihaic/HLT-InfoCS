"""COLLECTOR-01A: parser ATOM/CODICE del canal 643. Solo XML sintético; sin red ni disco de datos."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.placsp import parser as parser_module
from infocs.fetch.placsp import ParserLimits, PlacspParseError, parse_feed_page, resolve_duplicates
from ._placsp_helpers import ENTRY_ID_PREFIX, PAGE2_URL, entry_xml, feed_xml, tombstone_xml

FIXTURES = ROOT / "tests" / "fixtures" / "placsp"
DECOYS = (
    "Q0000000J", "B0000000J", "senuelo", "SENUELO", "example.invalid", "+34 900", "Calle", "12999",
    "pliego", "Adjudicataria", "Persona", "Jerarquia", "Ciudad", "Municipio", "1234.50", "EndTime", "14:00:00",
)


def _block_network(case: unittest.TestCase) -> None:
    for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection", "socket.getaddrinfo"):
        patcher = mock.patch(target, side_effect=AssertionError("el parser no debe abrir sockets"))
        patcher.start()
        case.addCleanup(patcher.stop)


def _parse(**kwargs: object):
    return parse_feed_page(feed_xml(**kwargs))  # type: ignore[arg-type]


def _diag(**kwargs: object):
    """Modo diagnóstico: devuelve la página aunque haya entradas descartadas (complete == False)."""
    return parse_feed_page(feed_xml(**kwargs), allow_discarded=True)  # type: ignore[arg-type]


class ValidFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        _block_network(self)
        self.page = parse_feed_page((FIXTURES / "feed_valid_page.xml").read_bytes())
        self.by_key = {entry.atom_id.rsplit("/", 1)[1]: entry for entry in self.page.entries}

    def test_page_shape_and_counts(self) -> None:
        self.assertEqual((self.page.entries_seen, len(self.page.entries), self.page.issues), (3, 3, ()))
        self.assertEqual((self.page.superseded_duplicates, self.page.benign_duplicates), (0, 0))
        self.assertEqual(self.page.feed.next_href, "https://contrataciondelestado.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3_20261023_202231.atom")
        self.assertEqual(self.page.feed.updated.utcoffset(), timedelta(hours=2))

    def test_minimal_entry_has_only_required_fields(self) -> None:
        entry = self.by_key["SYN-0001"]
        self.assertEqual(entry.contract_folder_id, "SYN/2026/0001")
        self.assertEqual((entry.id_plataforma, entry.dir3), ("9990000000001", None))
        self.assertEqual(
            (entry.title, entry.status, entry.contract_type, entry.procedure, entry.cpv_codes, entry.notices,
             entry.submission_deadline, entry.execution_locations, entry.has_lots),
            (None, None, None, None, (), (), None, (), False),
        )

    def test_full_entry_allowed_fields(self) -> None:
        entry = self.by_key["SYN-0002"]
        self.assertEqual(entry.title, "Servicio ficticio de mantenimiento")
        self.assertEqual((entry.id_plataforma, entry.dir3), ("9990000000002", "L01990001"))
        self.assertEqual((entry.status.value, entry.status.list_uri, entry.status.list_version), ("EV", "urn:synthetic:status", "1.0"))
        self.assertEqual((entry.contract_type.value, entry.procedure.value), ("2", "1"))
        self.assertEqual(entry.cpv_codes, ("45000000", "50000000"))
        self.assertEqual((entry.submission_deadline.precision, entry.submission_deadline.value), ("date", "2026-11-10"))
        self.assertEqual([c.value for c in entry.execution_locations], ["ES522"])

    def test_several_notices_keep_type_date_association_and_order(self) -> None:
        notices = self.by_key["SYN-0002"].notices
        self.assertEqual([(n.notice_type.value, n.issue_date.value) for n in notices], [("DOC_CAN_ADJ", "2026-10-24"), ("DOC_CN", "2026-10-20")])

    def test_es522_is_province_signal_only(self) -> None:
        self.assertTrue(self.by_key["SYN-0002"].declares_castellon_province_execution)
        self.assertFalse(self.by_key["SYN-0003"].declares_castellon_province_execution)  # ES523, y el lote con ES522 se ignora
        self.assertFalse(self.by_key["SYN-0001"].declares_castellon_province_execution)
        self.assertEqual([c.value for c in self.by_key["SYN-0003"].execution_locations], ["ES523"])

    def test_lots_are_flagged_but_never_stored(self) -> None:
        self.assertTrue(self.by_key["SYN-0003"].has_lots)
        self.assertFalse(self.by_key["SYN-0002"].has_lots)
        self.assertNotIn("lote", repr(dataclasses.asdict(self.by_key["SYN-0003"])).lower().replace("con lotes", ""))

    def test_title_states_on_fixture(self) -> None:
        self.assertEqual(self.by_key["SYN-0001"].title_state, "absent")
        self.assertEqual((self.by_key["SYN-0002"].title_state, self.by_key["SYN-0003"].title_state), ("present", "present"))

    def test_missing_dir3_and_optional_fields(self) -> None:
        self.assertIsNone(self.by_key["SYN-0003"].dir3)
        self.assertIsNone(self.by_key["SYN-0003"].procedure)

    def test_tombstones_are_technical_observations(self) -> None:
        kinds = [(t.kind, t.official_ref.rsplit("/", 1)[1]) for t in self.page.tombstones]
        self.assertEqual(kinds, [("ANULADA", "SYN-0900"), ("CERRADA", "SYN-0901")])
        self.assertTrue(all(t.official_ref.startswith("643::") for t in self.page.tombstones))
        self.assertEqual(self.page.tombstones[0].when.utcoffset(), timedelta(hours=2))
        self.assertEqual(len(self.page.entries), 3)  # un tombstone no elimina ni crea entradas

    def test_no_personal_or_excluded_data_leaks_anywhere(self) -> None:
        dumped = repr(self.page) + repr(dataclasses.asdict(self.page)) + str(self.page.entries) + repr(self.page.tombstones)
        for decoy in DECOYS:
            self.assertNotIn(decoy, dumped, decoy)
        for entry in self.page.entries:
            self.assertNotIn(entry.atom_id, repr(entry))  # repr sin identificadores ni títulos

    def test_official_id_is_literal_and_not_a_path(self) -> None:
        entry = self.by_key["SYN-0001"]
        self.assertEqual(entry.official_id, "643::https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/SYN-0001")
        self.assertEqual(entry.atom_id, ENTRY_ID_PREFIX + "SYN-0001")
        self.assertFalse(hasattr(entry, "path") or hasattr(entry, "filename"))

    def test_results_are_deterministic(self) -> None:
        again = parse_feed_page((FIXTURES / "feed_valid_page.xml").read_bytes())
        self.assertEqual(self.page, again)

    def test_excluded_content_is_never_retained_in_memory(self) -> None:
        created: list[object] = []
        real_node = parser_module._Node

        class RecordingNode(real_node):  # type: ignore[misc, valid-type]
            __slots__ = ()

            def __init__(self, path: tuple, attrib: dict) -> None:
                super().__init__(path, attrib)
                created.append(self)

        with mock.patch.object(parser_module, "_Node", RecordingNode):
            parse_feed_page((FIXTURES / "feed_valid_page.xml").read_bytes())
        self.assertGreater(len(created), 10)
        for node in created:
            self.assertIn(node.path, parser_module._ALLOWED_PATHS)
            for decoy in DECOYS:
                self.assertNotIn(decoy, node.value())
                self.assertNotIn(decoy, repr(node.attrib))


class OffsetAndInstantTests(unittest.TestCase):
    def test_offset_change_preserves_offsets_and_orders_by_instant(self) -> None:
        page = parse_feed_page((FIXTURES / "feed_dst_offsets.xml").read_bytes())
        first, second = page.entries
        self.assertEqual((first.updated.utcoffset(), second.updated.utcoffset()), (timedelta(hours=2), timedelta(hours=1)))
        self.assertLess(first.updated, second.updated)  # 00:30Z < 01:10Z aunque la hora local 02:30 > 02:10
        self.assertEqual(first.updated.astimezone(timezone.utc), datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc))

    def test_updated_without_offset_or_invalid_is_entry_issue(self) -> None:
        for bad in ("2026-10-24T12:00:00", "2026-13-24T12:00:00+02:00", "2026-10-24", "ayer"):
            page = _diag(entries=entry_xml(updated=bad))
            self.assertEqual((len(page.entries), page.issues[0].codes), (0, ("invalid_updated",)), bad)

    def test_fraction_and_z_suffix(self) -> None:
        page = _parse(entries=entry_xml(updated="2026-10-24T10:00:00.123456789Z"))
        self.assertEqual(page.entries[0].updated.utcoffset(), timedelta(0))
        self.assertEqual(page.entries[0].updated.microsecond, 123456)


class DuplicateTests(unittest.TestCase):
    def test_same_id_different_updated_keeps_latest(self) -> None:
        older = entry_xml("SYN-5", updated="2026-10-24T10:00:00+02:00", folder="OLD")
        newer = entry_xml("SYN-5", updated="2026-10-24T11:00:00+02:00", folder="NEW")
        for entries in (older + newer, newer + older):
            page = _parse(entries=entries)
            self.assertEqual([e.contract_folder_id for e in page.entries], ["NEW"])
            self.assertEqual((page.superseded_duplicates, page.benign_duplicates), (1, 0))

    def test_same_id_same_instant_identical_content_is_benign(self) -> None:
        a = entry_xml("SYN-6", updated="2026-10-24T12:00:00+02:00")
        b = entry_xml("SYN-6", updated="2026-10-24T10:00:00Z")  # mismo instante, otro offset
        page = _parse(entries=a + b)
        self.assertEqual((len(page.entries), page.benign_duplicates), (1, 1))

    def test_same_id_same_instant_conflicting_content_is_batch_error(self) -> None:
        a = entry_xml("SYN-7", updated="2026-10-24T12:00:00+02:00", folder="A")
        b = entry_xml("SYN-7", updated="2026-10-24T10:00:00Z", folder="B")
        with self.assertRaises(PlacspParseError) as raised:
            _parse(entries=a + b)
        self.assertEqual(raised.exception.code, "duplicate_incompatible")
        self.assertEqual(str(raised.exception), "duplicate_incompatible")

    def test_resolve_duplicates_across_pages(self) -> None:
        page_a = _parse(entries=entry_xml("SYN-8", updated="2026-10-24T10:00:00+02:00", folder="A"))
        page_b = _parse(entries=entry_xml("SYN-8", updated="2026-10-24T09:00:00+02:00", folder="B"))
        winners, superseded, benign = resolve_duplicates([page_a, page_b])
        self.assertEqual(([e.contract_folder_id for e in winners], superseded, benign), (["A"], 1, 0))

    def test_correction_without_updated_change_is_conflict_not_silent(self) -> None:
        same = "2026-10-24T12:00:00+02:00"
        with self.assertRaises(PlacspParseError):
            _parse(entries=entry_xml("SYN-9", updated=same, status="PUB") + entry_xml("SYN-9", updated=same, status="EV"))


class TombstoneTests(unittest.TestCase):
    def test_kinds_and_unknown_kind(self) -> None:
        tombs = tombstone_xml("T1", "ANULADA") + tombstone_xml("T2", "CERRADA") + tombstone_xml("T3", None) + tombstone_xml("T4", "OTRA")
        page = _parse(tombstones=tombs)
        self.assertEqual([t.kind for t in page.tombstones], ["ANULADA", "CERRADA", None, None])
        self.assertEqual((page.diagnostics, page.complete), (("tombstone_kind_unknown",), True))

    def test_invalid_tombstone_is_counted_and_fails_closed(self) -> None:
        tombs = tombstone_xml("T1", "ANULADA") + tombstone_xml("T5", "ANULADA", when="mañana")
        with self.assertRaises(PlacspParseError) as raised:
            _parse(tombstones=tombs)
        self.assertEqual(raised.exception.code, "tombstones_discarded")
        page = _diag(tombstones=tombs)
        self.assertEqual((len(page.tombstones), page.discarded_tombstones, page.complete), (1, 1, False))

    def test_tombstone_and_entry_with_same_ref_are_independent(self) -> None:
        page = _parse(tombstones=tombstone_xml("SYN-X"), entries=entry_xml("SYN-X"))
        self.assertEqual((len(page.tombstones), len(page.entries)), (1, 1))


class StructureTests(unittest.TestCase):
    def test_conflicting_values_are_entry_issues(self) -> None:
        folders = entry_xml(extra_status="<cbc:ContractFolderID>OTRO</cbc:ContractFolderID>")
        dir3s = entry_xml(dir3="L01990001", extra_status=(
            "<ext:LocatedContractingParty><cac:Party><cac:PartyIdentification>"
            '<cbc:ID schemeName="DIR3">L01990002</cbc:ID></cac:PartyIdentification></cac:Party></ext:LocatedContractingParty>'
        ))
        for entries in (folders, dir3s):
            page = _diag(entries=entries)
            self.assertEqual(len(page.entries), 0)
            self.assertIn("structured_fields_inconsistent", page.issues[0].codes)

    def test_missing_identity_components(self) -> None:
        self.assertEqual(_diag(entries=entry_xml(folder=None)).issues[0].codes, ("identity_missing",))
        self.assertEqual(_diag(entries=entry_xml(platform=None)).issues[0].codes, ("identity_missing",))
        self.assertEqual(len(_diag(entries=entry_xml(platform=None, dir3="L01990001")).entries), 1)

    def test_atom_id_is_never_trimmed(self) -> None:
        page = _diag(entries=entry_xml(atom_id=" " + ENTRY_ID_PREFIX + "SYN-W"))
        self.assertEqual((len(page.entries), page.issues[0].codes), (0, ("structured_fields_inconsistent",)))
        exact = ENTRY_ID_PREFIX + "syn-Mixto%20Caso"
        self.assertEqual(_diag(entries=entry_xml(atom_id=exact)).entries[0].atom_id, exact)

    def test_unexpected_namespace_is_not_reinterpreted(self) -> None:
        wrong = entry_xml().replace("urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2", "urn:otro:ns")
        feed = feed_xml(entries=entry_xml()).replace(
            b'xmlns:ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2"', b'xmlns:ext="urn:otro:ns"'
        )
        page = parse_feed_page(feed, allow_discarded=True)
        self.assertEqual((len(page.entries), page.issues[0].codes), (0, ("entry_structure_unrecognized",)))
        with self.assertRaises(PlacspParseError) as raised:
            parse_feed_page(feed)
        self.assertEqual(raised.exception.code, "entries_discarded")
        self.assertTrue(wrong)

    def test_invalid_codes_and_dates_are_entry_issues(self) -> None:
        self.assertEqual(_diag(entries=entry_xml(nuts="es522")).issues[0].codes, ("invalid_nuts_code",))
        self.assertEqual(_diag(entries=entry_xml(cpv="4500")).issues[0].codes, ("invalid_cpv_code",))
        self.assertEqual(_diag(entries=entry_xml(deadline="2026-02-30")).issues[0].codes, ("invalid_administrative_date",))
        self.assertEqual(_diag(entries=entry_xml(notices=(("DOC_CN", "ayer"),))).issues[0].codes, ("invalid_administrative_date",))

    def test_valid_temporal_precisions_and_other_nuts(self) -> None:
        page = _parse(entries=entry_xml(deadline="2026-11-10+01:00", nuts="ES", cpv="45000000-7", notices=((None, "2026-10-20T10:00:00+02:00"),)))
        entry = page.entries[0]
        self.assertEqual((entry.submission_deadline.precision, entry.cpv_codes, entry.execution_locations[0].value), ("date", ("45000000-7",), "ES"))
        self.assertEqual((entry.notices[0].issue_date.precision, entry.notices[0].notice_type), ("date_time", None))
        self.assertFalse(entry.declares_castellon_province_execution)

    def test_execution_code_never_invents_municipality(self) -> None:
        entry = _parse(entries=entry_xml(nuts="ES522")).entries[0]
        self.assertEqual(sorted(f.name for f in dataclasses.fields(entry) if "municip" in f.name or "city" in f.name), [])

    def test_issue_does_not_leak_content(self) -> None:
        bad = entry_xml(cpv="NOPE", extra_status="<cac:Contact><cbc:ElectronicMail>fuga@example.invalid</cbc:ElectronicMail></cac:Contact>")
        page = _diag(entries=bad)
        self.assertNotIn("example.invalid", repr(page))
        self.assertEqual(page.issues[0].position, 0)

    def test_pagination_metadata(self) -> None:
        self.assertEqual(_parse().feed.next_href, PAGE2_URL)
        self.assertIsNone(_parse(next_url=None).feed.next_href)
        both = '<link href="https://contrataciondelestado.es/sindicacion/sindicacion_643/otra.atom" rel="next"/>'
        with self.assertRaises(PlacspParseError) as raised:
            _parse(extra_links=both)
        self.assertEqual(raised.exception.code, "pagination_ambiguous")

    def test_xml_base_is_ignored_and_reported(self) -> None:
        page = _parse(root_attrs='xml:base="https://evil.example/"')
        self.assertTrue(page.feed.xml_base_present)
        self.assertEqual(page.feed.next_href, PAGE2_URL)  # el href no se reescribe
        self.assertIn("xml_base_ignored", page.diagnostics)


class IntegrityTests(unittest.TestCase):
    """FIX 1: éxito de parseo XML no es completitud del lote."""

    def setUp(self) -> None:
        _block_network(self)
        self.valid = entry_xml("SYN-OK")
        self.invalid = entry_xml("SYN-BAD", cpv="NOPE", extra_status="<cac:Contact><cbc:ElectronicMail>fuga@example.invalid</cbc:ElectronicMail></cac:Contact>")

    def test_valid_fixture_is_complete(self) -> None:
        page = parse_feed_page((FIXTURES / "feed_valid_page.xml").read_bytes())
        self.assertEqual((page.complete, page.issues, page.discarded_tombstones, page.withheld_entries), (True, (), 0, 0))

    def test_page_with_valid_and_discarded_entry_fails_closed(self) -> None:
        with self.assertRaises(PlacspParseError) as raised:
            _parse(entries=self.valid + self.invalid)
        error = raised.exception
        self.assertEqual((error.code, str(error)), ("entries_discarded", "entries_discarded"))
        self.assertEqual([(i.position, i.codes) for i in error.issues], [(1, ("invalid_cpv_code",))])
        dumped = repr(error) + str(error) + repr(error.issues)
        for secret in ("fuga@", "example.invalid", "SYN-BAD", "SYN/9001", "9990000009001"):
            self.assertNotIn(secret, dumped)
        self.assertRegex(error.issues[0].atom_id_digest, r"^[0-9a-f]{16}$")

    def test_diagnostic_mode_counts_and_marks_incomplete(self) -> None:
        page = _diag(entries=self.valid + self.invalid + self.invalid.replace("SYN-BAD", "SYN-BAD2"))
        self.assertEqual((page.entries_seen, len(page.entries), len(page.issues)), (3, 1, 2))
        self.assertFalse(page.complete)
        self.assertEqual(page.entries_seen, len(page.entries) + len(page.issues) + page.superseded_duplicates + page.benign_duplicates + page.withheld_entries)

    def test_older_valid_version_never_replaces_newer_discarded_one(self) -> None:
        older = entry_xml("SYN-5", updated="2026-10-24T10:00:00+02:00", folder="OLD")
        newer_bad = entry_xml("SYN-5", updated="2026-10-24T11:00:00+02:00", cpv="NOPE")
        for entries in (older + newer_bad, newer_bad + older):
            with self.assertRaises(PlacspParseError) as raised:
                _parse(entries=entries)
            self.assertEqual(raised.exception.code, "entries_discarded")
            page = _diag(entries=entries)
            self.assertEqual((page.entries, page.withheld_entries, page.complete), ((), 1, False))

    def test_resolve_duplicates_rejects_incomplete_batch(self) -> None:
        good = _parse(entries=self.valid)
        partial = _diag(entries=self.valid.replace("SYN-OK", "SYN-OK2") + self.invalid)
        with self.assertRaises(PlacspParseError) as raised:
            resolve_duplicates([good, partial])
        self.assertEqual(raised.exception.code, "incomplete_batch")
        self.assertEqual(len(resolve_duplicates([good])[0]), 1)
        with self.assertRaises(TypeError):
            resolve_duplicates(list(good.entries))  # type: ignore[arg-type]

    def test_no_partial_result_is_returned_as_success(self) -> None:
        pages = []
        with self.assertRaises(PlacspParseError):
            pages.append(_parse(entries=self.valid + self.invalid))
        self.assertEqual(pages, [])


class TitleTests(unittest.TestCase):
    """FIX 2: el título se conserva literal y su estado es explícito."""

    def _entry(self, title: str | None):
        return _parse(entries=entry_xml(title=title)).entries[0]

    def test_whitespace_is_preserved_exactly(self) -> None:
        for raw in ("  Texto  ", "Texto\n", "\tTexto con  espacios \n internos\n"):
            entry = self._entry(raw)
            self.assertEqual((entry.title, entry.title_state), (raw, "present"), repr(raw))

    def test_absent_empty_blank_and_multiple_are_distinct(self) -> None:
        self.assertEqual((self._entry(None).title, self._entry(None).title_state), (None, "absent"))
        self.assertEqual((self._entry("").title, self._entry("").title_state), (None, "empty"))
        blank = self._entry("   \n ")
        self.assertEqual((blank.title, blank.title_state), ("   \n ", "blank"))
        doubled = _parse(entries=entry_xml(title="A").replace("<title>A</title>", "<title>A</title><title>B</title>")).entries[0]
        self.assertEqual((doubled.title, doubled.title_state), (None, "multiple"))
        self.assertEqual(len(_parse(entries=entry_xml(title="A").replace("<title>A</title>", "<title>A</title><title>B</title>")).entries), 1)

    def test_structured_title_without_text_is_empty(self) -> None:
        xml = entry_xml(title="").replace("<title></title>", '<title type="xhtml"><div>Contenido ignorado</div></title>')
        entry = _parse(entries=xml).entries[0]
        self.assertEqual((entry.title, entry.title_state), (None, "empty"))

    def test_title_whitespace_difference_is_a_content_difference(self) -> None:
        plain, padded = self._entry("Texto"), self._entry(" Texto")
        self.assertNotEqual(plain.semantic_projection(), padded.semantic_projection())

    def test_title_states_do_not_leak_into_repr(self) -> None:
        self.assertNotIn("Texto", repr(self._entry("Texto")))


def _projects(*codes: str) -> str:
    return "".join(f"<cac:ProcurementProject><cbc:TypeCode>{c}</cbc:TypeCode></cac:ProcurementProject>" for c in codes)


def _processes(*codes: str) -> str:
    return "".join(f"<cac:TenderingProcess><cbc:ProcedureCode>{c}</cbc:ProcedureCode></cac:TenderingProcess>" for c in codes)


def _deadlines(*dates: str) -> str:
    return "".join(
        f"<cac:TenderingProcess><cac:TenderSubmissionDeadlinePeriod><cbc:EndDate>{d}</cbc:EndDate></cac:TenderSubmissionDeadlinePeriod></cac:TenderingProcess>"
        for d in dates
    )


class ContradictoryStructuredValuesTests(unittest.TestCase):
    """Ningún valor singular se elige por orden de aparición."""

    def setUp(self) -> None:
        _block_network(self)

    def _assert_rejected_both_orders(self, first: str, second: str) -> None:
        for extra in (first + second, second + first):
            page = _diag(entries=entry_xml(extra_status=extra))
            self.assertEqual((len(page.entries), page.issues[0].codes), (0, ("structured_fields_inconsistent",)))
            self.assertFalse(page.complete)
            with self.assertRaises(PlacspParseError) as raised:
                _parse(entries=entry_xml(extra_status=extra))
            self.assertEqual(raised.exception.code, "entries_discarded")

    def test_contradictory_contract_type_in_two_projects(self) -> None:
        self._assert_rejected_both_orders(_projects("1"), _projects("9"))

    def test_contradictory_contract_type_inside_one_project(self) -> None:
        both = "<cac:ProcurementProject><cbc:TypeCode>1</cbc:TypeCode><cbc:TypeCode>9</cbc:TypeCode></cac:ProcurementProject>"
        page = _diag(entries=entry_xml(extra_status=both))
        self.assertEqual(page.issues[0].codes, ("structured_fields_inconsistent",))

    def test_contradictory_procedure(self) -> None:
        self._assert_rejected_both_orders(_processes("1"), _processes("2"))

    def test_contradictory_submission_deadline(self) -> None:
        self._assert_rejected_both_orders(_deadlines("2026-11-10"), _deadlines("2026-11-11"))

    def test_identical_duplicates_are_not_contradictions(self) -> None:
        extra = _projects("1", "1") + _processes("3", "3") + _deadlines("2026-11-10", "2026-11-10")
        page = _parse(entries=entry_xml(extra_status=extra))
        entry = page.entries[0]
        self.assertEqual((entry.contract_type.value, entry.procedure.value, entry.submission_deadline.value), ("1", "3", "2026-11-10"))
        self.assertTrue(page.complete)

    def test_value_in_one_container_and_absent_in_another_is_accepted(self) -> None:
        page = _parse(entries=entry_xml(extra_status=_projects("1") + "<cac:ProcurementProject/>" + _processes("3") + "<cac:TenderingProcess/>"))
        self.assertEqual((page.entries[0].contract_type.value, page.entries[0].procedure.value), ("1", "3"))

    def test_result_does_not_depend_on_order(self) -> None:
        a = _parse(entries=entry_xml(extra_status=_projects("1", "1") + _deadlines("2026-11-10")))
        b = _parse(entries=entry_xml(extra_status=_deadlines("2026-11-10") + _projects("1", "1")))
        self.assertEqual(a.entries, b.entries)


class CumulativeTextLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        _block_network(self)

    def _assert_limit(self, data: bytes, limit: int = 250) -> None:
        with self.assertRaises(PlacspParseError) as raised:
            parse_feed_page(data, ParserLimits(max_element_text_chars=limit))
        self.assertEqual((raised.exception.code, str(raised.exception)), ("limits_exceeded", "limits_exceeded"))

    def test_title_fragmented_by_ignored_children_cannot_bypass_limit(self) -> None:
        pieces = ("x" * 200 + "<cbc:Note>ignorado</cbc:Note>") * 30  # > 5.000 caracteres en segmentos de 200
        title = f"<title>{pieces}</title>"
        data = feed_xml(entries=entry_xml().replace("<updated>", title + "<updated>", 1))
        self._assert_limit(data)

    def test_fragmented_text_under_the_limit_is_still_accepted(self) -> None:
        pieces = ("x" * 40 + "<cbc:Note>y</cbc:Note>") * 5  # 200 caracteres en total
        data = feed_xml(entries=entry_xml().replace("<updated>", f"<title>{pieces}</title><updated>", 1))
        page = parse_feed_page(data, ParserLimits(max_element_text_chars=250))
        self.assertEqual(page.entries[0].title, "x" * 200)

    def test_text_in_ignored_element_fragmented_by_its_children_is_counted(self) -> None:
        pieces = ("z" * 200 + "<cbc:Note>y</cbc:Note>") * 30
        data = feed_xml(entries=entry_xml(extra_status=f"<cac:Contact>{pieces}</cac:Contact>"))
        self._assert_limit(data)

    def test_many_separate_ignored_elements_each_under_limit_are_accepted(self) -> None:
        many = "".join(f"<cac:Contact><cbc:Note>{'q' * 200}</cbc:Note></cac:Contact>" for _ in range(30))
        page = parse_feed_page(feed_xml(entries=entry_xml(extra_status=many)), ParserLimits(max_element_text_chars=250))
        self.assertEqual(len(page.entries), 1)

    def test_indentation_between_children_does_not_count(self) -> None:
        entries = "\n      ".join(entry_xml(f"SYN-{i}") for i in range(300))
        data = feed_xml(entries="\n      " + entries + "\n")
        page = parse_feed_page(data, ParserLimits(max_element_text_chars=250))
        self.assertEqual(len(page.entries), 300)

    def _with_title(self, inner: str) -> bytes:
        return feed_xml(entries=entry_xml().replace("<updated>", f"<title>{inner}</title><updated>", 1))

    def test_whitespace_only_title_counts_against_the_limit(self) -> None:
        self._assert_limit(self._with_title(" " * 5000))
        self._assert_limit(self._with_title("\t\n" * 2500))
        ok = parse_feed_page(self._with_title(" " * 200), ParserLimits(max_element_text_chars=250))
        self.assertEqual((ok.entries[0].title, ok.entries[0].title_state), (" " * 200, "blank"))

    def test_whitespace_fragmented_by_children_is_counted(self) -> None:
        self._assert_limit(self._with_title((" " * 100 + "<cbc:Note>y</cbc:Note>") * 5))
        ok = parse_feed_page(self._with_title((" " * 40 + "<cbc:Note>y</cbc:Note>") * 5), ParserLimits(max_element_text_chars=250))
        self.assertEqual(ok.entries[0].title, " " * 200)

    def test_title_over_limit_fragmented_with_content_is_rejected(self) -> None:
        self._assert_limit(self._with_title(("a" * 60 + "<cbc:Note>y</cbc:Note>") * 5))  # 300 > 250

    def test_title_of_exactly_the_limit_is_kept_literally(self) -> None:
        text = " " + "a" * 248 + " "
        page = parse_feed_page(self._with_title(text), ParserLimits(max_element_text_chars=250))
        self.assertEqual((page.entries[0].title, page.entries[0].title_state), (text, "present"))

    def test_indentation_inside_structural_containers_never_counts(self) -> None:
        indented = entry_xml(extra_status="\n" + "    \n" * 400 + "<cac:ProcurementProject>\n" + "        \n" * 400 + "</cac:ProcurementProject>")
        page = parse_feed_page(feed_xml(entries=indented), ParserLimits(max_element_text_chars=250))
        self.assertEqual(len(page.entries), 1)

    def test_other_limits_still_apply(self) -> None:
        data = feed_xml(entries=entry_xml())
        for limits in (ParserLimits(max_bytes=10), ParserLimits(max_depth=3), ParserLimits(max_nodes=5)):
            with self.assertRaises(PlacspParseError) as raised:
                parse_feed_page(data, limits)
            self.assertEqual(raised.exception.code, "limits_exceeded")


class SecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        _block_network(self)

    def _assert_code(self, data: bytes, code: str, limits: ParserLimits | None = None) -> None:
        with self.assertRaises(PlacspParseError) as raised:
            parse_feed_page(data, limits)
        self.assertEqual((raised.exception.code, str(raised.exception)), (code, code))

    def test_malformed_and_empty(self) -> None:
        self._assert_code((FIXTURES / "feed_malformed.xml").read_bytes(), "invalid_xml")
        self._assert_code(b"", "invalid_xml")
        self._assert_code(b"no es xml", "invalid_xml")
        self._assert_code(feed_xml()[:-9], "invalid_xml")  # truncado

    def test_doctype_and_entities_are_rejected(self) -> None:
        self._assert_code((FIXTURES / "feed_doctype.xml").read_bytes(), "xml_security_rejection")
        self._assert_code((FIXTURES / "feed_entity.xml").read_bytes(), "xml_security_rejection")
        bomb = (
            b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
            b'<feed xmlns="http://www.w3.org/2005/Atom"><id>&b;</id></feed>'
        )
        self._assert_code(bomb, "xml_security_rejection")
        external = b'<?xml version="1.0"?><!DOCTYPE f SYSTEM "http://127.0.0.1/x.dtd"><feed xmlns="http://www.w3.org/2005/Atom"/>'
        self._assert_code(external, "xml_security_rejection")

    def test_undeclared_entity_reference_without_dtd(self) -> None:
        self._assert_code(b'<feed xmlns="http://www.w3.org/2005/Atom"><id>&nada;</id></feed>', "invalid_xml")

    def test_wrong_root_and_namespace(self) -> None:
        self._assert_code(b"<rss><channel/></rss>", "invalid_atom_root")
        self._assert_code(b'<feed xmlns="urn:otro"><id>x</id></feed>', "invalid_atom_root")

    def test_unsupported_encodings(self) -> None:
        self._assert_code('<?xml version="1.0" encoding="UTF-16"?><feed/>'.encode("utf-16"), "xml_encoding_unsupported")
        self._assert_code(b'<?xml version="1.0" encoding="ISO-8859-1"?><feed xmlns="http://www.w3.org/2005/Atom"/>', "xml_encoding_unsupported")

    def test_limits(self) -> None:
        big = feed_xml(entries=entry_xml())
        self._assert_code(big, "limits_exceeded", ParserLimits(max_bytes=len(big) - 1))
        self._assert_code(big, "limits_exceeded", ParserLimits(max_nodes=10))
        self._assert_code(big, "limits_exceeded", ParserLimits(max_depth=3))
        self._assert_code(big, "limits_exceeded", ParserLimits(max_element_text_chars=20))
        many = feed_xml(entries=entry_xml("SYN-A") + entry_xml("SYN-B"))
        self._assert_code(many, "limits_exceeded", ParserLimits(max_entries=1))
        deep = b'<feed xmlns="http://www.w3.org/2005/Atom">' + b"<x>" * 200 + b"</x>" * 200 + b"</feed>"
        self._assert_code(deep, "limits_exceeded", ParserLimits(max_depth=64))

    def test_oversized_text_in_skipped_element_is_still_limited(self) -> None:
        payload = feed_xml(entries=entry_xml(extra_status="<cac:Contact><cbc:Note>" + "x" * 50_000 + "</cbc:Note></cac:Contact>"))
        self._assert_code(payload, "limits_exceeded", ParserLimits(max_element_text_chars=10_000))

    def test_errors_never_echo_content(self) -> None:
        secret = b"Q0000000J-persona.senuelo@example.invalid"
        for data in (b"<feed>" + secret, b'<!DOCTYPE x [<!ENTITY e "' + secret + b'">]><x/>'):
            with self.assertRaises(PlacspParseError) as raised:
                parse_feed_page(data)
            self.assertNotIn("senuelo", repr(raised.exception) + str(raised.exception))

    def test_parser_does_not_touch_network_or_disk(self) -> None:
        with mock.patch("builtins.open", side_effect=AssertionError("sin disco")):
            parse_feed_page(feed_xml(entries=entry_xml()))


if __name__ == "__main__":
    unittest.main()
