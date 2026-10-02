"""Políticas BDNS: metadata v1 productiva y capacidad enriquecida v2 aislada."""

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
from infocs.privacy import PrivacyDecision, PrivacyDecisionType, PrivacyGate
from infocs.diff.core import content_hash
from infocs.fetch.bdns.enrichment import (
    BDNS_ENRICHED_NORMALIZER_VERSION, BDNS_ENRICHED_EVENT_POLICY_ID,
    valid_bdns_supplied_url,
    valid_bdns_regulatory_bases_source_url,
)
from infocs.publication.authorization import (
    PublicationAuthorization,
    _issue_publication_authorization,
)
from infocs.publication.source_policy import (
    SourcePublicationEligibilityDecision,
    SourcePublicationEligibilityType,
    source_eligible,
)


BDNS_EVENT_POLICY_ID = "bdns.metadata-publication.v1"


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
        elif self.reason_code not in {"metadata_scope_not_publishable", "publication_source_data_hold"}:
            raise BDNSPublicationPolicyError("hold requiere un motivo seguro reconocido.")


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
        else "publication_source_data_hold" if record.source_data is not None else "metadata_scope_not_publishable",
    )
    return BDNSPublicationEvaluation(privacy_decision, eligibility, decision)


def authorize_bdns_event(
    record: Record,
    evaluation: BDNSPublicationEvaluation,
) -> PublicationAuthorization | None:
    """Adapta los tres gates BDNS a la autorización transitoria de Events."""
    if not isinstance(record, Record) or not isinstance(evaluation, BDNSPublicationEvaluation):
        raise BDNSPublicationPolicyError("Se requieren Record y evaluación BDNS válidos.")
    if record.source.id != BDNS_SOURCE_ID:
        raise BDNSPublicationPolicyError("La autorización sólo admite Records BDNS.")
    if evaluation.privacy_decision.record_id != record.id:
        raise BDNSPublicationPolicyError("La evaluación no corresponde al Record.")
    if record.source_data is not None:
        # Una decisión ALLOW v1 o stale ligada sólo al ID no autoriza nueva superficie.
        actual_privacy = PrivacyGate.default().evaluate(record)
        if actual_privacy != evaluation.privacy_decision:
            raise BDNSPublicationPolicyError("privacy_source_data_decision_mismatch")
    canonical = evaluate_bdns_publication(record, evaluation.privacy_decision)
    if canonical != evaluation:
        raise BDNSPublicationPolicyError("La evaluación BDNS no coincide con las políticas actuales.")
    if canonical.privacy_decision.decision is not PrivacyDecisionType.ALLOW:
        return None
    if (
        canonical.source_eligibility is None
        or canonical.source_eligibility.decision is not SourcePublicationEligibilityType.ELIGIBLE
        or canonical.metadata_publication is None
        or canonical.metadata_publication.decision is not BDNSMetadataPublicationDecisionType.PUBLISHABLE_METADATA
    ):
        return None
    policy_id = BDNS_ENRICHED_EVENT_POLICY_ID if record.source_data is not None else BDNS_EVENT_POLICY_ID
    return _issue_publication_authorization(record, policy_id)


def _record_is_publishable_metadata(record: Record) -> bool:
    enriched = record.source_data is not None
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
        or record.provenance.normalizer_version != (BDNS_ENRICHED_NORMALIZER_VERSION if enriched else BDNS_NORMALIZER_VERSION)
        or record.technical.extraction_method != BDNS_EXTRACTION_METHOD
    ):
        return False
    if not any(_is_canonical_castellon_match(match) for match in record.provenance.territorial_matches):
        return False
    if enriched and not _enriched_metadata_is_publishable(record):
        return False
    expected_url = detail_url_for(record.source.official_id)
    return record.source_url == expected_url


def _enriched_metadata_is_publishable(record: Record) -> bool:
    try:
        Record.from_dict(record.to_dict())
        if record.technical.content_hash_version != 2 or content_hash(record.to_dict()) != record.technical.content_hash:
            return False
        data = record.source_data.bdns
        if data.budget_total is not None and data.budget_total.currency is not None:
            return False  # El contrato fuente actual no aporta evidencia de moneda.
        if CASTELLON_REGION_LABEL not in data.impact_regions:
            return False
        hierarchy = data.authority_hierarchy
        if hierarchy is None:
            if record.authority is not None:
                return False
        else:
            expected_name = " / ".join(value.strip() for value in (hierarchy.nivel1, hierarchy.nivel2, hierarchy.nivel3) if value is not None)
            if record.authority is None or record.authority.name != expected_name:
                return False
        urls = [data.electronic_office_url]
        if data.regulatory_bases is not None:
            bases_url = data.regulatory_bases.official_source_url
            if bases_url is not None and not valid_bdns_regulatory_bases_source_url(bases_url):
                return False
        urls.extend(item.source_url for item in data.extracts)
        return all(valid_bdns_supplied_url(url) for url in urls if url is not None)
    except (ValueError, TypeError, AttributeError):
        return False


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
