"""Barrera offline de ingestión BOP anterior a cualquier persistencia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re

from infocs.fetch.bop_castellon.models import BOPFetchResult, BOPFetchStatus
from infocs.fetch.bop_castellon.normalize import normalize_bop_announcement
from infocs.fetch.bop_castellon.publication import evaluate_bop_publication
from infocs.finalize import finalize_record
from infocs.privacy import PrivacyDecisionType, PrivacyGate
from infocs.publication import SourcePublicationEligibilityType


class BOPIngestionStatus(StrEnum):
    COMPLETE_SUCCESS = "complete_success"
    NO_PUBLICATION = "no_publication"
    INVALID_REQUEST = "invalid_request"
    SOURCE_FAILURE = "source_failure"


@dataclass(frozen=True, slots=True)
class BOPIngestionMetrics:
    """Contadores agregados; nunca incluyen metadatos de un anuncio."""

    seen: int = 0
    normalized: int = 0
    finalized: int = 0
    privacy_allow: int = 0
    privacy_quarantine: int = 0
    privacy_reject: int = 0
    source_hold: int = 0
    persistence_blocked: int = 0
    records_written: int = 0
    events_written: int = 0
    manual_reviews: int = 0
    review_queue_items: int = 0
    errors: int = 0

    def __post_init__(self) -> None:
        for name, value in self.to_dict().items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"La métrica {name} debe ser un entero >= 0.")

    def to_dict(self) -> dict[str, int]:
        return {
            "seen": self.seen,
            "normalized": self.normalized,
            "finalized": self.finalized,
            "privacy_allow": self.privacy_allow,
            "privacy_quarantine": self.privacy_quarantine,
            "privacy_reject": self.privacy_reject,
            "source_hold": self.source_hold,
            "persistence_blocked": self.persistence_blocked,
            "records_written": self.records_written,
            "events_written": self.events_written,
            "manual_reviews": self.manual_reviews,
            "review_queue_items": self.review_queue_items,
            "errors": self.errors,
        }


@dataclass(frozen=True, slots=True)
class BOPIngestionResult:
    """Resumen seguro de una ejecución; deliberadamente no expone Records."""

    status: BOPIngestionStatus
    metrics: BOPIngestionMetrics
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, BOPIngestionStatus) or not isinstance(self.metrics, BOPIngestionMetrics):
            raise ValueError("El resultado de ingestión BOP no es válido.")
        if self.reason_code is not None and not re.fullmatch(
            r"(?:invalid_request|source_failure|pipeline_failure|reuse_policy_unresolved)",
            self.reason_code,
        ):
            raise ValueError("reason_code no es un código BOP seguro conocido.")
        if self.metrics.records_written or self.metrics.events_written or self.metrics.manual_reviews or self.metrics.review_queue_items:
            raise ValueError("La barrera BOP v1 no permite escritura ni revisión individual.")
        if self.status is BOPIngestionStatus.COMPLETE_SUCCESS:
            if self.metrics.errors or not (
                self.metrics.seen == self.metrics.normalized == self.metrics.finalized
            ):
                raise ValueError("complete_success requiere normalización y finalización completas.")
            if self.metrics.privacy_allow + self.metrics.privacy_quarantine + self.metrics.privacy_reject != self.metrics.finalized:
                raise ValueError("Las decisiones de privacidad deben cubrir todos los Records finalizados.")
            if self.metrics.source_hold != self.metrics.privacy_allow:
                raise ValueError("La política BOP vigente debe retener cada Record con Privacy ALLOW.")
            if self.metrics.persistence_blocked != self.metrics.finalized:
                raise ValueError("La barrera debe impedir persistir todos los Records del lote.")
            expected_reason = "reuse_policy_unresolved" if self.metrics.source_hold else None
            if self.reason_code != expected_reason:
                raise ValueError("reason_code debe reflejar el hold source-wide agregado.")
        elif self.status is BOPIngestionStatus.NO_PUBLICATION:
            if any(self.metrics.to_dict().values()) or self.reason_code is not None:
                raise ValueError("no_publication requiere métricas cero y sin motivo de bloqueo.")
        elif self.metrics.errors < 1:
            raise ValueError("Un resultado de fallo requiere al menos un error agregado.")

    @property
    def technical_success(self) -> bool:
        return self.status in {BOPIngestionStatus.COMPLETE_SUCCESS, BOPIngestionStatus.NO_PUBLICATION}

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "status": self.status.value,
            "technical_success": self.technical_success,
            "metrics": self.metrics.to_dict(),
        }
        if self.reason_code is not None:
            result["reason_code"] = self.reason_code
        return result


def ingest_bop_fetch_result(
    fetch_result: BOPFetchResult,
    *,
    detected_at: datetime,
    last_checked_at: datetime,
    privacy_gate: PrivacyGate | None = None,
) -> BOPIngestionResult:
    """Normaliza, finaliza y evalúa gates; no recibe ni invoca stores.

    El diseño de la interfaz impide que esta fase pueda escribir Records,
    Events, tareas de revisión o artefactos de observabilidad.
    """
    if not isinstance(fetch_result, BOPFetchResult):
        raise TypeError("Se requiere BOPFetchResult.")
    if fetch_result.status is BOPFetchStatus.NO_PUBLICATION:
        return BOPIngestionResult(BOPIngestionStatus.NO_PUBLICATION, BOPIngestionMetrics())
    if fetch_result.status is BOPFetchStatus.INVALID_REQUEST:
        return _failed_result(BOPIngestionStatus.INVALID_REQUEST, "invalid_request")
    if fetch_result.status is BOPFetchStatus.SOURCE_FAILURE:
        return _failed_result(BOPIngestionStatus.SOURCE_FAILURE, "source_failure")
    if fetch_result.status is not BOPFetchStatus.COMPLETE_SUCCESS or fetch_result.issue is None:
        return _failed_result(BOPIngestionStatus.SOURCE_FAILURE, "pipeline_failure")

    announcements = fetch_result.issue.announcements
    counts = {
        "seen": len(announcements),
        "normalized": 0,
        "finalized": 0,
        "privacy_allow": 0,
        "privacy_quarantine": 0,
        "privacy_reject": 0,
        "source_hold": 0,
        "persistence_blocked": 0,
        "records_written": 0,
        "events_written": 0,
        "manual_reviews": 0,
        "review_queue_items": 0,
        "errors": 0,
    }
    if not announcements:
        return _failed_result(BOPIngestionStatus.SOURCE_FAILURE, "pipeline_failure", seen=0)

    gate = privacy_gate if privacy_gate is not None else PrivacyGate.default()
    try:
        gate.validate()
        for announcement in announcements:
            candidate = normalize_bop_announcement(
                fetch_result.issue,
                announcement,
                detected_at=detected_at,
                last_checked_at=last_checked_at,
            )
            counts["normalized"] += 1
            record = finalize_record(candidate)
            counts["finalized"] += 1

            privacy = gate.evaluate(record)
            evaluation = evaluate_bop_publication(record, privacy)
            if privacy.decision is PrivacyDecisionType.ALLOW:
                counts["privacy_allow"] += 1
                if (
                    evaluation.source_eligibility is not None
                    and evaluation.source_eligibility.decision is SourcePublicationEligibilityType.HOLD
                ):
                    counts["source_hold"] += 1
            elif privacy.decision is PrivacyDecisionType.QUARANTINE:
                counts["privacy_quarantine"] += 1
            elif privacy.decision is PrivacyDecisionType.REJECT:
                counts["privacy_reject"] += 1
            else:  # pragma: no cover - enum exhaustiveness guard
                raise ValueError("privacy_decision_invalid")

        if counts["source_hold"] != counts["privacy_allow"]:
            # La política BOP activa debe bloquear cada ALLOW source-wide.
            raise ValueError("source_eligibility_contract_invalid")
        counts["persistence_blocked"] = counts["finalized"]
        metrics = BOPIngestionMetrics(**counts)
        reason = "reuse_policy_unresolved" if counts["source_hold"] else None
        return BOPIngestionResult(BOPIngestionStatus.COMPLETE_SUCCESS, metrics, reason)
    except Exception:
        # No propagar excepciones que puedan incluir texto o valores del anuncio.
        counts["errors"] = 1
        return BOPIngestionResult(
            BOPIngestionStatus.SOURCE_FAILURE,
            BOPIngestionMetrics(**counts),
            "pipeline_failure",
        )


def _failed_result(
    status: BOPIngestionStatus,
    reason_code: str,
    *,
    seen: int = 0,
) -> BOPIngestionResult:
    return BOPIngestionResult(
        status,
        BOPIngestionMetrics(seen=seen, errors=1),
        reason_code,
    )
