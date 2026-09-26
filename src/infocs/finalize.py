"""Único punto de preparación de records normalizados para almacenamiento."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from infocs.diff.core import canonical_decimal, canonical_set, content_hash
from infocs.identity.core import identify
from infocs.models import DataValidationError, Record, RecordCandidate


def finalize_record(candidate: RecordCandidate | Mapping[str, Any]) -> Record:
    """Valida, normaliza, identifica, calcula hash y devuelve un Record nuevo.

    No escribe en disco y nunca modifica el candidato recibido.
    """
    if isinstance(candidate, RecordCandidate):
        if candidate.dates.detected_at.tzinfo is None or candidate.dates.last_checked_at.tzinfo is None:
            raise DataValidationError("Los timestamps internos deben incluir zona horaria.")
        payload = candidate.to_dict()
    elif isinstance(candidate, Record):
        raise DataValidationError("finalize_record() recibe RecordCandidate, no un Record final.")
    else:
        payload = deepcopy(dict(candidate))

    # Validación inicial del candidato, incluida la igualdad de niveles.
    validated = RecordCandidate.from_dict(payload)
    if validated.dates.last_checked_at < validated.dates.detected_at:
        raise DataValidationError("last_checked_at no puede preceder a detected_at.")
    result = validated.to_dict()  # Los timestamps ya están expresados en UTC.

    for money in result.get("financial", {}).values():
        money["value"] = canonical_decimal(money["value"])

    if result["authority"] is not None and "aliases" in result["authority"]:
        result["authority"]["aliases"] = canonical_set(result["authority"]["aliases"])
    for key in ("tags", "documents", "relations"):
        if key in result:
            result[key] = canonical_set(result[key])
    if "procurement" in result and "cpv" in result["procurement"]:
        result["procurement"]["cpv"] = canonical_set(result["procurement"]["cpv"])
    matches = result["provenance"]["territorial_matches"]
    result["provenance"]["territorial_matches"] = canonical_set(matches)

    identity = identify(result)
    result["id"] = identity.record_id
    technical = result.setdefault("technical", {})
    technical["identity_strategy"] = identity.strategy
    technical["content_hash"] = content_hash(result)

    # El schema portable y las reglas Python validan exactamente el resultado.
    return Record.from_dict(result)
