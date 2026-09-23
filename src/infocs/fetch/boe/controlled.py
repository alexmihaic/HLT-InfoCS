"""Preflight y persistencia manualmente aprobada para el primer lote BOE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping

from infocs.diff.core import content_hash
from infocs.finalize import finalize_record
from infocs.fetch.boe.models import BOEFetchResult, BOEFetchStatus, BOETerritorialDecisionStatus
from infocs.fetch.boe.normalize import normalize_boe_item
from infocs.fetch.boe.territorial import BOETerritorialRegistry, decide_boe_territorial_inclusion, load_castellon_registry
from infocs.models import Record, RecordStatus, validate_record_payload
from infocs.privacy import PrivacyDecision, PrivacyDecisionType, PrivacyGate
from infocs.publication import PublicationDecision, PublicationDecisionType, PublicationReviewConfig, review_publication
from infocs.store import RecordStore, RecordStoreError


class BOEControlledPublicationError(ValueError):
    """Fallo de preflight; no se inicia ninguna escritura del lote."""


@dataclass(frozen=True, slots=True)
class BOEPublicationItem:
    publication_date: date
    official_id: str
    record: Record
    privacy_decision: PrivacyDecision
    publication_decision: PublicationDecision
    territorial_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BOEPublicationPreview:
    dates: tuple[date, ...]
    seen: int
    included: int
    excluded: int
    items: tuple[BOEPublicationItem, ...]

    @property
    def approved(self) -> tuple[BOEPublicationItem, ...]:
        return tuple(item for item in self.items if item.publication_decision.decision is PublicationDecisionType.APPROVED)

    @property
    def holds(self) -> tuple[BOEPublicationItem, ...]:
        return tuple(item for item in self.items if item.publication_decision.decision is PublicationDecisionType.HOLD)

    @property
    def rejected(self) -> tuple[BOEPublicationItem, ...]:
        return tuple(item for item in self.items if item.publication_decision.decision is PublicationDecisionType.REJECTED)


@dataclass(frozen=True, slots=True)
class BOEControlledPersistenceResult:
    created_paths: tuple[Path, ...]
    updated_paths: tuple[Path, ...]
    unchanged_ids: tuple[str, ...]


def prepare_boe_publication_preview(
    fetched_by_date: Mapping[date, BOEFetchResult],
    *,
    review_config: PublicationReviewConfig,
    detected_at: datetime,
    last_checked_at: datetime,
    registry: BOETerritorialRegistry | None = None,
    privacy_gate: PrivacyGate | None = None,
) -> BOEPublicationPreview:
    """Prepara y valida todo el conjunto en memoria; no recibe ni crea un store."""
    try:
        review_config.validate()
        gate = privacy_gate if privacy_gate is not None else PrivacyGate.default()
        gate.validate()
        active_registry = registry if registry is not None else load_castellon_registry()
    except Exception as error:
        raise BOEControlledPublicationError("La configuración de publicación, privacidad o territorio no es válida.") from None

    if not fetched_by_date or any(not isinstance(day, date) or isinstance(day, datetime) for day in fetched_by_date):
        raise BOEControlledPublicationError("El preflight requiere fechas BOE explícitas.")
    seen = included = excluded = 0
    processed_ids: set[str] = set()
    output: list[BOEPublicationItem] = []
    processed_record_ids: set[str] = set()
    for day in sorted(fetched_by_date):
        fetched = fetched_by_date[day]
        if not isinstance(fetched, BOEFetchResult) or fetched.status is not BOEFetchStatus.COMPLETE_SUCCESS:
            raise BOEControlledPublicationError("Todas las fechas deben tener sumario BOE completo y válido.")
        summary = fetched.summary
        if summary is None or summary.publication_date != day:
            raise BOEControlledPublicationError("La fecha del sumario no coincide con la consultada.")
        seen += len(summary.items)
        for item in summary.items:
            if item.published_on != day:
                raise BOEControlledPublicationError("La fecha de publicación de un ítem no coincide con su sumario.")
            decision = decide_boe_territorial_inclusion(item, active_registry)
            if decision.status is BOETerritorialDecisionStatus.NO_MATCH:
                excluded += 1
                continue
            included += 1
            if item.official_id in processed_ids:
                raise BOEControlledPublicationError("El lote contiene official_id duplicado.")
            processed_ids.add(item.official_id)
            try:
                candidate = normalize_boe_item(item, decision, detected_at=detected_at, last_checked_at=last_checked_at)
                if candidate is None:
                    raise ValueError("include_without_candidate")
                record = finalize_record(candidate)
                validate_record_payload(record.to_dict())
                if record.source.id != review_config.source_id or record.source.official_id != item.official_id:
                    raise ValueError("source_identity_mismatch")
                if record.id in processed_record_ids:
                    raise ValueError("record_id_duplicate")
                processed_record_ids.add(record.id)
                if record.status is not RecordStatus.ACTIVE:
                    raise ValueError("record_not_active")
                if not record.technical.content_hash or content_hash(record.to_dict()) != record.technical.content_hash:
                    raise ValueError("content_hash_mismatch")
                privacy = gate.evaluate(record)
                publication = review_publication(record, privacy, review_config)
            except Exception:
                raise BOEControlledPublicationError("Un ítem territorial incluido no superó el preflight contractual.") from None
            if publication.decision is PublicationDecisionType.APPROVED and privacy.decision is not PrivacyDecisionType.ALLOW:
                raise BOEControlledPublicationError("Aprobación inconsistente con Privacy Gate.")
            output.append(
                BOEPublicationItem(
                    day,
                    item.official_id,
                    record,
                    privacy,
                    publication,
                    tuple(sorted({match.reason.value for match in decision.matches})),
                )
            )

    found_approved = {item.official_id for item in output if item.publication_decision.decision is PublicationDecisionType.APPROVED}
    missing = review_config.approved_ids - found_approved
    if missing:
        raise BOEControlledPublicationError("Falta uno o más IDs aprobados explícitamente en los sumarios consultados.")
    return BOEPublicationPreview(tuple(sorted(fetched_by_date)), seen, included, excluded, tuple(output))


def persist_approved_preview(
    preview: BOEPublicationPreview,
    *,
    store: RecordStore,
    review_config: PublicationReviewConfig,
    privacy_gate: PrivacyGate | None = None,
) -> BOEControlledPersistenceResult:
    """Escribe sólo aprobados tras validar en bloque cada Record y privacidad."""
    gate = privacy_gate if privacy_gate is not None else store.privacy_gate
    try:
        review_config.validate()
        gate.validate()
        approved = preview.approved
        if not approved:
            return BOEControlledPersistenceResult((), (), ())
        ids: set[str] = set()
        planned: list[tuple[BOEPublicationItem, Path, str]] = []
        seen_paths: set[Path] = set()
        for item in approved:
            record = item.record
            if item.publication_decision.decision is not PublicationDecisionType.APPROVED or not item.publication_decision.explicitly_listed:
                raise ValueError("approval_not_explicit")
            if item.privacy_decision.decision is not PrivacyDecisionType.ALLOW:
                raise ValueError("privacy_not_allow")
            if record.source.id != "boe" or record.source.official_id != item.official_id:
                raise ValueError("unexpected_record_identity")
            validate_record_payload(record.to_dict())
            if not record.technical.content_hash or content_hash(record.to_dict()) != record.technical.content_hash:
                raise ValueError("content_hash_mismatch")
            fresh_privacy = gate.evaluate(record)
            if fresh_privacy.decision is not PrivacyDecisionType.ALLOW or fresh_privacy.record_id != record.id:
                raise ValueError("privacy_changed_after_preflight")
            configured_decision = review_publication(record, fresh_privacy, review_config)
            if configured_decision != item.publication_decision or configured_decision.decision is not PublicationDecisionType.APPROVED:
                raise ValueError("publication_review_mismatch")
            if record.id in ids:
                raise ValueError("record_id_duplicate")
            ids.add(record.id)
            path = store.path_for("boe", record.id)
            if path in seen_paths:
                raise ValueError("store_path_collision")
            seen_paths.add(path)
            existing = store.get(record.id, source_id="boe")
            if existing is None:
                operation = "create"
            elif existing.technical.content_hash == record.technical.content_hash:
                operation = "no_change"
            else:
                operation = "update"
            planned.append((item, path, operation))
    except Exception:
        raise BOEControlledPublicationError("El preflight global falló; no se inició ninguna escritura.") from None

    created: list[Path] = []
    updated: list[Path] = []
    unchanged: list[str] = []
    for item, expected_path, operation in planned:
        if operation == "no_change":
            unchanged.append(item.record.id)
            continue
        try:
            actual_path = store.write(item.record)
        except Exception:
            # El store garantiza atomicidad individual; el lote no ofrece rollback
            # multiarchivo si un error de I/O ocurre después del primer reemplazo.
            raise BOEControlledPublicationError("Error de almacenamiento; cada archivo es atómico, el lote no tiene rollback.") from None
        if actual_path != expected_path:
            raise BOEControlledPublicationError("RecordStore devolvió un path distinto del preflight.")
        (created if operation == "create" else updated).append(actual_path)
    return BOEControlledPersistenceResult(tuple(created), tuple(updated), tuple(unchanged))
