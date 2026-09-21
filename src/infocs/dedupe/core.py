"""Dedupe de una fuente y transiciones de observación sin inferir retiradas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from copy import deepcopy
import json
from typing import Any, Mapping, Sequence

from infocs.diff.core import content_hash, diff
from infocs.finalize import finalize_record
from infocs.models import DataValidationError, Record, RecordCandidate, RecordStatus


class ObservationStatus(StrEnum):
    COMPLETE_SUCCESS = "complete_success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class DuplicateConflictError(ValueError):
    """Dos observaciones con un ID aportan contenido de fuente incompatible."""


@dataclass(frozen=True, slots=True)
class Event:
    schema_version: str
    type: str
    record_id: str
    source_id: str
    detected_at: str
    previous_content_hash: str | None = None
    new_content_hash: str | None = None
    changed_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "type": self.type,
            "record_id": self.record_id,
            "source_id": self.source_id,
            "detected_at": self.detected_at,
            "changed_fields": list(self.changed_fields),
        }
        if self.previous_content_hash is not None:
            result["previous_content_hash"] = self.previous_content_hash
        if self.new_content_hash is not None:
            result["new_content_hash"] = self.new_content_hash
        return result


def _utc_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DataValidationError("checked_at debe ser un timestamp ISO 8601.") from error
    if parsed.tzinfo is None:
        raise DataValidationError("checked_at debe incluir zona horaria.")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validated_internal_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Valida una transición interna que no altera el contenido semántico."""
    record = Record.from_dict(payload)
    if record.dates.last_checked_at < record.dates.detected_at:
        raise DataValidationError("last_checked_at no puede preceder a detected_at.")
    return record.to_dict()


def dedupe(records: Sequence[RecordCandidate | Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Agrupa por ID; ante contenido observado contradictorio, exige revisión."""
    seen: dict[str, dict[str, Any]] = {}
    for candidate in records:
        record = finalize_record(candidate).to_dict()
        record_id = record["id"]
        if record_id in seen and content_hash(seen[record_id]) != content_hash(record):
            raise DuplicateConflictError(f"Conflicto no resoluble para {record_id}.")
        if record_id in seen and seen[record_id]["status"] != record["status"]:
            raise DuplicateConflictError(f"Estados internos contradictorios para {record_id}.")
        # Para observaciones equivalentes se conserva la última comprobación.
        if (
            record_id not in seen
            or record["dates"]["last_checked_at"] > seen[record_id]["dates"]["last_checked_at"]
            or (
                record["dates"]["last_checked_at"] == seen[record_id]["dates"]["last_checked_at"]
                and json.dumps(record, ensure_ascii=False, sort_keys=True) < json.dumps(seen[record_id], ensure_ascii=False, sort_keys=True)
            )
        ):
            seen[record_id] = record
    return tuple(seen[key] for key in sorted(seen))


def reconcile(
    previous: Mapping[str, Mapping[str, Any]],
    observed: Sequence[RecordCandidate | Mapping[str, Any]],
    observation: ObservationStatus,
    *,
    source_id: str,
    checked_at: str,
) -> tuple[dict[str, dict[str, Any]], tuple[Event, ...]]:
    """Concilia una ejecución de una sola fuente con su estado anterior.

    ``checked_at`` es la hora real de esta observación, también para ausencias.
    """
    observation = ObservationStatus(observation)
    checked_at = _utc_timestamp(checked_at)
    if observation == ObservationStatus.FAILED and observed:
        raise DataValidationError("Una ejecución fallida no puede aportar records válidos.")
    for record_id, record in previous.items():
        Record.from_dict(record)
        if record["source"]["id"] != source_id or record["id"] != record_id:
            raise DataValidationError("El estado anterior contiene un ID o fuente incongruente.")
        if record.get("technical", {}).get("content_hash") != content_hash(record):
            raise DataValidationError("El estado anterior no está finalizado o tiene un hash incoherente.")
    current = {record["id"]: record for record in dedupe(observed)}
    if any(record["source"]["id"] != source_id for record in current.values()):
        raise DataValidationError("La observación contiene records de otra fuente.")
    if any(record["status"] == RecordStatus.MISSING_FROM_SOURCE.value for record in current.values()):
        raise DataValidationError("Un record observado no puede llegar como missing_from_source.")

    result = {key: dict(value) for key, value in previous.items()}
    events: list[Event] = []
    for record_id, record in current.items():
        old = previous.get(record_id)
        record = deepcopy(record)
        if old is not None:
            # La primera detección pertenece a la identidad, no a la ejecución.
            record["dates"]["detected_at"] = old["dates"]["detected_at"]
            # Un candidato nuevo no deshace por sí solo una decisión interna
            # previa de privacidad o retirada evidenciada.
            if old["status"] in (RecordStatus.QUARANTINE.value, RecordStatus.WITHDRAWN.value):
                record["status"] = old["status"]
        record["dates"]["last_checked_at"] = checked_at
        # Las transiciones internas cambian solo timestamps o estado, ambos
        # excluidos del hash semántico. El candidato ya se finalizó en dedupe.
        record = _validated_internal_record(record)
        new_hash = record["technical"]["content_hash"]
        old_hash = content_hash(old) if old is not None else None
        result[record_id] = record

        if old is None:
            kind = "create"
            paths: tuple[str, ...] = ()
        elif old["status"] == RecordStatus.MISSING_FROM_SOURCE.value:
            kind = "reappeared"
            paths = tuple(change.path for change in diff(old, record))
        elif old_hash != new_hash:
            kind = "update"
            paths = tuple(change.path for change in diff(old, record))
        else:
            continue
        events.append(Event("1.0", kind, record_id, source_id, checked_at, old_hash, new_hash, paths))

    if observation == ObservationStatus.COMPLETE_SUCCESS:
        for record_id, old in previous.items():
            if record_id in current:
                continue
            if old["status"] not in (RecordStatus.ACTIVE.value, RecordStatus.MISSING_FROM_SOURCE.value):
                continue
            missing = deepcopy(dict(old))
            missing["dates"] = {**old["dates"], "last_checked_at": checked_at}
            missing["status"] = RecordStatus.MISSING_FROM_SOURCE.value
            missing = _validated_internal_record(missing)
            result[record_id] = missing
            if old["status"] == RecordStatus.ACTIVE.value:
                old_hash = content_hash(old)
                events.append(Event(
                    "1.0", "missing_from_source", record_id, source_id,
                    checked_at, old_hash, old_hash,
                ))
    return result, tuple(events)
