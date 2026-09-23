"""Adaptador en memoria de resultados de ingesta BOE a RunManifest v1."""

from __future__ import annotations

from datetime import date, datetime

from infocs.fetch.boe.ingest import BOEIngestionResult, BOEIngestionStatus
from infocs.manifests.model import (
    CollectionMode,
    ErrorSummary,
    MANIFEST_VERSION,
    RunManifest,
    RunMetrics,
    RunStatus,
    RequestedScope,
    SoftwareMetadata,
)


BOE_MANIFEST_SOURCE_ID = "boe"
BOE_MANIFEST_COLLECTION_MODE = CollectionMode.INCREMENTAL_FEED


def manifest_from_boe_result(
    result: BOEIngestionResult,
    *,
    requested_date: date,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    software_metadata: SoftwareMetadata,
) -> RunManifest:
    """Construye un manifest sin red ni escritura, usando métricas ya agregadas.

    El resultado de ingesta no cuenta normalización/finalización por separado;
    en `complete_success`, el contrato fail-closed garantiza que todo `included`
    llegó a ambas etapas. Los errores de transporte se resumen con texto fijo:
    no se copia ``result.error`` ni una excepción al artefacto público.
    """
    if not isinstance(result, BOEIngestionResult):
        raise TypeError("Se requiere BOEIngestionResult.")
    if not isinstance(requested_date, date) or isinstance(requested_date, datetime):
        raise TypeError("requested_date debe ser datetime.date.")

    source_metrics = result.metrics
    event_counts = {"create": 0, "update": 0}
    for event in result.events:
        if event.type in event_counts:
            event_counts[event.type] += 1

    if result.status is BOEIngestionStatus.COMPLETE_SUCCESS:
        if result.error is not None:
            raise ValueError("complete_success no admite error en BOEIngestionResult.")
        status = RunStatus.SUCCESS
        error_summary = None
        errors = 0
    elif result.status is BOEIngestionStatus.NO_DAILY_PUBLICATION:
        if any(source_metrics.to_dict().values()) or result.events or result.operations or result.error is not None:
            raise ValueError("no_daily_publication debe tener métricas cero y no producir operaciones.")
        status = RunStatus.NO_PUBLICATION
        error_summary = None
        errors = 0
    else:
        status = RunStatus.FAILED
        error_summary = ErrorSummary(
            stage="transport",
            error_code=result.status.value,
            safe_message="La ejecución de la fuente no produjo un resultado utilizable.",
        )
        errors = 1

    if status is RunStatus.NO_PUBLICATION:
        metrics = RunMetrics()
    else:
        metrics = RunMetrics(
            seen=source_metrics.seen,
            included=source_metrics.included,
            excluded=source_metrics.excluded,
            normalized=source_metrics.included if status is RunStatus.SUCCESS else 0,
            finalized=source_metrics.included if status is RunStatus.SUCCESS else 0,
            privacy_allowed=source_metrics.privacy_allowed,
            privacy_quarantined=source_metrics.privacy_quarantined,
            privacy_rejected=source_metrics.privacy_rejected,
            publication_approved=source_metrics.publication_approved,
            publication_hold=source_metrics.publication_hold,
            publication_rejected=source_metrics.publication_rejected,
            created=source_metrics.created,
            updated=source_metrics.updated,
            unchanged=source_metrics.unchanged,
            events_created=event_counts["create"],
            events_updated=event_counts["update"],
            errors=errors,
        )
    return RunManifest(
        manifest_version=MANIFEST_VERSION,
        run_id=run_id,
        source_id=BOE_MANIFEST_SOURCE_ID,
        collection_mode=BOE_MANIFEST_COLLECTION_MODE,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        status=status,
        requested_scope=RequestedScope("date", requested_date.isoformat()),
        metrics=metrics,
        software_metadata=software_metadata,
        error_summary=error_summary,
    )
