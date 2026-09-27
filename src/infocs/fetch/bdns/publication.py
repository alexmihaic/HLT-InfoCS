"""Políticas source-specific de publicación de metadata BDNS v1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json

from infocs.fetch.bdns.normalize import (
    BDNS_EXTRACTION_METHOD,
    BDNS_NORMALIZER_VERSION,
    BDNS_SOURCE_ID,
    CASTELLON_PROVINCE_NAME,
    CASTELLON_REGION_CATALOG_ID,
    CASTELLON_REGION_CODE,
    CASTELLON_REGION_LABEL,
)
from infocs.fetch.bdns.config import detail_url_for
from infocs.models import Category, Record, TerritorialMatchReason
from infocs.privacy import PrivacyDecision, PrivacyDecisionType
from infocs.publication.source_policy import (
    SourcePublicationEligibilityDecision,
    SourcePublicationEligibilityType,
    source_eligible,
)


class BDNSMetadataPublicationDecisionType(StrEnum):
    PUBLISHABLE_METADATA = "publishable_metadata"
    HOLD = "hold"


class BDNSPublicationPolicyError(ValueError):
    """Contrato inválido entre Record y decisión Privacy."""


@dataclass(frozen=True, slots=True)
class BDNSMetadataPublicationDecision:
    decision: BDNSMetadataPublicationDecisionType
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, BDNSMetadataPublicationDecisionType):
            raise BDNSPublicationPolicyError("La decisión de metadata BDNS no es válida.")
        if self.decision is BDNSMetadataPublicationDecisionType.PUBLISHABLE_METADATA:
            if self.reason_code is not None:
                raise BDNSPublicationPolicyError("publishable_metadata no admite reason_code.")
        elif self.reason_code != "metadata_scope_not_publishable":
            raise BDNSPublicationPolicyError("hold requiere metadata_scope_not_publishable.")


@dataclass(frozen=True, slots=True)
class BDNSPublicationEvaluation:
    privacy_decision: PrivacyDecision
    source_eligibility: SourcePublicationEligibilityDecision | None
    metadata_publication: BDNSMetadataPublicationDecision | None

    def __post_init__(self) -> None:
        if not isinstance(self.privacy_decision, PrivacyDecision):
            raise BDNSPublicationPolicyError("Se requiere una decisión de Privacy Gate.")
        allowed = self.privacy_decision.decision is PrivacyDecisionType.ALLOW
        if allowed != (self.source_eligibility is not None):
            raise BDNSPublicationPolicyError("Privacy debe preceder a Source Publication Eligibility.")
        if not allowed and self.metadata_publication is not None:
            raise BDNSPublicationPolicyError("Una decisión Privacy no permitida no alcanza metadata policy.")
        if self.source_eligibility is None:
            if self.metadata_publication is not None:
                raise BDNSPublicationPolicyError("Sin elegibilidad source-wide no puede haber metadata decision.")
            return
        if not isinstance(self.source_eligibility, SourcePublicationEligibilityDecision):
            raise BDNSPublicationPolicyError("Source Publication Eligibility no es válida.")
        eligible = self.source_eligibility.decision is SourcePublicationEligibilityType.ELIGIBLE
        if eligible != (self.metadata_publication is not None):
            raise BDNSPublicationPolicyError("Metadata policy sólo se evalúa tras Source Eligibility ELIGIBLE.")


def bdns_source_publication_eligibility() -> SourcePublicationEligibilityDecision:
    """BDNS permite avanzar a política por Record bajo sus condiciones de reutilización."""
    return source_eligible()


def evaluate_bdns_publication(
    record: Record,
    privacy_decision: PrivacyDecision,
) -> BDNSPublicationEvaluation:
    """Aplica Privacy precedence, elegibilidad source-wide y scope de metadata.

    No ejecuta Privacy Gate ni usa Publication Review, Stores o Review Queue.
    """
    if not isinstance(record, Record) or not isinstance(privacy_decision, PrivacyDecision):
        raise BDNSPublicationPolicyError("Se requieren Record finalizado y decisión de privacidad.")
    if record.source.id != BDNS_SOURCE_ID:
        raise BDNSPublicationPolicyError("La política BDNS sólo admite Records BDNS.")
    if privacy_decision.record_id != record.id:
        raise BDNSPublicationPolicyError("La decisión de privacidad no corresponde al Record.")
    if not isinstance(privacy_decision.decision, PrivacyDecisionType):
        raise BDNSPublicationPolicyError("La decisión de privacidad no es válida.")
    if privacy_decision.decision is not PrivacyDecisionType.ALLOW:
        return BDNSPublicationEvaluation(privacy_decision, None, None)

    eligibility = bdns_source_publication_eligibility()
    if eligibility.decision is not SourcePublicationEligibilityType.ELIGIBLE:
        return BDNSPublicationEvaluation(privacy_decision, eligibility, None)
    metadata = (
        BDNSMetadataPublicationDecisionType.PUBLISHABLE_METADATA
        if _record_is_publishable_metadata(record)
        else BDNSMetadataPublicationDecisionType.HOLD
    )
    decision = BDNSMetadataPublicationDecision(
        metadata,
        None if metadata is BDNSMetadataPublicationDecisionType.PUBLISHABLE_METADATA
        else "metadata_scope_not_publishable",
    )
    return BDNSPublicationEvaluation(privacy_decision, eligibility, decision)


def _record_is_publishable_metadata(record: Record) -> bool:
    if (
        record.source.id != BDNS_SOURCE_ID
        or not record.source.official_id
        or record.category is not Category.GRANTS_CALL
        or record.grant is None
        or record.grant.call_id != record.source.official_id
        or record.grant.resolution_id is not None
        or record.grant.beneficiary is not None
        or record.geography is None
        or record.geography.province != CASTELLON_PROVINCE_NAME
        or record.geography.municipality is not None
        or record.administration_level is not None
        or (record.authority is not None and record.authority.administration_level is not None)
        or record.description is not None
        or record.financial is not None
        or record.procurement is not None
        or record.documents
        or record.tags
        or record.relations
        or record.dates.event_at is not None
        or record.provenance.collector != BDNS_SOURCE_ID
        or record.provenance.normalizer_version != BDNS_NORMALIZER_VERSION
        or record.technical.extraction_method != BDNS_EXTRACTION_METHOD
    ):
        return False
    if not any(_is_canonical_castellon_match(match) for match in record.provenance.territorial_matches):
        return False
    expected_url = detail_url_for(record.source.official_id)
    return record.source_url == expected_url


def _is_canonical_castellon_match(match) -> bool:
    if match.reason is not TerritorialMatchReason.OFFICIAL_CODE_MATCH or not isinstance(match.detail, str):
        return False
    try:
        details = json.loads(match.detail)
    except json.JSONDecodeError:
        return False
    return isinstance(details, dict) and all(
        details.get(key) == value
        for key, value in {
            "catalog": "bdns_regions",
            "catalog_id": CASTELLON_REGION_CATALOG_ID,
            "catalog_label": CASTELLON_REGION_LABEL,
            "catalog_code": CASTELLON_REGION_CODE,
            "source_field": "regiones[].descripcion",
            "scope": "province",
        }.items()
    )
