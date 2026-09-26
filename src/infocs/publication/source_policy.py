"""Contrato source-wide anterior a la revisión manual por Record."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


_SOURCE_POLICY_HOLD_REASONS = frozenset({"reuse_policy_unresolved"})


class SourcePublicationEligibilityError(ValueError):
    """Decisión source-wide inválida o desconocida."""


class SourcePublicationEligibilityType(StrEnum):
    ELIGIBLE = "eligible"
    HOLD = "hold"


@dataclass(frozen=True, slots=True)
class SourcePublicationEligibilityDecision:
    """Indica si la fuente puede avanzar; no aprueba un Record individual."""

    decision: SourcePublicationEligibilityType
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, SourcePublicationEligibilityType):
            raise SourcePublicationEligibilityError("La decisión source-wide no es válida.")
        if self.decision is SourcePublicationEligibilityType.ELIGIBLE:
            if self.reason_code is not None:
                raise SourcePublicationEligibilityError("eligible no admite reason_code.")
            return
        if not isinstance(self.reason_code, str) or self.reason_code not in _SOURCE_POLICY_HOLD_REASONS:
            raise SourcePublicationEligibilityError("hold requiere un reason_code source-wide conocido.")


def source_eligible() -> SourcePublicationEligibilityDecision:
    """No se conoce una barrera global; la aprobación individual sigue pendiente."""
    return SourcePublicationEligibilityDecision(SourcePublicationEligibilityType.ELIGIBLE)


def source_hold(reason_code: str) -> SourcePublicationEligibilityDecision:
    return SourcePublicationEligibilityDecision(SourcePublicationEligibilityType.HOLD, reason_code)
