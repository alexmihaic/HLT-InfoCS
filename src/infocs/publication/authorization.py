"""Autorización transitoria para persistir Events de un Record exacto."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from infocs.diff.core import content_hash
from infocs.models import Record


_HASH_RE = re.compile(r"[a-f0-9]{64}\Z")
_POLICY_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*[._-]v[1-9][0-9]*\Z")
_AUTHORIZATION_SEAL = object()


class PublicationAuthorizationError(ValueError):
    """Autorización ausente, inválida o ligada a otra versión de Record."""


@dataclass(frozen=True, slots=True, init=False)
class PublicationAuthorization:
    """Capability inmutable: PASS de política, ligado a identidad, fuente y hash."""

    record_id: str
    source_id: str
    content_hash: str
    policy_id: str
    _seal: object = field(repr=False, compare=False)

    def matches(self, record: Record) -> bool:
        return (
            _is_issued(self)
            and isinstance(record, Record)
            and self.record_id == record.id
            and self.source_id == record.source.id
            and self.content_hash == record.technical.content_hash
            and content_hash(record.to_dict()) == self.content_hash
        )


def _issue_publication_authorization(record: Record, policy_id: str) -> PublicationAuthorization:
    """Emite el token sólo para adaptadores de políticas tras su evaluación PASS."""
    if not isinstance(record, Record):
        raise PublicationAuthorizationError("La autorización requiere un Record canónico.")
    if not isinstance(policy_id, str) or not _POLICY_ID_RE.fullmatch(policy_id):
        raise PublicationAuthorizationError("policy_id debe ser un identificador versionado no vacío.")
    if not record.id or not record.source.id or not _HASH_RE.fullmatch(record.technical.content_hash):
        raise PublicationAuthorizationError("El Record no tiene identidad o hash canónico válido.")
    if content_hash(record.to_dict()) != record.technical.content_hash:
        raise PublicationAuthorizationError("El hash del Record no coincide con su contenido.")
    authorization = object.__new__(PublicationAuthorization)
    object.__setattr__(authorization, "record_id", record.id)
    object.__setattr__(authorization, "source_id", record.source.id)
    object.__setattr__(authorization, "content_hash", record.technical.content_hash)
    object.__setattr__(authorization, "policy_id", policy_id)
    object.__setattr__(authorization, "_seal", _AUTHORIZATION_SEAL)
    return authorization


def _is_issued(value: object) -> bool:
    return (
        isinstance(value, PublicationAuthorization)
        and value._seal is _AUTHORIZATION_SEAL
        and bool(value.record_id)
        and bool(value.source_id)
        and bool(_HASH_RE.fullmatch(value.content_hash))
        and bool(_POLICY_ID_RE.fullmatch(value.policy_id))
    )


def validate_publication_authorization(
    authorization: PublicationAuthorization,
    record: Record,
) -> None:
    if not isinstance(authorization, PublicationAuthorization) or not authorization.matches(record):
        raise PublicationAuthorizationError("La autorización no corresponde al Record y hash actuales.")
