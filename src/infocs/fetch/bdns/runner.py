"""Runner operativo BDNS v1: paginación acotada, Stores y observabilidad."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Callable

from infocs.events import EventStore
from infocs.fetch.bdns.ingest import (
    BDNS_ATTRIBUTION_PATH,
    BDNSIngestionMetrics,
    BDNSIngestionStatus,
    _attribution_preflight,
    ingest_bdns,
)
from infocs.fetch.bdns.models import (
    BDNSConvocatoriaDetail,
    BDNSConvocatoriaSummary,
    BDNSFetchResult,
    BDNSPage,
    BDNSRequestStatus,
    BDNSSearchQuery,
)
from infocs.fetch.bdns.transport import BDNSTransport
from infocs.manifests import (
    CollectionMode,
    ErrorSummary,
    ManifestStore,
    RequestedScope,
    RunManifest,
    RunMetrics,
    RunStatus,
    SoftwareMetadata,
    derive_source_health,
    new_run_id,
    write_source_health,
)
from infocs.privacy import PrivacyGate
from infocs.store import RecordStore


PROJECT_ROOT = Path(__file__).resolve().parents[4]
BDNS_REGION_ID = 56
BDNS_PAGE_SIZE = 50
BDNS_MAX_PAGES = 5
BDNS_MAX_DETAILS = 250
BDNS_TIME_BUDGET_SECONDS = 600
BDNS_DEFAULT_OVERLAP_DAYS = 14
BDNS_TEMPORAL_POLICY_VERSION = "fecha-recepcion-provisional-v1"
BDNS_INCREMENTAL_SCOPE_TYPE = "bdns_incremental_update"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


class BDNSRunMode(StrEnum):
    DISCOVERY = "discovery"
    INCREMENTAL_UPDATE = "incremental_update"
    COMPLETE_SCOPE = "complete_scope"


class BDNSRunnerStatus(StrEnum):
    COMPLETE_SUCCESS = "complete_success"
    NO_RESULTS = "no_results"
    PARTIAL_SUCCESS = "partial_success"
    SOURCE_FAILURE = "source_failure"
    TERRITORIAL_CONTRACT_DRIFT = "territorial_contract_drift"
    PERSISTENCE_BLOCKED = "persistence_blocked"


@dataclass(frozen=True, slots=True)
class BDNSRunnerMetrics:
    seen: int = 0
    included: int = 0
    excluded: int = 0
    normalized: int = 0
    finalized: int = 0
    privacy_allowed: int = 0
    privacy_quarantined: int = 0
    privacy_rejected: int = 0
    publication_approved: int = 0
    publication_hold: int = 0
    publication_rejected: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    events_created: int = 0
    events_updated: int = 0
    errors: int = 0

    def to_manifest_metrics(self) -> RunMetrics:
        return RunMetrics(**{field.name: getattr(self, field.name) for field in fields(self)})


@dataclass(frozen=True, slots=True)
class BDNSRunnerResult:
    run_id: str
    status: str
    metrics: BDNSRunnerMetrics
    request_count: int
    http_statuses: tuple[int, ...]
    error_code: str | None
    manifest: RunManifest

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "source_id": "bdns",
            "status": self.status,
            "metrics": self.metrics.to_manifest_metrics().to_dict(),
            "request_count": self.request_count,
            "http_statuses": list(self.http_statuses),
            "error_code": self.error_code,
        }


class _PrefetchedTransport:
    """Adapta un par search/detail ya recuperado al pipeline de ingesta común."""

    def __init__(self, summary: BDNSConvocatoriaSummary, detail: BDNSConvocatoriaDetail) -> None:
        self.summary = summary
        self.detail = detail

    def search(self, query: BDNSSearchQuery | None = None) -> BDNSFetchResult[BDNSPage]:
        page = BDNSPage((self.summary,), 0, 1, 0, 1, 1, 1, True, True, False)
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=page)

    def fetch_detail(self, numero_convocatoria: str) -> BDNSFetchResult[BDNSConvocatoriaDetail]:
        if numero_convocatoria != self.summary.numero_convocatoria:
            return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, 200, reason="identity_mismatch")
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, 200, payload=self.detail)


def resolve_incremental_window(
    manifests: tuple[RunManifest, ...],
    *,
    through_date: date,
    initial_from_date: date | None,
    overlap_days: int,
) -> tuple[date, date]:
    """Calcula una ventana desde el último incremental completo; partial no avanza."""
    if not isinstance(through_date, date) or isinstance(through_date, datetime):
        raise ValueError("through_date debe ser una fecha.")
    if isinstance(overlap_days, bool) or not isinstance(overlap_days, int) or overlap_days < 0:
        raise ValueError("overlap_days debe ser un entero no negativo.")
    completed = [
        item for item in manifests
        if item.source_id == "bdns"
        and item.status is RunStatus.SUCCESS
        and item.requested_scope.type == BDNS_INCREMENTAL_SCOPE_TYPE
    ]
    if not completed:
        if initial_from_date is None:
            raise ValueError("El primer incremental requiere --initial-from-date.")
        start_date = initial_from_date
    else:
        windows: list[tuple[date, RunManifest]] = []
        for item in completed:
            policy = re.search(r"(?:^|;)temporal_policy=([^;]+)(?:;|$)", item.requested_scope.value)
            if policy is None or policy.group(1) != BDNS_TEMPORAL_POLICY_VERSION:
                continue
            match = re.search(r"(?:^|;)to=(\d{4}-\d{2}-\d{2})(?:;|$)", item.requested_scope.value)
            if match is not None:
                windows.append((date.fromisoformat(match.group(1)), item))
        if not windows:
            if initial_from_date is None:
                raise ValueError("No hay checkpoint con la política temporal vigente; se requiere --initial-from-date.")
            start_date = initial_from_date
            if start_date > through_date:
                raise ValueError("El límite inicial incremental es posterior al final solicitado.")
            return start_date, through_date
        last_completed_to, _latest = max(windows, key=lambda pair: (pair[0], pair[1].finished_at, pair[1].run_id))
        start_date = last_completed_to - timedelta(days=overlap_days)
    if start_date > through_date:
        raise ValueError("El límite inicial incremental es posterior al final solicitado.")
    return start_date, through_date


def run_bdns_productive_collection(
    *,
    mode: str,
    from_date: date | None,
    through_date: date,
    started_at: datetime,
    run_id: str,
    clock: Callable[[], datetime],
    transport: BDNSTransport | None = None,
    record_store: RecordStore | None = None,
    event_store: EventStore | None = None,
    manifest_store: ManifestStore | None = None,
    health_path: str | Path | None = None,
    privacy_gate: PrivacyGate | None = None,
    software_metadata: SoftwareMetadata | None = None,
    overlap_days: int = BDNS_DEFAULT_OVERLAP_DAYS,
    max_pages: int = BDNS_MAX_PAGES,
    max_details: int = BDNS_MAX_DETAILS,
    time_budget_seconds: int = BDNS_TIME_BUDGET_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
) -> BDNSRunnerResult:
    """Ejecuta un scope temporal acotado y conserva resultados seguros de run.

    El runner no avanza un watermark persistido: el último Manifest incremental
    con status success es el checkpoint. Events son obligatorios para el run.
    """
    if mode not in {BDNSRunMode.DISCOVERY, BDNSRunMode.INCREMENTAL_UPDATE, BDNSRunMode.COMPLETE_SCOPE}:
        raise ValueError("mode no soportado.")
    _validate_aware(started_at, "started_at")
    if not isinstance(through_date, date) or isinstance(through_date, datetime):
        raise ValueError("through_date debe ser una fecha.")
    if mode == BDNSRunMode.INCREMENTAL_UPDATE:
        active_manifests = manifest_store or ManifestStore(PROJECT_ROOT / "data" / "manifests")
        from_date, through_date = resolve_incremental_window(
            active_manifests.list_source("bdns"),
            through_date=through_date,
            initial_from_date=from_date,
            overlap_days=overlap_days,
        )
    if not isinstance(from_date, date) or isinstance(from_date, datetime) or from_date > through_date:
        raise ValueError("Se requiere un rango de fechas válido y cerrado.")
    if isinstance(max_pages, bool) or not 1 <= max_pages <= BDNS_MAX_PAGES:
        raise ValueError(f"max_pages debe estar entre 1 y {BDNS_MAX_PAGES}.")
    if isinstance(max_details, bool) or not 1 <= max_details <= BDNS_MAX_DETAILS:
        raise ValueError(f"max_details debe estar entre 1 y {BDNS_MAX_DETAILS}.")
    if isinstance(time_budget_seconds, bool) or not 1 <= time_budget_seconds <= BDNS_TIME_BUDGET_SECONDS:
        raise ValueError(f"time_budget_seconds debe estar entre 1 y {BDNS_TIME_BUDGET_SECONDS}.")

    manifests = manifest_store or ManifestStore(PROJECT_ROOT / "data" / "manifests")
    health_target = Path(health_path) if health_path is not None else PROJECT_ROOT / "data" / "health" / "bdns.json"
    gate = privacy_gate or PrivacyGate.default()
    records = record_store or RecordStore(PROJECT_ROOT / "data" / "records", privacy_gate=gate)
    events = event_store or EventStore(PROJECT_ROOT / "data" / "events")
    client = transport or BDNSTransport()
    metadata = software_metadata or SoftwareMetadata(
        collector_version="0.2.0",
        source_contract_version="1",
        git_commit_sha=os.environ.get("GITHUB_SHA") or None,
    )
    collection_mode = CollectionMode.SNAPSHOT if mode == BDNSRunMode.COMPLETE_SCOPE else CollectionMode.INCREMENTAL_FEED
    scope = RequestedScope(
        type=f"bdns_{mode}",
        value=(
            f"region={BDNS_REGION_ID};from={from_date.isoformat()};to={through_date.isoformat()};"
            f"temporal_policy={BDNS_TEMPORAL_POLICY_VERSION}"
        ),
    )

    # Validar identidad, schema y ruta del Manifest antes de empezar cualquier
    # request o write de Record/Event.
    if not isinstance(metadata, SoftwareMetadata) or not isinstance(manifests, ManifestStore):
        raise ValueError("Manifest metadata/store preflight inválido.")
    probe_manifest = RunManifest(
        manifest_version="1.0",
        run_id=run_id,
        source_id="bdns",
        collection_mode=collection_mode,
        started_at=started_at.isoformat(),
        finished_at=started_at.isoformat(),
        status=RunStatus.SUCCESS,
        requested_scope=scope,
        metrics=RunMetrics(),
        software_metadata=metadata,
    )
    manifests.path_for(probe_manifest)
    if manifests.exists(run_id):
        raise ValueError("run_id ya existe; se requiere una identidad de ejecución nueva.")

    started_clock = monotonic()
    request_count = 0
    statuses: list[int] = []
    counts = {field.name: 0 for field in fields(BDNSRunnerMetrics)}
    details_attempted = 0
    result_status = BDNSRunnerStatus.SOURCE_FAILURE
    error_code = "runner_preflight_failed"
    try:
        gate.validate()
        from infocs.fetch.bdns.baseline import BDNSBaselineError, productive_hash_version
        try:
            productive_hash_version(records, events)
        except BDNSBaselineError as error:
            raise _RunFault(BDNSRunnerStatus.SOURCE_FAILURE, str(error)) from None
        if not _attribution_preflight(BDNS_ATTRIBUTION_PATH):
            raise RuntimeError("attribution_preflight_failed")
        if not isinstance(events, EventStore):
            raise RuntimeError("event_store_required")
        if not isinstance(records, RecordStore):
            raise RuntimeError("record_store_required")
        if not isinstance(manifests, ManifestStore):
            raise RuntimeError("manifest_store_required")
        initial_query = _query(page=0, from_date=from_date, through_date=through_date)
        request_count += 1
        first_result = client.search(initial_query)
        _append_status(statuses, first_result)
        first_page = first_result.payload
        if first_result.status not in {BDNSRequestStatus.SUCCESS, BDNSRequestStatus.NO_RESULTS} or first_page is None:
            raise _RunFault(BDNSRunnerStatus.SOURCE_FAILURE, "search_failure")
        if not _page_contract_valid(first_page, expected_page=0, page_size=BDNS_PAGE_SIZE):
            raise _RunFault(BDNSRunnerStatus.SOURCE_FAILURE, "page_contract_invalid")
        total_pages = first_page.total_pages
        total_elements = first_page.total_elements
        if total_pages is None or total_elements is None:
            raise _RunFault(BDNSRunnerStatus.SOURCE_FAILURE, "page_totals_missing")
        if total_elements == 0:
            if total_pages != 0 or first_page.items:
                raise _RunFault(BDNSRunnerStatus.SOURCE_FAILURE, "page_totals_inconsistent")
            if _budget_exhausted(started_clock, monotonic, time_budget_seconds):
                raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "run_budget_exhausted")
            request_count += 1
            control = client.search(initial_query)
            _append_status(statuses, control)
            control_page = control.payload
            if (
                control.status not in {BDNSRequestStatus.SUCCESS, BDNSRequestStatus.NO_RESULTS}
                or control_page is None
                or not _page_contract_valid(control_page, expected_page=0, page_size=BDNS_PAGE_SIZE)
                or control_page.total_pages != 0
                or control_page.total_elements != 0
                or control_page.items
            ):
                raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "scope_drift")
            if _budget_exhausted(started_clock, monotonic, time_budget_seconds):
                raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "run_budget_exhausted")
            result_status = BDNSRunnerStatus.NO_RESULTS
            error_code = None
        else:
            if total_pages < 1 or not first_page.items:
                raise _RunFault(BDNSRunnerStatus.SOURCE_FAILURE, "page_totals_inconsistent")
            seen_codes: set[str] = set()
            initial_codes = tuple(item.numero_convocatoria for item in first_page.items)
            result_pages = min(total_pages, max_pages)
            for page_number in range(result_pages):
                if _budget_exhausted(started_clock, monotonic, time_budget_seconds):
                    raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "run_budget_exhausted")
                if page_number > 0:
                    request_count += 1
                if page_number == 0:
                    page = first_page
                else:
                    page_result = client.search(_query(page=page_number, from_date=from_date, through_date=through_date))
                    _append_status(statuses, page_result)
                    if page_result.status is not BDNSRequestStatus.SUCCESS or page_result.payload is None:
                        raise _RunFault(BDNSRunnerStatus.SOURCE_FAILURE, "search_failure")
                    page = page_result.payload
                if not _page_contract_valid(page, expected_page=page_number, page_size=BDNS_PAGE_SIZE):
                    raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "scope_drift")
                if page.total_pages != total_pages or page.total_elements != total_elements:
                    raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "scope_drift")
                counts["seen"] += len(page.items)
                for summary in page.items:
                    if summary.numero_convocatoria in seen_codes:
                        raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "duplicate_search_identity")
                    seen_codes.add(summary.numero_convocatoria)
                    if details_attempted >= max_details:
                        raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "run_budget_exhausted")
                    if _budget_exhausted(started_clock, monotonic, time_budget_seconds):
                        raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "run_budget_exhausted")
                    details_attempted += 1
                    request_count += 1
                    detail_result = client.fetch_detail(summary.numero_convocatoria)
                    _append_status(statuses, detail_result)
                    if detail_result.status is not BDNSRequestStatus.SUCCESS or detail_result.payload is None:
                        counts["errors"] += 1
                        raise _RunFault(BDNSRunnerStatus.SOURCE_FAILURE, "detail_failure")
                    item_result = ingest_bdns(
                        record_store=records,
                        started_at=started_at,
                        transport=_PrefetchedTransport(summary, detail_result.payload),
                        privacy_gate=gate,
                        event_store=events,
                        clock=clock,
                        page_size=1,
                        max_details=1,
                        attribution_path=BDNS_ATTRIBUTION_PATH,
                    )
                    _merge_ingestion_metrics(counts, item_result.metrics)
                    if item_result.status is BDNSIngestionStatus.TERRITORIAL_CONTRACT_DRIFT:
                        raise _RunFault(BDNSRunnerStatus.TERRITORIAL_CONTRACT_DRIFT, "territorial_contract_drift")
                    if item_result.status is BDNSIngestionStatus.PERSISTENCE_BLOCKED:
                        raise _RunFault(BDNSRunnerStatus.PERSISTENCE_BLOCKED, item_result.safe_reason or "persistence_blocked")
                    if item_result.status is BDNSIngestionStatus.SOURCE_FAILURE or item_result.metrics.errors:
                        raise _RunFault(BDNSRunnerStatus.SOURCE_FAILURE, "item_ingestion_failure")

            if total_pages > max_pages or total_elements > max_details:
                raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "run_budget_exhausted")
            if counts["seen"] != total_elements:
                raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "scope_count_mismatch")
            if _budget_exhausted(started_clock, monotonic, time_budget_seconds):
                raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "run_budget_exhausted")
            request_count += 1
            control = client.search(initial_query)
            _append_status(statuses, control)
            control_page = control.payload
            if (
                control.status not in {BDNSRequestStatus.SUCCESS, BDNSRequestStatus.NO_RESULTS}
                or control_page is None
                or control_page.total_pages != total_pages
                or control_page.total_elements != total_elements
                or not _page_contract_valid(control_page, expected_page=0, page_size=BDNS_PAGE_SIZE)
                or tuple(item.numero_convocatoria for item in control_page.items) != initial_codes
            ):
                raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "scope_drift")
            if _budget_exhausted(started_clock, monotonic, time_budget_seconds):
                raise _RunFault(BDNSRunnerStatus.PARTIAL_SUCCESS, "run_budget_exhausted")
            result_status = BDNSRunnerStatus.COMPLETE_SUCCESS
            error_code = None
    except _RunFault as fault:
        result_status = fault.status
        error_code = fault.code
        counts["errors"] += 1
    except Exception:
        result_status = BDNSRunnerStatus.SOURCE_FAILURE
        error_code = "runner_failure"
        counts["errors"] += 1

    finished_at = clock()
    _validate_aware(finished_at, "finished_at")
    if finished_at < started_at:
        finished_at = started_at
    metrics = BDNSRunnerMetrics(**counts)
    if result_status in {BDNSRunnerStatus.COMPLETE_SUCCESS, BDNSRunnerStatus.NO_RESULTS}:
        manifest_status = RunStatus.SUCCESS
        summary = None
        manifest_errors = 0
    elif result_status is BDNSRunnerStatus.PARTIAL_SUCCESS:
        manifest_status = RunStatus.PARTIAL
        summary = ErrorSummary("run", error_code or "run_incomplete", "La ejecución terminó parcialmente.")
        manifest_errors = max(1, metrics.errors)
    else:
        manifest_status = RunStatus.FAILED
        summary = ErrorSummary("run", _safe_code(error_code), "El procesamiento de la fuente falló antes de completar el lote.")
        manifest_errors = max(1, metrics.errors)
    manifest_metrics = metrics.to_manifest_metrics()
    if manifest_errors != manifest_metrics.errors:
        manifest_metrics = RunMetrics(**{**manifest_metrics.to_dict(), "errors": manifest_errors})
    manifest = RunManifest(
        manifest_version="1.0",
        run_id=run_id,
        source_id="bdns",
        collection_mode=collection_mode,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        status=manifest_status,
        requested_scope=scope,
        metrics=manifest_metrics,
        software_metadata=metadata,
        error_summary=summary,
    )
    manifests.write(manifest)
    health = derive_source_health(manifests.list_source("bdns"), source_id="bdns")
    write_source_health(health_target, health)
    return BDNSRunnerResult(
        run_id=run_id,
        status=str(result_status),
        metrics=metrics,
        request_count=request_count,
        http_statuses=tuple(statuses),
        error_code=error_code,
        manifest=manifest,
    )


class _RunFault(RuntimeError):
    def __init__(self, status: str, code: str) -> None:
        self.status = status
        self.code = code


class _RunnerArgumentParser(argparse.ArgumentParser):
    """Mantiene el código de salida OPS-C para invocaciones inválidas."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _query(*, page: int, from_date: date, through_date: date) -> BDNSSearchQuery:
    return BDNSSearchQuery(
        page=page,
        page_size=BDNS_PAGE_SIZE,
        order="fechaRecepcion",
        direction="desc",
        region_ids=(BDNS_REGION_ID,),
        date_from=from_date,
        date_to=through_date,
    )


