"""Normalización offline de anuncios BOP al contrato Core de InfoCs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata

from infocs.fetch.bop_castellon.config import validate_official_url
from infocs.fetch.bop_castellon.models import BOPAnnouncement, BOPIssue
from infocs.models import (
    AdministrationLevel,
    Authority,
    CandidateTechnicalMetadata,
    Category,
    DataValidationError,
    Document,
    DocumentArchiveStatus,
    Geography,
    Provenance,
    RecordCandidate,
    RecordDates,
    RecordStatus,
    SCHEMA_VERSION,
    SourceReference,
    TerritorialMatch,
    TerritorialMatchReason,
)


BOP_SOURCE_ID = "bop_castellon"
BOP_COLLECTOR_VERSION = "0.1.0"
BOP_NORMALIZER_VERSION = "1.0.0"
BOP_EXTRACTION_METHOD = "bop_listing_html"
CASTELLON_PROVINCE_CODE = "12"
CASTELLON_PROVINCE_NAME = "Castellón/Castelló"
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_REGISTRY_PATH = _PROJECT_ROOT / "config" / "entities" / "castellon.json"


class BOPNormalizationError(ValueError):
    """Error contractual seguro; el mensaje no contiene datos del anuncio."""


@dataclass(frozen=True, slots=True)
class _Municipality:
    code: str
    official_name: str
    variants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _AuthorityContext:
    name: str
    identifier: str
    level: AdministrationLevel | None
    municipality: _Municipality | None = None
    evidence: str = "explicit_heading"


_MUNICIPAL_PREFIXES = (
    "ayuntamiento de ",
    "ayuntamiento del ",
    "ajuntament de ",
    "ajuntament del ",
)
_GENERIC_HEADINGS = {
    "ayuntamientos",
    "diputacion provincial",
    "mancomunidades",
    "consorcios",
    "administracion de justicia",
    "administracion del estado",
    "administracion autonomica",
    "otras administraciones",
    "anuncios",
}
_OTHER_AUTHORITY_PREFIXES = (
    "mancomunidad ", "mancomunitat ", "consorcio ", "juzgado ", "juzgados ", "tribunal ",
    "consejeria ", "conselleria ", "generalitat ", "ministerio ",
    "delegacion del gobierno ", "subdelegacion del gobierno ",
    "direccion general ", "organismo autonomo ", "agencia ",
    "universidad ", "autoridad portuaria ", "comunidad de regantes ",
    "servicio provincial ", "gerencia ", "hospital ", "instituto ",
)
_CATEGORY_RULES: tuple[tuple[Category, re.Pattern[str]], ...] = (
    (Category.EMPLOYMENT, re.compile(r"\b(?:empleo|oposicion(?:es)?|bolsas? de trabajo|proceso(?:s)? selectivo(?:s)?|personal funcionario|personal laboral|concurso oposicion)\b")),
    (Category.PROCUREMENT, re.compile(r"\b(?:contratacion|licitacion(?:es)?|adjudicacion(?:es)?|contrato(?:s)? publicos?)\b")),
    (Category.GRANTS, re.compile(r"\b(?:subvenciones?|ayudas?|convocatoria de ayudas)\b")),
    (Category.REGULATION, re.compile(r"\b(?:ordenanzas?|reglamentos?|disposiciones? generales?|normativa municipal)\b")),
    (Category.BUDGET, re.compile(r"\bpresupuestos?\b")),
    (Category.URBANISM, re.compile(r"\b(?:urbanismo|plan general de ordenacion|plan especial)\b")),
    (Category.AUCTION, re.compile(r"\bsubastas?\b")),
    (Category.AGREEMENT, re.compile(r"\bconvenios?\b")),
)


def normalize_bop_announcement(
    issue: BOPIssue,
    announcement: BOPAnnouncement,
    *,
    detected_at: datetime,
    last_checked_at: datetime,
) -> RecordCandidate:
    """Convierte un anuncio BOP estructuralmente válido en RecordCandidate.

    El alcance provincial determina la inclusión; el contexto del encabezado
    sólo enriquece autoridad/geografía y nunca se deduce del título.
    """
    if not isinstance(issue, BOPIssue) or not isinstance(announcement, BOPAnnouncement):
        raise BOPNormalizationError("input_model_invalid")
    if not isinstance(issue.published_date, date) or isinstance(issue.published_date, datetime):
        raise BOPNormalizationError("published_date_invalid")
    _validate_observation_timestamps(detected_at, last_checked_at)
    if not isinstance(announcement.title, str) or not announcement.title.strip():
        raise BOPNormalizationError("announcement_title_invalid")
    try:
        source_url = validate_official_url(
            announcement.document_url,
            path="/PortalBOP/api/descargarAnuncio",
        )
    except (TypeError, ValueError) as error:
        raise BOPNormalizationError("announcement_url_invalid") from error

    authority = _authority_from_heading_path(announcement.heading_path)
    territorial_matches = [
        TerritorialMatch(
            reason=TerritorialMatchReason.OTHER_DOCUMENTED,
            detail=_canonical_json({
                "collection_scope": "province",
                "province_code": CASTELLON_PROVINCE_CODE,
                "source_id": BOP_SOURCE_ID,
                "basis": "official_bulletin_scope",
            }),
        )
    ]
    geography = Geography(province=CASTELLON_PROVINCE_NAME)
    if authority is not None and authority.municipality is not None:
        geography = Geography(
            municipality=authority.municipality.official_name,
            province=CASTELLON_PROVINCE_NAME,
        )
    if authority is not None:
        authority_detail: dict[str, str] = {
            "basis": authority.evidence,
            "heading": authority.name,
        }
        if authority.municipality is not None:
            authority_detail["municipality_code"] = authority.municipality.code
        territorial_matches.append(
            TerritorialMatch(
                reason=TerritorialMatchReason.AUTHORITY_MATCH,
                detail=_canonical_json(authority_detail),
            )
        )

    candidate = RecordCandidate(
        schema_version=SCHEMA_VERSION,
        source=SourceReference(id=BOP_SOURCE_ID, official_id=announcement.portal_id),
        authority=(
            Authority(
                id=authority.identifier,
                name=authority.name,
                administration_level=authority.level,
            )
            if authority is not None
            else None
        ),
        administration_level=authority.level if authority is not None else None,
        category=category_for_bop_title(announcement.title),
        title=announcement.title,
        dates=RecordDates(
            published_at=issue.published_date,
            detected_at=detected_at,
            last_checked_at=last_checked_at,
        ),
        source_url=source_url,
        provenance=Provenance(
            collector=BOP_SOURCE_ID,
            collector_version=BOP_COLLECTOR_VERSION,
            normalizer_version=BOP_NORMALIZER_VERSION,
            territorial_matches=tuple(territorial_matches),
            transformed_by_infocs=True,
        ),
        status=RecordStatus.ACTIVE,
        geography=geography,
        documents=(
            Document(
                source_url=source_url,
                archive_status=DocumentArchiveStatus.NOT_ARCHIVED,
                has_local_copy=False,
                publication_allowed=False,
            ),
        ),
        technical=CandidateTechnicalMetadata(extraction_method=BOP_EXTRACTION_METHOD),
    )
    try:
        return RecordCandidate.from_dict(candidate.to_dict())
    except DataValidationError as error:
        raise BOPNormalizationError("candidate_contract_invalid") from error


def category_for_bop_title(title: str) -> Category:
    """Clasificación de keywords cerrada; sólo informa una categoría derivada."""
    if not isinstance(title, str) or not title.strip():
        raise BOPNormalizationError("announcement_title_invalid")
    normalized = _fold_words(title)
    for category, pattern in _CATEGORY_RULES:
        if pattern.search(normalized):
            return category
    return Category.OTHER


@lru_cache(maxsize=1)
def _municipality_index() -> dict[str, _Municipality]:
    try:
        payload = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BOPNormalizationError("territorial_registry_invalid") from error
    province = payload.get("province", {})
    municipalities = payload.get("municipalities")
    if province.get("code") != CASTELLON_PROVINCE_CODE or not isinstance(municipalities, list):
        raise BOPNormalizationError("territorial_registry_invalid")
    index: dict[str, _Municipality] = {}
    for item in municipalities:
        if not isinstance(item, dict):
            raise BOPNormalizationError("territorial_registry_invalid")
        code = item.get("code")
        name = item.get("official_name")
        variants = item.get("official_variants")
        aliases = item.get("technical_aliases", [])
        if (
            not isinstance(code, str) or not re.fullmatch(r"12\d{3}", code)
            or not isinstance(name, str) or not name.strip()
            or not isinstance(variants, list) or not variants
            or not isinstance(aliases, list)
            or any(not isinstance(value, str) or not value.strip() for value in (*variants, *aliases))
        ):
            raise BOPNormalizationError("territorial_registry_invalid")
        municipality = _Municipality(code, name, tuple((*variants, *aliases)))
        for variant in municipality.variants:
            key = _fold_words(variant)
            if key in index and index[key].code != code:
                raise BOPNormalizationError("territorial_registry_ambiguous")
            index[key] = municipality
    if len({item.code for item in index.values()}) != len(municipalities):
        raise BOPNormalizationError("territorial_registry_invalid")
    return index


def _authority_from_heading_path(heading_path: tuple[str, ...]) -> _AuthorityContext | None:
    municipalities = _municipality_index()
    for raw_heading in reversed(heading_path):
        folded = _fold_words(raw_heading)
        if not folded or folded in _GENERIC_HEADINGS:
            continue

        for prefix in _MUNICIPAL_PREFIXES:
            normalized_prefix = _fold_words(prefix)
            if folded.startswith(normalized_prefix + " "):
                observed_name = raw_heading.strip()
                municipality = municipalities.get(folded[len(normalized_prefix) + 1 :])
                if municipality is not None:
                    return _AuthorityContext(
                        observed_name,
                        f"bop-castellon:municipality:{municipality.code}",
                        AdministrationLevel.MUNICIPAL,
                        municipality,
                        "exact_municipality_registry_heading",
                    )
                return _AuthorityContext(
                    observed_name,
                    _derived_authority_id(folded),
                    AdministrationLevel.MUNICIPAL,
                    evidence="explicit_municipal_authority_heading",
                )

        direct_municipality = municipalities.get(folded)
        if direct_municipality is not None:
            return _AuthorityContext(
                raw_heading.strip(),
                f"bop-castellon:municipality:{direct_municipality.code}",
                AdministrationLevel.MUNICIPAL,
                direct_municipality,
                "exact_municipality_registry_heading",
            )

        if folded.startswith(("diputacion provincial de castellon", "diputacion provincial de castello", "diputacion de castellon", "diputacion de castello")):
            return _AuthorityContext(
                "Diputación Provincial de Castellón",
                "bop-castellon:diputacion:12",
                AdministrationLevel.PROVINCIAL,
                evidence="explicit_provincial_deputation_heading",
            )

        level = _known_level_for_heading(folded)
        if any(folded.startswith(prefix) for prefix in _OTHER_AUTHORITY_PREFIXES):
            return _AuthorityContext(
                raw_heading.strip(),
                _derived_authority_id(folded),
                level,
                evidence="explicit_observed_organization_heading",
            )
    return None


def _known_level_for_heading(folded: str) -> AdministrationLevel | None:
    if folded.startswith(("generalitat valenciana", "consejeria ", "conselleria ")):
        return AdministrationLevel.AUTONOMOUS
    if folded.startswith(("ministerio ", "delegacion del gobierno ", "subdelegacion del gobierno ")):
        return AdministrationLevel.STATE
    return None


def _derived_authority_id(folded_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", folded_name).strip("-")[:48] or "observed"
    digest = sha256(folded_name.encode("utf-8")).hexdigest()[:16]
    return f"bop-castellon:authority:{slug}-{digest}"


def _fold_words(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def _canonical_json(value: dict[str, str]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_observation_timestamps(detected_at: datetime, last_checked_at: datetime) -> None:
    for value in (detected_at, last_checked_at):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise BOPNormalizationError("observation_timestamp_invalid")
    if last_checked_at < detected_at:
        raise BOPNormalizationError("observation_timestamp_order_invalid")
