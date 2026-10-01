"""Vista semántica observada en la fuente, hash y diferencias estructuradas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Mapping


_MISSING = object()


class HashContractTransitionError(ValueError):
    """Versiones de baseline distintas no prueban un cambio administrativo."""


def hash_contract_version(record: Mapping[str, Any]) -> int:
    version = record.get("technical", {}).get("content_hash_version", 1)
    if type(version) is not int or version not in (1, 2):
        raise HashContractTransitionError("Versión de hash no soportada.")
    if ("source_data" in record) != (version == 2):
        raise HashContractTransitionError("source_data requiere hash v2 explícito; sin extensión se usa v1.")
    return version


def assert_same_hash_contract(previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    if hash_contract_version(previous) != hash_contract_version(current):
        raise HashContractTransitionError("Se requiere migración explícita de baseline; no es un update administrativo.")


def canonical_bdns_data(data: Mapping[str, Any]) -> dict[str, Any]:
    """Proyección cerrada material v2. Sin UI, versiones o enlaces derivados."""
    result = {
        key: data[key] for key in (
            "official_title_coofficial", "authority_hierarchy", "call_type",
            "received_date", "application", "purpose", "regulatory_bases",
            "electronic_office_url", "extract_published_in_official_diary",
        ) if data.get(key) is not None
    }
    if data.get("budget_total") is not None:
        budget = data["budget_total"]
        # Sin Decimal.normalize(): su contexto podría redondear importes largos.
        number = Decimal(budget["value"])
        value = format(number, "f")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        result["budget_total"] = {"value": "0" if number.is_zero() else value}
        if budget.get("currency") is not None:
            result["budget_total"]["currency"] = budget["currency"]
    for key in ("authority_hierarchy", "application", "regulatory_bases"):
        if key in result:
            result[key] = {name: value for name, value in result[key].items() if value is not None}
    for key in ("instruments", "eligible_beneficiary_types", "sectors", "impact_regions", "documents", "extracts"):
        if data.get(key):
            items = [
                {name: value for name, value in item.items() if value is not None}
                if isinstance(item, dict) else item for item in data[key]
            ]
            result[key] = canonical_set(items)
    return result


def canonical_decimal(value: str) -> str:
    number = Decimal(value)
    if number.is_zero():
        return "0"
    return format(number.normalize(), "f")


def canonical_set(items: list[Any]) -> list[Any]:
    """Canonicaliza colecciones sin orden semántico, sin alterar la entrada."""
    unique = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")): item
        for item in items
    }
    return [unique[key] for key in sorted(unique)]


def semantic_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Selecciona únicamente información administrativa observada.

    La lista de campos es cerrada: ampliar el modelo no cambia el hash hasta
    decidir expresamente si el nuevo campo procede de la fuente.
    """
    version = hash_contract_version(record)
    result: dict[str, Any] = {
        "title": record["title"],
        "source_url": record["source_url"],
    }
    if "description" in record:
        result["description"] = record["description"]

    dates = {
        key: record.get("dates", {})[key]
        for key in ("published_at", "event_at")
        if key in record.get("dates", {})
    }
    if dates:
        result["dates"] = dates

    financial = {
        key: {"value": canonical_decimal(money["value"]), "currency": money["currency"]}
        for key, money in record.get("financial", {}).items()
    }
    if financial:
        result["financial"] = financial

    procurement = record.get("procurement", {})
    observed_procurement: dict[str, Any] = {}
    for key in ("expediente", "awardee"):
        if key in procurement:
            observed_procurement[key] = procurement[key]
    if procurement.get("cpv"):
        observed_procurement["cpv"] = canonical_set(list(procurement["cpv"]))
    if observed_procurement:
        result["procurement"] = observed_procurement

    grant = record.get("grant", {})
    observed_grant = {
        key: grant[key] for key in ("call_id", "resolution_id", "beneficiary") if key in grant
    }
    if observed_grant:
        result["grant"] = observed_grant

    documents = [
        {key: document[key] for key in ("source_url", "sha256") if key in document}
        for document in record.get("documents", ())
    ]
    if documents:
        result["documents"] = canonical_set(documents)
    if version == 2:
        result["source_data"] = {"bdns": canonical_bdns_data(record["source_data"]["bdns"])}
    return result


def content_hash(record: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        semantic_payload(record), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class FieldChange:
    path: str
    old_value: Any | None = None
    new_value: Any | None = None


def diff(previous: Mapping[str, Any], current: Mapping[str, Any]) -> tuple[FieldChange, ...]:
    """Compara exactamente el contenido que se usa para ``content_hash``."""
    assert_same_hash_contract(previous, current)
    changes: list[FieldChange] = []

    def walk(left: Any, right: Any, path: str) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(left.keys() | right.keys()):
                walk(left.get(key, _MISSING), right.get(key, _MISSING), f"{path}.{key}" if path else key)
        elif left != right:
            changes.append(FieldChange(
                path,
                None if left is _MISSING else left,
                None if right is _MISSING else right,
            ))

    walk(semantic_payload(previous), semantic_payload(current), "")
    return tuple(changes)
