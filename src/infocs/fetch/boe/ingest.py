"""Ingesta incremental BOE en memoria y persistencia canónica opcional."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from infocs.dedupe.core import Event
from infocs.diff.core import diff
from infocs.fetch.boe.models import (
    BOEFetchResult,
    BOEFetchStatus,
    BOEItem,
    BOESummary,
)
from infocs.fetch.boe.normalize import BOENormalizationError, normalize_boe_item
from infocs.fetch.boe.territorial import (
    BOETerritorialRegistry,
    decide_boe_territorial_inclusion,
)
from infocs.models import DataValidationError, Record
from infocs.store import RecordStore, RecordStoreError


class BOEIngestionStatus(StrEnum):
    COMPLETE_SUCCESS = "complete_success"
    NO_DAILY_PUBLICATION = "no_daily_publication"
    SOURCE_FAILURE = "source_failure"
    INVALID_REQUEST = "invalid_request"


class BOECollectionSemantics(StrEnum):
    INCREMENTAL_FEED = "incremental_feed"
    SNAPSHOT = "snapshot"


BOE_COLLECTION_SEMANTICS = BOECollectionSemantics.INCREMENTAL_FEED


class BOEIngestionError(ValueError):
    """Error contractual que aborta el batch antes de cualquier escritura."""


class BOEOperationType(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    NO_CHANGE = "no_change"


@dataclass(frozen=True, slots=True)
class BOEIngestionMetrics:
    seen: int = 0
    included: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    excluded: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "seen": self.seen,
            "included": self.included,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "excluded": self.excluded,
        }


@dataclass(frozen=True, slots=True)
class BOEOperation:
    type: BOEOperationType
    record: Record
    changed_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BOEIngestionResult:
    status: BOEIngestionStatus
    metrics: BOEIngestionMetrics
    collection_semantics: BOECollectionSemantics = BOE_COLLECTION_SEMANTICS
    operations: tuple[BOEOperation, ...] = ()
    events: tuple[Event, ...] = ()
    error: str | None = None


def ingest_boe_summary(
    fetched: BOESummary | BOEFetchResult,
    *,
    registry: BOETerritorialRegistry,
    store: RecordStore,
    detected_at: datetime,
    last_checked_at: datetime,
) -> BOEIngestionResult:
    """Procesa una edición BOE sin aplicar reconciliación de snapshots.

    Los candidatos y records se preparan y comparan completamente antes de
    llamar a ``store.write``. Una excepción contractual no produce ninguna
    escritura. La ausencia de un ítem en otro sumario no se examina.
    """
    summary = _summary_or_status(fetched)
    if isinstance(summary, BOEIngestionResult):
        return summary

    metrics = {"seen": len(summary.items), "included": 0, "created": 0, "updated": 0, "unchanged": 0, "excluded": 0}
    planned: dict[str, tuple[Record, BOEOperation]] = {}
    events: list[Event] = []

    for item in summary.items:
        decision = decide_boe_territorial_inclusion(item, registry)
        if decision.status.value == "no_match":
            metrics["excluded"] += 1
            continue
        metrics["included"] += 1
        try:
            candidate = normalize_boe_item(
                item,
                decision,
                detected_at=detected_at,
                last_checked_at=last_checked_at,
            )
            if candidate is None:  # pragma: no cover - defensa ante deriva de contrato
                raise BOEIngestionError("Una decisión include no produjo candidato.")
            record = _finalize_candidate(candidate)
        except (BOENormalizationError, DataValidationError, RecordStoreError) as error:
            raise BOEIngestionError(
                f"El ítem BOE {item.official_id!r} no puede incorporarse; batch abortado."
            ) from error

        if record.id in planned:
            previous_batch_record, _ = planned[record.id]
            if previous_batch_record.technical.content_hash != record.technical.content_hash:
                raise BOEIngestionError(
                    f"El sumario contiene contenido incompatible para {record.id}."
                )
            continue

        existing = store.get(record.id, source_id=record.source.id)
        if existing is None:
            operation = BOEOperation(BOEOperationType.CREATE, record)
            metrics["created"] += 1
            events.append(_event_for("create", record, checked_at=record.dates.last_checked_at))
        elif existing.technical.content_hash == record.technical.content_hash:
            operation = BOEOperation(BOEOperationType.NO_CHANGE, record)
            metrics["unchanged"] += 1
        else:
            changed_fields = tuple(change.path for change in diff(existing.to_dict(), record.to_dict()))
            operation = BOEOperation(BOEOperationType.UPDATE, record, changed_fields)
            metrics["updated"] += 1
            events.append(
                _event_for(
                    "update",
                    record,
                    checked_at=record.dates.last_checked_at,
                    previous=existing,
                    changed_fields=changed_fields,
                )
            )
        planned[record.id] = (record, operation)

    # Se escribe sólo después de finalizar y comparar todos los ítems. No hay
    # recorrido de records anteriores: BOE es un feed incremental, no snapshot.
    operations = tuple(planned[key][1] for key in sorted(planned))
    for operation in operations:
        if operation.type in (BOEOperationType.CREATE, BOEOperationType.UPDATE):
            store.write(operation.record)
    return BOEIngestionResult(
        status=BOEIngestionStatus.COMPLETE_SUCCESS,
        metrics=BOEIngestionMetrics(**metrics),
        operations=operations,
        events=tuple(events),
    )


def _summary_or_status(fetched: BOESummary | BOEFetchResult) -> BOESummary | BOEIngestionResult:
    if isinstance(fetched, BOESummary):
        return fetched
    if not isinstance(fetched, BOEFetchResult):
        raise BOEIngestionError("La ingesta requiere BOESummary o BOEFetchResult.")
    if fetched.status is BOEFetchStatus.COMPLETE_SUCCESS:
        if fetched.summary is None:  # pragma: no cover - protegido por BOEFetchResult
            raise BOEIngestionError("complete_success requiere un sumario BOE.")
        return fetched.summary
    status = BOEIngestionStatus(fetched.status.value)
    return BOEIngestionResult(
        status=status,
        metrics=BOEIngestionMetrics(),
        error=fetched.reason,
    )


def _finalize_candidate(candidate):
    # Import local evita hacer que el paquete BOE dependa de una reexportación
    # circular del finalizador.
    from infocs.finalize import finalize_record

    try:
        return finalize_record(candidate)
    except DataValidationError:
        raise


def _event_for(
    event_type: str,
    record: Record,
    *,
    checked_at: datetime,
    previous: Record | None = None,
    changed_fields: tuple[str, ...] = (),
) -> Event:
    timestamp = checked_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return Event(
        schema_version="1.0",
        type=event_type,
        record_id=record.id,
        source_id=record.source.id,
        detected_at=timestamp,
        previous_content_hash=previous.technical.content_hash if previous else None,
        new_content_hash=record.technical.content_hash,
        changed_fields=changed_fields,
    )
