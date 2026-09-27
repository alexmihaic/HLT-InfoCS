"""Ingesta controlada BDNS; persistence only follows all publication gates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
import re

from infocs.fetch.bdns.models import BDNSRequestStatus, BDNSSearchQuery
from infocs.fetch.bdns.normalize import (
    BDNSNormalizationError,
    BDNSTerritorialStatus,
    normalize_bdns_detail,
)
from infocs.fetch.bdns.publication import (
    BDNSMetadataPublicationDecisionType,
    BDNSPublicationPolicyError,
    evaluate_bdns_publication,
)
from infocs.fetch.bdns.transport import BDNSTransport
from infocs.finalize import finalize_record
from infocs.models import DataValidationError, Record
from infocs.privacy import PrivacyDecision, PrivacyDecisionType, PrivacyGate, PrivacyGateError
from infocs.publication.source_policy import SourcePublicationEligibilityType
from infocs.store import RecordStore, RecordStoreError


BDNS_ATTRIBUTION_PATH = Path(__file__).resolve().parents[4] / "data" / "records" / "bdns" / "README.md"
BDNS_ATTRIBUTION = "Origen de los datos: Intervención General de la Administración del Estado"
BDNS_ATTRIBUTION_REQUIREMENTS = (
    BDNS_ATTRIBUTION,
    "no desnaturalizar",
    "fecha de actualización",
    "disociación",
    "no insinuar patrocinio",
)


class BDNSIngestionStatus(StrEnum):
    COMPLETE_SUCCESS = "complete_success"
    NO_RESULTS = "no_results"
    SOURCE_FAILURE = "source_failure"
    TERRITORIAL_CONTRACT_DRIFT = "territorial_contract_drift"
    PERSISTENCE_BLOCKED = "persistence_blocked"


class BDNSRecordOperation(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    NO_CHANGE = "no_change"


class BDNSEventStatus(StrEnum):
    CREATED = "created"
    NOT_REQUIRED = "not_required"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class BDNSIngestionMetrics:
    search_seen: int = 0
    details_fetched: int = 0
    in_scope: int = 0
    unresolved: int = 0
    out_of_scope: int = 0
    finalized: int = 0
    privacy_allow: int = 0
    privacy_quarantine: int = 0
    privacy_reject: int = 0
    source_eligible: int = 0
    metadata_publishable: int = 0
    metadata_hold: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    events_created: int = 0
    errors: int = 0

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field.name} debe ser un entero no negativo.")

    def to_dict(self) -> dict[str, int]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


@dataclass(frozen=True, slots=True)
class BDNSIngestionResult:
    status: BDNSIngestionStatus
    metrics: BDNSIngestionMetrics
    request_count: int
    http_statuses: tuple[int, ...] = ()
    operation: BDNSRecordOperation | None = None
    event_status: BDNSEventStatus = BDNSEventStatus.NOT_REQUIRED
    record_path: Path | None = None
    content_hash: str | None = None
    safe_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Resumen sin códigos BDNS, títulos, autoridades, URLs ni payloads."""
        return {
            "status": self.status.value,
            "metrics": self.metrics.to_dict(),
            "request_count": self.request_count,
            "http_statuses": list(self.http_statuses),
            "operation": self.operation.value if self.operation else None,
            "event_status": self.event_status.value,
            "record_path": "data/records/bdns/r-<encoded-record-id>.json" if self.record_path else None,
            "content_hash": self.content_hash,
            "safe_reason": self.safe_reason,
        }


