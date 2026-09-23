"""Ejecución manual del pipeline BOE y persistencia de observabilidad."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable

from infocs.events import EventStore
from infocs.fetch.boe.ingest import (
    BOEIngestionMetrics,
    BOEIngestionResult,
    BOEIngestionStatus,
    ingest_boe_summary,
)
from infocs.fetch.boe.manifest import manifest_from_boe_result
from infocs.fetch.boe.models import BOEFetchResult, BOEFetchStatus
from infocs.fetch.boe.territorial import load_castellon_registry
from infocs.fetch.boe.transport import BOETransport
from infocs.manifests import (
    ManifestStore,
    RunStatus,
    SoftwareMetadata,
    derive_source_health,
    new_run_id,
    write_source_health,
)
from infocs.privacy import PrivacyGate
from infocs.publication.review import PublicationReviewConfig
from infocs.store import RecordStore


PROJECT_ROOT = Path(__file__).resolve().parents[4]
_INPUT_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


class BOERunnerError(RuntimeError):
    """Error operativo seguro del runner BOE."""


def parse_requested_date(value: str) -> date:
    """Valida estrictamente YYYY-MM-DD, sin aliases ni rangos."""
    if not isinstance(value, str) or not _INPUT_DATE.fullmatch(value):
        raise argparse.ArgumentTypeError("--date debe usar exactamente YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--date no es una fecha de calendario válida.") from error
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("--date debe usar exactamente YYYY-MM-DD.")
    return parsed


def run_boe_collection(
    requested_date: date,
    *,
    started_at: datetime,
    run_id: str,
    clock: Callable[[], datetime],
    transport: BOETransport | None = None,
    record_store: RecordStore | None = None,
    event_store: EventStore | None = None,
    manifest_store: ManifestStore | None = None,
    health_path: str | Path | None = None,
    review_config: PublicationReviewConfig | None = None,
    privacy_gate: PrivacyGate | None = None,
    software_metadata: SoftwareMetadata | None = None,
) -> BOEIngestionResult:
    """Ejecuta una fecha, finaliza Manifest y materializa Health derivado.

    ``started_at``, ``run_id`` y ``clock`` se inyectan para que la identidad y
    los timestamps sean explícitos y testables. El mismo ``started_at`` se
    asigna como detección/comprobación a todos los Records del run.
    """
    _validate_aware(started_at, "started_at")
    if not isinstance(requested_date, date) or isinstance(requested_date, datetime):
        raise BOERunnerError("requested_date debe ser una fecha explícita.")

    active_manifest_store = manifest_store or ManifestStore(PROJECT_ROOT / "data" / "manifests")
    active_health_path = Path(health_path) if health_path is not None else PROJECT_ROOT / "data" / "health" / "boe.json"
    active_software = software_metadata or SoftwareMetadata(
        collector_version="0.1.0",
        source_contract_version="1",
        git_commit_sha=os.environ.get("GITHUB_SHA") or None,
    )

    try:
        active_gate = privacy_gate or PrivacyGate.default()
        active_review = review_config or PublicationReviewConfig.from_file()
        active_review.validate()
        active_gate.validate()
        active_transport = transport or BOETransport()
        active_record_store = record_store or RecordStore(PROJECT_ROOT / "data" / "records", privacy_gate=active_gate)
        active_event_store = event_store or EventStore(PROJECT_ROOT / "data" / "events")
        fetched: BOEFetchResult = active_transport.fetch_daily_summary(requested_date)
        result = ingest_boe_summary(
            fetched,
            registry=load_castellon_registry(),
            store=active_record_store,
            event_store=active_event_store,
            detected_at=started_at,
            last_checked_at=started_at,
            publication_review_config=active_review,
            privacy_gate=active_gate,
        )
    except Exception:
        # El artefacto público no recibe mensajes de excepción ni contenido de
        # Records. La ejecución fallida queda observable con un código estable.
        result = BOEIngestionResult(
            status=BOEIngestionStatus.SOURCE_FAILURE,
            metrics=BOEIngestionMetrics(),
            error="pipeline_failure",
        )

    finished_at = clock()
    _validate_aware(finished_at, "finished_at")
    try:
        manifest = manifest_from_boe_result(
            result,
            requested_date=requested_date,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            software_metadata=active_software,
        )
        active_manifest_store.write(manifest)
        health = derive_source_health(active_manifest_store.list_source("boe"), source_id="boe")
        write_source_health(active_health_path, health)
    except Exception as error:
        raise BOERunnerError("No se pudo finalizar la observabilidad de la ejecución.") from error
    return result


def _validate_aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise BOERunnerError(f"{field} debe incluir zona horaria.")


def runner_exit_code(status: RunStatus) -> int:
    """Los runs failed finalizan observabilidad, pero deben fallar en Actions."""
    return 1 if status is RunStatus.FAILED else 0


def _utc_now() -> datetime:
    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ejecuta una fecha del sumario diario BOE.")
    parser.add_argument("--date", required=True, type=parse_requested_date, help="Fecha BOE YYYY-MM-DD")
    args = parser.parse_args(argv)

    started_at = _utc_now()
    run_id = new_run_id()
    try:
        result = run_boe_collection(
            args.date,
            started_at=started_at,
            run_id=run_id,
            clock=_utc_now,
        )
    except Exception:
        print(json.dumps({"run_id": run_id, "status": "failed", "error": "runner_failure"}), file=sys.stderr)
        return 1

    manifests = ManifestStore(PROJECT_ROOT / "data" / "manifests")
    manifest = manifests.get(run_id)
    if manifest is None:
        print(json.dumps({"run_id": run_id, "status": "failed", "error": "manifest_missing"}), file=sys.stderr)
        return 1
    print(json.dumps({
        "run_id": run_id,
        "source_id": "boe",
        "requested_date": args.date.isoformat(),
        "status": manifest.status.value,
        "metrics": manifest.metrics.to_dict(),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return runner_exit_code(manifest.status)


if __name__ == "__main__":  # pragma: no cover - exercised via CLI smoke tests
    raise SystemExit(main())
