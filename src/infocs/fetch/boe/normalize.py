"""Normalización determinista de ``BOEItem`` al contrato InfoCs.

Esta capa recibe exclusivamente modelos ya parseados y una decisión territorial
ya tomada. No abre enlaces, no realiza HTTP y no escribe records.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import re

from infocs.fetch.boe.config import validate_boe_url
from infocs.fetch.boe.models import (
    BOEDocumentLinks,
    BOEItem,
    BOETerritorialDecision,
    BOETerritorialDecisionStatus,
    BOETerritorialMatch,
    BOETerritorialMatchReason,
)
from infocs.models import (
    AdministrationLevel,
    Authority,
    CandidateTechnicalMetadata,
    Category,
    DataValidationError,
    Document,
    DocumentArchiveStatus,
    Geography,
    Provenance,
    RecordCandidate,
    RecordDates,
    RecordStatus,
    SCHEMA_VERSION,
    SourceReference,
    TerritorialMatch,
    TerritorialMatchReason,
)


BOE_COLLECTOR = "boe_summary"
BOE_COLLECTOR_VERSION = "0.1.0"
BOE_NORMALIZER_VERSION = "1.0.0"
BOE_EXTRACTION_METHOD = "boe_summary_json"

_MUNICIPALITY_CODE = re.compile(r"12\d{3}\Z")
_CATEGORY_BY_SECTION = {
    "1": Category.REGULATION,
    "2B": Category.EMPLOYMENT,
    "5A": Category.PROCUREMENT,
}
_CORE_REASON_BY_BOE_REASON = {
    BOETerritorialMatchReason.MUNICIPALITY_EXACT: TerritorialMatchReason.MUNICIPALITY_MATCH,
    BOETerritorialMatchReason.PROVINCE_EXACT: TerritorialMatchReason.EXPLICIT_TEXT_MATCH,
    BOETerritorialMatchReason.AUTHORITY_EXACT: TerritorialMatchReason.AUTHORITY_MATCH,
}


class BOENormalizationError(ValueError):
    """Un ``BOEItem`` incluido no cumple el contrato de normalización BOE."""


def normalize_boe_item(
    item: BOEItem,
    decision: BOETerritorialDecision,
    *,
    detected_at: datetime,
    last_checked_at: datetime,
) -> RecordCandidate | None:
    """Convierte una inclusión territorial BOE en un candidato activo.

    ``no_match`` representa simplemente que el ítem no entra en InfoCs y por
    ello devuelve ``None``. La función no reevalúa la política territorial.
    """
    if decision.status is BOETerritorialDecisionStatus.NO_MATCH:
        return None
    if decision.status is not BOETerritorialDecisionStatus.INCLUDE:
        raise BOENormalizationError("La decisión territorial BOE no es válida.")
    if not decision.matches:
        raise BOENormalizationError("Una decisión BOE include requiere coincidencias.")

    official_id = _required_text(item.official_id, "BOEItem.official_id")
    department_code = _required_text(item.department_code, "BOEItem.department_code")
    department_name = _required_text(item.department_name, "BOEItem.department_name")
    title = _normalise_title(item.title)
    published_on = _publication_date(item.published_on)
    _validate_observation_timestamps(detected_at, last_checked_at)

    source_url, documents = _documents(item.documents)
    territorial_matches = _territorial_matches(decision.matches)
    geography = _geography(decision.matches)

    candidate = RecordCandidate(
        schema_version=SCHEMA_VERSION,
        source=SourceReference(id="boe", official_id=official_id),
        authority=Authority(
            id=f"boe-department:{department_code}",
            name=department_name,
            administration_level=AdministrationLevel.STATE,
        ),
        administration_level=AdministrationLevel.STATE,
        category=category_for_boe_section(item.section_code),
        title=title,
        dates=RecordDates(
            published_at=published_on,
            detected_at=detected_at,
            last_checked_at=last_checked_at,
        ),
        source_url=source_url,
        documents=documents,
        geography=geography,
        provenance=Provenance(
            collector=BOE_COLLECTOR,
            collector_version=BOE_COLLECTOR_VERSION,
            normalizer_version=BOE_NORMALIZER_VERSION,
            territorial_matches=territorial_matches,
            transformed_by_infocs=True,
        ),
        status=RecordStatus.ACTIVE,
        technical=CandidateTechnicalMetadata(extraction_method=BOE_EXTRACTION_METHOD),
    )

    # La construcción directa de dataclasses no valida formatos JSON. Volver a
    # cargar el payload garantiza que el resultado ya satisface el schema del
    # candidato y normaliza los timestamps a UTC sin mutar el objeto anterior.
    try:
        return RecordCandidate.from_dict(candidate.to_dict())
    except DataValidationError as error:
        raise BOENormalizationError("El candidato BOE no cumple el contrato InfoCs.") from error


def category_for_boe_section(section_code: str) -> Category:
    """Aplica el mapping inicial, deliberadamente pequeño, de secciones BOE."""
    if not isinstance(section_code, str):
        raise BOENormalizationError("BOEItem.section_code debe ser texto.")
    return _CATEGORY_BY_SECTION.get(section_code.strip().upper(), Category.OTHER)


def _documents(links: BOEDocumentLinks) -> tuple[str, tuple[Document, ...]]:
    alternatives = (links.html_url, links.xml_url, links.pdf_url)
    available: list[str] = []
    for url in alternatives:
        if not isinstance(url, str):
            raise BOENormalizationError("Las URLs documentales BOE deben ser texto.")
        if not url:
            continue
        try:
            validate_boe_url(url)
        except ValueError as error:
            raise BOENormalizationError("El ítem BOE contiene una URL oficial no válida.") from error
        available.append(url)
    if not available:
        raise BOENormalizationError("El ítem BOE no aporta una URL oficial navegable.")

    # HTML es la referencia principal navegable. XML y PDF son alternativas
    # oficiales; el orden de documents no tiene significado y se estabiliza.
    source_url = available[0]
    unique_urls = tuple(sorted(set(available)))
    return source_url, tuple(
        Document(
            source_url=url,
            archive_status=DocumentArchiveStatus.NOT_ARCHIVED,
            has_local_copy=False,
            publication_allowed=False,
        )
        for url in unique_urls
    )


def _territorial_matches(matches: tuple[BOETerritorialMatch, ...]) -> tuple[TerritorialMatch, ...]:
    normalized: dict[tuple[str, str], TerritorialMatch] = {}
    for match in matches:
        _validate_boe_match(match)
        detail = json.dumps(
            {
                "boe_reason": match.reason.value,
                "entity_code": match.entity_code,
                "entity_name": match.entity_name,
                "field": match.field.value,
                "matched_text": match.matched_text,
                "method": match.method,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        core_match = TerritorialMatch(_CORE_REASON_BY_BOE_REASON[match.reason], detail)
        normalized[(core_match.reason.value, detail)] = core_match
    return tuple(normalized[key] for key in sorted(normalized))


def _geography(matches: tuple[BOETerritorialMatch, ...]) -> Geography | None:
    """Asigna municipio sólo ante una única coincidencia municipal inequívoca."""
    if len(matches) != 1:
        return None
    match = matches[0]
    if (
        match.reason is BOETerritorialMatchReason.MUNICIPALITY_EXACT
        and _MUNICIPALITY_CODE.fullmatch(match.entity_code)
        and match.entity_name.strip()
    ):
        return Geography(municipality=match.entity_name)
    return None


def _validate_boe_match(match: BOETerritorialMatch) -> None:
    if match.reason not in _CORE_REASON_BY_BOE_REASON:
        raise BOENormalizationError("La razón territorial BOE no está soportada.")
    for value, field in (
        (match.entity_code, "entity_code"),
        (match.entity_name, "entity_name"),
        (match.matched_text, "matched_text"),
        (match.method, "method"),
    ):
        _required_text(value, f"BOETerritorialMatch.{field}")


def _publication_date(value: date) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise BOENormalizationError("BOEItem.published_on debe ser una fecha ISO sin hora.")
    return value


def _validate_observation_timestamps(detected_at: datetime, last_checked_at: datetime) -> None:
    for value, field in ((detected_at, "detected_at"), (last_checked_at, "last_checked_at")):
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise BOENormalizationError(f"{field} debe ser un timestamp con zona horaria.")
    if last_checked_at < detected_at:
        raise BOENormalizationError("last_checked_at no puede preceder a detected_at.")


def _normalise_title(value: str) -> str:
    return " ".join(_required_text(value, "BOEItem.title").split())


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BOENormalizationError(f"{field} debe ser texto no vacío.")
    return value
