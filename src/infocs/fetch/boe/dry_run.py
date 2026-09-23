"""Ejecución BOE de auditoría, separada de toda ruta de persistencia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from infocs.finalize import finalize_record
from infocs.fetch.boe.models import (
    BOEFetchResult,
    BOEFetchStatus,
    BOEItem,
    BOETerritorialDecision,
    BOETerritorialDecisionStatus,
)
from infocs.fetch.boe.normalize import normalize_boe_item
from infocs.fetch.boe.territorial import (
    BOETerritorialRegistry,
    decide_boe_territorial_inclusion,
    load_castellon_registry,
)
from infocs.fetch.boe.transport import BOETransport
from infocs.models import Record
from infocs.privacy import PrivacyDecision, PrivacyDecisionType, PrivacyGate


class BOEDryRunMatchAudit(StrEnum):
    EXPECTED_MATCH = "expected_match"
    SUSPICIOUS_MATCH = "suspicious_match"


@dataclass(frozen=True, slots=True)
class BOEDryRunError:
    stage: str
    error_type: str
    official_id: str | None = None
    detail: str = "pipeline_stage_failed"

    def to_dict(self) -> dict[str, str]:
        result = {"stage": self.stage, "error_type": self.error_type, "detail": self.detail}
        if self.official_id is not None:
            result["official_id"] = self.official_id
        return result


@dataclass(frozen=True, slots=True)
class BOEDryRunItemAudit:
    official_id: str
    privacy_decision: PrivacyDecisionType
    title: str | None = None
    authority_name: str | None = None
    category: str | None = None
    published_at: str | None = None
    identity_strategy: str | None = None
    geography_municipality: str | None = None
    territorial_matches: tuple[dict[str, str], ...] = ()
    privacy_reasons: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        # Un registro en quarantine/reject sólo expone ID y motivos seguros.
        result: dict[str, object] = {
            "official_id": self.official_id,
            "privacy_decision": self.privacy_decision.value,
        }
        if self.privacy_decision is not PrivacyDecisionType.ALLOW:
            result["privacy_reasons"] = list(self.privacy_reasons)
            return result
        result.update(
            {
                "title": self.title,
                "authority_name": self.authority_name,
                "category": self.category,
                "published_at": self.published_at,
                "identity_strategy": self.identity_strategy,
                "geography_municipality": self.geography_municipality,
                "territorial_matches": list(self.territorial_matches),
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class BOEDryRunMetrics:
    seen: int = 0
    included: int = 0
    excluded: int = 0
    normalized: int = 0
    finalized: int = 0
    privacy_allowed: int = 0
    privacy_quarantined: int = 0
    privacy_rejected: int = 0
    unprocessed: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "seen": self.seen,
            "included": self.included,
            "excluded": self.excluded,
            "normalized": self.normalized,
            "finalized": self.finalized,
            "privacy_allowed": self.privacy_allowed,
            "privacy_quarantined": self.privacy_quarantined,
            "privacy_rejected": self.privacy_rejected,
            "unprocessed": self.unprocessed,
        }


@dataclass(frozen=True, slots=True)
class BOEDryRunResult:
    date: str
    transport_status: str
    http_status: int | None
    metrics: BOEDryRunMetrics
    items: tuple[BOEDryRunItemAudit, ...] = ()
    errors: tuple[BOEDryRunError, ...] = ()
    identity_checks: tuple[tuple[str, object], ...] = ()
    content_hash_stable: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "date": self.date,
            "transport_status": self.transport_status,
            "http_status": self.http_status,
            **self.metrics.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "errors": [error.to_dict() for error in self.errors],
            "identity_checks": dict(self.identity_checks),
            "content_hash_stable": self.content_hash_stable,
        }


def dry_run_boe_date(
    publication_date: date,
    *,
    detected_at: datetime,
    last_checked_at: datetime,
    registry: BOETerritorialRegistry | None = None,
    privacy_gate: PrivacyGate | None = None,
    transport: BOETransport | None = None,
) -> BOEDryRunResult:
    """Ejecuta BOE hasta Privacy Gate y devuelve una vista segura en memoria.

    No acepta ``RecordStore``, no importa la ingesta persistente y no escribe
    records, events, respuestas, manifests ni health. El transporte real solo
    consulta el endpoint diario configurado en ``BOETransport``.
    """
    if not isinstance(publication_date, date) or isinstance(publication_date, datetime):
        raise TypeError("publication_date debe ser datetime.date.")
    date_text = publication_date.isoformat()
    metrics = BOEDryRunMetrics()
    empty_errors: tuple[BOEDryRunError, ...] = ()
    try:
        active_registry = registry or load_castellon_registry()
        active_gate = privacy_gate or PrivacyGate.default()
        active_gate.validate()
    except Exception as error:
        return BOEDryRunResult(
            date_text,
            BOEFetchStatus.SOURCE_FAILURE.value,
            None,
            metrics,
            errors=(BOEDryRunError("privacy_or_configuration", type(error).__name__),),
        )

    try:
        fetched = (transport or BOETransport()).fetch_daily_summary(publication_date)
    except Exception as error:
        return BOEDryRunResult(
            date_text,
            BOEFetchStatus.SOURCE_FAILURE.value,
            None,
            metrics,
            errors=(BOEDryRunError("transport", type(error).__name__),),
        )

    if not isinstance(fetched, BOEFetchResult):
        return BOEDryRunResult(
            date_text,
            BOEFetchStatus.SOURCE_FAILURE.value,
            None,
            metrics,
            errors=(BOEDryRunError("transport", "InvalidTransportResult"),),
        )
    if fetched.status is not BOEFetchStatus.COMPLETE_SUCCESS:
        errors = empty_errors
        if fetched.status not in (
            BOEFetchStatus.NO_DAILY_PUBLICATION,
        ):
            errors = (BOEDryRunError("transport", fetched.status.value, detail=fetched.reason or fetched.status.value),)
        return BOEDryRunResult(date_text, fetched.status.value, fetched.http_status, metrics, errors=errors)

    summary = fetched.summary
    if summary is None:  # BOEFetchResult protege esta situación; defensa contractual.
        return BOEDryRunResult(
            date_text,
            BOEFetchStatus.SOURCE_FAILURE.value,
            fetched.http_status,
            metrics,
            errors=(BOEDryRunError("parser", "MissingSummary"),),
        )
    if summary.publication_date != publication_date:
        return BOEDryRunResult(
            date_text,
            BOEFetchStatus.SOURCE_FAILURE.value,
            fetched.http_status,
            metrics,
            errors=(BOEDryRunError("parser", "PublicationDateMismatch"),),
        )

    items = summary.items
    seen = len(items)
    included = excluded = normalized = finalized = allowed = quarantined = rejected = 0
    unprocessed = 0
    audit_items: list[BOEDryRunItemAudit] = []
    errors: list[BOEDryRunError] = []
    seen_ids: dict[str, str] = {}
    collision_count = 0
    fallback_count = 0
    unique_id_count = 0
    hash_stable = True

    for index, item in enumerate(items):
        stage = "territorial"
        try:
            decision = decide_boe_territorial_inclusion(item, active_registry)
            if not isinstance(decision, BOETerritorialDecision):
                raise TypeError("InvalidTerritorialDecision")
            if decision.status is BOETerritorialDecisionStatus.NO_MATCH:
                excluded += 1
                continue
            included += 1

            stage = "normalization"
            candidate = normalize_boe_item(
                item,
                decision,
                detected_at=detected_at,
                last_checked_at=last_checked_at,
            )
            if candidate is None:
                raise ValueError("IncludedItemWithoutCandidate")
            normalized += 1

            stage = "finalization"
            record = finalize_record(candidate)
            repeated = finalize_record(candidate)
            finalized += 1
            hash_stable = hash_stable and (
                record.technical.content_hash == repeated.technical.content_hash
            )
            if not record.technical.content_hash:
                raise ValueError("MissingContentHash")
            strategy = _enum_value(record.technical.identity_strategy)
            if strategy != "official_id" or not item.official_id or record.source.official_id != item.official_id:
                fallback_count += 1
                errors.append(BOEDryRunError("identity", "IdentityFallback", item.official_id))
                unprocessed = seen - included - excluded
                break
            prior_official_id = seen_ids.get(record.id)
            if prior_official_id is None:
                seen_ids[record.id] = item.official_id
                unique_id_count += 1
            elif prior_official_id != item.official_id:
                collision_count += 1
                errors.append(BOEDryRunError("identity", "RecordIdCollision", item.official_id))
                unprocessed = seen - included - excluded
                break

            stage = "privacy"
            privacy = active_gate.evaluate(record)
            if not isinstance(privacy, PrivacyDecision) or privacy.record_id != record.id:
                raise TypeError("InvalidPrivacyDecision")
            if privacy.decision is PrivacyDecisionType.ALLOW:
                allowed += 1
                audit_items.append(_allowed_audit_item(item, decision, record, privacy))
            elif privacy.decision is PrivacyDecisionType.QUARANTINE:
                quarantined += 1
                audit_items.append(_blocked_audit_item(item, privacy))
            elif privacy.decision is PrivacyDecisionType.REJECT:
                rejected += 1
                audit_items.append(_blocked_audit_item(item, privacy))
            else:  # pragma: no cover - PrivacyDecision valida el enum.
                raise TypeError("UnknownPrivacyDecision")
        except Exception as error:
            errors.append(BOEDryRunError(stage, type(error).__name__, _safe_official_id(item)))
            unprocessed = seen - included - excluded
            # Una excepción del gate impide evaluar más registros con seguridad.
            if stage == "privacy":
                break

    if unprocessed == 0:
        unprocessed = max(0, seen - included - excluded)
    metrics = BOEDryRunMetrics(
        seen=seen,
        included=included,
        excluded=excluded,
        normalized=normalized,
        finalized=finalized,
        privacy_allowed=allowed,
        privacy_quarantined=quarantined,
        privacy_rejected=rejected,
        unprocessed=unprocessed,
    )
    return BOEDryRunResult(
        date_text,
        BOEFetchStatus.COMPLETE_SUCCESS.value,
        fetched.http_status,
        metrics,
        tuple(audit_items),
        tuple(errors),
        (
            ("official_id_strategy_count", unique_id_count),
            ("fallback_count", fallback_count),
            ("record_id_collision_count", collision_count),
        ),
        hash_stable if finalized else None,
    )


def _allowed_audit_item(
    item: BOEItem,
    decision: BOETerritorialDecision,
    record: Record,
    privacy: PrivacyDecision,
) -> BOEDryRunItemAudit:
    match_data: list[dict[str, str]] = []
    for match in decision.matches:
        reason = match.reason.value
        # Provincia exacta es una señal válida de inclusión, pero más amplia que
        # una coincidencia municipal y por ello se señala para revisión humana.
        audit_class = (
            BOEDryRunMatchAudit.SUSPICIOUS_MATCH
            if reason == "province_exact"
            else BOEDryRunMatchAudit.EXPECTED_MATCH
        )
        match_data.append(
            {
                "audit": audit_class.value,
                "reason": reason,
                "entity_code": match.entity_code,
                "entity_name": match.entity_name,
                "field": match.field.value,
                "matched_text": match.matched_text,
                "method": match.method,
            }
        )
    municipality = record.geography.municipality if record.geography is not None else None
    return BOEDryRunItemAudit(
        official_id=item.official_id,
        privacy_decision=privacy.decision,
        title=record.title,
        authority_name=record.authority.name,
        category=_enum_value(record.category),
        published_at=record.dates.published_at.isoformat() if record.dates.published_at else None,
        identity_strategy=_enum_value(record.technical.identity_strategy),
        geography_municipality=municipality,
        territorial_matches=tuple(match_data),
    )


def _blocked_audit_item(item: BOEItem, privacy: PrivacyDecision) -> BOEDryRunItemAudit:
    return BOEDryRunItemAudit(
        official_id=item.official_id,
        privacy_decision=privacy.decision,
        privacy_reasons=tuple(reason.to_dict() for reason in privacy.reasons),
    )


def _safe_official_id(item: BOEItem) -> str | None:
    value = getattr(item, "official_id", None)
    return value if isinstance(value, str) and value.startswith("BOE-") and len(value) <= 64 else None


def _enum_value(value: object) -> str:
    enum_value = getattr(value, "value", value)
    return str(enum_value)