def _page_contract_valid(page: BDNSPage, *, expected_page: int, page_size: int) -> bool:
    if not isinstance(page, BDNSPage) or page.page_number != expected_page or page.page_size != page_size:
        return False
    if page.total_pages is None or page.total_elements is None or page.total_pages < 0 or page.total_elements < 0:
        return False
    count = len(page.items)
    expected_offset = expected_page * page_size
    if page.offset != expected_offset or page.number_of_elements != count:
        return False
    if page.first is not (expected_page == 0):
        return False
    expected_last = expected_page == (page.total_pages - 1 if page.total_pages else 0)
    if page.last is not expected_last:
        return False
    if page.empty is not (count == 0):
        return False
    expected_total_pages = (page.total_elements + page_size - 1) // page_size
    if page.total_pages != expected_total_pages:
        return False
    expected_count = max(0, min(page_size, page.total_elements - expected_offset))
    if count != expected_count:
        return False
    if count > page_size or count == 0 and page.total_elements > 0:
        return False
    return True


def _append_status(statuses: list[int], result) -> None:
    if result.http_status is not None:
        statuses.append(result.http_status)


def _merge_ingestion_metrics(target: dict[str, int], source: BDNSIngestionMetrics) -> None:
    mapping = {
        "included": "in_scope",
        "normalized": "in_scope",
        "finalized": "finalized",
        "privacy_allowed": "privacy_allow",
        "privacy_quarantined": "privacy_quarantine",
        "privacy_rejected": "privacy_reject",
        "publication_approved": "metadata_publishable",
        "publication_hold": "metadata_hold",
        "created": "records_created",
        "updated": "records_updated",
        "unchanged": "records_unchanged",
        "events_created": "events_created",
        "events_updated": "events_updated",
    }
    for destination, source_name in mapping.items():
        target[destination] += getattr(source, source_name)
    target["errors"] += source.errors


