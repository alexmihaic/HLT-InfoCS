"""Adaptador entre la aprobación manual BOE y autorización de Events."""

from __future__ import annotations

from infocs.fetch.boe.publication_rules import RULE_APPROVED_REASON, BOERuleEvaluation, BOERuleOutcome
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
    *,
    rule_evaluation: BOERuleEvaluation | None = None,
) -> PublicationAuthorization | None:
    """Emite autorización sólo tras ALLOW y aprobación manual o regla activa.

    Una aprobación por regla exige la evaluación sellada que la produjo, activa,
    CANDIDATE y ligada exactamente a este Record y su hash.
    """
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
    if publication.reason_code == "reviewed_safe" and publication.explicitly_listed is True:
        return _issue_publication_authorization(record, BOE_EVENT_POLICY_ID)
    if (
        publication.reason_code == RULE_APPROVED_REASON
        and publication.explicitly_listed is False
        and isinstance(rule_evaluation, BOERuleEvaluation)
        and rule_evaluation.is_issued()
        and rule_evaluation.active
        and rule_evaluation.outcome is BOERuleOutcome.CANDIDATE
        and rule_evaluation.record_id == record.id
        and rule_evaluation.content_hash == record.technical.content_hash
        and rule_evaluation.policy_id is not None
    ):
        return _issue_publication_authorization(record, rule_evaluation.policy_id)
    return None
