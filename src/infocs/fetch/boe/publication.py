"""Adaptador entre la aprobación manual BOE y autorización de Events."""

from __future__ import annotations

from infocs.models import Record
from infocs.privacy import PrivacyDecision, PrivacyDecisionType
from infocs.publication.authorization import (
    PublicationAuthorization,
    _issue_publication_authorization,
)
from infocs.publication.review import PublicationDecision, PublicationDecisionType


BOE_EVENT_POLICY_ID = "boe.manual-publication-review.v1"


def authorize_boe_event(
    record: Record,
    privacy: PrivacyDecision,
    publication: PublicationDecision,
) -> PublicationAuthorization | None:
    """Emite autorización sólo tras ALLOW y aprobación manual explícita."""
    if not isinstance(record, Record) or not isinstance(privacy, PrivacyDecision):
        raise ValueError("Se requieren Record y decisión Privacy válidos.")
    if not isinstance(publication, PublicationDecision):
        raise ValueError("Se requiere la decisión de Publication Review BOE.")
    if record.source.id != "boe" or privacy.record_id != record.id:
        raise ValueError("La evaluación BOE no corresponde al Record.")
    if privacy.decision is not PrivacyDecisionType.ALLOW:
        return None
    if publication.decision is not PublicationDecisionType.APPROVED:
        return None
    if publication.reason_code != "reviewed_safe" or publication.explicitly_listed is not True:
        return None
    return _issue_publication_authorization(record, BOE_EVENT_POLICY_ID)
