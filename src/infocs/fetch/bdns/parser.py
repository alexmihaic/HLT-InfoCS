"""Parseo estricto de las respuestas JSON públicas documentadas por SNPSAP."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from infocs.fetch.bdns.models import (
    BDNSAuthority,
    BDNSCodeLabel,
    BDNSConvocatoriaDetail,
    BDNSConvocatoriaSummary,
    BDNSDocumentMetadata,
    BDNSExtractMetadata,
    BDNSPage,
    BDNSRegion,
)


class BDNSContractError(ValueError):
    """La respuesta no satisface la forma mínima documentada; no incluye payload."""


def parse_bdns_search(payload: Mapping[str, Any]) -> BDNSPage:
    root = _mapping(payload, "raíz")
    raw_items = root.get("content")
    if not isinstance(raw_items, list):
        raise BDNSContractError("content debe ser una lista JSON.")
    items = tuple(_parse_summary(item, f"content[{index}]") for index, item in enumerate(raw_items))

    pageable_value = root.get("pageable")
    pageable = _mapping(pageable_value, "pageable") if pageable_value is not None else {}
    page_number = _optional_int(pageable, "pageNumber", "pageable")
    page_size = _optional_int(pageable, "pageSize", "pageable")
    offset = _optional_int(pageable, "offset", "pageable")
    total_pages = _optional_int(root, "totalPages", "raíz")
    total_elements = _optional_int(root, "totalElements", "raíz")
    number_of_elements = _optional_int(root, "numberOfElements", "raíz")
    first = _optional_bool(root, "first", "raíz")
    last = _optional_bool(root, "last", "raíz")
    empty = _optional_bool(root, "empty", "raíz")
    return BDNSPage(
        items=items,
        page_number=page_number,
        page_size=page_size,
        offset=offset,
        total_pages=total_pages,
        total_elements=total_elements,
        number_of_elements=number_of_elements,
        first=first,
        last=last,
        empty=empty,
    )


def _parse_summary(value: Any, path: str) -> BDNSConvocatoriaSummary:
    raw = _mapping(value, path)
    code = _required_string(raw, "numeroConvocatoria", path)
    internal_id = _optional_int(raw, "id", path)
    return BDNSConvocatoriaSummary(
        numero_convocatoria=code,
        internal_id=internal_id,
        title=_optional_string(raw, "descripcion", path),
        title_coofficial=_optional_string(raw, "descripcionLeng", path),
        fecha_recepcion=_optional_date(raw, "fechaRecepcion", path),
        nivel1=_optional_string(raw, "nivel1", path),
        nivel2=_optional_string(raw, "nivel2", path),
        nivel3=_optional_string(raw, "nivel3", path),
        codigo_invente=_optional_string(raw, "codigoInvente", path),
        mrr=_optional_bool(raw, "mrr", path),
    )


def parse_bdns_detail(payload: Mapping[str, Any]) -> BDNSConvocatoriaDetail:
    raw = _mapping(payload, "raíz")
    codigo = _required_string(raw, "codigoBDNS", "raíz")
    authority_value = raw.get("organo")
    authority = None
    if authority_value is not None:
        org = _mapping(authority_value, "organo")
        authority = BDNSAuthority(
            nivel1=_optional_string(org, "nivel1", "organo"),
            nivel2=_optional_string(org, "nivel2", "organo"),
            nivel3=_optional_string(org, "nivel3", "organo"),
        )

    detail = BDNSConvocatoriaDetail(
        codigo_bdns=codigo,
        internal_id=_optional_int(raw, "id", "raíz"),
        title=_optional_string(raw, "descripcion", "raíz"),
        title_coofficial=_optional_string(raw, "descripcionLeng", "raíz"),
        authority=authority,
        electronic_office=_optional_string(raw, "sedeElectronica", "raíz"),
        fecha_recepcion=_optional_date(raw, "fechaRecepcion", "raíz"),
        total_budget=_optional_decimal(raw, "presupuestoTotal", "raíz"),
        convocatoria_type=_optional_string(raw, "tipoConvocatoria", "raíz"),
        instruments=_description_list(raw, "instrumentos", "raíz"),
        eligible_beneficiaries=_code_label_list(raw, "tiposBeneficiarios", "raíz"),
        sectors=_code_label_list(raw, "sectores", "raíz"),
        regions=_regions(raw),
        purpose=_optional_string(raw, "descripcionFinalidad", "raíz"),
        regulatory_bases_title=_optional_string(raw, "descripcionBasesReguladoras", "raíz"),
        regulatory_bases_url=_optional_string(raw, "urlBasesReguladoras", "raíz"),
        extract_published_in_official_diary=_optional_bool(raw, "sePublicaDiarioOficial", "raíz"),
        open_ended_application=_optional_bool(raw, "abierto", "raíz"),
        application_start_date=_optional_date(raw, "fechaInicioSolicitud", "raíz"),
        application_end_date=_optional_date(raw, "fechaFinSolicitud", "raíz"),
        application_start_text=_optional_string(raw, "textInicio", "raíz"),
        application_end_text=_optional_string(raw, "textFin", "raíz"),
        documents=_documents(raw),
        extracts=_extracts(raw),
    )
    return detail


def _description_list(raw: Mapping[str, Any], key: str, path: str) -> tuple[str, ...]:
    values = _optional_list(raw, key, path)
    result: list[str] = []
    for index, value in enumerate(values):
        item = _mapping(value, f"{path}.{key}[{index}]")
        description = _required_string(item, "descripcion", f"{path}.{key}[{index}]")
        result.append(description)
    return tuple(result)


def _code_label_list(raw: Mapping[str, Any], key: str, path: str) -> tuple[BDNSCodeLabel, ...]:
    values = _optional_list(raw, key, path)
    result: list[BDNSCodeLabel] = []
    for index, value in enumerate(values):
        item = _mapping(value, f"{path}.{key}[{index}]")
        item_path = f"{path}.{key}[{index}]"
        result.append(
            BDNSCodeLabel(
                code=_optional_string(item, "codigo", item_path),
                description=_optional_string(item, "descripcion", item_path),
            )
        )
    return tuple(result)


def _regions(raw: Mapping[str, Any]) -> tuple[BDNSRegion, ...]:
    result: list[BDNSRegion] = []
    for index, value in enumerate(_optional_list(raw, "regiones", "raíz")):
        item = _mapping(value, f"regiones[{index}]")
        result.append(BDNSRegion(_required_string(item, "descripcion", f"regiones[{index}]")))
    return tuple(result)


def _documents(raw: Mapping[str, Any]) -> tuple[BDNSDocumentMetadata, ...]:
    result: list[BDNSDocumentMetadata] = []
    for index, value in enumerate(_optional_list(raw, "documentos", "raíz")):
        item = _mapping(value, f"documentos[{index}]")
        path = f"documentos[{index}]"
        result.append(
            BDNSDocumentMetadata(
                document_id=_required_int(item, "id", path),
                filename=_optional_string(item, "nombreFic", path),
                description=_optional_string(item, "descripcion", path),
                length=_optional_int(item, "long", path),
                modified_at=_optional_string(item, "datMod", path),
                publication_date=_optional_date(item, "datPublicacion", path),
            )
        )
    return tuple(result)


def _extracts(raw: Mapping[str, Any]) -> tuple[BDNSExtractMetadata, ...]:
    result: list[BDNSExtractMetadata] = []
    for index, value in enumerate(_optional_list(raw, "anuncios", "raíz")):
        item = _mapping(value, f"anuncios[{index}]")
        path = f"anuncios[{index}]"
        result.append(
            BDNSExtractMetadata(
                announcement_number=_optional_int(item, "numAnuncio", path),
                title=_optional_string(item, "titulo", path),
                title_coofficial=_optional_string(item, "tituloLeng", path),
                cve=_optional_string(item, "cve", path),
                official_diary=_optional_string(item, "desDiarioOficial", path),
                publication_date=_optional_date(item, "datPublicacion", path),
                url=_optional_string(item, "url", path),
            )
        )
    return tuple(result)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BDNSContractError(f"{path} debe ser objeto.")
    return value


def _optional_list(raw: Mapping[str, Any], key: str, path: str) -> list[Any]:
    value = raw.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise BDNSContractError(f"{path}.{key} debe ser lista.")
    return value


def _required_string(raw: Mapping[str, Any], key: str, path: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BDNSContractError(f"{path}.{key} debe ser texto no vacío.")
    return value


def _optional_string(raw: Mapping[str, Any], key: str, path: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BDNSContractError(f"{path}.{key} debe ser texto o null.")
    return value


def _optional_int(raw: Mapping[str, Any], key: str, path: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BDNSContractError(f"{path}.{key} debe ser entero no negativo o null.")
    return value


def _required_int(raw: Mapping[str, Any], key: str, path: str) -> int:
    value = _optional_int(raw, key, path)
    if value is None:
        raise BDNSContractError(f"{path}.{key} es obligatorio.")
    return value


def _optional_bool(raw: Mapping[str, Any], key: str, path: str) -> bool | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise BDNSContractError(f"{path}.{key} debe ser booleano o null.")
    return value


def _optional_date(raw: Mapping[str, Any], key: str, path: str) -> date | None:
    value = _optional_string(raw, key, path)
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise BDNSContractError(f"{path}.{key} debe ser fecha ISO YYYY-MM-DD.") from error
    if parsed.isoformat() != value:
        raise BDNSContractError(f"{path}.{key} debe ser fecha ISO YYYY-MM-DD.")
    return parsed


def _optional_decimal(raw: Mapping[str, Any], key: str, path: str) -> Decimal | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise BDNSContractError(f"{path}.{key} debe ser número JSON o null.")
    amount = Decimal(value)
    if not amount.is_finite():
        raise BDNSContractError(f"{path}.{key} debe ser número finito.")
    return amount
