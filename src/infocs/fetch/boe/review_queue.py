"""Índice derivado y minimizado de Records BOE pendientes de revisión."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping
import uuid

from jsonschema import Draft202012Validator, FormatChecker

from infocs.fetch.boe.config import validate_boe_url


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_PATH = _PROJECT_ROOT / "schemas" / "review-queue.schema.json"
_OFFICIAL_ID = re.compile(r"[A-Z0-9]+-[A-Z]-\d{4}-\d+\Z")
_RUN_ID = re.compile(r"run-v1-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_TERRITORIAL_REASONS = frozenset({"municipality_exact", "province_exact", "authority_exact"})
_REVIEW_REASONS = frozenset({
    "not_in_allowlist", "personal_content_review", "territorial_review_required",
})


class ReviewQueueError(ValueError):
    """La cola de revisión no cumple el contrato seguro v1."""


@dataclass(frozen=True, slots=True)
class ReviewQueueEntry:
    source_id: str
    official_id: str
    source_url: str
    published_at: str
    run_id: str
    territorial_reason_codes: tuple[str, ...]
    entity_codes: tuple[str, ...]
    publication_decision: str
    reason_code: str

    def __post_init__(self) -> None:
        if self.source_id != "boe":
            raise ReviewQueueError("La cola v1 sólo acepta la fuente BOE.")
        if not isinstance(self.official_id, str) or not _OFFICIAL_ID.fullmatch(self.official_id):
            raise ReviewQueueError("official_id no cumple el formato BOE esperado.")
        try:
            validate_boe_url(self.source_url)
        except ValueError as error:
            raise ReviewQueueError("source_url no es una referencia BOE permitida.") from error
        try:
            if date.fromisoformat(self.published_at).isoformat() != self.published_at:
                raise ValueError
        except (TypeError, ValueError) as error:
            raise ReviewQueueError("published_at debe ser una fecha ISO.") from error
        if not isinstance(self.run_id, str) or not _RUN_ID.fullmatch(self.run_id):
            raise ReviewQueueError("run_id no cumple el contrato de manifiestos v1.")
        if self.publication_decision != "hold" or self.reason_code not in _REVIEW_REASONS:
            raise ReviewQueueError("La cola sólo representa decisiones hold conocidas.")
        if not self.territorial_reason_codes or any(code not in _TERRITORIAL_REASONS for code in self.territorial_reason_codes):
            raise ReviewQueueError("La cola requiere razones territoriales v1.")
        if not self.entity_codes or any(not isinstance(code, str) or not re.fullmatch(r"[a-zA-Z0-9._:-]{1,64}", code) for code in self.entity_codes):
            raise ReviewQueueError("La cola requiere códigos de entidad acotados.")
        if tuple(sorted(set(self.territorial_reason_codes))) != self.territorial_reason_codes:
            raise ReviewQueueError("territorial_reason_codes debe estar ordenado y sin duplicados.")
        if tuple(sorted(set(self.entity_codes))) != self.entity_codes:
            raise ReviewQueueError("entity_codes debe estar ordenado y sin duplicados.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "official_id": self.official_id,
            "source_url": self.source_url,
            "published_at": self.published_at,
            "run_id": self.run_id,
            "territorial_reason_codes": list(self.territorial_reason_codes),
            "entity_codes": list(self.entity_codes),
            "publication_decision": self.publication_decision,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReviewQueueEntry":
        expected = {
            "source_id", "official_id", "source_url", "published_at", "run_id",
            "territorial_reason_codes", "entity_codes", "publication_decision", "reason_code",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ReviewQueueError("La entrada de review queue no cumple el contrato cerrado.")
        try:
            return cls(
                source_id=value["source_id"], official_id=value["official_id"],
                source_url=value["source_url"], published_at=value["published_at"],
                run_id=value["run_id"],
                territorial_reason_codes=tuple(value["territorial_reason_codes"]),
                entity_codes=tuple(value["entity_codes"]),
                publication_decision=value["publication_decision"], reason_code=value["reason_code"],
            )
        except (TypeError, KeyError) as error:
            raise ReviewQueueError("La entrada de review queue no es válida.") from error


@dataclass(frozen=True, slots=True)
class ReviewQueueObservation:
    """Resultado mínimo por ID evaluado; nunca contiene texto de Record."""

    source_id: str
    official_id: str
    entry: ReviewQueueEntry | None

    def __post_init__(self) -> None:
        if self.source_id != "boe" or not isinstance(self.official_id, str) or not _OFFICIAL_ID.fullmatch(self.official_id):
            raise ReviewQueueError("La observación de review queue no identifica un ítem BOE válido.")
        if self.entry is not None and (self.entry.source_id, self.entry.official_id) != (self.source_id, self.official_id):
            raise ReviewQueueError("La entrada de review queue no corresponde a la observación.")


@dataclass(frozen=True, slots=True)
class ReviewQueueUpdate:
    path: Path
    pending_count: int
    changed: bool


class BOEReviewQueueStore:
    """Materializa pending.json como índice reemplazable, no como dato canónico."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def update(self, observations: Iterable[ReviewQueueObservation]) -> ReviewQueueUpdate:
        updates = tuple(observations)
        if not updates:
            existing = self._read() if self.path.exists() else {}
            return ReviewQueueUpdate(self.path, len(existing), False)

        pending = self._read() if self.path.exists() else {}
        seen: dict[tuple[str, str], ReviewQueueObservation] = {}
        for observation in updates:
            if not isinstance(observation, ReviewQueueObservation):
                raise ReviewQueueError("La actualización contiene una observación inválida.")
            key = observation.source_id, observation.official_id
            if key in seen and seen[key] != observation:
                raise ReviewQueueError("El mismo ítem BOE tiene decisiones incompatibles en un run.")
            seen[key] = observation

        for key, observation in seen.items():
            if observation.entry is None:
                pending.pop(key, None)
            else:
                pending[key] = observation.entry

        payload = {"schema_version": "1", "source_id": "boe", "records": [
            pending[key].to_dict() for key in sorted(pending)
        ]}
        self._validate_payload(payload)
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        if self.path.exists() and self.path.read_bytes() == encoded:
            return ReviewQueueUpdate(self.path, len(pending), False)
        self._atomic_write(encoded)
        return ReviewQueueUpdate(self.path, len(pending), True)

    def _read(self) -> dict[tuple[str, str], ReviewQueueEntry]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ReviewQueueError("No se pudo leer pending.json con seguridad.") from error
        self._validate_payload(payload)
        entries = [ReviewQueueEntry.from_mapping(item) for item in payload["records"]]
        keys = [(entry.source_id, entry.official_id) for entry in entries]
        if len(keys) != len(set(keys)) or keys != sorted(keys):
            raise ReviewQueueError("pending.json contiene IDs duplicados o no ordenados.")
        return dict(zip(keys, entries, strict=True))

    @staticmethod
    def _validate_payload(payload: Any) -> None:
        validate_review_queue_payload(payload)

    def _atomic_write(self, encoded: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=self.path.parent, prefix=".pending-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
            raise ReviewQueueError("No se pudo actualizar pending.json de forma atómica.") from error


def validate_review_queue_payload(payload: Any) -> None:
    """Valida la forma pública cerrada de la cola, incluida minimización."""
    try:
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "source_id", "records"}:
            raise ValueError
        if payload["schema_version"] != "1" or payload["source_id"] != "boe" or not isinstance(payload["records"], list):
            raise ValueError
        for item in payload["records"]:
            ReviewQueueEntry.from_mapping(item)
    except Exception as error:
        raise ReviewQueueError("pending.json no cumple el schema seguro v1.") from error