def ingest_bdns(
    *,
    record_store: RecordStore,
    started_at: datetime,
    transport: BDNSTransport | None = None,
    privacy_gate: PrivacyGate | None = None,
    clock: Callable[[], datetime] | None = None,
    attribution_path: Path = BDNS_ATTRIBUTION_PATH,
    page_size: int = 3,
    max_details: int = 3,
    max_persisted_records: int = 1,
) -> BDNSIngestionResult:
    """Procesa hasta tres detalles y persiste como máximo un Record elegible.

    No usa EventStore porque su contrato v1 exige Publication Review manual
    BOE. En create/update informa ``BDNS_CREATE_EVENT_DEFERRED`` sin fabricar
    una aprobación BOE ni cambiar el contrato Event actual.
    """
    if not isinstance(record_store, RecordStore):
        raise TypeError("record_store debe ser RecordStore.")
    for name, value in (("page_size", page_size), ("max_details", max_details)):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3:
            raise ValueError(f"{name} debe estar entre 1 y 3.")
    if max_persisted_records != 1:
        raise ValueError("Esta fase permite persistir como máximo un Record.")
    _validate_aware_timestamp(started_at, "started_at")

    client = transport or BDNSTransport()
    gate = privacy_gate or PrivacyGate.default()
    timestamp = clock or (lambda: datetime.now(UTC))
    counts = {field.name: 0 for field in fields(BDNSIngestionMetrics)}
    statuses: list[int] = []
    requests = 1
    try:
        search = client.search(
            BDNSSearchQuery(
                page=0,
                page_size=page_size,
                order="fechaRecepcion",
                direction="desc",
                region_ids=(56,),
            )
        )
    except Exception:
        counts["errors"] += 1
        return _result(BDNSIngestionStatus.SOURCE_FAILURE, counts, requests, statuses, safe_reason="search_failure")
    if search.http_status is not None:
        statuses.append(search.http_status)
    if search.status is BDNSRequestStatus.NO_RESULTS:
        return _result(BDNSIngestionStatus.NO_RESULTS, counts, requests, statuses)
    if search.status is not BDNSRequestStatus.SUCCESS or search.payload is None:
        return _result(BDNSIngestionStatus.SOURCE_FAILURE, counts, requests, statuses, safe_reason="search_failure")
    summaries = search.payload.items[:max_details]
    counts["search_seen"] = len(search.payload.items)
    if not summaries:
        return _result(BDNSIngestionStatus.NO_RESULTS, counts, requests, statuses)

    for summary in summaries:
        requests += 1
        try:
            detail_result = client.fetch_detail(summary.numero_convocatoria)
        except Exception:
            counts["errors"] += 1
            continue
        if detail_result.http_status is not None:
            statuses.append(detail_result.http_status)
        if detail_result.status is not BDNSRequestStatus.SUCCESS or detail_result.payload is None:
            counts["errors"] += 1
            continue
        counts["details_fetched"] += 1
        observed_at = timestamp()
        try:
            _validate_aware_timestamp(observed_at, "observation timestamp")
            if observed_at < started_at:
                raise ValueError("observation timestamp precedes the run start.")
            normalized = normalize_bdns_detail(
                summary,
                detail_result.payload,
                detected_at=started_at,
                last_checked_at=observed_at,
            )
        except (BDNSNormalizationError, ValueError):
            counts["errors"] += 1
            continue

        territorial = normalized.territorial_decision.status
        if territorial is BDNSTerritorialStatus.OUT_OF_SCOPE:
            counts["out_of_scope"] += 1
            counts["errors"] += 1
            return _result(
                BDNSIngestionStatus.TERRITORIAL_CONTRACT_DRIFT,
                counts,
                requests,
                statuses,
                safe_reason="territorial_contract_drift",
            )
        if territorial is BDNSTerritorialStatus.UNRESOLVED:
            counts["unresolved"] += 1
            counts["errors"] += 1
            return _result(
                BDNSIngestionStatus.TERRITORIAL_CONTRACT_DRIFT,
                counts,
                requests,
                statuses,
                safe_reason="territorial_contract_drift",
            )
        if normalized.candidate is None:
            counts["errors"] += 1
            continue
        counts["in_scope"] += 1

        try:
            record = finalize_record(normalized.candidate)
        except DataValidationError:
            counts["errors"] += 1
            continue
        counts["finalized"] += 1

        try:
            privacy = gate.evaluate(record)
            if not isinstance(privacy, PrivacyDecision) or privacy.record_id != record.id:
                counts["errors"] += 1
                continue
        except PrivacyGateError:
            counts["errors"] += 1
            continue
        if privacy.decision is PrivacyDecisionType.QUARANTINE:
            counts["privacy_quarantine"] += 1
            continue
        if privacy.decision is PrivacyDecisionType.REJECT:
            counts["privacy_reject"] += 1
            continue
        if privacy.decision is not PrivacyDecisionType.ALLOW:
            counts["errors"] += 1
            continue
        counts["privacy_allow"] += 1

        try:
            publication = evaluate_bdns_publication(record, privacy)
        except BDNSPublicationPolicyError:
            counts["errors"] += 1
            continue
        if (
            publication.source_eligibility is None
            or publication.source_eligibility.decision is not SourcePublicationEligibilityType.ELIGIBLE
            or publication.metadata_publication is None
        ):
            counts["errors"] += 1
            continue
        counts["source_eligible"] += 1
        if publication.metadata_publication.decision is not BDNSMetadataPublicationDecisionType.PUBLISHABLE_METADATA:
            counts["metadata_hold"] += 1
            continue
        counts["metadata_publishable"] += 1

        if not _attribution_preflight(attribution_path):
            counts["errors"] += 1
            return _result(
                BDNSIngestionStatus.PERSISTENCE_BLOCKED,
                counts,
                requests,
                statuses,
                safe_reason="attribution_preflight_failed",
            )
        try:
            # Re-evaluate the supplied decisions before the Store receives data.
            _assert_persistence_gates(record, privacy)
            record_store.validate(record)
            target_path = record_store.path_for(record.source.id, record.id)
            existing = record_store.get(record.id, source_id=record.source.id)
        except (RecordStoreError, BDNSPublicationPolicyError):
            counts["errors"] += 1
            return _result(
                BDNSIngestionStatus.PERSISTENCE_BLOCKED,
                counts,
                requests,
                statuses,
                safe_reason="record_preflight_failed",
            )

        if existing is None:
            operation = BDNSRecordOperation.CREATE
        elif existing.technical.content_hash == record.technical.content_hash:
            operation = BDNSRecordOperation.NO_CHANGE
        else:
            operation = BDNSRecordOperation.UPDATE

        if operation is BDNSRecordOperation.CREATE:
            counts["records_created"] += 1
        elif operation is BDNSRecordOperation.UPDATE:
            counts["records_updated"] += 1
        else:
            counts["records_unchanged"] += 1

        event_status = BDNSEventStatus.NOT_REQUIRED
        if operation in {BDNSRecordOperation.CREATE, BDNSRecordOperation.UPDATE}:
            event_status = BDNSEventStatus.DEFERRED
        try:
            if operation is not BDNSRecordOperation.NO_CHANGE:
                _assert_persistence_gates(record, privacy)
                written_path = record_store.write(record)
            else:
                written_path = target_path
        except (RecordStoreError, OSError):
            counts["errors"] += 1
            return _result(
                BDNSIngestionStatus.PERSISTENCE_BLOCKED,
                counts,
                requests,
                statuses,
                safe_reason="record_write_failed",
            )

        # Event v1 writes are coupled to manual Publication Review; BDNS has its
        # own source metadata policy, so no EventStore call is safe in this phase.
        return _result(
            BDNSIngestionStatus.COMPLETE_SUCCESS,
            counts,
            requests,
            statuses,
            operation=operation,
            event_status=event_status,
            record_path=written_path,
            content_hash=record.technical.content_hash,
            safe_reason=(
                "BDNS_CREATE_EVENT_DEFERRED"
                if operation is BDNSRecordOperation.CREATE
                else "BDNS_UPDATE_EVENT_DEFERRED"
                if operation is BDNSRecordOperation.UPDATE
                else None
            ),
        )

    status = BDNSIngestionStatus.SOURCE_FAILURE if counts["errors"] else BDNSIngestionStatus.COMPLETE_SUCCESS
    return _result(status, counts, requests, statuses, safe_reason="no_publishable_record_in_budget")


