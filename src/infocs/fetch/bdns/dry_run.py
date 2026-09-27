"""Dry-run in-memory BDNS pipeline; deliberately has no persistence dependency."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum

from infocs.fetch.bdns.models import BDNSRequestStatus, BDNSSearchQuery
from infocs.fetch.bdns.normalize import (
    BDNSNormalizationError,
    BDNSTerritorialStatus,
    normalize_bdns_detail,
)
from infocs.fetch.bdns.publication import (
    BDNSPublicationPolicyError,
    BDNSMetadataPublicationDecisionType,
    evaluate_bdns_publication,
)
from infocs.fetch.bdns.transport import BDNSTransport
from infocs.finalize import finalize_record
from infocs.models import DataValidationError
from infocs.privacy import PrivacyDecisionType, PrivacyGate, PrivacyGateError
from infocs.publication.source_policy import SourcePublicationEligibilityType


class BDNSDryRunStatus(StrEnum):
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    PARTIAL = "partial"
    SOURCE_FAILURE = "source_failure"
    TERRITORIAL_CONTRACT_DRIFT = "territorial_contract_drift"


@dataclass(frozen=True, slots=True)
class BDNSDryRunMetrics:
    search_seen: int = 0
    detail_fetched: int = 0
    in_scope: int = 0
    out_of_scope: int = 0
    unresolved: int = 0
    finalized: int = 0
    privacy_allow: int = 0
    privacy_quarantine: int = 0
    privacy_reject: int = 0
    source_eligible: int = 0
    metadata_publishable: int = 0
    metadata_hold: int = 0
    errors: int = 0

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field.name} debe ser un entero no negativo.")

    def to_dict(self) -> dict[str, int]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


@dataclass(frozen=True, slots=True)
class BDNSDryRunReport:
    status: BDNSDryRunStatus
    metrics: BDNSDryRunMetrics
    request_count: int
    http_statuses: tuple[int, ...]
    error_stages: tuple[str, ...] = ()
    territorial_reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "metrics": self.metrics.to_dict(),
            "request_count": self.request_count,
            "http_statuses": list(self.http_statuses),
            "error_stages": list(self.error_stages),
            "territorial_reason_codes": list(self.territorial_reason_codes),
            "writes": 0,
        }


def run_bdns_dry_run(
    *,
    detected_at: datetime,
    last_checked_at: datetime,
    transport: BDNSTransport | None = None,
    privacy_gate: PrivacyGate | None = None,
    page_size: int = 3,
    max_details: int = 3,
) -> BDNSDryRunReport:
    """Consulta región BDNS 56, procesa como máximo tres detalles y no escribe.

    El cliente sólo recibe transporte y Privacy Gate; no admite Stores ni
    Review Queue. El reporte omite IDs, títulos, URLs, valores y cuerpos raw.
    """
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 3:
        raise ValueError("page_size debe estar entre 1 y 3 para el dry-run BDNS.")
    if isinstance(max_details, bool) or not isinstance(max_details, int) or not 1 <= max_details <= 3:
        raise ValueError("max_details debe estar entre 1 y 3 para el dry-run BDNS.")
    client = transport or BDNSTransport()
    gate = privacy_gate or PrivacyGate.default()
    counts = {field.name: 0 for field in fields(BDNSDryRunMetrics)}
    request_count = 0
    http_statuses: list[int] = []
    error_stages: list[str] = []
    territorial_reason_codes: list[str] = []

    request_count += 1
    try:
        search_result = client.search(
            BDNSSearchQuery(page=0, page_size=page_size, order="fechaRecepcion", direction="desc", region_ids=(56,))
        )
    except Exception:
        return _report(
            BDNSDryRunStatus.SOURCE_FAILURE, counts, request_count, http_statuses, ("search_transport",)
        )
    if search_result.http_status is not None:
        http_statuses.append(search_result.http_status)
    if search_result.status is BDNSRequestStatus.NO_RESULTS:
        return _report(BDNSDryRunStatus.NO_RESULTS, counts, request_count, http_statuses, ())
    if search_result.status is not BDNSRequestStatus.SUCCESS or search_result.payload is None:
        counts["errors"] += 1
        return _report(
            BDNSDryRunStatus.SOURCE_FAILURE,
            counts,
            request_count,
            http_statuses,
            ("search_" + _safe_reason(search_result.reason),),
        )

    summaries = search_result.payload.items
    counts["search_seen"] = len(summaries)
    if not summaries:
        return _report(BDNSDryRunStatus.NO_RESULTS, counts, request_count, http_statuses, ())

    for summary in summaries[:max_details]:
        request_count += 1
        try:
            detail_result = client.fetch_detail(summary.numero_convocatoria)
        except Exception:
            counts["errors"] += 1
            error_stages.append("detail_transport")
            continue
        if detail_result.http_status is not None:
            http_statuses.append(detail_result.http_status)
        if detail_result.status is not BDNSRequestStatus.SUCCESS or detail_result.payload is None:
            counts["errors"] += 1
            error_stages.append("detail_" + _safe_reason(detail_result.reason))
            continue

        counts["detail_fetched"] += 1
        try:
            normalized = normalize_bdns_detail(
                summary,
                detail_result.payload,
                detected_at=detected_at,
                last_checked_at=last_checked_at,
            )
        except BDNSNormalizationError:
            counts["errors"] += 1
            error_stages.append("normalize_contract")
            continue

        status = normalized.territorial_decision.status
        territorial_reason_codes.append(normalized.territorial_decision.reason_code)
        if status is BDNSTerritorialStatus.OUT_OF_SCOPE:
            counts["out_of_scope"] += 1
            error_stages.append("territorial_contract_drift")
            counts["errors"] += 1
            return _report(
                BDNSDryRunStatus.TERRITORIAL_CONTRACT_DRIFT,
                counts,
                request_count,
                http_statuses,
                tuple(error_stages),
                tuple(territorial_reason_codes),
            )
        if status is BDNSTerritorialStatus.UNRESOLVED:
            counts["unresolved"] += 1
            error_stages.append("territorial_contract_drift")
            counts["errors"] += 1
            return _report(
                BDNSDryRunStatus.TERRITORIAL_CONTRACT_DRIFT,
                counts,
                request_count,
                http_statuses,
                tuple(error_stages),
                tuple(territorial_reason_codes),
            )
        if normalized.candidate is None:
            counts["errors"] += 1
            error_stages.append("normalize_result_contract")
            continue
        counts["in_scope"] += 1

        try:
            record = finalize_record(normalized.candidate)
        except DataValidationError:
            counts["errors"] += 1
            error_stages.append("finalize_contract")
            continue
        counts["finalized"] += 1

        try:
            privacy = gate.evaluate(record)
        except PrivacyGateError:
            counts["errors"] += 1
            error_stages.append("privacy_gate")
            continue
        if privacy.decision is PrivacyDecisionType.ALLOW:
            counts["privacy_allow"] += 1
        elif privacy.decision is PrivacyDecisionType.QUARANTINE:
            counts["privacy_quarantine"] += 1
            continue
        elif privacy.decision is PrivacyDecisionType.REJECT:
            counts["privacy_reject"] += 1
            continue
        else:
            counts["errors"] += 1
            error_stages.append("privacy_decision_contract")
            continue

        try:
            publication = evaluate_bdns_publication(record, privacy)
        except BDNSPublicationPolicyError:
            counts["errors"] += 1
            error_stages.append("publication_policy")
            continue
        if (
            publication.source_eligibility is not None
            and publication.source_eligibility.decision is SourcePublicationEligibilityType.ELIGIBLE
        ):
            counts["source_eligible"] += 1
        if publication.metadata_publication is not None:
            if publication.metadata_publication.decision is BDNSMetadataPublicationDecisionType.PUBLISHABLE_METADATA:
                counts["metadata_publishable"] += 1
                break
            counts["metadata_hold"] += 1

    final_status = (
        BDNSDryRunStatus.PARTIAL
        if counts["errors"] and counts["detail_fetched"]
        else BDNSDryRunStatus.SOURCE_FAILURE
        if counts["errors"]
        else BDNSDryRunStatus.SUCCESS
    )
    return _report(
        final_status,
        counts,
        request_count,
        http_statuses,
        tuple(error_stages),
        tuple(territorial_reason_codes),
    )


def _safe_reason(reason: str | None) -> str:
    if isinstance(reason, str) and reason and all(character.isalnum() or character in "_-" for character in reason):
        return reason[:64]
    return "request_failure"


def _report(
    status: BDNSDryRunStatus,
    counts: dict[str, int],
    request_count: int,
    http_statuses: list[int],
    error_stages: tuple[str, ...],
    territorial_reason_codes: tuple[str, ...] = (),
) -> BDNSDryRunReport:
    return BDNSDryRunReport(
        status=status,
        metrics=BDNSDryRunMetrics(**counts),
        request_count=request_count,
        http_statuses=tuple(http_statuses),
        error_stages=error_stages,
        territorial_reason_codes=territorial_reason_codes,
    )
