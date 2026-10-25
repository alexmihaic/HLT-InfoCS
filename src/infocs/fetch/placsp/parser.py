"""Parser puro ATOM/CODICE del canal 643. Sin red, sin disco, sin estado.

Solo se materializan los elementos de la lista blanca del contrato v0.2 §8. El
resto del XML (contactos, NIF, direcciones, resultados, documentos, lotes) se
descarta en el propio evento de lectura: nunca llega a un nodo ni a un resultado.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
import hashlib
import re
from xml.parsers import expat

from infocs.fetch.placsp.models import (
    CodeReference,
    EntryIssue,
    FeedMetadata,
    NoticeObservation,
    OfficialTemporalValue,
    ParserLimits,
    PlacspEntry,
    PlacspPage,
    PlacspParseError,
    Tombstone,
)

_ATOM = "http://www.w3.org/2005/Atom"
_TOMB = "http://purl.org/atompub/tombstones/1.0"
_XML_BASE = "http://www.w3.org/XML/1998/namespace}base"
_NS_GROUPS = {
    _ATOM: "atom",
    _TOMB: "tomb",
    "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2": "cbc",
    "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2": "cbc",
    "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2": "cac",
    "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2": "cac",
    "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2": "ext",
    "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2": "bext",
}

_FEED = (("atom", "feed"),)
_ENTRY = _FEED + (("atom", "entry"),)
_STATUS = _ENTRY + (("ext", "ContractFolderStatus"),)
_LCP = _STATUS + (("ext", "LocatedContractingParty"),)
_PARTY_ID = _LCP + (("cac", "Party"), ("cac", "PartyIdentification"))
_ID_PATH = _PARTY_ID + (("cbc", "ID"),)
_PROJECT = _STATUS + (("cac", "ProcurementProject"),)
_CLASSIFICATION = _PROJECT + (("cac", "RequiredCommodityClassification"),)
_PLACE = _PROJECT + (("cac", "RealizedLocation"),)
_PROCESS = _STATUS + (("cac", "TenderingProcess"),)
_DEADLINE = _PROCESS + (("cac", "TenderSubmissionDeadlinePeriod"),)
_NOTICE = _STATUS + (("ext", "ValidNoticeInfo"),)
_LOTS = _STATUS + (("cac", "ProcurementProjectLot"),)
_DELETED = _FEED + (("tomb", "deleted-entry"),)
_COMMENT = _DELETED + (("tomb", "comment"),)
_FEED_ID, _FEED_UPDATED, _FEED_LINK = (_FEED + (("atom", name),) for name in ("id", "updated", "link"))

_ALLOWED_PATHS = frozenset(
    {
        _FEED, _FEED_ID, _FEED_UPDATED, _FEED_LINK, _DELETED, _COMMENT,
        _ENTRY, _ENTRY + (("atom", "id"),), _ENTRY + (("atom", "updated"),), _ENTRY + (("atom", "title"),),
        _STATUS, _STATUS + (("cbc", "ContractFolderID"),), _STATUS + (("bext", "ContractFolderStatusCode"),),
        _LCP, _LCP + (("cac", "Party"),), _PARTY_ID, _ID_PATH,
        _PROJECT, _PROJECT + (("cbc", "TypeCode"),),
        _CLASSIFICATION, _CLASSIFICATION + (("cbc", "ItemClassificationCode"),),
        _PLACE, _PLACE + (("cbc", "CountrySubentityCode"),),
        _PROCESS, _PROCESS + (("cbc", "ProcedureCode"),),
        _DEADLINE, _DEADLINE + (("cbc", "EndDate"),),
        _NOTICE, _NOTICE + (("bext", "NoticeTypeCode"),), _NOTICE + (("bext", "NoticeIssueDate"),),
    }
)
# Hojas de la lista blanca: elementos que contienen texto (no son prefijo de otra ruta permitida).
_LEAF_PATHS = frozenset(
    path for path in _ALLOWED_PATHS if not any(other != path and other[: len(path)] == path for other in _ALLOWED_PATHS)
)
_KEPT_ATTRIBUTES = frozenset({"schemeName", "listURI", "listVersionID", "rel", "href", "ref", "when", "type"})
_AUTHORITY_SCHEMES = frozenset({"ID_PLATAFORMA", "DIR3"})
_TOMBSTONE_KINDS = frozenset({"ANULADA", "CERRADA"})

_INSTANT = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})\Z")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})(Z|[+-]\d{2}:\d{2})?\Z")
_CPV = re.compile(r"\d{8}(?:-\d)?\Z")
_NUTS = re.compile(r"[A-Z]{2}[A-Z0-9]{0,3}\Z")
_ENCODING_DECLARATION = re.compile(rb"<\?xml[^>]*?encoding\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_MAX_ATTRIBUTE_CHARS = 300


class _Node:
    __slots__ = ("path", "attrib", "text", "children")

    def __init__(self, path: tuple, attrib: dict[str, str]) -> None:
        self.path = path
        self.attrib = attrib
        self.text: list[str] = []
        self.children: list[_Node] = []

    def value(self) -> str:
        return "".join(self.text)


def _parse_instant(text: str) -> datetime | None:
    match = _INSTANT.fullmatch(text)
    if match is None:
        return None
    base, fraction, offset = match.groups()
    micro = (fraction or "").ljust(6, "0")[:6]
    try:
        return datetime.fromisoformat(f"{base}.{micro}{'+00:00' if offset == 'Z' else offset}")
    except ValueError:
        return None


def _parse_temporal(text: str) -> OfficialTemporalValue | None:
    if "T" in text:
        return OfficialTemporalValue("date_time", text) if _parse_instant(text) is not None else None
    match = _DATE.fullmatch(text)
    if match is None:
        return None
    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        return None
    return OfficialTemporalValue("date", text)


def _key(name: str) -> tuple[str, str]:
    uri, sep, local = name.rpartition("}")
    return (_NS_GROUPS.get(uri, "other") if sep else "none", local)


def _kids(node: _Node, suffix: tuple) -> list[_Node]:
    return [child for child in node.children if child.path[-len(suffix):] == suffix]


def _singular(nodes: list[_Node], codes: list[str]) -> str | None:
    """Valor único (sin recortar) de varios nodos del mismo elemento."""
    values = {node.value() for node in nodes}
    if len(values) > 1:
        codes.append("structured_fields_inconsistent")
        return None
    if not values:
        return None
    value = values.pop()
    if not value or value != value.strip():
        codes.append("structured_fields_inconsistent")
        return None
    return value


def _code_reference(nodes: list[_Node], codes: list[str]) -> CodeReference | None:
    refs = set()
    for node in nodes:
        value = node.value()
        uri, version = node.attrib.get("listURI"), node.attrib.get("listVersionID")
        if (
            not value or value != value.strip() or len(value) > _MAX_ATTRIBUTE_CHARS
            or any(item is not None and len(item) > _MAX_ATTRIBUTE_CHARS for item in (uri, version))
        ):
            codes.append("invalid_code")
            return None
        refs.add(CodeReference(value, uri, version))
    if len(refs) > 1:
        codes.append("structured_fields_inconsistent")
        return None
    return next(iter(refs), None)


def _notice_sort_key(notice: NoticeObservation) -> tuple:
    kind = notice.notice_type
    when = notice.issue_date
    return (
        (kind.value, kind.list_uri or "", kind.list_version or "") if kind else ("",),
        (when.precision, when.value) if when else ("",),
    )


def _title(titles: list[_Node]) -> tuple[str | None, str]:
    """Título literal (sin `strip` ni normalización) y su estado.

    absent: sin `atom:title`; multiple: más de uno (no se elige ninguno);
    empty: texto de longitud cero; blank: solo espacios (se conserva tal cual);
    present: texto con contenido. Cualquier transformación de presentación
    queda para la capa de normalización.
    """
    if not titles:
        return None, "absent"
    if len(titles) > 1:
        return None, "multiple"
    raw = titles[0].value()
    if raw == "":
        return None, "empty"
    return raw, ("blank" if not raw.strip() else "present")


def _id_digest(node: _Node) -> str | None:
    values = {item.value() for item in _kids(node, (("atom", "id"),))}
    if len(values) != 1:
        return None
    return hashlib.sha256(next(iter(values)).encode("utf-8")).hexdigest()[:16]


def _extract_entry(node: _Node, has_lots: bool) -> tuple[PlacspEntry | None, list[str]]:
    codes: list[str] = []
    atom_id = _singular(_kids(node, (("atom", "id"),)), codes)
    if atom_id is None and "structured_fields_inconsistent" not in codes:
        codes.append("identity_missing")
    updated_text = _singular(_kids(node, (("atom", "updated"),)), codes)
    updated = _parse_instant(updated_text) if updated_text else None
    if updated is None:
        codes.append("invalid_updated")
    title, title_state = _title(_kids(node, (("atom", "title"),)))

    statuses = _kids(node, (("ext", "ContractFolderStatus"),))
    if len(statuses) != 1:
        codes.append("entry_structure_unrecognized")
        return None, codes
    status = statuses[0]

    folder_id = _singular(_kids(status, (("cbc", "ContractFolderID"),)), codes)
    if folder_id is None and "structured_fields_inconsistent" not in codes:
        codes.append("identity_missing")
    by_scheme: dict[str, list[_Node]] = {"ID_PLATAFORMA": [], "DIR3": []}
    for lcp in _kids(status, (("ext", "LocatedContractingParty"),)):
        for party in _kids(lcp, (("cac", "Party"),)):
            for party_id in _kids(party, (("cac", "PartyIdentification"),)):
                for id_node in _kids(party_id, (("cbc", "ID"),)):
                    by_scheme[id_node.attrib["schemeName"]].append(id_node)
    id_plataforma = _singular(by_scheme["ID_PLATAFORMA"], codes)
    dir3 = _singular(by_scheme["DIR3"], codes)
    if id_plataforma is None and dir3 is None and "structured_fields_inconsistent" not in codes:
        codes.append("identity_missing")

    status_code = _code_reference(_kids(status, (("bext", "ContractFolderStatusCode"),)), codes)
    cpv_codes: set[str] = set()
    locations: set[CodeReference] = set()
    projects = _kids(status, (("cac", "ProcurementProject"),))
    # Valores singulares: se juntan los nodos de TODOS los contenedores y se validan como conjunto;
    # contradicciones -> structured_fields_inconsistent, nunca "gana" el último ni el primero.
    contract_type = _code_reference([n for project in projects for n in _kids(project, (("cbc", "TypeCode"),))], codes)
    for project in projects:
        for classification in _kids(project, (("cac", "RequiredCommodityClassification"),)):
            for cpv_node in _kids(classification, (("cbc", "ItemClassificationCode"),)):
                if _CPV.fullmatch(cpv_node.value()):
                    cpv_codes.add(cpv_node.value())
                else:
                    codes.append("invalid_cpv_code")
        for place in _kids(project, (("cac", "RealizedLocation"),)):
            for code_node in _kids(place, (("cbc", "CountrySubentityCode"),)):
                if _NUTS.fullmatch(code_node.value()):
                    locations.add(
                        CodeReference(code_node.value(), code_node.attrib.get("listURI"), code_node.attrib.get("listVersionID"))
                    )
                else:
                    codes.append("invalid_nuts_code")
    processes = _kids(status, (("cac", "TenderingProcess"),))
    procedure = _code_reference([n for process in processes for n in _kids(process, (("cbc", "ProcedureCode"),))], codes)
    deadline = None
    end_dates = [
        n for process in processes for period in _kids(process, (("cac", "TenderSubmissionDeadlinePeriod"),))
        for n in _kids(period, (("cbc", "EndDate"),))
    ]
    deadline_text = _singular(end_dates, codes)
    if deadline_text is not None:
        deadline = _parse_temporal(deadline_text)
        if deadline is None:
            codes.append("invalid_administrative_date")
    notices: set[NoticeObservation] = set()
    for info in _kids(status, (("ext", "ValidNoticeInfo"),)):
        notice_type = _code_reference(_kids(info, (("bext", "NoticeTypeCode"),)), codes)
        issue_text = _singular(_kids(info, (("bext", "NoticeIssueDate"),)), codes)
        issue_date = _parse_temporal(issue_text) if issue_text is not None else None
        if issue_text is not None and issue_date is None:
            codes.append("invalid_administrative_date")
        if notice_type is not None or issue_date is not None:
            notices.add(NoticeObservation(notice_type, issue_date))

    if codes:
        return None, codes
    assert atom_id is not None and updated is not None and folder_id is not None
    entry = PlacspEntry(
        atom_id=atom_id,
        updated=updated,
        title=title,
        title_state=title_state,
        contract_folder_id=folder_id,
        id_plataforma=id_plataforma,
        dir3=dir3,
        status=status_code,
        contract_type=contract_type,
        procedure=procedure,
        cpv_codes=tuple(sorted(cpv_codes)),
        notices=tuple(sorted(notices, key=_notice_sort_key)),
        submission_deadline=deadline,
        execution_locations=tuple(sorted(locations)),
        has_lots=has_lots,
    )
    return entry, []


class _FeedReader:
    def __init__(self, limits: ParserLimits) -> None:
        self.limits = limits
        self.nodes = 0
        self.depth = 0
        self.skip = 0
        self.stack: list[_Node] = []
        self.root_seen = False
        self.char_stack: list[int] = []  # texto propio acumulado de cada elemento abierto
        self.entry_has_lots = False
        self.xml_base = False
        self.entries_seen = 0
        self.parsed: list[PlacspEntry] = []
        self.issues: list[EntryIssue] = []
        self.tombstones: list[Tombstone] = []
        self.discarded_tombstones = 0
        self.diagnostics: set[str] = set()
        self.feed_ids: list[str] = []
        self.feed_updates: list[str] = []
        self.feed_links: list[tuple[str, str]] = []

    def start(self, name: str, attrs: dict[str, str]) -> None:
        self.depth += 1
        self.nodes += 1
        self.char_stack.append(0)
        if self.depth > self.limits.max_depth or self.nodes > self.limits.max_nodes:
            raise PlacspParseError("limits_exceeded")
        if _XML_BASE in attrs:
            self.xml_base = True  # se ignora: no puede ampliar permisos de red
        if self.skip:
            self.skip += 1
            return
        key = _key(name)
        if not self.root_seen:
            if key != ("atom", "feed"):
                raise PlacspParseError("invalid_atom_root")
            self.root_seen = True
            self.stack.append(_Node(_FEED, {}))
            return
        path = self.stack[-1].path + (key,)
        if path == _LOTS:
            self.entry_has_lots = True  # solo presencia; el contenido del lote se descarta
        if path not in _ALLOWED_PATHS or (path == _ID_PATH and attrs.get("schemeName") not in _AUTHORITY_SCHEMES):
            self.skip = 1
            return
        if path == _ENTRY:
            self.entry_has_lots = False
        self.stack.append(_Node(path, {k: v for k, v in attrs.items() if k in _KEPT_ATTRIBUTES}))

    def end(self, name: str) -> None:
        self.depth -= 1
        self.char_stack.pop()
        if self.skip:
            self.skip -= 1
            return
        node = self.stack.pop()
        if not self.stack:
            return
        path = node.path
        if path == _ENTRY:
            self._finish_entry(node)
        elif path == _DELETED:
            self._finish_tombstone(node)
        elif path == _FEED_ID:
            self.feed_ids.append(node.value())
        elif path == _FEED_UPDATED:
            self.feed_updates.append(node.value())
        elif path == _FEED_LINK:
            self.feed_links.append((node.attrib.get("rel", ""), node.attrib.get("href", "")))
        else:
            self.stack[-1].children.append(node)

    def chars(self, data: str) -> None:
        # Todo carácter de un campo de texto conservado (hoja de la lista blanca) cuenta, espacios
        # incluidos. La sangría entre hijos de contenedores estructurales y el texto de elementos
        # excluidos solo cuentan si tienen contenido (su volumen lo acota `max_bytes`).
        if self.char_stack:
            kept_leaf = not self.skip and bool(self.stack) and self.stack[-1].path in _LEAF_PATHS
            if kept_leaf or not data.isspace():
                self.char_stack[-1] += len(data)
                if self.char_stack[-1] > self.limits.max_element_text_chars:
                    raise PlacspParseError("limits_exceeded")
        if not self.skip and self.stack:
            self.stack[-1].text.append(data)

    @staticmethod
    def reject_dtd(*_args: object) -> None:
        raise PlacspParseError("xml_security_rejection")

    def _finish_entry(self, node: _Node) -> None:
        self.entries_seen += 1
        if self.entries_seen > self.limits.max_entries:
            raise PlacspParseError("limits_exceeded")
        entry, codes = _extract_entry(node, self.entry_has_lots)
        if entry is not None:
            self.parsed.append(entry)
        else:
            self.issues.append(EntryIssue(self.entries_seen - 1, tuple(sorted(set(codes))), _id_digest(node)))

    def _finish_tombstone(self, node: _Node) -> None:
        ref = node.attrib.get("ref")
        when = _parse_instant(node.attrib.get("when", ""))
        if not ref or ref != ref.strip() or when is None:
            self.discarded_tombstones += 1
            return
        kind = next((c.attrib.get("type") for c in node.children if c.path == _COMMENT), None)
        if kind is not None and kind not in _TOMBSTONE_KINDS:
            self.diagnostics.add("tombstone_kind_unknown")
        self.tombstones.append(Tombstone(ref, when, kind if kind in _TOMBSTONE_KINDS else None))


def resolve_duplicates(pages: Sequence[PlacspPage]) -> tuple[tuple[PlacspEntry, ...], int, int]:
    """Resuelve duplicados de un lote de PÁGINAS, que deben ser completas.

    Recibe páginas (no entradas sueltas) para poder rechazar un lote incompleto:
    si alguna página tiene incidencias, `incomplete_batch`. Devuelve (ganadoras,
    versiones anteriores descartadas, duplicados benignos).
    """
    if not all(isinstance(page, PlacspPage) for page in pages):
        raise TypeError("resolve_duplicates recibe PlacspPage, no entradas sueltas.")
    if not all(page.complete for page in pages):
        raise PlacspParseError("incomplete_batch")
    return _resolve_entries([entry for page in pages for entry in page.entries])


def _resolve_entries(
    entries: list[PlacspEntry] | tuple[PlacspEntry, ...],
) -> tuple[tuple[PlacspEntry, ...], int, int]:
    """Por `entry.id` prevalece el mayor `updated` (instante). Mismo id, mismo
    instante y contenido distinto es `duplicate_incompatible` (error de lote).
    """
    groups: dict[str, list[tuple[int, PlacspEntry]]] = {}
    for index, entry in enumerate(entries):
        groups.setdefault(entry.atom_id, []).append((index, entry))
    winners: list[tuple[int, PlacspEntry]] = []
    superseded = benign = 0
    for group in groups.values():
        latest = max(entry.updated for _, entry in group)
        tied = [(index, entry) for index, entry in group if entry.updated == latest]
        if len({entry.semantic_projection() for _, entry in tied}) > 1:
            raise PlacspParseError("duplicate_incompatible")
        winners.append(tied[0])
        benign += len(tied) - 1
        superseded += len(group) - len(tied)
    winners.sort(key=lambda item: item[0])
    return tuple(entry for _, entry in winners), superseded, benign


def parse_feed_page(data: bytes, limits: ParserLimits | None = None, *, allow_discarded: bool = False) -> PlacspPage:
    """Parsea una página. Por defecto falla cerrado si se descartó cualquier entrada
    o tombstone (`entries_discarded` / `tombstones_discarded`, con `error.issues` como
    diagnóstico). `allow_discarded=True` es solo para diagnóstico: devuelve una página
    con `complete == False`, sin las entradas válidas que compartan id con una descartada.
    """
    limits = limits or ParserLimits()
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise PlacspParseError("invalid_xml")
    if len(data) > limits.max_bytes:
        raise PlacspParseError("limits_exceeded")
    data = bytes(data)
    if data.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")):
        raise PlacspParseError("xml_encoding_unsupported")
    declaration = _ENCODING_DECLARATION.search(data[:200])
    if declaration is not None and declaration.group(1).lower() != b"utf-8":
        raise PlacspParseError("xml_encoding_unsupported")

    reader = _FeedReader(limits)
    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = True
    parser.StartElementHandler = reader.start
    parser.EndElementHandler = reader.end
    parser.CharacterDataHandler = reader.chars
    parser.StartDoctypeDeclHandler = reader.reject_dtd
    parser.EntityDeclHandler = reader.reject_dtd
    parser.ExternalEntityRefHandler = reader.reject_dtd
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(data, True)
    except PlacspParseError:
        raise
    except expat.ExpatError:
        raise PlacspParseError("invalid_xml") from None
    except RecursionError:
        raise PlacspParseError("limits_exceeded") from None
    if not reader.root_seen:
        raise PlacspParseError("invalid_atom_root")

    feed_atom_id = reader.feed_ids[0] if len(set(reader.feed_ids)) == 1 else None
    feed_updated = _parse_instant(reader.feed_updates[0]) if len(set(reader.feed_updates)) == 1 else None
    next_hrefs = {href for rel, href in reader.feed_links if rel == "next"}
    if len(next_hrefs) > 1:
        raise PlacspParseError("pagination_ambiguous")
    if reader.xml_base:
        reader.diagnostics.add("xml_base_ignored")
    issues = tuple(reader.issues)
    if not allow_discarded:
        if issues:
            raise PlacspParseError("entries_discarded", issues)
        if reader.discarded_tombstones:
            raise PlacspParseError("tombstones_discarded")
    shadowed = {issue.atom_id_digest for issue in issues if issue.atom_id_digest is not None}
    kept = [e for e in reader.parsed if hashlib.sha256(e.atom_id.encode("utf-8")).hexdigest()[:16] not in shadowed]
    withheld = len(reader.parsed) - len(kept)
    entries, superseded, benign = _resolve_entries(kept)
    return PlacspPage(
        feed=FeedMetadata(feed_atom_id, feed_updated, next(iter(next_hrefs), None), reader.xml_base),
        entries=entries,
        tombstones=tuple(reader.tombstones),
        issues=issues,
        entries_seen=reader.entries_seen,
        superseded_duplicates=superseded,
        benign_duplicates=benign,
        nodes_seen=reader.nodes,
        diagnostics=tuple(sorted(reader.diagnostics)),
        discarded_tombstones=reader.discarded_tombstones,
        withheld_entries=withheld,
    )
