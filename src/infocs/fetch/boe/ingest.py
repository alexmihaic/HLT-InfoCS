"""Ingesta incremental BOE en memoria y persistencia canónica opcional."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from infocs.events import Event, EventStore, create_event, update_event
from infocs.diff.core import diff
from infocs.fetch.boe.models import (
    BOEFetchResult,
    BOEFetchStatus,
    BOEItem,
    BOESummary,
)
from infocs.fetch.boe.normalize import BOENormalizationError, normalize_boe_item
from infocs.fetch.boe.review_queue import ReviewQueueEntry, ReviewQueueObservation
from infocs.fetch.boe.territorial import (
    BOETerritorialRegistry,
    decide_boe_territorial_inclusion,
)
from infocs.models import DataValidationError, Record
from infocs.privacy import PrivacyDecision, PrivacyDecisionType, PrivacyGate, PrivacyGateError
from infocs.publication.review import (
    PublicationDecisionType,
    PublicationReviewConfig,
    PublicationReviewError,
    review_publication,
)
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
    privacy_allowed: int = 0
    privacy_quarantined: int = 0
    privacy_rejected: int = 0
    publication_approved: int = 0
    publication_hold: int = 0
    publication_rejected: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "seen": self.seen,
            "included": self.included,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "excluded": self.excluded,
            "privacy_allowed": self.privacy_allowed,
            "privacy_quarantined": self.privacy_quarantined,
            "privacy_rejected": self.privacy_rejected,
            "publication_approved": self.publication_approved,
            "publication_hold": self.publication_hold,
            "publication_rejected": self.publication_rejected,
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
    review_queue_observations: tuple[ReviewQueueObservation, ...] = ()
    error: str | None = None


def ingest_boe_summary(
    fetched: BOESummary | BOEFetchResult,
    *,
    registry: BOETerritorialRegistry,
    store: RecordStore,
    detected_at: datetime,
    last_checked_at: datetime,
    publication_review_config: PublicationReviewConfig,
    event_store: EventStore | None = None,
    privacy_gate: PrivacyGate | None = None,
    run_id: str | None = None,
) -> BOEIngestionResult:
    """Procesa una edición BOE sin aplicar reconciliación de snapshots.

    Los candidatos y records se preparan y comparan completamente antes de
    llamar a ``store.write``. Una excepción contractual no produce ninguna
    escritura. La ausencia de un ítem en otro sumario no se examina.
    """
    if not isinstance(publication_review_config, PublicationReviewConfig):
        raise BOEIngestionError("La ingesta requiere una configuración de Publication Review válida.")
    try:
        publication_review_config.validate()
    except PublicationReviewError:
        raise BOEIngestionError("La configuración de Publication Review no es válida.") from None

    gate = privacy_gate if privacy_gate is not None else PrivacyGate.default()
    try:
        gate.validate()
    except PrivacyGateError as error:
        raise BOEIngestionError("La configuración del Privacy Gate no es válida.") from error

    summary = _summary_or_status(fetched)
    if isinstance(summary, BOEIngestionResult):
        return summary

    metrics = {
        "seen": len(summary.items), "included": 0, "created": 0, "updated": 0,
        "unchanged": 0, "excluded": 0, "privacy_allowed": 0,
        "privacy_quarantined": 0, "privacy_rejected": 0,
        "publication_approved": 0, "publication_hold": 0, "publication_rejected": 0,
    }
    planned: dict[str, tuple[Record, BOEOperation]] = {}
    events: list[Event] = []
    review_observations: list[ReviewQueueObservation] = []

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

        try:
            privacy_decision = gate.evaluate(record)
            if not isinstance(privacy_decision, PrivacyDecision) or privacy_decision.record_id != record.id:
                raise PrivacyGateError("El Privacy Gate devolvió una decisión inválida.")
        except Exception:
            raise BOEIngestionError("El Privacy Gate falló; batch abortado antes de escribir.") from None
        if privacy_decision.decision == PrivacyDecisionType.QUARANTINE:
            metrics["privacy_quarantined"] += 1
            review_observations.append(ReviewQueueObservation("boe", item.official_id, None))
            continue
        if privacy_decision.decision == PrivacyDecisionType.REJECT:
            metrics["privacy_rejected"] += 1
            review_observations.append(ReviewQueueObservation("boe", item.official_id, None))
            continue
        metrics["privacy_allowed"] += 1

        try:
            publication_decision = review_publication(record, privacy_decision, publication_review_config)
        except PublicationReviewError:
            raise BOEIngestionError("Publication Review falló; batch abortado antes de escribir.") from None
        if publication_decision.decision is PublicationDecisionType.HOLD:
            metrics["publication_hold"] += 1
            if run_id is not None:
                review_observations.append(ReviewQueueObservation(
                    "boe", item.official_id,
                    ReviewQueueEntry(
                        source_id="boe",
                        official_id=item.official_id,
                        source_url=record.source_url,
                        published_at=item.published_on.isoformat(),
                        run_id=run_id,
                        territorial_reason_codes=tuple(sorted({match.reason.value for match in decision.matches})),
                        entity_codes=tuple(sorted({match.entity_code for match in decision.matches})),
                        publication_decision="hold",
                        reason_code=publication_decision.reason_code,
                    ),
                ))
            continue
        if publication_decision.decision is PublicationDecisionType.REJECTED:
            metrics["publication_rejected"] += 1
            review_observations.append(ReviewQueueObservation("boe", item.official_id, None))
            continue
        metrics["publication_approved"] += 1
        review_observations.append(ReviewQueueObservation("boe", item.official_id, None))

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
            event = create_event(
                record, observed_at=last_checked_at, privacy=privacy_decision,
                publication=publication_decision,
            )
        elif existing.technical.content_hash == record.technical.content_hash:
            operation = BOEOperation(BOEOperationType.NO_CHANGE, record)
            metrics["unchanged"] += 1
            event = None
        else:
            changed_fields = tuple(change.path for change in diff(existing.to_dict(), record.to_dict()))
            operation = BOEOperation(BOEOperationType.UPDATE, record, changed_fields)
            metrics["updated"] += 1
            event = update_event(
                existing, record, observed_at=last_checked_at,
                privacy=privacy_decision, publication=publication_decision,
            )
        if event is not None:
            events.append(event)
        planned[record.id] = (record, operation)

    # Se escribe sólo después de finalizar y comparar todos los ítems. No hay
    # recorrido de records anteriores: BOE es un feed incremental, no snapshot.
    operations = tuple(planned[key][1] for key in sorted(planned))
    try:
        for operation in operations:
            if operation.type in (BOEOperationType.CREATE, BOEOperationType.UPDATE):
                store.validate(operation.record)
                store.path_for(operation.record.source.id, operation.record.id)
        if event_store is not None:
            for event in events:
                event_record = planned[event.record_id][0]
                event_store.preflight(
                    event, record=event_record,
                    publication_review_config=publication_review_config,
                    privacy_gate=gate,
                )
    except Exception:
        raise BOEIngestionError("El preflight de Record/Event falló; no se inició escritura.") from None

    # Event-first makes interrupted batches recoverable: if a later Record
    # write fails, retrying the same transition hits the existing Event and
    # can safely retry the Record write.
    if event_store is not None:
        for event in events:
            event_store.write(
                event, record=planned[event.record_id][0],
                publication_review_config=publication_review_config,
                privacy_gate=gate,
            )
    for operation in operations:
        if operation.type in (BOEOperationType.CREATE, BOEOperationType.UPDATE):
            store.write(operation.record)
    return BOEIngestionResult(
        status=BOEIngestionStatus.COMPLETE_SUCCESS,
        metrics=BOEIngestionMetrics(**metrics),
        operations=operations,
        events=tuple(events),
        review_queue_observations=tuple(review_observations),
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
        # 404 es una respuesta operativamente válida: no describe un fallo.
        error=None if status is BOEIngestionStatus.NO_DAILY_PUBLICATION else fetched.reason,
    )


def _finalize_candidate(candidate):
    # Import local evita hacer que el paquete BOE dependa de una reexportación
    # circular del finalizador.
    from infocs.finalize import finalize_record

    try:
        return finalize_record(candidate)
    except DataValidationError:
        raise
