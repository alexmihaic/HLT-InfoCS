"""Decisión manual, versionada y fail-closed para publicación."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
import re
from typing import Any, Mapping

from infocs.models import Record
from infocs.privacy import PrivacyDecision, PrivacyDecisionType


_OFFICIAL_ID = re.compile(r"[A-Z0-9]+-[A-Z]-\d{4}-\d+\Z")
_REASON_CODES = frozenset(
    {
        "reviewed_safe",
        "privacy_quarantine",
        "personal_content_review",
        "territorial_review_required",
    }
)
DEFAULT_PUBLICATION_REVIEW_CONFIG = (
    Path(__file__).resolve().parents[3] / "config" / "publication-review" / "boe-initial.json"
)


class PublicationDecisionType(StrEnum):
    APPROVED = "approved"
    HOLD = "hold"
    REJECTED = "rejected"


class PublicationReviewError(ValueError):
    """La revisión humana versionada no cumple el contrato de publicación."""


@dataclass(frozen=True, slots=True)
class PublicationReviewEntry:
    official_id: str
    decision: PublicationDecisionType
    reason_code: str


@dataclass(frozen=True, slots=True)
class PublicationDecision:
    decision: PublicationDecisionType
    reason_code: str
    explicitly_listed: bool


@dataclass(frozen=True, slots=True)
class PublicationReviewConfig:
    source_id: str
    entries: tuple[PublicationReviewEntry, ...]

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_PUBLICATION_REVIEW_CONFIG) -> "PublicationReviewConfig":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PublicationReviewError("No se pudo cargar la configuración de publicación.") from error
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: Any) -> "PublicationReviewConfig":
        if not isinstance(payload, Mapping) or set(payload) != {"schema_version", "source_id", "records"}:
            raise PublicationReviewError("La configuración de publicación debe declarar sólo schema_version, source_id y records.")
        if payload.get("schema_version") != "1" or not _non_empty(payload.get("source_id")):
            raise PublicationReviewError("La versión o fuente de la configuración de publicación no es válida.")
        raw_entries = payload.get("records")
        if not isinstance(raw_entries, list):
            raise PublicationReviewError("records debe ser una lista explícita.")
        entries: list[PublicationReviewEntry] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_entries):
            if not isinstance(raw, Mapping) or set(raw) != {"official_id", "decision", "reason_code"}:
                raise PublicationReviewError(f"La entrada de revisión {index} no cumple el contrato cerrado.")
            official_id = raw.get("official_id")
            reason_code = raw.get("reason_code")
            if not isinstance(official_id, str) or not _OFFICIAL_ID.fullmatch(official_id):
                raise PublicationReviewError(f"El official_id de la entrada {index} no es válido.")
            if official_id in seen:
                raise PublicationReviewError("La configuración contiene official_id duplicados.")
            if not isinstance(reason_code, str) or reason_code not in _REASON_CODES:
                raise PublicationReviewError(f"El reason_code de la entrada {index} no está permitido.")
            try:
                decision = PublicationDecisionType(raw.get("decision"))
            except ValueError as error:
                raise PublicationReviewError(f"La decisión de la entrada {index} no está permitida.") from error
            if decision is PublicationDecisionType.APPROVED and reason_code != "reviewed_safe":
                raise PublicationReviewError("Una aprobación requiere reason_code reviewed_safe.")
            if decision is PublicationDecisionType.REJECTED and reason_code != "privacy_quarantine":
                raise PublicationReviewError("Un rechazo de esta allowlist requiere privacy_quarantine.")
            if decision is PublicationDecisionType.HOLD and reason_code in {"reviewed_safe", "privacy_quarantine"}:
                raise PublicationReviewError("El motivo no corresponde a una decisión hold.")
            seen.add(official_id)
            entries.append(PublicationReviewEntry(official_id, decision, reason_code))
        return cls(str(payload["source_id"]), tuple(entries))

    @property
    def approved_ids(self) -> frozenset[str]:
        return frozenset(entry.official_id for entry in self.entries if entry.decision is PublicationDecisionType.APPROVED)

    def validate(self) -> None:
        # Reparse the immutable public shape so even directly constructed
        # dataclasses cannot bypass entry invariants.
        self.from_mapping(
            {
                "schema_version": "1",
                "source_id": self.source_id,
                "records": [
                    {"official_id": e.official_id, "decision": e.decision.value, "reason_code": e.reason_code}
                    for e in self.entries
                ],
            }
        )


def review_publication(
    record: Record,
    privacy: PrivacyDecision,
    config: PublicationReviewConfig,
) -> PublicationDecision:
    """Aplica revisión manual; ausencia de entrada significa hold, nunca allow."""
    config.validate()
    if record.source.id != config.source_id:
        raise PublicationReviewError("La fuente del Record no coincide con la configuración de publicación.")
    if privacy.record_id != record.id or not isinstance(privacy.decision, PrivacyDecisionType):
        raise PublicationReviewError("La decisión de privacidad no corresponde al Record.")
    entry = next((item for item in config.entries if item.official_id == record.source.official_id), None)
    if entry is None:
        return PublicationDecision(PublicationDecisionType.HOLD, "not_in_allowlist", False)
    if entry.decision is PublicationDecisionType.APPROVED and privacy.decision is not PrivacyDecisionType.ALLOW:
        raise PublicationReviewError("La aprobación humana contradice Privacy Gate; publicación abortada.")
    return PublicationDecision(entry.decision, entry.reason_code, True)


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
