"""Privacy Gate común previo a la persistencia pública."""

from infocs.privacy.gate import (
    PrivacyConfig,
    PrivacyDecision,
    PrivacyDecisionType,
    PrivacyGate,
    PrivacyGateError,
    PrivacyClassification,
    PrivacyReason,
    TaxIdentifierClassification,
    classify_spanish_tax_identifier,
)

__all__ = [
    "PrivacyConfig",
    "PrivacyDecision",
    "PrivacyDecisionType",
    "PrivacyGate",
    "PrivacyGateError",
    "PrivacyClassification",
    "PrivacyReason",
    "TaxIdentifierClassification",
    "classify_spanish_tax_identifier",
]
