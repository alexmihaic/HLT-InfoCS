"""Barrera de elegibilidad source-wide para publicación de BOP Castellón."""

from __future__ import annotations

from dataclasses import dataclass

from infocs.models import Record
from infocs.privacy import PrivacyDecision, PrivacyDecisionType
from infocs.publication.source_policy import (
    SourcePublicationEligibilityDecision,
    source_hold,
)


class BOPPublicationPolicyError(ValueError):
    """El Record y la decisión de Privacy Gate no forman un par coherente."""


@dataclass(frozen=True, slots=True)
class BOPPublicationEvaluation:
    """Resultado de barreras BOP; ausencia de source decision indica privacy stop."""

    privacy_decision: PrivacyDecision
    source_eligibility: SourcePublicationEligibilityDecision | None

    def __post_init__(self) -> None:
        if not isinstance(self.privacy_decision, PrivacyDecision):
            raise BOPPublicationPolicyError("Se requiere una decisión de Privacy Gate.")
        privacy_allowed = self.privacy_decision.decision is PrivacyDecisionType.ALLOW
        if privacy_allowed != (self.source_eligibility is not None):
            raise BOPPublicationPolicyError("El orden de las barreras de publicación no es válido.")
        if self.source_eligibility is not None and not isinstance(
            self.source_eligibility, SourcePublicationEligibilityDecision
        ):
            raise BOPPublicationPolicyError("La decisión source-wide no es válida.")


def bop_source_publication_eligibility() -> SourcePublicationEligibilityDecision:
    """La reutilización BOP sigue sin estar confirmada; bloquea toda la fuente."""
    return source_hold("reuse_policy_unresolved")


def evaluate_bop_publication(
    record: Record,
    privacy_decision: PrivacyDecision,
) -> BOPPublicationEvaluation:
    """Evalúa source eligibility sólo después de Privacy ALLOW.

    No ejecuta el Privacy Gate, la revisión manual ni crea tareas de revisión.
    El llamador debe evaluar Privacy Gate sobre el Record finalizado y pasar aquí
    su decisión sin alterarla.
    """
    if not isinstance(record, Record) or not isinstance(privacy_decision, PrivacyDecision):
        raise BOPPublicationPolicyError("Se requieren un Record finalizado y una decisión de privacidad.")
    if record.source.id != "bop_castellon":
        raise BOPPublicationPolicyError("La política BOP sólo admite Records de bop_castellon.")
    if privacy_decision.record_id != record.id:
        raise BOPPublicationPolicyError("La decisión de privacidad no corresponde al Record.")
    if privacy_decision.decision is not PrivacyDecisionType.ALLOW:
        return BOPPublicationEvaluation(privacy_decision, None)
    return BOPPublicationEvaluation(privacy_decision, bop_source_publication_eligibility())
