"""Parseo estricto y sin efectos laterales del JSON del sumario BOE."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
import re
from typing import Any

from infocs.fetch.boe.config import validate_boe_url
from infocs.fetch.boe.models import (
    BOEDepartment,
    BOEDiary,
    BOEDocumentLinks,
    BOEHeading,
    BOEItem,
    BOESection,
    BOESummary,
)


class BOEContractError(ValueError):
    """La respuesta no satisface el contrato mínimo documentado del sumario."""


_DATE_PATTERN = re.compile(r"\d{8}\Z")
_INTEGER_PATTERN = re.compile(r"\d+\Z")


def parse_boe_summary(payload: Mapping[str, Any]) -> BOESummary:
    """Valida y convierte un payload JSON BOE correcto en modelos tipados.

    La observación real del 2026-09-21 y la documentación muestran
    ``status.code`` como cadena, por ejemplo ``"200"``. El contrato se mantiene
    estricto para detectar un cambio de API en vez de normalizarlo en silencio.
    """
    root = _mapping(payload, "raíz")
    status = _mapping(root.get("status"), "status")
    code = status.get("code")
    if not isinstance(code, str) or code != "200":
        raise BOEContractError('status.code debe ser la cadena "200".')

    data = _mapping(root.get("data"), "data")
    summary = _mapping(data.get("sumario"), "data.sumario")
    metadata = _mapping(summary.get("metadatos"), "data.sumario.metadatos")
    if _required_string(metadata, "publicacion", "data.sumario.metadatos") != "BOE":
        raise BOEContractError('data.sumario.metadatos.publicacion debe ser "BOE".')
    publication_date = _parse_date(
        _required_string(metadata, "fecha_publicacion", "data.sumario.metadatos"),
        "data.sumario.metadatos.fecha_publicacion",
    )

    diaries = tuple(
        _parse_diary(raw_diary, publication_date, f"data.sumario.diario[{index}]")
        for index, raw_diary in enumerate(_nodes(summary.get("diario"), "data.sumario.diario", required=True))
    )
    return BOESummary(publication_date=publication_date, diaries=diaries)


def _parse_diary(raw: Mapping[str, Any], published_on: date, path: str) -> BOEDiary:
    number = _required_string(raw, "numero", path)
    sections = tuple(
        _parse_section(item, published_on, f"{path}.seccion[{index}]")
        for index, item in enumerate(_nodes(raw.get("seccion"), f"{path}.seccion", required=True))
    )
    return BOEDiary(number=number, sections=sections)


def _parse_section(raw: Mapping[str, Any], published_on: date, path: str) -> BOESection:
    code = _required_string(raw, "codigo", path)
    name = _required_string(raw, "nombre", path)
    departments = tuple(
        _parse_department(item, published_on, code, name, f"{path}.departamento[{index}]")
        for index, item in enumerate(_nodes(raw.get("departamento"), f"{path}.departamento", required=True))
    )
    return BOESection(code=code, name=name, departments=departments)


def _parse_department(
    raw: Mapping[str, Any],
    published_on: date,
    section_code: str,
    section_name: str,
    path: str,
) -> BOEDepartment:
    code = _required_string(raw, "codigo", path)
    name = _required_string(raw, "nombre", path)
    direct_items = _parse_items(
        raw.get("item"),
        published_on,
        section_code,
        section_name,
        code,
        name,
        None,
        f"{path}.item",
    )
    headings = tuple(
        _parse_heading(
            heading,
            published_on,
            section_code,
            section_name,
            code,
            name,
            f"{path}.epigrafe[{index}]",
        )
        for index, heading in enumerate(_nodes(raw.get("epigrafe"), f"{path}.epigrafe", required=False))
    )
    return BOEDepartment(code=code, name=name, headings=headings, direct_items=direct_items)


def _parse_heading(
    raw: Mapping[str, Any],
    published_on: date,
    section_code: str,
    section_name: str,
    department_code: str,
    department_name: str,
    path: str,
) -> BOEHeading:
    name = _required_string(raw, "nombre", path)
    items = _parse_items(
        raw.get("item"),
        published_on,
        section_code,
        section_name,
        department_code,
        department_name,
        name,
        f"{path}.item",
    )
    return BOEHeading(name=name, items=items)


def _parse_items(
    raw_items: Any,
    published_on: date,
    section_code: str,
    section_name: str,
    department_code: str,
    department_name: str,
    heading_name: str | None,
    path: str,
) -> tuple[BOEItem, ...]:
    return tuple(
        _parse_item(
            raw,
            published_on,
            section_code,
            section_name,
            department_code,
            department_name,
            heading_name,
            f"{path}[{index}]",
        )
        for index, raw in enumerate(_nodes(raw_items, path, required=False))
    )


def _parse_item(
    raw: Mapping[str, Any],
    published_on: date,
    section_code: str,
    section_name: str,
    department_code: str,
    department_name: str,
    heading_name: str | None,
    path: str,
) -> BOEItem:
    pdf = _mapping(raw.get("url_pdf"), f"{path}.url_pdf")
    documents = BOEDocumentLinks(
        xml_url=_required_boe_url(raw, "url_xml", path),
        html_url=_required_boe_url(raw, "url_html", path),
        pdf_url=_required_boe_url(pdf, "texto", f"{path}.url_pdf"),
        pdf_size_bytes=_optional_non_negative_integer(pdf.get("szBytes"), f"{path}.url_pdf.szBytes"),
        pdf_size_kbytes=_optional_non_negative_integer(pdf.get("szKBytes"), f"{path}.url_pdf.szKBytes"),
        pdf_first_page=_optional_non_negative_integer(pdf.get("pagina_inicial"), f"{path}.url_pdf.pagina_inicial"),
        pdf_last_page=_optional_non_negative_integer(pdf.get("pagina_final"), f"{path}.url_pdf.pagina_final"),
    )
    control = raw.get("control")
    if control is not None and not isinstance(control, str):
        raise BOEContractError(f"{path}.control debe ser texto si está presente.")
    return BOEItem(
        official_id=_required_string(raw, "identificador", path),
        title=_required_string(raw, "titulo", path),
        section_code=section_code,
        section_name=section_name,
        department_code=department_code,
        department_name=department_name,
        heading_name=heading_name,
        control=control,
        published_on=published_on,
        documents=documents,
    )


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BOEContractError(f"{path} debe ser un objeto JSON.")
    return value


def _nodes(value: Any, path: str, *, required: bool) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        if required:
            raise BOEContractError(f"{path} es obligatorio.")
        return ()
    values = value if isinstance(value, list) else [value]
    if required and not values:
        raise BOEContractError(f"{path} no puede estar vacío.")
    return tuple(_mapping(item, f"{path}[{index}]") for index, item in enumerate(values))


def _required_string(raw: Mapping[str, Any], field: str, path: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value:
        raise BOEContractError(f"{path}.{field} debe ser texto no vacío.")
    return value


def _required_boe_url(raw: Mapping[str, Any], field: str, path: str) -> str:
    value = _required_string(raw, field, path)
    try:
        validate_boe_url(value)
    except ValueError as error:
        raise BOEContractError(f"{path}.{field} contiene una URL BOE no autorizada.") from error
    return value


def _optional_non_negative_integer(value: Any, path: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise BOEContractError(f"{path} debe ser un entero no negativo.")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and _INTEGER_PATTERN.fullmatch(value):
        return int(value)
    raise BOEContractError(f"{path} debe ser un entero no negativo.")


def _parse_date(value: str, path: str) -> date:
    if not _DATE_PATTERN.fullmatch(value):
        raise BOEContractError(f"{path} debe usar YYYYMMDD.")
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as error:
        raise BOEContractError(f"{path} no contiene una fecha válida.") from error