def _assert_persistence_gates(record: Record, privacy: PrivacyDecision) -> None:
    if privacy.decision is not PrivacyDecisionType.ALLOW or privacy.record_id != record.id:
        raise BDNSPublicationPolicyError("Privacy gate does not permit this persistence.")
    decision = evaluate_bdns_publication(record, privacy)
    if (
        decision.source_eligibility is None
        or decision.source_eligibility.decision is not SourcePublicationEligibilityType.ELIGIBLE
        or decision.metadata_publication is None
        or decision.metadata_publication.decision is not BDNSMetadataPublicationDecisionType.PUBLISHABLE_METADATA
    ):
        raise BDNSPublicationPolicyError("BDNS publication gates do not permit persistence.")


def _attribution_preflight(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, TypeError):
        return False
    folded = re.sub(r"\s+", " ", text.casefold())
    return all(requirement.casefold() in folded for requirement in BDNS_ATTRIBUTION_REQUIREMENTS)


def _validate_aware_timestamp(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} debe incluir zona horaria.")


def _result(
    status: BDNSIngestionStatus,
    counts: dict[str, int],
    requests: int,
    statuses: list[int],
    *,
    operation: BDNSRecordOperation | None = None,
    event_status: BDNSEventStatus = BDNSEventStatus.NOT_REQUIRED,
    record_path: Path | None = None,
    content_hash: str | None = None,
    safe_reason: str | None = None,
) -> BDNSIngestionResult:
    return BDNSIngestionResult(
        status=status,
        metrics=BDNSIngestionMetrics(**counts),
        request_count=requests,
        http_statuses=tuple(statuses),
        operation=operation,
        event_status=event_status,
        record_path=record_path,
        content_hash=content_hash,
        safe_reason=safe_reason,
    )
