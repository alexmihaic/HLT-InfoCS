"""Capacidad offline v2; deliberadamente NO conectada a ingest/runner v1."""

from dataclasses import dataclass, replace
from datetime import datetime
import ipaddress
import re
from urllib.parse import urlsplit
from typing import TYPE_CHECKING

from infocs.fetch.bdns.models import BDNSCodeLabel, BDNSConvocatoriaDetail, BDNSConvocatoriaSummary
from infocs.fetch.bdns.normalize import BDNSNormalizationResult, normalize_bdns_detail
from infocs.models import (
    BDNSApplicationPeriod, BDNSAuthorityHierarchy, BDNSBudgetTotal,
    BDNSCanonicalData, BDNSDocumentReference, BDNSExtractReference,
    BDNSOfficialClassification, BDNSRegulatoryBases, DataValidationError,
    Record, RecordCandidate, SourceData,
    MAX_BDNS_SOURCE_LOCATOR_LENGTH, valid_bdns_regulatory_bases_source_locator,
)

if TYPE_CHECKING:
    from infocs.privacy import PrivacyDecision
    from infocs.fetch.bdns.publication import BDNSPublicationEvaluation
    from infocs.publication.authorization import PublicationAuthorization
    from infocs.store import RecordStore


BDNS_ENRICHED_NORMALIZER_VERSION = "2.0.0"
BDNS_ENRICHED_EVENT_POLICY_ID = "bdns.enriched-metadata-publication.v2"
MAX_BDNS_URL_LENGTH = MAX_BDNS_SOURCE_LOCATOR_LENGTH


class BDNSEnrichmentError(ValueError):
    """Sólo códigos estáticos seguros; nunca contenido fuente en diagnóstico."""


def valid_bdns_supplied_url(value: str) -> bool:
    """URL suministrada por BDNS, NO certificación institucional ni petición."""
    return _valid_bdns_url(value, schemes=("https",))


def clickable_bdns_regulatory_bases_url(source_locator: str) -> str | None:
    """Única elegibilidad derivada; devuelve literal HTTPS o None, sin reparar."""
    if valid_bdns_regulatory_bases_source_locator(source_locator) and valid_bdns_supplied_url(source_locator):
        return source_locator
    return None


def _valid_bdns_url(value: str, *, schemes: tuple[str, ...]) -> bool:
    if not isinstance(value, str) or not value or len(value) > MAX_BDNS_URL_LENGTH:
        return False
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        return False
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        return False
    try:
        url = urlsplit(value)
        host = url.hostname
        if url.scheme not in schemes or not host or url.username is not None or url.password is not None:
            return False
        url.port
        try:
            ipaddress.ip_address(host)
            return False  # No se enlazan IPs literales como webs institucionales.
        except ValueError:
            pass
        ascii_host = host.encode("idna").decode("ascii")
        labels = ascii_host.split(".")
        if len(labels) < 2 or len(ascii_host) > 253 or ascii_host.endswith((".local", ".localhost")):
            return False
        return all(re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label) for label in labels)
    except (ValueError, UnicodeError):
        return False


def _url(value: str | None) -> str | None:
    if value is not None and not valid_bdns_supplied_url(value):
        raise BDNSEnrichmentError("enrichment_invalid_url")
    return value  # No reescritura ni normalización semántica.


def _regulatory_bases_locator(value: str | None) -> str | None:
    if value is not None and not valid_bdns_regulatory_bases_source_locator(value):
        raise BDNSEnrichmentError("enrichment_invalid_url")
    return value  # Preservación literal; no HTTP→HTTPS ni descarte silencioso.


def _classifications(values: tuple[BDNSCodeLabel, ...]) -> tuple[BDNSOfficialClassification, ...]:
    result = []
    for item in values:
        if not isinstance(item.description, str) or not item.description.strip():
            raise BDNSEnrichmentError("enrichment_missing_required_label")
        result.append(BDNSOfficialClassification(label=item.description, code=item.code))
    return tuple(result)


def build_bdns_source_data(detail: BDNSConvocatoriaDetail) -> SourceData:
    """Mapeo all-or-nothing de campos aprobados, desde modelo ya parseado."""
    if not isinstance(detail, BDNSConvocatoriaDetail):
        raise BDNSEnrichmentError("enrichment_invalid_model")
    try:
        budget = None
        if detail.total_budget is not None:
            try:
                budget = BDNSBudgetTotal(detail.total_budget)  # Moneda no modelada por fuente: None.
            except DataValidationError:
                raise BDNSEnrichmentError("enrichment_invalid_decimal") from None
        ids = [item.document_id for item in detail.documents]
        if len(set(ids)) != len(ids):
            raise BDNSEnrichmentError("enrichment_duplicate_document_id")
        try:
            documents = tuple(BDNSDocumentReference(
                source_document_id=item.document_id, description=item.description,
                filename=item.filename, published_date=item.publication_date,
                modified_value=item.modified_at,
            ) for item in detail.documents)
        except (DataValidationError, TypeError, AttributeError):
            raise BDNSEnrichmentError("enrichment_invalid_document_metadata") from None
        hierarchy = None
        if detail.authority is not None:
            levels = (detail.authority.nivel1, detail.authority.nivel2, detail.authority.nivel3)
            if any(value is not None for value in levels):
                hierarchy = BDNSAuthorityHierarchy(*levels)
        application_values = (
            detail.application_start_date, detail.application_end_date,
            detail.application_start_text, detail.application_end_text, detail.open_ended_application,
        )
        application = BDNSApplicationPeriod(*application_values) if any(value is not None for value in application_values) else None
        bases = None
        if detail.regulatory_bases_title is not None or detail.regulatory_bases_url is not None:
            bases = BDNSRegulatoryBases(detail.regulatory_bases_title, _regulatory_bases_locator(detail.regulatory_bases_url))
        extracts = tuple(BDNSExtractReference(
            cve=item.cve, diary=item.official_diary, source_url=_url(item.url),
            publication_date=item.publication_date, title=item.title, title_coofficial=item.title_coofficial,
        ) for item in detail.extracts)
        data = BDNSCanonicalData(
            official_title_coofficial=detail.title_coofficial, authority_hierarchy=hierarchy,
            budget_total=budget, call_type=detail.convocatoria_type, instruments=detail.instruments,
            eligible_beneficiary_types=_classifications(detail.eligible_beneficiaries),
            sectors=_classifications(detail.sectors),
            impact_regions=tuple(item.description for item in detail.regions),
            received_date=detail.fecha_recepcion, application=application, purpose=detail.purpose,
            regulatory_bases=bases, electronic_office_url=_url(detail.electronic_office),
            extract_published_in_official_diary=detail.extract_published_in_official_diary,
            documents=documents, extracts=extracts,
        )
        # Schema + constructores, sin entregar raw al candidato o a observabilidad.
        return SourceData(data)
    except BDNSEnrichmentError:
        raise
    except (DataValidationError, TypeError, AttributeError, ValueError):
        raise BDNSEnrichmentError("enrichment_contract_invalid") from None


