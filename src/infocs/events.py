"""Eventos canónicos append-only para cambios de Records publicados."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
from urllib.parse import quote

from jsonschema import Draft202012Validator, FormatChecker

from infocs.diff.core import content_hash, diff
from infocs.models import Record
from infocs.privacy import PrivacyDecision, PrivacyDecisionType, PrivacyGate
from infocs.publication.review import (
    PublicationDecision,
    PublicationDecisionType,
    PublicationReviewConfig,
    PublicationReviewError,
    review_publication,
)


_EVENT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "event.schema.json"
_HASH_RE = re.compile(r"[a-f0-9]{64}\Z")
_EVENT_ID_RE = re.compile(r"evt-v1-[a-f0-9]{64}\Z")
_FIELD_PATH_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*\Z")


class EventValidationError(ValueError):
    """Event canónico que no cumple el contrato persistible."""


class EventStoreError(ValueError):
    """Error seguro de validación o escritura del EventStore."""


class EventStoreConflictError(EventStoreError):
    """El mismo event_id ya existe con contenido distinto."""


@dataclass(frozen=True, slots=True)
class Event:
    schema_version: str
    event_id: str
    type: str
    record_id: str
    source_id: str
    observed_at: str
    content_hash: str
    official_id: str | None = None
    previous_content_hash: str | None = None
    changed_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.type not in {"create", "update"}:
            raise EventValidationError("Event v1 sólo admite create y update.")
        if self.type == "create" and (self.previous_content_hash is not None or self.changed_fields):
            raise EventValidationError("Un create no incluye hash previo ni changed_fields.")
        if self.type == "update" and (self.previous_content_hash is None or not self.changed_fields):
            raise EventValidationError("Un update requiere hash previo y changed_fields.")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "type": self.type,
            "record_id": self.record_id,
            "source_id": self.source_id,
            "observed_at": self.observed_at,
        }
        if self.official_id is not None:
            payload["official_id"] = self.official_id
        payload["content_hash"] = self.content_hash
        if self.type == "update":
            payload["previous_content_hash"] = self.previous_content_hash
            payload["changed_fields"] = list(self.changed_fields)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Event":
        validate_event_payload(payload)
        return cls(
            schema_version=payload["schema_version"],
            event_id=payload["event_id"],
            type=payload["type"],
            record_id=payload["record_id"],
            source_id=payload["source_id"],
            observed_at=_canonical_timestamp(payload["observed_at"]),
            content_hash=payload["content_hash"],
            official_id=payload.get("official_id"),
            previous_content_hash=payload.get("previous_content_hash"),
            changed_fields=tuple(payload.get("changed_fields", ())),
        )


@dataclass(frozen=True, slots=True)
class EventWriteResult:
    path: Path
    created: bool


def event_identity(
    record_id: str,
    event_type: str,
    content_hash: str,
    previous_content_hash: str | None = None,
) -> str:
    """ID v1 = SHA256(JSON compacto [record_id, type, previous_hash, current_hash])."""
    if (
        event_type not in {"create", "update"}
        or not record_id
        or not _HASH_RE.fullmatch(content_hash)
        or (event_type == "create" and previous_content_hash is not None)
        or (event_type == "update" and (previous_content_hash is None or not _HASH_RE.fullmatch(previous_content_hash)))
    ):
        raise EventValidationError("No se puede derivar event_id de una identidad o hash inválido.")
    seed = json.dumps(
        [record_id, event_type, previous_content_hash, content_hash],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "evt-v1-" + hashlib.sha256(seed).hexdigest()


def create_event(
    record: Record,
    *,
    observed_at: datetime,
    privacy: PrivacyDecision,
    publication: PublicationDecision,
) -> Event | None:
    """Construye un create solo para record permitido y aprobado; en otro caso no emite Event."""
    if not _publication_allowed(record, privacy, publication):
        return None
    return _make_event("create", record, observed_at, previous=None, changed_fields=())


def update_event(
    previous: Record,
    current: Record,
    *,
    observed_at: datetime,
    privacy: PrivacyDecision,
    publication: PublicationDecision,
) -> Event | None:
    """Construye update con rutas del diff común, sin valores anteriores/nuevos."""
    if previous.id != current.id or previous.source.id != current.source.id:
        raise EventValidationError("Un update debe conservar identidad y fuente del Record.")
    if previous.technical.content_hash == current.technical.content_hash:
        return None
    if not _publication_allowed(current, privacy, publication):
        return None
    paths = tuple(sorted({change.path for change in diff(previous.to_dict(), current.to_dict())}))
    if not paths:
        raise EventValidationError("Hash distinto sin campos semánticos modificados.")
    return _make_event(
        "update", current, observed_at,
        previous=previous.technical.content_hash,
        changed_fields=paths,
    )


def validate_event_payload(payload: Mapping[str, Any]) -> None:
    try:
        schema = json.loads(_EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(dict(payload))
        record_id = payload["record_id"]
        expected = event_identity(
            record_id, payload["type"], payload["content_hash"], payload.get("previous_content_hash")
        )
        if payload["event_id"] != expected:
            raise EventValidationError("event_id no coincide con la identidad determinista.")
        source_slug = re.sub(r"[^a-z0-9]+", "-", payload["source_id"].strip().lower()).strip("-")
        if not source_slug or not record_id.startswith(f"infocs:{source_slug}:"):
            raise EventValidationError("record_id no pertenece a source_id.")
        if payload["type"] == "update" and payload["previous_content_hash"] == payload["content_hash"]:
            raise EventValidationError("Un update debe cambiar el content_hash.")
        fields = payload.get("changed_fields", [])
        if fields != sorted(set(fields)):
            raise EventValidationError("changed_fields debe estar deduplicado y ordenado.")
        if any(not _FIELD_PATH_RE.fullmatch(path) for path in fields):
            raise EventValidationError("changed_fields contiene una ruta inválida.")
        return None
    except EventValidationError:
        raise
    except Exception as error:
        raise EventValidationError("Event no cumple el schema canónico v1.") from error


class EventStore:
    """Almacén JSON append-only. Igual ID/contenido es idempotente; distinto contenido es conflicto."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    def path_for(self, source_id: str, record_id: str, event_id: str) -> Path:
        if not _EVENT_ID_RE.fullmatch(event_id):
            raise EventStoreError("event_id no es seguro.")
        source = _path_component(source_id)
        record = _path_component(record_id)
        path = (self.root / source / record / f"{event_id}.json").resolve()
        root = self.root.resolve()
        if root != path and root not in path.parents:
            raise EventStoreError("El path calculado queda fuera del almacén.")
        return path

    def get(self, event_id: str) -> Event | None:
        if not _EVENT_ID_RE.fullmatch(event_id) or not self.root.is_dir():
            return None
        matches = sorted(self.root.glob(f"**/{event_id}.json"))
        if len(matches) > 1:
            raise EventStoreError("event_id aparece en más de una ruta.")
        return self._read(matches[0]) if matches else None

    def exists(self, event_id: str) -> bool:
        return self.get(event_id) is not None

    def preflight(
        self,
        event: Event,
        *,
        record: Record,
        publication_review_config: PublicationReviewConfig,
        privacy_gate: PrivacyGate | None = None,
    ) -> bool:
        """Valida el Event y detecta colisión antes de comenzar un batch de escrituras."""
        validated = self._validate_publication(event, record, publication_review_config, privacy_gate)
        path = self.path_for(validated.source_id, validated.record_id, validated.event_id)
        if not path.exists():
            return True
        existing = self._read(path)
        if existing is None or not _same_transition(existing, validated):
            raise EventStoreConflictError("event_id existente con contenido diferente.")
        return False

    def write(
        self,
        event: Event,
        *,
        record: Record,
        publication_review_config: PublicationReviewConfig,
        privacy_gate: PrivacyGate | None = None,
    ) -> EventWriteResult:
        validated = self._validate_publication(event, record, publication_review_config, privacy_gate)
        path = self.path_for(validated.source_id, validated.record_id, validated.event_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = self._read(path)
            if existing is None or not _same_transition(existing, validated):
                raise EventStoreConflictError("event_id existente con contenido diferente.")
            return EventWriteResult(path, False)

        temporary: Path | None = None
        try:
            descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            temporary = Path(temp_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(_canonical_json(validated.to_dict()) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._read(temporary)
            try:
                # Hard-linking the validated temp atomically creates without ever replacing history.
                os.link(temporary, path)
                created = True
            except FileExistsError:
                existing = self._read(path)
                if existing is None or not _same_transition(existing, validated):
                    raise EventStoreConflictError("event_id concurrente con contenido diferente.")
                created = False
            temporary.unlink(missing_ok=True)
            return EventWriteResult(path, created)
        except EventStoreError:
            raise
        except Exception as error:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise EventStoreError("No se pudo añadir el Event de forma atómica.") from error

    def list_record(self, record_id: str) -> tuple[Event, ...]:
        if not self.root.is_dir():
            return ()
        found: list[Event] = []
        for path in sorted(self.root.glob(f"**/{_path_component(record_id)}/*.json")):
            event = self._read(path)
            if event is not None and event.record_id == record_id:
                found.append(event)
        return tuple(sorted(found, key=lambda event: (event.observed_at, event.event_id)))

    def list_source(self, source_id: str) -> tuple[Event, ...]:
        directory = self.root / _path_component(source_id)
        if not directory.is_dir():
            return ()
        events = [self._read(path) for path in sorted(directory.glob("**/*.json"))]
        return tuple(sorted((event for event in events if event is not None), key=lambda event: (event.observed_at, event.event_id)))

    @staticmethod
    def _validate_publication(
        event: Event,
        record: Record,
        publication_review_config: PublicationReviewConfig,
        privacy_gate: PrivacyGate | None,
    ) -> Event:
        validated = _validated_event(event)
        if not isinstance(record, Record):
            raise EventStoreError("La escritura de Event requiere el Record publicado asociado.")
        try:
            record = Record.from_dict(record.to_dict())
        except Exception:
            raise EventStoreError("El Record asociado a Event no es persistible.") from None
        if (
            record.id != validated.record_id
            or record.source.id != validated.source_id
            or record.source.official_id != validated.official_id
            or record.technical.content_hash != validated.content_hash
            or content_hash(record.to_dict()) != validated.content_hash
        ):
            raise EventStoreError("El Event no corresponde al Record final actual.")
        if not isinstance(publication_review_config, PublicationReviewConfig):
            raise EventStoreError("La escritura de Event requiere Publication Review.")
        gate = privacy_gate if privacy_gate is not None else PrivacyGate.default()
        try:
            gate.validate()
            privacy = gate.evaluate(record)
            publication = review_publication(record, privacy, publication_review_config)
        except Exception:
            raise EventStoreError("Privacy Gate o Publication Review falló para Event.") from None
        if (
            not isinstance(privacy, PrivacyDecision)
            or privacy.record_id != record.id
            or privacy.decision is not PrivacyDecisionType.ALLOW
            or publication.decision is not PublicationDecisionType.APPROVED
        ):
            raise EventStoreError("Event requiere Privacy Gate allow y Publication Review approved.")
        return validated

    def _read(self, path: Path) -> Event | None:
        try:
            raw = path.read_text(encoding="utf-8")
            event = Event.from_dict(json.loads(raw))
            if raw != _canonical_json(event.to_dict()) + "\n":
                raise EventStoreError("La serialización persistida no es canónica.")
            if path.suffix != ".tmp" and (
                path.stem != event.event_id
                or path.parent.name != _path_component(event.record_id)
                or path.parent.parent.name != _path_component(event.source_id)
            ):
                raise EventStoreError("La ruta del Event no coincide con su contenido.")
            return event
        except EventValidationError as error:
            raise EventStoreError("Event persistido inválido.") from error
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise EventStoreError("Event persistido ilegible.") from error


def _make_event(
    event_type: str,
    record: Record,
    observed_at: datetime,
    *,
    previous: str | None,
    changed_fields: tuple[str, ...],
) -> Event:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise EventValidationError("observed_at debe incluir zona horaria.")
    current_hash = record.technical.content_hash
    event = Event(
        schema_version="1.0",
        event_id=event_identity(record.id, event_type, current_hash, previous),
        type=event_type,
        record_id=record.id,
        source_id=record.source.id,
        official_id=record.source.official_id,
        observed_at=observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        content_hash=current_hash,
        previous_content_hash=previous,
        changed_fields=tuple(sorted(set(changed_fields))),
    )
    validate_event_payload(event.to_dict())
    return event


def _publication_allowed(record: Record, privacy: PrivacyDecision, publication: PublicationDecision) -> bool:
    if not isinstance(privacy, PrivacyDecision) or privacy.record_id != record.id:
        raise EventValidationError("Decisión de privacidad ausente o no correspondiente al Record.")
    if not isinstance(publication, PublicationDecision):
        raise EventValidationError("Decisión de publicación ausente.")
    if privacy.decision is not PrivacyDecisionType.ALLOW:
        return False
    return publication.decision is PublicationDecisionType.APPROVED


def _validated_event(event: Event) -> Event:
    if not isinstance(event, Event):
        raise EventStoreError("EventStore.write() requiere un Event canónico.")
    return Event.from_dict(event.to_dict())


def _same_transition(existing: Event, candidate: Event) -> bool:
    """observed_at es la primera persistencia; el resto del payload debe coincidir."""
    old = existing.to_dict()
    new = candidate.to_dict()
    old.pop("observed_at", None)
    new.pop("observed_at", None)
    return old == new


def _canonical_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise EventValidationError("observed_at no es ISO 8601 válido.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventValidationError("observed_at debe incluir zona horaria.")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _path_component(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise EventStoreError("Identificador de ruta no válido.")
    return quote(value, safe="-_~").replace(".", "%2E")


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
