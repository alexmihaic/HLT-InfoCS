"""Modelos canónicos de ejecución y métricas, sin I/O ni reloj implícito."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
from pathlib import Path
import re
from typing import Any, Mapping
import uuid

from jsonschema import Draft202012Validator, FormatChecker


MANIFEST_VERSION = "1.0"
_SOURCE_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_CODE_RE = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_GIT_SHA_RE = re.compile(r"[a-fA-F0-9]{40,64}\Z")
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,79}\Z")
_SAFE_ERROR_MESSAGES = frozenset({
    "La ejecución de la fuente no produjo un resultado utilizable.",
    "La ejecución terminó parcialmente.",
    "El procesamiento de la fuente falló antes de completar el lote.",
})
_METRIC_NAMES = (
    "seen", "included", "excluded", "normalized", "finalized",
    "privacy_allowed", "privacy_quarantined", "privacy_rejected",
    "publication_approved", "publication_hold", "publication_rejected",
    "created", "updated", "unchanged", "events_created", "events_updated",
    "errors",
)


class ManifestValidationError(ValueError):
    """Run Manifest inválido o incompatible con el contrato v1."""


class CollectionMode(StrEnum):
    INCREMENTAL_FEED = "incremental_feed"
    SNAPSHOT = "snapshot"


class RunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NO_PUBLICATION = "no_publication"


def new_run_id() -> str:
    """Genera al inicio de cada ejecución una identidad de ocurrencia UUIDv4."""
    return f"run-v1-{uuid.uuid4()}"


@dataclass(frozen=True, slots=True)
class RequestedScope:
    type: str
    value: str

    def __post_init__(self) -> None:
        if not _CODE_RE.fullmatch(self.type) or not _non_empty(self.value):
            raise ManifestValidationError("requested_scope requiere type y value no vacíos.")
        if len(self.value) > 160 or any(ord(char) < 32 for char in self.value) or "/" in self.value or "\\" in self.value:
            raise ManifestValidationError("requested_scope.value debe ser breve y no contener paths ni controles.")
        if self.type == "date":
            try:
                if datetime.strptime(self.value, "%Y-%m-%d").date().isoformat() != self.value:
                    raise ValueError
            except ValueError as error:
                raise ManifestValidationError("El scope de tipo date debe usar YYYY-MM-DD.") from error

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "value": self.value}


@dataclass(frozen=True, slots=True)
class RunMetrics:
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

    def __post_init__(self) -> None:
        for name in _METRIC_NAMES:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ManifestValidationError(f"La métrica {name} debe ser un entero >= 0.")

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in _METRIC_NAMES}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RunMetrics":
        if not isinstance(value, Mapping) or set(value) != set(_METRIC_NAMES):
            raise ManifestValidationError("metrics debe contener exactamente las métricas v1.")
        try:
            return cls(**dict(value))
        except TypeError as error:
            raise ManifestValidationError("metrics no cumple el contrato v1.") from error


@dataclass(frozen=True, slots=True)
class ErrorSummary:
    stage: str
    error_code: str
    safe_message: str

    def __post_init__(self) -> None:
        if not _CODE_RE.fullmatch(self.stage) or not _CODE_RE.fullmatch(self.error_code):
            raise ManifestValidationError("stage y error_code deben ser códigos estables en minúsculas.")
        if (
            not _non_empty(self.safe_message)
            or self.safe_message not in _SAFE_ERROR_MESSAGES
        ):
            raise ManifestValidationError("safe_message debe usar una plantilla pública v1 permitida.")

    def to_dict(self) -> dict[str, str]:
        return {"stage": self.stage, "error_code": self.error_code, "safe_message": self.safe_message}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ErrorSummary":
        if not isinstance(value, Mapping) or set(value) != {"stage", "error_code", "safe_message"}:
            raise ManifestValidationError("error_summary no cumple el contrato cerrado.")
        try:
            return cls(**dict(value))
        except (TypeError, ValueError) as error:
            raise ManifestValidationError("error_summary no es válido.") from error


@dataclass(frozen=True, slots=True)
class SoftwareMetadata:
    collector_version: str
    source_contract_version: str | None = None
    git_commit_sha: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.collector_version, str) or not _VERSION_RE.fullmatch(self.collector_version):
            raise ManifestValidationError("collector_version debe ser una versión acotada sin paths.")
        if self.source_contract_version is not None and (
            not isinstance(self.source_contract_version, str)
            or not _VERSION_RE.fullmatch(self.source_contract_version)
        ):
            raise ManifestValidationError("source_contract_version debe ser una versión acotada sin paths.")
        if self.git_commit_sha is not None and not _GIT_SHA_RE.fullmatch(self.git_commit_sha):
            raise ManifestValidationError("git_commit_sha debe ser un SHA hexadecimal de 40 a 64 caracteres.")

    def to_dict(self) -> dict[str, str]:
        value = {"collector_version": self.collector_version}
        if self.source_contract_version is not None:
            value["source_contract_version"] = self.source_contract_version
        if self.git_commit_sha is not None:
            value["git_commit_sha"] = self.git_commit_sha.lower()
        return value

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SoftwareMetadata":
        allowed = {"collector_version", "source_contract_version", "git_commit_sha"}
        if not isinstance(value, Mapping) or not {"collector_version"} <= set(value) or set(value) - allowed:
            raise ManifestValidationError("software_metadata no cumple el contrato cerrado.")
        try:
            return cls(**dict(value))
        except (TypeError, ValueError) as error:
            raise ManifestValidationError("software_metadata no es válido.") from error


@dataclass(frozen=True, slots=True)
class RunManifest:
    manifest_version: str
    run_id: str
    source_id: str
    collection_mode: CollectionMode
    started_at: str
    finished_at: str
    status: RunStatus
    requested_scope: RequestedScope
    metrics: RunMetrics
    software_metadata: SoftwareMetadata
    error_summary: ErrorSummary | None = None

    def __post_init__(self) -> None:
        if self.manifest_version != MANIFEST_VERSION:
            raise ManifestValidationError("manifest_version debe ser 1.0.")
        if not isinstance(self.run_id, str) or not self.run_id.startswith("run-v1-"):
            raise ManifestValidationError("run_id debe tener prefijo run-v1-.")
        try:
            raw_uuid = self.run_id.removeprefix("run-v1-")
            if str(uuid.UUID(raw_uuid)) != raw_uuid:
                raise ValueError
        except (ValueError, AttributeError) as error:
            raise ManifestValidationError("run_id debe contener un UUID canónico.") from error
        if not _SOURCE_ID_RE.fullmatch(self.source_id):
            raise ManifestValidationError("source_id no es válido.")
        if not isinstance(self.collection_mode, CollectionMode) or not isinstance(self.status, RunStatus):
            raise ManifestValidationError("collection_mode o status no están soportados.")
        started = _canonical_timestamp(self.started_at, "started_at")
        finished = _canonical_timestamp(self.finished_at, "finished_at")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "finished_at", finished)
        if _parse_timestamp(finished) < _parse_timestamp(started):
            raise ManifestValidationError("finished_at no puede preceder a started_at.")
        if not isinstance(self.requested_scope, RequestedScope) or not isinstance(self.metrics, RunMetrics):
            raise ManifestValidationError("requested_scope y metrics deben ser modelos v1.")
        if not isinstance(self.software_metadata, SoftwareMetadata):
            raise ManifestValidationError("software_metadata debe ser un modelo v1.")
        if self.error_summary is not None and not isinstance(self.error_summary, ErrorSummary):
            raise ManifestValidationError("error_summary debe ser un modelo v1.")
        _validate_invariants(self.status, self.metrics, self.error_summary)
        _validate_schema(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "manifest_version": self.manifest_version,
            "run_id": self.run_id,
            "source_id": self.source_id,
            "collection_mode": self.collection_mode.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status.value,
            "requested_scope": self.requested_scope.to_dict(),
            "metrics": self.metrics.to_dict(),
            "software_metadata": self.software_metadata.to_dict(),
        }
        if self.error_summary is not None:
            payload["error_summary"] = self.error_summary.to_dict()
        return payload

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RunManifest":
        _validate_schema(payload)
        try:
            return cls(
                manifest_version=payload["manifest_version"],
                run_id=payload["run_id"],
                source_id=payload["source_id"],
                collection_mode=CollectionMode(payload["collection_mode"]),
                started_at=payload["started_at"],
                finished_at=payload["finished_at"],
                status=RunStatus(payload["status"]),
                requested_scope=RequestedScope(**payload["requested_scope"]),
                metrics=RunMetrics.from_mapping(payload["metrics"]),
                software_metadata=SoftwareMetadata.from_mapping(payload["software_metadata"]),
                error_summary=(ErrorSummary.from_mapping(payload["error_summary"]) if "error_summary" in payload else None),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ManifestValidationError):
                raise
            raise ManifestValidationError("El RunManifest no cumple el contrato v1.") from error


def validate_manifest_payload(payload: Mapping[str, Any]) -> RunManifest:
    """Valida schema, tipos e invariantes y devuelve el modelo canónico."""
    return RunManifest.from_mapping(payload)


def _validate_invariants(status: RunStatus, metrics: RunMetrics, error: ErrorSummary | None) -> None:
    if status is RunStatus.SUCCESS:
        if error is not None or metrics.errors != 0:
            raise ManifestValidationError("success no admite error_summary ni errores.")
        if metrics.seen != metrics.included + metrics.excluded:
            raise ManifestValidationError("success requiere seen = included + excluded.")
        if not (metrics.included == metrics.normalized == metrics.finalized):
            raise ManifestValidationError("success requiere included = normalized = finalized.")
        if metrics.privacy_allowed + metrics.privacy_quarantined + metrics.privacy_rejected != metrics.finalized:
            raise ManifestValidationError("Las decisiones de privacidad deben cubrir finalized.")
        if metrics.publication_approved + metrics.publication_hold + metrics.publication_rejected != metrics.privacy_allowed:
            raise ManifestValidationError("Las decisiones de publicación deben cubrir los Records privacy_allowed.")
        if metrics.created + metrics.updated + metrics.unchanged != metrics.publication_approved:
            raise ManifestValidationError("Las operaciones deben cubrir los Records aprobados.")
        if metrics.events_created != metrics.created or metrics.events_updated != metrics.updated:
            raise ManifestValidationError("Los Events en memoria deben corresponder a create/update.")
    elif status is RunStatus.NO_PUBLICATION:
        if error is not None or any(metrics.to_dict().values()):
            raise ManifestValidationError("no_publication requiere métricas cero y sin error.")
    elif status is RunStatus.FAILED:
        if error is None or metrics.errors < 1:
            raise ManifestValidationError("failed requiere error_summary y al menos un error.")
    elif status is RunStatus.PARTIAL:
        if error is None or metrics.errors < 1:
            raise ManifestValidationError("partial requiere resumen seguro y al menos un error.")


def _validate_schema(payload: Mapping[str, Any]) -> None:
    try:
        schema_path = Path(__file__).resolve().parents[3] / "schemas" / "run-manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(dict(payload))
    except Exception as error:
        raise ManifestValidationError("El RunManifest no valida contra su JSON Schema.") from error


def _canonical_timestamp(value: str, field: str) -> str:
    parsed = _parse_timestamp(value, field)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str, field: str = "timestamp") -> datetime:
    if not isinstance(value, str):
        raise ManifestValidationError(f"{field} debe ser un timestamp ISO 8601 con zona horaria.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestValidationError(f"{field} no es ISO 8601 válido.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ManifestValidationError(f"{field} debe incluir zona horaria.")
    return parsed


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