def _budget_exhausted(started: float, monotonic: Callable[[], float], limit: int) -> bool:
    return monotonic() - started >= limit


def _safe_code(value: str | None) -> str:
    code = re.sub(r"[^a-z0-9_.-]+", "_", (value or "runner_failure").lower()).strip("_")
    return code[:64] or "runner_failure"


def _validate_aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} debe incluir zona horaria.")


def runner_exit_code(status: str) -> int:
    """Mapea el resultado operativo a un código estable para invocadores CI."""
    try:
        normalized = BDNSRunnerStatus(status)
    except ValueError:
        return 1
    if normalized in {BDNSRunnerStatus.COMPLETE_SUCCESS, BDNSRunnerStatus.NO_RESULTS}:
        return 0
    if normalized is BDNSRunnerStatus.PARTIAL_SUCCESS:
        return 2
    return 1


def _parse_date(value: str) -> date:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("La fecha debe usar YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("La fecha no es válida.") from error


def main(argv: list[str] | None = None) -> int:
    parser = _RunnerArgumentParser(description="Ejecuta un scope BDNS Castellón con límites v1.")
    parser.add_argument("--mode", required=True, choices=(BDNSRunMode.DISCOVERY, BDNSRunMode.INCREMENTAL_UPDATE, BDNSRunMode.COMPLETE_SCOPE))
    parser.add_argument("--from-date", type=_parse_date)
    parser.add_argument("--initial-from-date", type=_parse_date)
    parser.add_argument("--through-date", type=_parse_date, required=True)
    parser.add_argument("--overlap-days", type=int, default=BDNS_DEFAULT_OVERLAP_DAYS)
    parser.add_argument("--max-pages", type=int, default=BDNS_MAX_PAGES)
    parser.add_argument("--max-details", type=int, default=BDNS_MAX_DETAILS)
    args = parser.parse_args(argv)
    if args.mode != BDNSRunMode.INCREMENTAL_UPDATE and args.from_date is None:
        parser.error("--from-date es obligatorio salvo para incremental_update.")
    start = datetime.now(UTC)
    run_id = new_run_id()
    try:
        result = run_bdns_productive_collection(
            mode=args.mode,
            from_date=args.initial_from_date if args.mode == BDNSRunMode.INCREMENTAL_UPDATE else args.from_date,
            through_date=args.through_date,
            started_at=start,
            run_id=run_id,
            clock=lambda: datetime.now(UTC),
            overlap_days=args.overlap_days,
            max_pages=args.max_pages,
            max_details=args.max_details,
        )
    except Exception:
        print(json.dumps({"run_id": run_id, "source_id": "bdns", "status": "failed", "error_code": "runner_failure"}), file=sys.stderr)
        return 1
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return runner_exit_code(result.status)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
