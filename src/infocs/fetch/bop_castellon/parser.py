"""Parseo acotado del flujo JSF del BOP y su listado de anuncios."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urljoin, urlsplit
import xml.etree.ElementTree as ET

from infocs.fetch.bop_castellon.config import (
    BOP_ANNOUNCEMENTS_CONTAINER_ID,
    BOP_ARCHIVE_URL,
    BOP_BASE_URL,
    BOP_REDUCED_FORM_ID,
    BOP_RESULT_UPDATE_ID,
    validate_official_url,
    validate_portal_navigation_url,
)
from infocs.fetch.bop_castellon.models import BOPAnnouncement, BOPIssue


class BOPContractError(ValueError):
    """Respuesta BOP sin la estructura contractual mínima; no incluye payload."""

    def __init__(self, code: str, *, diagnostic: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.diagnostic = diagnostic


_DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}\Z")
_ISSUE_CODE_RE = re.compile(r"B\d{6}\Z", re.IGNORECASE)
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_PRIMEFACES_AB_RE = re.compile(
    r"PrimeFaces\.ab\(\s*\{\s*s\s*:\s*['\"]([^'\"]+)['\"]\s*,\s*f\s*:\s*['\"]([^'\"]+)['\"]",
)
_CARD_NUMBER_RE = re.compile(r"\bN[ºo°]\s*(\d+)\b", re.IGNORECASE)
_CARD_DATE_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s+(?P<month>enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


@dataclass(frozen=True, slots=True)
class BOPIssueSelection:
    """Metadatos de edición y acción de UI extraída del markup servido."""

    issue: BOPIssue
    form_id: str
    source_component: str
    action_url: str
    hidden_fields: tuple[tuple[str, str], ...]


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None = None
    children: list[_Node] = field(default_factory=list)
    text: list[str] = field(default_factory=list)

    def descendants(self, tag: str | None = None) -> list[_Node]:
        found: list[_Node] = []
        for child in self.children:
            if tag is None or child.tag == tag:
                found.append(child)
            found.extend(child.descendants(tag))
        return found

    def all_text(self) -> str:
        chunks = list(self.text)
        for child in self.children:
            chunks.append(child.all_text())
        return " ".join(" ".join(chunks).split())

    def ancestors(self) -> list[_Node]:
        nodes: list[_Node] = []
        node = self.parent
        while node is not None:
            nodes.append(node)
            node = node.parent
        return nodes


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {key.lower(): value or "" for key, value in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag.lower() not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {key.lower(): value or "" for key, value in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].text.append(data)


class _FormStateParser(HTMLParser):
    def __init__(self, form_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.form_id = form_id
        self._inside = False
        self.form_count = 0
        self.action: str | None = None
        self.hidden_fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "form":
            if self._inside:
                self._inside = False
            self._inside = values.get("id") == self.form_id
            if self._inside:
                self.form_count += 1
                self.action = values.get("action")
        elif self._inside and tag.lower() == "input" and values.get("type", "").lower() == "hidden":
            name = values.get("name")
            if name:
                self.hidden_fields[name] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._inside:
            self._inside = False


def parse_view_state(html: str) -> tuple[str, dict[str, str]]:
    """Extrae ViewState y hidden inputs exclusivamente del formulario buscadorForm."""
    action, fields = _parse_form(html, "buscadorForm")
    del action
    view_state = fields.get("javax.faces.ViewState", "")
    if not view_state:
        raise BOPContractError("view_state_missing")
    return view_state, fields


def parse_search_partial_response(
    xml_text: str,
    requested_date: date,
    *,
    current_view_state: str,
    archive_url: str = BOP_ARCHIVE_URL,
) -> BOPIssueSelection | None:
    """Interpreta búsqueda de ediciones y extrae la acción PrimeFaces de su tarjeta."""
    root = _parse_xml(xml_text, "invalid_search_partial_xml")
    result_update = _find_update(root, BOP_RESULT_UPDATE_ID)
    if result_update is None:
        raise BOPContractError("result_update_missing")
    tree = _parse_html(_update_html(result_update))
    if not tree.descendants("table"):
        raise BOPContractError("listing_structure_invalid")

    matched: list[tuple[str, date, str, str]] = []
    for row in tree.descendants("tr"):
        row_data = _parse_issue_row(row)
        if row_data is not None and row_data[1] == requested_date:
            matched.append(row_data)
    if not matched:
        return None
    if len(matched) != 1:
        raise BOPContractError("duplicate_requested_issue")

    portal_id, published_date, issue_number, issue_code = matched[0]
    reduced_update = _find_update(root, BOP_REDUCED_FORM_ID)
    if reduced_update is None:
        raise BOPContractError("selection_component_missing")
    reduced_html = _update_html(reduced_update)
    form_action, hidden = _parse_form(reduced_html, BOP_REDUCED_FORM_ID)
    if not form_action:
        raise BOPContractError("selection_form_action_missing")
    try:
        action_url = validate_portal_navigation_url(urljoin(archive_url, form_action))
    except ValueError as error:
        raise BOPContractError("selection_action_unsafe") from error
    reduced_tree = _parse_html(reduced_html)
    source_component = _find_issue_card_source(reduced_tree, published_date, issue_number)
    if not source_component:
        raise BOPContractError("selection_component_missing")

    view_state = update_view_state_from_partial(xml_text, current_view_state)
    hidden["javax.faces.ViewState"] = view_state
    issue = BOPIssue(
        portal_id=portal_id,
        published_date=published_date,
        issue_number=issue_number,
        issue_code=issue_code,
    )
    return BOPIssueSelection(
        issue=issue,
        form_id=BOP_REDUCED_FORM_ID,
        source_component=source_component,
        action_url=action_url,
        hidden_fields=tuple(hidden.items()),
    )


def update_view_state_from_partial(xml_text: str, current_view_state: str) -> str:
    """Usa el ViewState actualizado si el partial-response lo reemplaza."""
    if not current_view_state:
        raise BOPContractError("view_state_missing")
    root = _parse_xml(xml_text, "invalid_partial_xml")
    updates = [
        element for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "update"
        and "javax.faces.ViewState" in element.attrib.get("id", "")
    ]
    states = ["".join(element.itertext()).strip() for element in updates]
    states = [state for state in states if state]
    if not states:
        return current_view_state
    if len(set(states)) != 1:
        raise BOPContractError("view_state_update_ambiguous")
    return states[0]


def parse_selection_redirect(xml_text: str, *, response_url: str) -> str:
    """Lee la instrucción redirect JSF y sólo permite navegación al portal oficial."""
    root = _parse_xml(xml_text, "invalid_selection_partial_xml")
    redirects = [
        element for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "redirect"
    ]
    if len(redirects) != 1:
        raise BOPContractError("navigation_instruction_missing")
    target = redirects[0].attrib.get("url", "").strip()
    if not target:
        raise BOPContractError("navigation_instruction_missing")
    try:
        return validate_portal_navigation_url(urljoin(response_url, target))
    except ValueError as error:
        raise BOPContractError("navigation_unsafe") from error


def parse_announcements_page(html: str) -> tuple[BOPAnnouncement, ...]:
    """Empareja cada componente de descarga con su título por estructura DOM."""
    tree = _parse_html(html)
    containers = [node for node in tree.descendants() if node.attrs.get("id") == BOP_ANNOUNCEMENTS_CONTAINER_ID]
    if len(containers) != 1:
        raise BOPContractError("announcements_container_invalid")
    container = containers[0]
    titles = [node for node in container.descendants("span") if "titulo4" in _classes(node)]
    if not titles:
        raise BOPContractError("announcements_empty_unexpected")
    announcements: list[BOPAnnouncement] = []
    used_titles: set[int] = set()
    used_links: set[int] = set()
    seen_ids: set[str] = set()
    components = [
        node for node in container.descendants("span")
        if "linkDownloadFileCurrentAnuncioIcon" in _classes(node)
    ]
    if not components:
        raise BOPContractError("announcement_structure_invalid")
    heading_paths = _heading_paths_for_components(container, components)

    # El portal no siempre crea un contenedor por anuncio. En varios grupos,
    # el wrapper de descarga y el título son hermanos directos repetidos;
    # en otros, cada pareja vive dentro de i4t-include-secciones-con-titulo3.
    # En ambos casos se conserva la asociación local por hermanos, no por dos
    # listas globales ni por la posición de un enlace fuera de la pareja.
    for component_index, component in enumerate(components):
        anchors = [
            node for node in component.descendants("a")
            if "idAnuncio=" in node.attrs.get("href", "")
        ]
        if len(anchors) != 1:
            raise BOPContractError("announcement_link_cardinality_invalid")
        title = _next_announcement_title_sibling(component)
        if title is None or id(title) in used_titles:
            reason = "no_title_after_download" if title is None else "title_already_paired"
            raise BOPContractError(
                "announcement_pairing_invalid",
                diagnostic=diagnose_announcement_structure(
                    html,
                    failure={"reason_code": reason, "component_index": component_index},
                ),
            )
        link = anchors[0]
        if id(link) in used_links:
            raise BOPContractError(
                "announcement_pairing_invalid",
                diagnostic=diagnose_announcement_structure(
                    html,
                    failure={"reason_code": "link_already_paired", "component_index": component_index},
                ),
            )
        used_titles.add(id(title))
        used_links.add(id(link))
        raw_url = urljoin(f"{BOP_BASE_URL}/PortalBOP/", link.attrs["href"])
        try:
            document_url = validate_official_url(
                raw_url,
                path="/PortalBOP/api/descargarAnuncio",
            )
            query = parse_qs(urlsplit(document_url).query, strict_parsing=True)
        except (ValueError, TypeError) as error:
            raise BOPContractError("announcement_url_invalid") from error
        ids = query.get("idAnuncio", [])
        if len(ids) != 1 or not ids[0].isdigit():
            raise BOPContractError("announcement_id_missing")
        if ids[0] in seen_ids:
            raise BOPContractError("duplicate_announcement_id")
        seen_ids.add(ids[0])
        try:
            announcements.append(
                BOPAnnouncement(
                    ids[0],
                    title.all_text(),
                    document_url,
                    heading_path=heading_paths.get(id(component), ()),
                )
            )
        except ValueError as error:
            raise BOPContractError("announcement_fields_invalid") from error

    all_announcement_links = _announcement_links(container)
    if len(used_titles) != len(titles) or len(used_links) != len(all_announcement_links):
        raise BOPContractError(
            "announcement_pairing_invalid",
            diagnostic=diagnose_announcement_structure(
                html,
                failure={
                    "reason_code": "unpaired_global_elements",
                    "candidate_titles": len(titles) - len(used_titles),
                    "unpaired_id_links": len(all_announcement_links) - len(used_links),
                    "boundary": "announcements_root_complete",
                },
            ),
        )
    return tuple(announcements)


def _heading_paths_for_components(root: _Node, components: list[_Node]) -> dict[int, tuple[str, ...]]:
    """Conserva headings semánticos previos por nivel, sin exponer clases HTML."""
    targets = {id(component) for component in components}
    found: dict[int, tuple[str, ...]] = {}

    def visit(parent: _Node, inherited: dict[int, str]) -> None:
        active = dict(inherited)
        for child in parent.children:
            classes = _classes(child)
            heading_level: int | None = None
            if "ui-accordion-header" in classes:
                heading_level = 1
            else:
                for level in (1, 2, 3):
                    if f"titulo{level}" in classes:
                        heading_level = level
                        break
            if heading_level is not None:
                text = child.all_text().strip()
                if text:
                    active = {level: value for level, value in active.items() if level < heading_level}
                    active[heading_level] = text
            if id(child) in targets:
                found[id(child)] = tuple(active[level] for level in sorted(active))
            visit(child, active)

    visit(root, {})
    return found


def diagnose_announcement_structure(
    html: str,
    *,
    failure: dict[str, object] | None = None,
) -> dict[str, object]:
    """Devuelve sólo conteos y estructura DOM; nunca texto, IDs ni URLs."""
    tree = _parse_html(html)
    containers = [node for node in tree.descendants() if node.attrs.get("id") == BOP_ANNOUNCEMENTS_CONTAINER_ID]
    if len(containers) != 1:
        return {
            "global": _global_announcement_counts(tree),
            "container_count": len(containers),
            "components": [],
            "failure": failure,
        }
    root = containers[0]
    components = [
        node for node in root.descendants("span")
        if "linkDownloadFileCurrentAnuncioIcon" in _classes(node)
    ]
    component_reports: list[dict[str, object]] = []
    for component_index, component in enumerate(components):
        siblings = component.parent.children if component.parent is not None else []
        try:
            start = next(i for i, sibling in enumerate(siblings) if sibling is component)
        except StopIteration:
            start = -1
        intermediate: list[dict[str, object]] = []
        candidates: list[dict[str, object]] = []
        boundary = "end_of_parent"
        distance: int | None = None
        crosses_container = False
        next_download_before_title = False
        if start >= 0:
            for sibling_distance, sibling in enumerate(siblings[start + 1 :], start=1):
                if sibling.tag == "span" and "linkDownloadFileCurrentAnuncioIcon" in _classes(sibling):
                    boundary = "next_download_after_title" if candidates else "next_download_before_title"
                    next_download_before_title = not candidates
                    break
                if _is_structural_container(sibling):
                    boundary = "structural_container"
                    crosses_container = True
                    break
                subtree = [sibling, *sibling.descendants()]
                title_nodes = [node for node in subtree if node.tag == "span" and "titulo4" in _classes(node)]
                if title_nodes:
                    if distance is None:
                        distance = sibling_distance
                    for title_node in title_nodes:
                        candidates.append(
                            {
                                "sibling_distance": sibling_distance,
                                "tag": title_node.tag,
                                "classes": sorted(_classes(title_node)),
                                "nested_below_sibling": title_node is not sibling,
                            }
                        )
                    if any(node is not sibling for node in title_nodes):
                        crosses_container = True
                    boundary = "candidate_title"
                elif distance is None:
                    intermediate.append(_node_shape(sibling))
        link_count = sum(
            1
            for anchor in component.descendants("a")
            if _has_query_parameter(anchor.attrs.get("href", ""), "idAnuncio")
        )
        component_reports.append(
            {
                "index": component_index,
                "tag": component.tag,
                "classes": sorted(_classes(component)),
                "parent": _node_shape(component.parent) if component.parent else None,
                "ancestors": [_node_shape(node) for node in component.ancestors()[:3]],
                "idAnuncio_link_count": link_count,
                "next_compatible_titulo4": _next_announcement_title_sibling(component) is not None,
                "distance_element_siblings": distance,
                "intermediate_structure": intermediate,
                "crosses_structural_container": crosses_container,
                "next_download_before_title": next_download_before_title,
                "candidate_titles": candidates,
                "boundary": boundary,
            }
        )
    safe_failure = dict(failure) if failure is not None else None
    if safe_failure is not None and safe_failure.get("reason_code") == "no_title_after_download":
        failed_index = safe_failure.get("component_index")
        if isinstance(failed_index, int) and 0 <= failed_index < len(component_reports):
            candidates = component_reports[failed_index]["candidate_titles"]
            candidate_count = len(candidates)  # type: ignore[arg-type]
            if candidate_count > 1:
                safe_failure["reason_code"] = "multiple_title_candidates"
            elif candidate_count == 1:
                safe_failure["reason_code"] = "title_not_adjacent"
    if safe_failure is not None:
        failed_index = safe_failure.get("component_index")
        if isinstance(failed_index, int) and 0 <= failed_index < len(component_reports):
            failed_component = component_reports[failed_index]
            safe_failure["intermediate_structure"] = failed_component["intermediate_structure"]
            safe_failure["boundary"] = failed_component["boundary"]
            safe_failure["candidate_title_count"] = len(failed_component["candidate_titles"])  # type: ignore[arg-type]
    return {
        "global": _global_announcement_counts(root),
        "container_count": len(containers),
        "components": component_reports,
        "failure": safe_failure,
    }


def _global_announcement_counts(root: _Node) -> dict[str, int]:
    spans = root.descendants("span")
    return {
        "announcement_download_components": sum("linkDownloadFileCurrentAnuncioIcon" in _classes(node) for node in spans),
        "idAnuncio_links": len(_announcement_links(root)),
        "titulo4": sum("titulo4" in _classes(node) for node in spans),
        "titulo3": sum("titulo3" in _classes(node) for node in spans),
        "bulletin_download_components": sum("linkDownloadFileCurrentBoletinIcon" in _classes(node) for node in spans),
    }


def _node_shape(node: _Node) -> dict[str, object]:
    return {"tag": node.tag, "classes": sorted(_classes(node))}


def _is_structural_container(node: _Node) -> bool:
    return any(
        value.startswith("i4t-include-secciones-")
        for value in _classes(node)
    )


def _has_query_parameter(href: str, name: str) -> bool:
    try:
        return name in parse_qs(urlsplit(href).query, keep_blank_values=True)
    except ValueError:
        return False


def parse_bop_partial_response(xml_text: str, requested_date: date) -> BOPIssue | None:
    """Compatibilidad del parser de búsqueda: devuelve metadata, sin anuncios."""
    selection = parse_search_partial_response(
        xml_text,
        requested_date,
        current_view_state="parser-only-state",
    )
    return selection.issue if selection is not None else None


def parse_portal_date(value: str) -> date:
    """Parsea únicamente la fecha observada del portal, ``dd/mm/YYYY``."""
    if not _DATE_RE.fullmatch(value):
        raise BOPContractError("issue_date_format_invalid")
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as error:
        raise BOPContractError("issue_date_invalid") from error


def _parse_issue_row(row: _Node) -> tuple[str, date, str, str] | None:
    cells = [node.all_text() for node in row.descendants("td")]
    if not cells:
        return None
    ids: list[str] = []
    for link in row.descendants("a"):
        href = link.attrs.get("href")
        if not href:
            continue
        absolute = urljoin(f"{BOP_BASE_URL}/PortalBOP/", href)
        try:
            validate_official_url(absolute, path="/PortalBOP/api/descargarBoletin")
            params = parse_qs(urlsplit(absolute).query, strict_parsing=True).get("idBoletin", [])
        except ValueError:
            continue
        if len(params) == 1 and params[0].isdigit():
            ids.append(params[0])
    if len(ids) != 1:
        raise BOPContractError("issue_row_structure_invalid")
    dates = [parse_portal_date(value.strip()) for value in cells if _DATE_RE.fullmatch(value.strip())]
    number = next((value.strip() for value in cells if re.fullmatch(r"\d+", value.strip())), "")
    code = next((value.strip() for value in cells if _ISSUE_CODE_RE.fullmatch(value.strip())), "")
    if len(dates) != 1 or not number or not code:
        raise BOPContractError("issue_row_structure_invalid")
    return ids[0], dates[0], number, code


def _find_issue_card_source(tree: _Node, published_date: date, issue_number: str) -> str:
    matches: list[str] = []
    for anchor in tree.descendants("a"):
        onclick = anchor.attrs.get("onclick", "")
        parsed = _PRIMEFACES_AB_RE.search(onclick)
        if not parsed:
            continue
        source, form_id = parsed.groups()
        if form_id != BOP_REDUCED_FORM_ID:
            continue
        card_text = anchor.all_text()
        number_match = _CARD_NUMBER_RE.search(card_text)
        date_match = _CARD_DATE_RE.search(card_text)
        if number_match is None or date_match is None:
            continue
        try:
            card_date = date(
                int(date_match.group("year")),
                _SPANISH_MONTHS[date_match.group("month").lower()],
                int(date_match.group("day")),
            )
        except ValueError:
            raise BOPContractError("issue_card_date_invalid") from None
        if card_date == published_date and number_match.group(1) == issue_number:
            matches.append(source)
    if len(matches) != 1:
        return ""
    return matches[0]


def _parse_form(html: str, form_id: str) -> tuple[str | None, dict[str, str]]:
    parser = _FormStateParser(form_id)
    try:
        parser.feed(html)
        parser.close()
    except Exception as error:
        raise BOPContractError("form_html_invalid") from error
    if parser.form_count != 1:
        raise BOPContractError("form_missing_or_ambiguous")
    return parser.action, parser.hidden_fields


def _parse_xml(xml_text: str, error_code: str) -> ET.Element:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise BOPContractError(error_code) from error
    if root.tag.rsplit("}", 1)[-1] != "partial-response":
        raise BOPContractError(error_code)
    return root


def _find_update(root: ET.Element, update_id: str) -> ET.Element | None:
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "update" and element.attrib.get("id") == update_id:
            return element
    return None


def _update_html(element: ET.Element) -> str:
    chunks = [element.text or ""]
    for child in list(element):
        chunks.append(ET.tostring(child, encoding="unicode", method="html"))
        if child.tail:
            chunks.append(child.tail)
    return "".join(chunks)


def _parse_html(value: str) -> _Node:
    parser = _TreeBuilder()
    try:
        parser.feed(value)
        parser.close()
    except Exception as error:
        raise BOPContractError("listing_html_invalid") from error
    return parser.root


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _announcement_links(root: _Node) -> list[_Node]:
    links: list[_Node] = []
    for span in root.descendants("span"):
        if "linkDownloadFileCurrentAnuncioIcon" in _classes(span):
            links.extend(
                anchor for anchor in span.descendants("a")
                if anchor.attrs.get("href") and "idAnuncio=" in anchor.attrs["href"]
            )
    return links


def _next_announcement_title_sibling(component: _Node) -> _Node | None:
    """Devuelve el título que sigue al botón en el mismo bloque DOM."""
    if component.parent is None:
        return None
    siblings = component.parent.children
    component_index = next((i for i, sibling in enumerate(siblings) if sibling is component), None)
    if component_index is None:
        return None
    index = component_index + 1
    # PrimeFaces inserts an inline script node between this download component
    # and its title in the live announcements response. It is non-rendered DOM
    # scaffolding; keep the pairing local and stop at any other element.
    while index < len(siblings) and (
        siblings[index].tag == "br"
        or (siblings[index].tag == "script" and not siblings[index].children)
    ):
        index += 1
    if index >= len(siblings):
        return None
    candidate = siblings[index]
    if candidate.tag == "span" and "titulo4" in _classes(candidate):
        return candidate
    return None
