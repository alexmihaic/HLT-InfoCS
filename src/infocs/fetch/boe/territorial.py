"""Política territorial BOE v1: coincidencias literales y explicables.

No descarga enlaces de cada ítem ni decide aplicabilidad administrativa. Sólo
inspecciona tres metadatos ya presentes en :class:`BOEItem` y devuelve las
coincidencias objetivas que justifican una inclusión territorial por InfoCs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from infocs.fetch.boe.models import (
    BOEItem,
    BOETerritorialDecision,
    BOETerritorialDecisionStatus,
    BOETerritorialField,
    BOETerritorialMatch,
    BOETerritorialMatchReason,
)


_MATCH_METHOD_OFFICIAL = "official_variant_casefolded_diacritic_insensitive_boundary"
_MATCH_METHOD_TECHNICAL = "technical_alias_casefolded_diacritic_insensitive_boundary"
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CASTELLON_REGISTRY = _PROJECT_ROOT / "config" / "entities" / "castellon.json"
_PROVINCE_CODE_PATTERN = re.compile(r"\d{2}\Z")
_MUNICIPALITY_CODE_PATTERN = re.compile(r"12\d{3}\Z")


class BOETerritorialRegistryError(ValueError):
    """El registro territorial no satisface el contrato mínimo de la política."""


class BOETerritorialEntityKind(str, Enum):
    PROVINCE = "province"
    MUNICIPALITY = "municipality"
    AUTHORITY = "authority"


@dataclass(frozen=True, slots=True)
class BOETerritorialEntity:
    """Entidad territorial explícita, con variantes de procedencia separada."""

    code: str
    official_name: str
    official_variants: tuple[str, ...]
    technical_aliases: tuple[str, ...]
    kind: BOETerritorialEntityKind


@dataclass(frozen=True, slots=True)
class BOETerritorialRegistry:
    """Registro cargado desde configuración, sin datos implícitos en el código."""

    province: BOETerritorialEntity
    municipalities: tuple[BOETerritorialEntity, ...]
    authorities: tuple[BOETerritorialEntity, ...]


@dataclass(frozen=True, slots=True)
class _CandidateMatch:
    entity: BOETerritorialEntity
    reason: BOETerritorialMatchReason
    field: BOETerritorialField
    matched_text: str
    method: str
    start: int
    end: int


def load_castellon_registry(path: Path | None = None) -> BOETerritorialRegistry:
    """Carga y valida el registro territorial JSON versionado de Castellón.

    JSON se usa deliberadamente en vez de YAML para que el registro sea
    configuración runtime validable con la biblioteca estándar, sin añadir un
    parser de producción sólo para esta fase.
    """

    registry_path = path or DEFAULT_CASTELLON_REGISTRY
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise BOETerritorialRegistryError(f"No se puede leer el registry: {registry_path}") from error
    except json.JSONDecodeError as error:
        raise BOETerritorialRegistryError(f"El registry no contiene JSON válido: {registry_path}") from error

    if not isinstance(raw, dict):
        raise BOETerritorialRegistryError("La raíz del registry debe ser un objeto.")
    if raw.get("schema_version") != "1.0.0":
        raise BOETerritorialRegistryError("El registry debe declarar schema_version 1.0.0.")

    province = _parse_entity(raw.get("province"), BOETerritorialEntityKind.PROVINCE, "province")
    municipalities = _parse_entities(raw.get("municipalities"), BOETerritorialEntityKind.MUNICIPALITY, "municipalities")
    authorities = _parse_entities(raw.get("authorities", []), BOETerritorialEntityKind.AUTHORITY, "authorities")
    _ensure_unique_codes((province, *municipalities, *authorities))
    _validate_castellon_codes(province, municipalities)
    return BOETerritorialRegistry(province=province, municipalities=municipalities, authorities=authorities)


def decide_boe_territorial_inclusion(
    item: BOEItem,
    registry: BOETerritorialRegistry | None = None,
) -> BOETerritorialDecision:
    """Devuelve sólo hechos de coincidencia territorial presentes en el sumario.

    El orden de evaluación de campos es epígrafe, departamento y título. La
    sección, el identificador y las URL quedan fuera de la política v1.
    """

    active_registry = registry or load_castellon_registry()
    matches: list[BOETerritorialMatch] = []
    seen: set[tuple[BOETerritorialMatchReason, str, BOETerritorialField]] = set()

    for field, value in _item_fields(item):
        strong_matches = _matches_for_entities(
            value,
            field,
            (*active_registry.authorities, *active_registry.municipalities),
        )
        province_matches = _matches_for_entities(value, field, (active_registry.province,))

        # "Castelló" o "Castellón" incluidos en el nombre compuesto de la
        # ciudad no añaden una segunda razón provincial genérica.
        province_matches = [
            candidate
            for candidate in province_matches
            if not any(
                strong.start <= candidate.start and candidate.end <= strong.end
                for strong in strong_matches
            )
        ]
        for candidate in (*strong_matches, *province_matches):
            key = (candidate.reason, candidate.entity.code, candidate.field)
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                BOETerritorialMatch(
                    reason=candidate.reason,
                    entity_code=candidate.entity.code,
                    entity_name=candidate.entity.official_name,
                    field=candidate.field,
                    matched_text=candidate.matched_text,
                    method=candidate.method,
                )
            )

    if not matches:
        return BOETerritorialDecision(status=BOETerritorialDecisionStatus.NO_MATCH, matches=())
    return BOETerritorialDecision(status=BOETerritorialDecisionStatus.INCLUDE, matches=tuple(matches))


def _item_fields(item: BOEItem) -> tuple[tuple[BOETerritorialField, str], ...]:
    candidates = (
        (BOETerritorialField.HEADING, item.heading_name),
        (BOETerritorialField.DEPARTMENT, item.department_name),
        (BOETerritorialField.TITLE, item.title),
    )
    return tuple((field, value) for field, value in candidates if value)


def _matches_for_entities(
    value: str,
    field: BOETerritorialField,
    entities: tuple[BOETerritorialEntity, ...],
) -> list[_CandidateMatch]:
    normalized_value, position_map = _normalise_with_positions(value)
    candidates: list[_CandidateMatch] = []

    # Los nombres compuestos se resuelven antes que los cortos (p. ej. la ciudad
    # antes de la provincia) y la ordenación final mantiene un resultado estable.
    patterns = sorted(
        (
            (entity, variant, _MATCH_METHOD_OFFICIAL)
            for entity in entities
            for variant in entity.official_variants
        ),
        key=lambda entry: (-len(_normalise(entry[1])), entry[0].kind.value, entry[0].code, entry[1]),
    )
    patterns.extend(
        sorted(
            (
                (entity, alias, _MATCH_METHOD_TECHNICAL)
                for entity in entities
                for alias in entity.technical_aliases
            ),
            key=lambda entry: (-len(_normalise(entry[1])), entry[0].kind.value, entry[0].code, entry[1]),
        )
    )

    for entity, variant, method in patterns:
        normalized_variant = _normalise(variant)
        if not normalized_variant:
            continue
        expression = re.compile(rf"(?<!\w){re.escape(normalized_variant)}(?!\w)")
        for match in expression.finditer(normalized_value):
            start, end = match.span()
            original_start = position_map[start]
            original_end = position_map[end - 1] + 1
            candidates.append(
                _CandidateMatch(
                    entity=entity,
                    reason=_reason_for(entity.kind),
                    field=field,
                    matched_text=value[original_start:original_end],
                    method=method,
                    start=start,
                    end=end,
                )
            )
    candidates.sort(key=lambda candidate: (candidate.start, candidate.end, candidate.entity.kind.value, candidate.entity.code))
    return candidates


def _normalise(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value).casefold()
        if not unicodedata.combining(character)
    )


def _normalise_with_positions(value: str) -> tuple[str, tuple[int, ...]]:
    characters: list[str] = []
    positions: list[int] = []
    for position, original in enumerate(value):
        normalized = _normalise(original)
        characters.extend(normalized)
        positions.extend([position] * len(normalized))
    return "".join(characters), tuple(positions)


def _reason_for(kind: BOETerritorialEntityKind) -> BOETerritorialMatchReason:
    if kind is BOETerritorialEntityKind.MUNICIPALITY:
        return BOETerritorialMatchReason.MUNICIPALITY_EXACT
    if kind is BOETerritorialEntityKind.AUTHORITY:
        return BOETerritorialMatchReason.AUTHORITY_EXACT
    return BOETerritorialMatchReason.PROVINCE_EXACT


def _parse_entities(value: Any, kind: BOETerritorialEntityKind, path: str) -> tuple[BOETerritorialEntity, ...]:
    if not isinstance(value, list):
        raise BOETerritorialRegistryError(f"{path} debe ser una lista.")
    return tuple(_parse_entity(item, kind, f"{path}[{index}]") for index, item in enumerate(value))


def _parse_entity(value: Any, kind: BOETerritorialEntityKind, path: str) -> BOETerritorialEntity:
    if not isinstance(value, dict):
        raise BOETerritorialRegistryError(f"{path} debe ser un objeto.")
    code = _required_text(value.get("code"), f"{path}.code")
    official_name = _required_text(value.get("official_name"), f"{path}.official_name")
    official_variants = _text_list(value.get("official_variants"), f"{path}.official_variants", required=True)
    technical_aliases = _text_list(value.get("technical_aliases", []), f"{path}.technical_aliases", required=False)
    return BOETerritorialEntity(
        code=code,
        official_name=official_name,
        official_variants=official_variants,
        technical_aliases=technical_aliases,
        kind=kind,
    )


def _required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BOETerritorialRegistryError(f"{path} debe ser texto no vacío.")
    return value


def _text_list(value: Any, path: str, *, required: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or (required and not value):
        raise BOETerritorialRegistryError(f"{path} debe ser una lista no vacía.")
    values = tuple(_required_text(item, f"{path}[]") for item in value)
    if len(set(values)) != len(values):
        raise BOETerritorialRegistryError(f"{path} no puede contener duplicados.")
    return values


def _ensure_unique_codes(entities: tuple[BOETerritorialEntity, ...]) -> None:
    codes = [entity.code for entity in entities]
    if len(set(codes)) != len(codes):
        raise BOETerritorialRegistryError("Los códigos de entidad territorial deben ser únicos.")


def _validate_castellon_codes(
    province: BOETerritorialEntity,
    municipalities: tuple[BOETerritorialEntity, ...],
) -> None:
    if not _PROVINCE_CODE_PATTERN.fullmatch(province.code) or province.code != "12":
        raise BOETerritorialRegistryError("province.code debe ser el código INE 12.")
    for municipality in municipalities:
        if not _MUNICIPALITY_CODE_PATTERN.fullmatch(municipality.code):
            raise BOETerritorialRegistryError(
                f"{municipality.code!r} no es un código INE municipal válido de la provincia 12."
            )
