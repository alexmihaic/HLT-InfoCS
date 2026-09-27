"""Normalización offline y conservadora de convocatorias BDNS al Core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json

from infocs.fetch.bdns.config import detail_url_for
from infocs.fetch.bdns.models import (
    BDNSConvocatoriaDetail,
    BDNSConvocatoriaSummary,
)
from infocs.models import (
    Authority,
    CandidateTechnicalMetadata,
    Category,
    DataValidationError,
    Geography,
    GrantDetails,
    Provenance,
    RecordCandidate,
    RecordDates,
    RecordStatus,
    SCHEMA_VERSION,
    SourceReference,
    TerritorialMatch,
    TerritorialMatchReason,
)


BDNS_SOURCE_ID = "bdns"
BDNS_COLLECTOR_VERSION = "0.1.0"
BDNS_NORMALIZER_VERSION = "1.0.0"
BDNS_EXTRACTION_METHOD = "bdns_rest_json"
CASTELLON_REGION_CATALOG_ID = 56
CASTELLON_REGION_CODE = "ES522"
CASTELLON_REGION_LABEL = "ES522 - Castellón / Castelló"
VALENCIA_REGION_LABEL = "ES523 - Valencia / València"
CASTELLON_PROVINCE_NAME = "Castellón/Castelló"


class BDNSTerritorialStatus(StrEnum):
    INCLUDE = "include"
    OUT_OF_SCOPE = "out_of_scope"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class BDNSTerritorialDecision:
    status: BDNSTerritorialStatus
    reason_code: str


@dataclass(frozen=True, slots=True)
class BDNSNormalizationResult:
    """Resultado sin datos fuente cuando el scope no permite Candidate."""

    territorial_decision: BDNSTerritorialDecision
    candidate: RecordCandidate | None

    def __post_init__(self) -> None:
        included = self.territorial_decision.status is BDNSTerritorialStatus.INCLUDE
        if included != (self.candidate is not None):
            raise ValueError("Sólo una decisión territorial INCLUDE puede llevar Candidate.")


class BDNSNormalizationError(ValueError):
    """Error contractual con códigos seguros; no incluye valores de la convocatoria."""


def evaluate_bdns_territory(detail: BDNSConvocatoriaDetail) -> BDNSTerritorialDecision:
    """Evalúa únicamente etiquetas oficiales exactas ya observadas en política v1."""
    if not isinstance(detail, BDNSConvocatoriaDetail):
        raise BDNSNormalizationError("detail_model_invalid")
    descriptions = tuple(region.description for region in detail.regions)
    if any(not isinstance(description, str) for description in descriptions):
        raise BDNSNormalizationError("region_contract_invalid")
    if any(description == CASTELLON_REGION_LABEL for description in descriptions):
        return BDNSTerritorialDecision(BDNSTerritorialStatus.INCLUDE, "exact_castellon_province_region")
    if descriptions and all(description == VALENCIA_REGION_LABEL for description in descriptions):
        return BDNSTerritorialDecision(BDNSTerritorialStatus.OUT_OF_SCOPE, "exact_disjoint_province_region")
    if not descriptions:
        return BDNSTerritorialDecision(BDNSTerritorialStatus.UNRESOLVED, "region_absent")
    return BDNSTerritorialDecision(BDNSTerritorialStatus.UNRESOLVED, "region_not_exactly_mapped")


def normalize_bdns_detail(
    summary: BDNSConvocatoriaSummary,
    detail: BDNSConvocatoriaDetail,
    *,
    detected_at: datetime,
    last_checked_at: datetime,
) -> BDNSNormalizationResult:
    """Une search+detail y produce Candidate sólo ante scope provincial exacto.

    No realiza red, privacidad, revisión de publicación ni persistencia.
    """
    if not isinstance(summary, BDNSConvocatoriaSummary) or not isinstance(detail, BDNSConvocatoriaDetail):
        raise BDNSNormalizationError("input_model_invalid")
    _validate_observation_timestamps(detected_at, last_checked_at)
    if summary.numero_convocatoria != detail.codigo_bdns:
        raise BDNSNormalizationError("identity_mismatch")

    decision = evaluate_bdns_territory(detail)
    if decision.status is not BDNSTerritorialStatus.INCLUDE:
        return BDNSNormalizationResult(decision, None)

    title = _preferred_title(detail.title, detail.title_coofficial)
    authority = _authority(summary, detail)
    source_url = detail_url_for(detail.codigo_bdns)
    published_at = _unambiguous_extract_publication_date(detail)
    candidate = RecordCandidate(
        schema_version=SCHEMA_VERSION,
        source=SourceReference(id=BDNS_SOURCE_ID, official_id=detail.codigo_bdns),
        authority=authority,
        administration_level=None,
        category=Category.GRANTS_CALL,
        title=title,
        dates=RecordDates(
            published_at=published_at,
            detected_at=detected_at,
            last_checked_at=last_checked_at,
            event_at=None,
        ),
        source_url=source_url,
        provenance=Provenance(
            collector=BDNS_SOURCE_ID,
            collector_version=BDNS_COLLECTOR_VERSION,
            normalizer_version=BDNS_NORMALIZER_VERSION,
            territorial_matches=(
                TerritorialMatch(
                    reason=TerritorialMatchReason.OFFICIAL_CODE_MATCH,
                    detail=_canonical_json(
                        {
                            "catalog": "bdns_regions",
                            "catalog_id": CASTELLON_REGION_CATALOG_ID,
                            "catalog_label": CASTELLON_REGION_LABEL,
                            "catalog_code": CASTELLON_REGION_CODE,
                            "source_field": "regiones[].descripcion",
                            "scope": "province",
                        }
                    ),
                ),
            ),
            transformed_by_infocs=True,
        ),
        status=RecordStatus.ACTIVE,
        grant=GrantDetails(call_id=detail.codigo_bdns),
        geography=Geography(province=CASTELLON_PROVINCE_NAME),
        technical=CandidateTechnicalMetadata(extraction_method=BDNS_EXTRACTION_METHOD),
    )
    try:
        validated = RecordCandidate.from_dict(candidate.to_dict())
    except DataValidationError as error:
        raise BDNSNormalizationError("candidate_contract_invalid") from error
    return BDNSNormalizationResult(decision, validated)


def _preferred_title(primary: str | None, coofficial: str | None) -> str:
    for title in (primary, coofficial):
        if isinstance(title, str) and title.strip():
            return title
    raise BDNSNormalizationError("title_unavailable")


def _authority(
    summary: BDNSConvocatoriaSummary,
    detail: BDNSConvocatoriaDetail,
) -> Authority | None:
    if detail.authority is None:
        return None
    levels = tuple(
        value.strip()
        for value in (detail.authority.nivel1, detail.authority.nivel2, detail.authority.nivel3)
        if isinstance(value, str) and value.strip()
    )
    if not levels:
        return None
    name = " / ".join(levels)
    if isinstance(summary.codigo_invente, str) and summary.codigo_invente.strip():
        authority_id = f"bdns:invente:{summary.codigo_invente.strip()}"
    else:
        canonical_levels = [" ".join(level.split()).casefold() for level in levels]
        canonical = _canonical_json({"levels": canonical_levels})
        digest = sha256(canonical.encode("utf-8")).hexdigest()[:20]
        authority_id = f"bdns:derived-authority:{digest}"
    return Authority(id=authority_id, name=name, administration_level=None)


def _unambiguous_extract_publication_date(detail: BDNSConvocatoriaDetail) -> date | None:
    """Sólo usa una fecha cuando hay un único extracto oficial identificable."""
    if len(detail.extracts) != 1:
        return None
    extract = detail.extracts[0]
    if (
        extract.publication_date is None
        or not extract.official_diary
        or not (extract.cve or extract.url)
    ):
        return None
    return extract.publication_date


def _validate_observation_timestamps(detected_at: datetime, last_checked_at: datetime) -> None:
    for value in (detected_at, last_checked_at):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise BDNSNormalizationError("observation_timestamp_invalid")
    if last_checked_at < detected_at:
        raise BDNSNormalizationError("observation_timestamp_order_invalid")


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
