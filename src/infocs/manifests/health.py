"""Source Health como proyección determinista y regenerable de Run Manifests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker

from infocs.manifests.model import ManifestValidationError, RunManifest, _canonical_timestamp


FAILURE_THRESHOLD = 3


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SourceHealth:
    source_id: str
    status: HealthStatus
    consecutive_failures: int
    last_run_id: str | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_error_code: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, HealthStatus):
            raise ManifestValidationError("Health status no está soportado.")
        if isinstance(self.consecutive_failures, bool) or not isinstance(self.consecutive_failures, int) or self.consecutive_failures < 0:
            raise ManifestValidationError("consecutive_failures debe ser un entero >= 0.")
        for name in ("last_attempt_at", "last_success_at", "updated_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _canonical_timestamp(value, name))
        if self.status is HealthStatus.UNKNOWN:
            if any((self.last_run_id, self.last_attempt_at, self.last_success_at, self.last_error_code, self.updated_at)) or self.consecutive_failures:
                raise ManifestValidationError("unknown no puede afirmar que haya habido ejecuciones.")
        elif not self.last_run_id or not self.last_attempt_at or not self.updated_at:
            raise ManifestValidationError("Health con ejecuciones requiere último run, intento y actualización.")
        if self.status is HealthStatus.FAILING and self.consecutive_failures < FAILURE_THRESHOLD:
            raise ManifestValidationError("failing requiere alcanzar el umbral v1.")
        if self.status is HealthStatus.HEALTHY and self.consecutive_failures != 0:
            raise ManifestValidationError("healthy requiere consecutive_failures = 0.")
        if self.status is HealthStatus.DEGRADED and self.consecutive_failures >= FAILURE_THRESHOLD:
            raise ManifestValidationError("degraded no puede alcanzar el umbral failing.")
        if self.last_success_at and self.updated_at and self.last_success_at > self.updated_at:
            raise ManifestValidationError("last_success_at no puede ser posterior a updated_at.")
        _validate_health_schema(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "source_id": self.source_id,
            "status": self.status.value,
            "consecutive_failures": self.consecutive_failures,
        }
        for field in ("last_run_id", "last_attempt_at", "last_success_at", "last_error_code", "updated_at"):
            candidate = getattr(self, field)
            if candidate is not None:
                value[field] = candidate
        return value

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SourceHealth":
        _validate_health_schema(payload)
        try:
            values = dict(payload)
            values["status"] = HealthStatus(values["status"])
            return cls(**values)
        except (TypeError, ValueError) as error:
            if isinstance(error, ManifestValidationError):
                raise
            raise ManifestValidationError("SourceHealth no cumple el contrato v1.") from error


def derive_source_health(
    manifests: Iterable[RunManifest],
    *,
    source_id: str,
) -> SourceHealth:
    """Deriva el estado usando el mismo resultado para cualquier orden de entrada."""
    items = tuple(manifests)
    if any(not isinstance(item, RunManifest) for item in items):
        raise ManifestValidationError("Health sólo puede derivarse de RunManifest validados.")
    if any(item.source_id != source_id for item in items):
        raise ManifestValidationError("No se pueden mezclar fuentes al derivar Health.")
    if not items:
        return SourceHealth(source_id=source_id, status=HealthStatus.UNKNOWN, consecutive_failures=0)

    ordered = tuple(sorted(items, key=lambda item: (item.finished_at, item.started_at, item.run_id)))
    latest = ordered[-1]
    consecutive_failures = 0
    for item in reversed(ordered):
        if item.status.value != "failed":
            break
        consecutive_failures += 1

    if latest.status.value in {"success", "no_publication"}:
        status = HealthStatus.HEALTHY
        consecutive_failures = 0
    elif consecutive_failures >= FAILURE_THRESHOLD:
        status = HealthStatus.FAILING
    else:
        status = HealthStatus.DEGRADED

    successes = [item for item in ordered if item.status.value in {"success", "no_publication"}]
    errors = [item.error_summary.error_code for item in ordered if item.error_summary is not None]
    return SourceHealth(
        source_id=source_id,
        status=status,
        consecutive_failures=consecutive_failures,
        last_run_id=latest.run_id,
        last_attempt_at=latest.started_at,
        last_success_at=successes[-1].finished_at if successes else None,
        last_error_code=errors[-1] if errors else None,
        # Derived as-of time, not the time this projection happened to be built.
        updated_at=latest.finished_at,
    )


def write_source_health(path: str | Path, health: SourceHealth) -> Path:
    """Materializa atómicamente una proyección Health regenerable como JSON."""
    if not isinstance(health, SourceHealth):
        raise ManifestValidationError("Sólo se puede materializar SourceHealth validado.")
    validated = SourceHealth.from_mapping(health.to_dict())
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        temporary = Path(name)
        payload = json.dumps(validated.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        SourceHealth.from_mapping(json.loads(temporary.read_text(encoding="utf-8")))
        os.replace(temporary, target)
        return target
    except Exception as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ManifestValidationError("No se pudo materializar SourceHealth de forma atómica.") from error


def _validate_health_schema(payload: Mapping[str, Any]) -> None:
    try:
        schema_path = Path(__file__).resolve().parents[3] / "schemas" / "source-health.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(dict(payload))
    except Exception as error:
        raise ManifestValidationError("SourceHealth no valida contra su JSON Schema.") from error