def normalize_bdns_enriched(
    summary: BDNSConvocatoriaSummary, detail: BDNSConvocatoriaDetail, *,
    detected_at: datetime, last_checked_at: datetime,
) -> BDNSNormalizationResult:
    """Ruta explícita para futuros baselines; normalización productiva intacta."""
    legacy = normalize_bdns_detail(summary, detail, detected_at=detected_at, last_checked_at=last_checked_at)
    if legacy.candidate is None:
        return legacy
    try:
        candidate = replace(legacy.candidate, source_data=build_bdns_source_data(detail),
            provenance=replace(legacy.candidate.provenance, normalizer_version=BDNS_ENRICHED_NORMALIZER_VERSION))
        candidate = RecordCandidate.from_dict(candidate.to_dict())
    except DataValidationError:
        raise BDNSEnrichmentError("enrichment_contract_invalid") from None
    return BDNSNormalizationResult(legacy.territorial_decision, candidate)


@dataclass(frozen=True, slots=True)
class BDNSEnrichedPreflight:
    """Objetos sólo en memoria, no report/payload raw para observabilidad."""

    record: Record | None
    privacy: "PrivacyDecision | None"
    publication: "BDNSPublicationEvaluation | None"
    authorization: "PublicationAuthorization | None"
    safe_reason: str | None


def prepare_bdns_enriched_record(
    summary: BDNSConvocatoriaSummary, detail: BDNSConvocatoriaDetail, *,
    detected_at: datetime, last_checked_at: datetime, record_store: "RecordStore",
) -> BDNSEnrichedPreflight:
    """Harness offline: mapping → hash v2 → gates → authorization → validate.

    Nunca escribe, crea Events ni llama red. No invocado por el runner.
    """
    from infocs.finalize import finalize_record
    from infocs.fetch.bdns.publication import BDNSPublicationPolicyError, authorize_bdns_event, evaluate_bdns_publication
    from infocs.publication.authorization import PublicationAuthorizationError
    from infocs.fetch.bdns.normalize import BDNSNormalizationError
    from infocs.store import RecordStore, RecordStoreError
    from infocs.privacy import PrivacyDecisionType, PrivacyGateError

    if not isinstance(record_store, RecordStore):
        raise BDNSEnrichmentError("enrichment_invalid_model")
    try:
        normalized = normalize_bdns_enriched(summary, detail, detected_at=detected_at, last_checked_at=last_checked_at)
        if normalized.candidate is None:
            return BDNSEnrichedPreflight(None, None, None, None, "enrichment_territorial_not_included")
        record = finalize_record(normalized.candidate)
    except (BDNSEnrichmentError, BDNSNormalizationError, DataValidationError) as error:
        # No diagnóstico de constructores/schema, que podría incluir valores.
        reason = str(error) if isinstance(error, BDNSEnrichmentError) else "enrichment_contract_invalid"
        return BDNSEnrichedPreflight(None, None, None, None, reason)
    try:
        privacy = record_store.privacy_gate.evaluate(record)
    except PrivacyGateError:
        return BDNSEnrichedPreflight(record, None, None, None, "privacy_source_data_blocked")
    publication = evaluate_bdns_publication(record, privacy)
    if privacy.decision is not PrivacyDecisionType.ALLOW:
        return BDNSEnrichedPreflight(record, privacy, publication, None, "privacy_source_data_blocked")
    try:
        authorization = authorize_bdns_event(record, publication)
    except (BDNSPublicationPolicyError, PublicationAuthorizationError, PrivacyGateError):
        return BDNSEnrichedPreflight(record, privacy, publication, None, "publication_source_data_hold")
    if authorization is None:
        return BDNSEnrichedPreflight(record, privacy, publication, None, "publication_source_data_hold")
    try:
        record_store.validate(record)
        record_store.path_for(record.source.id, record.id)
    except RecordStoreError:
        return BDNSEnrichedPreflight(record, privacy, publication, None, "enrichment_record_preflight_failed")
    return BDNSEnrichedPreflight(record, privacy, publication, authorization, None)
