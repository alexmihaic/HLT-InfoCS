"""Contrato interno v1 de datos de InfoCs.

Los modelos no conocen fuentes reales ni realizan operaciones de red. El JSON
Schema acompaña a estas clases como contrato portable y se valida antes de
construir un modelo desde JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import json
from pathlib import Path
import re
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource


SCHEMA_VERSION = "1.0"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_IDENTITY_STRATEGIES = frozenset({
    "official_id", "case_number", "canonical_url", "composite_fingerprint",
})


class DataValidationError(ValueError):
    """Indica que una carga no cumple el contrato InfoCs v1."""


class AdministrationLevel(StrEnum):
    MUNICIPAL = "municipal"
    PROVINCIAL = "provincial"
    AUTONOMOUS = "autonomous"
    STATE = "state"


class Category(StrEnum):
    REGULATION = "regulation"
    PROCUREMENT = "procurement"
    PROCUREMENT_NOTICE = "procurement.notice"
    PROCUREMENT_AWARD = "procurement.award"
    GRANTS = "grants"
    GRANTS_CALL = "grants.call"
    GRANTS_RESOLUTION = "grants.resolution"
    BUDGET = "budget"
    EMPLOYMENT = "employment"
    URBANISM = "urbanism"
    GOVERNING_BODIES = "governing_bodies"
    AGREEMENT = "agreement"
    AUCTION = "auction"
    OTHER = "other"


class RecordStatus(StrEnum):
    ACTIVE = "active"
    MISSING_FROM_SOURCE = "missing_from_source"
    WITHDRAWN = "withdrawn"
    QUARANTINE = "quarantine"


class RelationType(StrEnum):
    SAME_EVENT_AS = "same_event_as"
    SUPERSEDES = "supersedes"
    AMENDS = "amends"
    IMPLEMENTS = "implements"
    RELATED_CONTRACT = "related_contract"
    RELATED_GRANT = "related_grant"
    RELATED_AGENDA = "related_agenda"
    RELATED_MINUTES = "related_minutes"


class TerritorialMatchReason(StrEnum):
    AUTHORITY_MATCH = "authority_match"
    MUNICIPALITY_MATCH = "municipality_match"
    EXPLICIT_TEXT_MATCH = "explicit_text_match"
    OFFICIAL_CODE_MATCH = "official_code_match"
    OTHER_DOCUMENTED = "other_documented"


class AccessType(StrEnum):
    OFFICIAL_API = "official_api"
    STRUCTURED_DATA = "structured_data"
    FEED = "feed"
    STRUCTURED_DOWNLOAD = "structured_download"
    HTML = "html"
    PDF = "pdf"
    OBSERVED_PUBLIC_DOWNLOAD_ENDPOINT = "observed_public_download_endpoint"


class SourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    UNDER_REVIEW = "under_review"


class ReuseStatus(StrEnum):
    ALLOWED = "allowed"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"
    RESTRICTED = "restricted"


class DocumentArchiveStatus(StrEnum):
    NOT_ARCHIVED = "not_archived"
    ARCHIVED = "archived"


def _non_empty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DataValidationError(f"{field} debe ser una cadena no vacía.")


def _optional_date(value: str | None, field: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise DataValidationError(f"{field} debe ser una fecha ISO 8601.") from error


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise DataValidationError(f"{field} debe ser un timestamp ISO 8601.") from error
    if parsed.tzinfo is None:
        raise DataValidationError(f"{field} debe incluir zona horaria.")
    return parsed.astimezone(UTC)


def _timestamp_string(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256(value: str | None, field: str) -> None:
    if value is not None and not _SHA256_RE.fullmatch(value):
        raise DataValidationError(f"{field} debe ser un SHA-256 hexadecimal en minúsculas.")


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Identifica la fuente configurada y, opcionalmente, el ID oficial del ítem."""

    id: str
    official_id: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.id, "source.id")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"id": self.id}
        if self.official_id is not None:
            result["official_id"] = self.official_id
        return result


@dataclass(frozen=True, slots=True)
class Authority:
    """Organismo observado; el nivel ``None`` significa no clasificado por InfoCs v1."""

    id: str
    name: str
    administration_level: AdministrationLevel | None = None
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty(self.id, "authority.id")
        _non_empty(self.name, "authority.name")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "administration_level": (
                self.administration_level.value if self.administration_level is not None else None
            ),
        }
        if self.aliases:
            result["aliases"] = list(self.aliases)
        return result


@dataclass(frozen=True, slots=True)
class RecordDates:
    """Separa las fechas oficiales de los timestamps de observación InfoCs."""

    detected_at: datetime
    last_checked_at: datetime
    published_at: date | None = None
    event_at: date | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "detected_at": _timestamp_string(self.detected_at),
            "last_checked_at": _timestamp_string(self.last_checked_at),
        }
        if self.published_at is not None:
            result["published_at"] = self.published_at.isoformat()
        if self.event_at is not None:
            result["event_at"] = self.event_at.isoformat()
        return result


@dataclass(frozen=True, slots=True)
class Money:
    """Cantidad decimal exacta, expresada como cadena y nunca como float."""

    value: str
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.value, float):
            raise DataValidationError("Los importes monetarios no admiten float.")
        if not isinstance(self.value, str):
            raise DataValidationError("money.value debe ser una cadena decimal exacta.")
        try:
            Decimal(self.value)
        except (InvalidOperation, ValueError) as error:
            raise DataValidationError("money.value debe ser una cadena decimal válida.") from error
        if not re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?", self.value):
            raise DataValidationError("money.value no debe usar notación exponencial ni ceros ambiguos.")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise DataValidationError("money.currency debe ser un código ISO 4217 de tres letras.")

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "currency": self.currency}


@dataclass(frozen=True, slots=True)
class FinancialAmounts:
    """Conceptos económicos separados para evitar un campo amount ambiguo."""

    base_budget: Money | None = None
    estimated_value: Money | None = None
    tender_amount: Money | None = None
    award_amount: Money | None = None
    modification_amount: Money | None = None
    grant_amount: Money | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value.to_dict()
            for key, value in (
                ("base_budget", self.base_budget),
                ("estimated_value", self.estimated_value),
                ("tender_amount", self.tender_amount),
                ("award_amount", self.award_amount),
                ("modification_amount", self.modification_amount),
                ("grant_amount", self.grant_amount),
            )
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class Awardee:
    name: str
    type: str
    tax_identifier: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.name, "awardee.name")
        if self.type not in {"legal_entity", "natural_person", "unknown"}:
            raise DataValidationError("awardee.type no es válido.")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name, "type": self.type}
        if self.tax_identifier is not None:
            result["tax_identifier"] = self.tax_identifier
        return result


@dataclass(frozen=True, slots=True)
class ProcurementDetails:
    expediente: str | None = None
    cpv: tuple[str, ...] = ()
    awardee: Awardee | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.expediente is not None:
            result["expediente"] = self.expediente
        if self.cpv:
            result["cpv"] = list(self.cpv)
        if self.awardee is not None:
            result["awardee"] = self.awardee.to_dict()
        return result


@dataclass(frozen=True, slots=True)
class GrantDetails:
    call_id: str | None = None
    resolution_id: str | None = None
    beneficiary: Awardee | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.call_id is not None:
            result["call_id"] = self.call_id
        if self.resolution_id is not None:
            result["resolution_id"] = self.resolution_id
        if self.beneficiary is not None:
            result["beneficiary"] = self.beneficiary.to_dict()
        return result


def _bdns_fields(model, *, text=(), dates=(), flags=(), objects=None, sequences=None) -> None:
    """Valida modelos cerrados también cuando se construyen sin JSON Schema."""
    for name in text:
        value = getattr(model, name)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise DataValidationError(f"{name} debe ser texto no vacío o None.")
    for name in dates:
        value = getattr(model, name)
        if value is not None and type(value) is not date:
            raise DataValidationError(f"{name} debe ser date o None, no timestamp/texto.")
    for name in flags:
        value = getattr(model, name)
        if value is not None and type(value) is not bool:
            raise DataValidationError(f"{name} debe ser booleano o None.")
    for name, expected in (objects or {}).items():
        value = getattr(model, name)
        if value is not None and not isinstance(value, expected):
            raise DataValidationError(f"Tipo inválido en {name}.")
    for name, expected in (sequences or {}).items():
        value = getattr(model, name)
        if not isinstance(value, tuple) or any(not isinstance(item, expected) for item in value):
            raise DataValidationError(f"{name} debe ser una tupla tipada e inmutable.")
        if expected is str and any(not item.strip() for item in value):
            raise DataValidationError(f"{name} no admite texto vacío.")


def _bdns_dict(model) -> dict[str, Any]:
    """Serializa únicamente los fields declarados; no hay payload arbitrario."""
    result = {}
    for field in fields(model):
        value = getattr(model, field.name)
        if value is None or value == ():
            continue
        if isinstance(value, date):
            value = value.isoformat()
        elif isinstance(value, tuple):
            value = [item.to_dict() if hasattr(item, "to_dict") else item for item in value]
        elif hasattr(value, "to_dict"):
            value = value.to_dict()
        result[field.name] = value
    return result


@dataclass(frozen=True, slots=True)
class BDNSBudgetTotal:
    """Presupuesto de convocatoria; no importe concedido ni moneda inferida."""

    value: Decimal
    currency: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite() or self.value < 0:
            raise DataValidationError("budget_total.value requiere Decimal finito no negativo, no float.")
        if self.currency is not None and (
            not isinstance(self.currency, str) or not re.fullmatch(r"[A-Z]{3}", self.currency)
        ):
            raise DataValidationError("budget_total.currency debe ser ISO 4217 o None.")

    def to_dict(self) -> dict[str, str]:
        value = format(self.value, "f")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        result = {"value": "0" if self.value.is_zero() else value}
        if self.currency is not None:
            result["currency"] = self.currency
        return result


@dataclass(frozen=True, slots=True)
class BDNSOfficialClassification:
    label: str
    code: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.label, "classification.label")
        _bdns_fields(self, text=("code",))

    def to_dict(self) -> dict[str, str]:
        return _bdns_dict(self)


@dataclass(frozen=True, slots=True)
class BDNSAuthorityHierarchy:
    nivel1: str | None = None
    nivel2: str | None = None
    nivel3: str | None = None

    def __post_init__(self) -> None:
        _bdns_fields(self, text=("nivel1", "nivel2", "nivel3"))
        if not any((self.nivel1, self.nivel2, self.nivel3)):
            raise DataValidationError("authority_hierarchy no puede estar vacío.")

    def to_dict(self) -> dict[str, str]:
        return _bdns_dict(self)


@dataclass(frozen=True, slots=True)
class BDNSApplicationPeriod:
    start_date: date | None = None
    end_date: date | None = None
    start_text: str | None = None
    end_text: str | None = None
    abierto: bool | None = None

    def __post_init__(self) -> None:
        _bdns_fields(self, text=("start_text", "end_text"), dates=("start_date", "end_date"), flags=("abierto",))
        if not self.to_dict():
            raise DataValidationError("application no puede estar vacío.")

    def to_dict(self) -> dict[str, Any]:
        return _bdns_dict(self)


@dataclass(frozen=True, slots=True)
class BDNSRegulatoryBases:
    description: str | None = None
    source_locator: str | None = None

    def __post_init__(self) -> None:
        _bdns_fields(self, text=("description", "source_locator"))
        if self.source_locator is not None and not valid_bdns_regulatory_bases_source_locator(self.source_locator):
            raise DataValidationError("Locator fuente de bases inválido.")
        if not self.to_dict():
            raise DataValidationError("regulatory_bases no puede estar vacío.")

    def to_dict(self) -> dict[str, str]:
        return _bdns_dict(self)


MAX_BDNS_SOURCE_LOCATOR_LENGTH = 2048  # Límite InfoCs, no garantía SNPSAP.


def valid_bdns_regulatory_bases_source_locator(value: str) -> bool:
    """Persistencia literal segura; no certifica estructura URL ni navegación."""
    from urllib.parse import unquote, urlsplit

    if not isinstance(value, str) or not value or len(value) > MAX_BDNS_SOURCE_LOCATOR_LENGTH:
        return False
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value:
        return False
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        return False
    try:
        value.encode("utf-8", errors="strict")
        variants = [value]
        for _ in range(4):
            decoded = unquote(variants[-1], errors="strict")
            if decoded == variants[-1]:
                break
            variants.append(decoded)
        if unquote(variants[-1], errors="strict") != variants[-1]:
            return False
        # No ampliar a esquemas no web no observados, aunque no se vayan a enlazar.
        scheme = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):", value)
        if scheme and scheme[1].lower() not in {"http", "https"}:
            return False
        for candidate in variants:
            # Detecta credenciales también en //host y locators sin esquema.
            authority = candidate.split("://", 1)[-1].removeprefix("//")
            authority = re.split(r"[/?#]", authority, maxsplit=1)[0]
            if "@" in authority:
                return False
            try:
                parsed = urlsplit(candidate)
            except ValueError:
                continue  # Un locator no parseable sigue siendo texto inspeccionable.
            if parsed.username is not None or parsed.password is not None:
                return False
    except (UnicodeError, ValueError):
        return False
    return True


@dataclass(frozen=True, slots=True)
class BDNSDocumentReference:
    source_document_id: int
    description: str | None = None
    filename: str | None = None
    published_date: date | None = None
    modified_value: str | None = None

    def __post_init__(self) -> None:
        if type(self.source_document_id) is not int or self.source_document_id < 0:
            raise DataValidationError("source_document_id debe ser entero no negativo.")
        _bdns_fields(self, text=("description", "filename", "modified_value"), dates=("published_date",))

    def to_dict(self) -> dict[str, Any]:
        return _bdns_dict(self)


@dataclass(frozen=True, slots=True)
class BDNSExtractReference:
    cve: str | None = None
    diary: str | None = None
    source_url: str | None = None
    publication_date: date | None = None
    title: str | None = None
    title_coofficial: str | None = None

    def __post_init__(self) -> None:
        _bdns_fields(self, text=("cve", "diary", "source_url", "title", "title_coofficial"), dates=("publication_date",))
        if self.source_url is not None:
            _bdns_https_url(self.source_url)
        if not self.to_dict():
            raise DataValidationError("extract no puede estar vacío.")

    def to_dict(self) -> dict[str, Any]:
        return _bdns_dict(self)


def _bdns_https_url(value: str) -> None:
    _bdns_web_url(value, schemes=("https",))


def _bdns_web_url(value: str, *, schemes: tuple[str, ...]) -> None:
    from urllib.parse import urlsplit

    try:
        url = urlsplit(value)
        valid = url.scheme in schemes and bool(url.hostname) and url.username is None and url.password is None
        url.port  # Rechaza puertos mal formados.
    except ValueError:
        valid = False
    if not valid or any(char.isspace() for char in value):
        raise DataValidationError("URL fuente con esquema no permitido, estructura inválida o credenciales.")


@dataclass(frozen=True, slots=True)
class BDNSCanonicalData:
    """Estado fuente permitido por schema; NO autorización de publicación."""

    extension_version: str = "1.0"
    official_title_coofficial: str | None = None
    authority_hierarchy: BDNSAuthorityHierarchy | None = None
    budget_total: BDNSBudgetTotal | None = None
    call_type: str | None = None
    instruments: tuple[str, ...] = ()
    eligible_beneficiary_types: tuple[BDNSOfficialClassification, ...] = ()
    sectors: tuple[BDNSOfficialClassification, ...] = ()
    impact_regions: tuple[str, ...] = ()
    received_date: date | None = None
    application: BDNSApplicationPeriod | None = None
    purpose: str | None = None
    regulatory_bases: BDNSRegulatoryBases | None = None
    electronic_office_url: str | None = None
    extract_published_in_official_diary: bool | None = None
    documents: tuple[BDNSDocumentReference, ...] = ()
    extracts: tuple[BDNSExtractReference, ...] = ()

    def __post_init__(self) -> None:
        if self.extension_version != "1.0":
            raise DataValidationError("BDNS extension_version debe ser 1.0.")
        _bdns_fields(self, text=("official_title_coofficial", "call_type", "purpose", "electronic_office_url"),
            dates=("received_date",), flags=("extract_published_in_official_diary",),
            objects={"authority_hierarchy": BDNSAuthorityHierarchy, "budget_total": BDNSBudgetTotal,
                "application": BDNSApplicationPeriod, "regulatory_bases": BDNSRegulatoryBases},
            sequences={"instruments": str, "eligible_beneficiary_types": BDNSOfficialClassification,
                "sectors": BDNSOfficialClassification, "impact_regions": str,
                "documents": BDNSDocumentReference, "extracts": BDNSExtractReference})
        if self.electronic_office_url is not None:
            _bdns_https_url(self.electronic_office_url)
        if len(self.to_dict()) == 1:
            raise DataValidationError("La extensión requiere al menos un dato fuente.")
        ids = [item.source_document_id for item in self.documents]
        if len(set(ids)) != len(ids):
            raise DataValidationError("No se admiten document IDs duplicados.")

    def to_dict(self) -> dict[str, Any]:
        return _bdns_dict(self)


@dataclass(frozen=True, slots=True)
class SourceData:
    bdns: BDNSCanonicalData

    def __post_init__(self) -> None:
        if not isinstance(self.bdns, BDNSCanonicalData):
            raise DataValidationError("source_data.bdns requiere BDNSCanonicalData.")

    def to_dict(self) -> dict[str, Any]:
        return {"bdns": self.bdns.to_dict()}


@dataclass(frozen=True, slots=True)
class Document:
    source_url: str
    archive_status: DocumentArchiveStatus
    has_local_copy: bool
    publication_allowed: bool
    mime_type: str | None = None
    sha256: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.source_url, "documents.source_url")
        _sha256(self.sha256, "documents.sha256")
        if self.archive_status is DocumentArchiveStatus.ARCHIVED:
            if not self.has_local_copy or not self.publication_allowed:
                raise DataValidationError("Un documento archivado requiere copia local y publicación permitida.")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source_url": self.source_url,
            "archive_status": self.archive_status.value,
            "has_local_copy": self.has_local_copy,
            "publication_allowed": self.publication_allowed,
        }
        if self.mime_type is not None:
            result["mime_type"] = self.mime_type
        if self.sha256 is not None:
            result["sha256"] = self.sha256
        return result


@dataclass(frozen=True, slots=True)
class TerritorialMatch:
    reason: TerritorialMatchReason
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"reason": self.reason.value}
        if self.detail is not None:
            result["detail"] = self.detail
        return result


@dataclass(frozen=True, slots=True)
class Relation:
    type: RelationType
    target_id: str

    def __post_init__(self) -> None:
        _non_empty(self.target_id, "relations.target_id")

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type.value, "target_id": self.target_id}


@dataclass(frozen=True, slots=True)
class Geography:
    municipality: str | None = None
    province: str | None = None

    def to_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in (("municipality", self.municipality), ("province", self.province))
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class Provenance:
    collector: str
    collector_version: str
    territorial_matches: tuple[TerritorialMatch, ...]
    transformed_by_infocs: bool
    normalizer_version: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.collector, "provenance.collector")
        _non_empty(self.collector_version, "provenance.collector_version")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "collector": self.collector,
            "collector_version": self.collector_version,
            "territorial_matches": [match.to_dict() for match in self.territorial_matches],
            "transformed_by_infocs": self.transformed_by_infocs,
        }
        if self.normalizer_version is not None:
            result["normalizer_version"] = self.normalizer_version
        return result


@dataclass(frozen=True, slots=True)
class CandidateTechnicalMetadata:
    """Metadatos que un collector puede aportar antes del finalizado."""

    raw_sha256: str | None = None
    extraction_method: str | None = None

    def __post_init__(self) -> None:
        _sha256(self.raw_sha256, "technical.raw_sha256")

    def to_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in (
                ("raw_sha256", self.raw_sha256),
                ("extraction_method", self.extraction_method),
            )
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class TechnicalMetadata:
    """Metadatos de un Record finalizado y listo para persistir."""

    content_hash: str
    identity_strategy: str
    raw_sha256: str | None = None
    extraction_method: str | None = None
    content_hash_version: int = 1

    def __post_init__(self) -> None:
        _sha256(self.content_hash, "technical.content_hash")
        _sha256(self.raw_sha256, "technical.raw_sha256")
        if self.identity_strategy not in _IDENTITY_STRATEGIES:
            raise DataValidationError("technical.identity_strategy no es válido.")
        if type(self.content_hash_version) is not int or self.content_hash_version not in (1, 2):
            raise DataValidationError("content_hash_version debe ser 1 o 2.")

    def to_dict(self) -> dict[str, Any]:
        result = {
            key: value
            for key, value in (
                ("content_hash", self.content_hash),
                ("raw_sha256", self.raw_sha256),
                ("extraction_method", self.extraction_method),
                ("identity_strategy", self.identity_strategy),
            )
            if value is not None
        }
        if self.content_hash_version != 1:
            result["content_hash_version"] = self.content_hash_version
        return result


@dataclass(frozen=True, slots=True)
class RecordCandidate:
    """Salida normalizada de un collector, aún sin identidad ni hash InfoCs."""

    schema_version: str
    source: SourceReference
    authority: Authority | None
    administration_level: AdministrationLevel | None
    category: Category
    title: str
    dates: RecordDates
    source_url: str
    provenance: Provenance
    status: RecordStatus
    description: str | None = None
    financial: FinancialAmounts | None = None
    procurement: ProcurementDetails | None = None
    grant: GrantDetails | None = None
    geography: Geography | None = None
    documents: tuple[Document, ...] = ()
    tags: tuple[str, ...] = ()
    relations: tuple[Relation, ...] = ()
    technical: CandidateTechnicalMetadata | None = None
    source_data: SourceData | None = None

    def __post_init__(self) -> None:
        _validate_common_record_fields(self)
        if self.status is not RecordStatus.ACTIVE:
            raise DataValidationError("RecordCandidate.status debe ser active.")

    def to_dict(self) -> dict[str, Any]:
        result = _common_record_to_dict(self)
        if self.technical is not None:
            result["technical"] = self.technical.to_dict()
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RecordCandidate":
        validate_record_candidate_payload(payload)
        data = dict(payload)
        return cls(
            **_common_record_from_payload(data),
            technical=_candidate_technical_from_dict(data.get("technical")),
        )


@dataclass(frozen=True, slots=True)
class Record:
    """Record finalizado, válido para persistencia canónica."""

    schema_version: str
    id: str
    source: SourceReference
    authority: Authority | None
    administration_level: AdministrationLevel | None
    category: Category
    title: str
    dates: RecordDates
    source_url: str
    provenance: Provenance
    status: RecordStatus
    technical: TechnicalMetadata
    description: str | None = None
    financial: FinancialAmounts | None = None
    procurement: ProcurementDetails | None = None
    grant: GrantDetails | None = None
    geography: Geography | None = None
    documents: tuple[Document, ...] = ()
    tags: tuple[str, ...] = ()
    relations: tuple[Relation, ...] = ()
    source_data: SourceData | None = None

    def __post_init__(self) -> None:
        _validate_common_record_fields(self)
        _non_empty(self.id, "id")
        if (self.source_data is not None) != (self.technical.content_hash_version == 2):
            raise DataValidationError("source_data requiere hash v2; Record sin extensión requiere v1.")

    def to_dict(self) -> dict[str, Any]:
        result = _common_record_to_dict(self)
        result["id"] = self.id
        result["technical"] = self.technical.to_dict()
        return result

    def canonical_json(self) -> str:
        """JSON UTF-8 lógico: claves ordenadas y separadores estables para futuros hashes."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def canonical_json_bytes(self) -> bytes:
        return self.canonical_json().encode("utf-8")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Record":
        validate_record_payload(payload)
        data = dict(payload)
        return cls(
            **_common_record_from_payload(data),
            id=data["id"],
            technical=_technical_from_dict(data.get("technical")),
        )

    @classmethod
    def from_json(cls, serialized: str | bytes) -> "Record":
        try:
            payload = json.loads(serialized)
        except (TypeError, json.JSONDecodeError) as error:
            raise DataValidationError("El registro no contiene JSON válido.") from error
        return cls.from_dict(payload)


@dataclass(frozen=True, slots=True)
class ReusePolicy:
    status: ReuseStatus
    metadata_publication: bool
    transformed_data_publication: bool
    mirror_documents: bool
    fulltext_publication: bool
    default_document_policy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "metadata_publication": self.metadata_publication,
            "transformed_data_publication": self.transformed_data_publication,
            "mirror_documents": self.mirror_documents,
            "fulltext_publication": self.fulltext_publication,
            "default_document_policy": self.default_document_policy,
        }


@dataclass(frozen=True, slots=True)
class TermsReview:
    checked_at: date
    source: str
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"checked_at": self.checked_at.isoformat(), "source": self.source}
        if self.notes is not None:
            result["notes"] = self.notes
        return result


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    id: str
    name: str
    responsible_authority: Authority
    official_url: str
    access_type: AccessType
    status: SourceStatus
    reuse: ReusePolicy
    allowed_hosts: tuple[str, ...]
    terms: TermsReview | None = None

    def __post_init__(self) -> None:
        _non_empty(self.id, "source_definition.id")
        _non_empty(self.name, "source_definition.name")
        _non_empty(self.official_url, "source_definition.official_url")
        if self.responsible_authority.administration_level is None:
            raise DataValidationError("La autoridad responsable de una fuente requiere un nivel clasificado.")
        if not self.allowed_hosts:
            raise DataValidationError("source_definition.allowed_hosts no puede estar vacío.")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "responsible_authority": self.responsible_authority.to_dict(),
            "official_url": self.official_url,
            "access_type": self.access_type.value,
            "status": self.status.value,
            "reuse": self.reuse.to_dict(),
            "allowed_hosts": list(self.allowed_hosts),
        }
        if self.terms is not None:
            result["terms"] = self.terms.to_dict()
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceDefinition":
        validate_source_payload(payload)
        data = dict(payload)
        authority_data = data["responsible_authority"]
        reuse_data = data["reuse"]
        terms_data = data.get("terms")
        return cls(
            id=data["id"],
            name=data["name"],
            responsible_authority=Authority(
                id=authority_data["id"],
                name=authority_data["name"],
                administration_level=AdministrationLevel(authority_data["administration_level"]),
                aliases=tuple(authority_data.get("aliases", ())),
            ),
            official_url=data["official_url"],
            access_type=AccessType(data["access_type"]),
            status=SourceStatus(data["status"]),
            reuse=ReusePolicy(
                status=ReuseStatus(reuse_data["status"]),
                metadata_publication=reuse_data["metadata_publication"],
                transformed_data_publication=reuse_data["transformed_data_publication"],
                mirror_documents=reuse_data["mirror_documents"],
                fulltext_publication=reuse_data["fulltext_publication"],
                default_document_policy=reuse_data["default_document_policy"],
            ),
            allowed_hosts=tuple(data["allowed_hosts"]),
            terms=(
                TermsReview(
                    checked_at=_optional_date(terms_data["checked_at"], "terms.checked_at"),
                    source=terms_data["source"],
                    notes=terms_data.get("notes"),
                )
                if terms_data is not None
                else None
            ),
        )


def _validate_common_record_fields(record: RecordCandidate | Record) -> None:
    if record.schema_version != SCHEMA_VERSION:
        raise DataValidationError(f"schema_version debe ser {SCHEMA_VERSION}.")
    _non_empty(record.title, "title")
    _non_empty(record.source_url, "source_url")
    if record.source_data is not None:
        if not isinstance(record.source_data, SourceData) or record.source.id != "bdns" or record.category is not Category.GRANTS_CALL:
            raise DataValidationError("La extensión BDNS sólo es válida para source=bdns y grants.call.")
    if record.authority is None and record.administration_level is not None:
        raise DataValidationError("administration_level requiere una authority conocida.")
    if (
        record.authority is not None
        and record.authority.administration_level is not record.administration_level
    ):
        raise DataValidationError("authority.administration_level debe coincidir con administration_level.")


def _common_record_to_dict(record: RecordCandidate | Record) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": record.schema_version,
        "source": record.source.to_dict(),
        "authority": record.authority.to_dict() if record.authority is not None else None,
        "administration_level": (
            record.administration_level.value if record.administration_level is not None else None
        ),
        "category": record.category.value,
        "title": record.title,
        "dates": record.dates.to_dict(),
        "source_url": record.source_url,
        "provenance": record.provenance.to_dict(),
        "status": record.status.value,
    }
    if record.description is not None:
        result["description"] = record.description
    if record.financial is not None:
        result["financial"] = record.financial.to_dict()
    if record.procurement is not None:
        result["procurement"] = record.procurement.to_dict()
    if record.grant is not None:
        result["grant"] = record.grant.to_dict()
    if record.geography is not None:
        result["geography"] = record.geography.to_dict()
    if record.documents:
        result["documents"] = [document.to_dict() for document in record.documents]
    if record.tags:
        result["tags"] = list(record.tags)
    if record.relations:
        result["relations"] = [relation.to_dict() for relation in record.relations]
    if record.source_data is not None:
        result["source_data"] = record.source_data.to_dict()
    return result


def _common_record_from_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    authority_data = data["authority"]
    dates_data = data["dates"]
    provenance_data = data["provenance"]
    return {
        "schema_version": data["schema_version"],
        "source": SourceReference(**data["source"]),
        "authority": (
            Authority(
                id=authority_data["id"],
                name=authority_data["name"],
                administration_level=(
                    AdministrationLevel(authority_data["administration_level"])
                    if authority_data["administration_level"] is not None
                    else None
                ),
                aliases=tuple(authority_data.get("aliases", ())),
            )
            if authority_data is not None
            else None
        ),
        "administration_level": (
            AdministrationLevel(data["administration_level"])
            if data["administration_level"] is not None
            else None
        ),
        "category": Category(data["category"]),
        "title": data["title"],
        "dates": RecordDates(
            detected_at=_timestamp(dates_data["detected_at"], "dates.detected_at"),
            last_checked_at=_timestamp(dates_data["last_checked_at"], "dates.last_checked_at"),
            published_at=_optional_date(dates_data.get("published_at"), "dates.published_at"),
            event_at=_optional_date(dates_data.get("event_at"), "dates.event_at"),
        ),
        "source_url": data["source_url"],
        "provenance": Provenance(
            collector=provenance_data["collector"],
            collector_version=provenance_data["collector_version"],
            territorial_matches=tuple(
                TerritorialMatch(TerritorialMatchReason(item["reason"]), item.get("detail"))
                for item in provenance_data["territorial_matches"]
            ),
            transformed_by_infocs=provenance_data["transformed_by_infocs"],
            normalizer_version=provenance_data.get("normalizer_version"),
        ),
        "status": RecordStatus(data["status"]),
        "description": data.get("description"),
        "financial": _financial_from_dict(data.get("financial")),
        "procurement": _procurement_from_dict(data.get("procurement")),
        "grant": _grant_from_dict(data.get("grant")),
        "geography": _geography_from_dict(data.get("geography")),
        "documents": tuple(_document_from_dict(item) for item in data.get("documents", ())),
        "tags": tuple(data.get("tags", ())),
        "relations": tuple(
            Relation(RelationType(item["type"]), item["target_id"])
            for item in data.get("relations", ())
        ),
        "source_data": _source_data_from_dict(data.get("source_data")),
    }


def _source_data_from_dict(data: Mapping[str, Any] | None) -> SourceData | None:
    if data is None:
        return None
    raw = dict(data["bdns"])
    for name, constructor in (
        ("authority_hierarchy", BDNSAuthorityHierarchy), ("application", BDNSApplicationPeriod),
        ("regulatory_bases", BDNSRegulatoryBases),
    ):
        if raw.get(name) is not None:
            item = dict(raw[name])
            if name == "application":
                for key in ("start_date", "end_date"):
                    if item.get(key) is not None:
                        item[key] = _optional_date(item[key], key)
            raw[name] = constructor(**item)
    if raw.get("budget_total") is not None:
        raw["budget_total"] = BDNSBudgetTotal(Decimal(raw["budget_total"]["value"]), raw["budget_total"].get("currency"))
    if raw.get("received_date") is not None:
        raw["received_date"] = _optional_date(raw["received_date"], "received_date")
    for name, constructor, date_key in (
        ("eligible_beneficiary_types", BDNSOfficialClassification, None),
        ("sectors", BDNSOfficialClassification, None),
        ("documents", BDNSDocumentReference, "published_date"),
        ("extracts", BDNSExtractReference, "publication_date"),
    ):
        items = []
        for value in raw.get(name) or ():
            item = dict(value)
            if date_key and item.get(date_key) is not None:
                item[date_key] = _optional_date(item[date_key], date_key)
            items.append(constructor(**item))
        raw[name] = tuple(items)
    for name in ("instruments", "impact_regions"):
        raw[name] = tuple(raw.get(name) or ())
    return SourceData(BDNSCanonicalData(**raw))


def _money_from_dict(data: Mapping[str, Any] | None) -> Money | None:
    return Money(**data) if data is not None else None


def _financial_from_dict(data: Mapping[str, Any] | None) -> FinancialAmounts | None:
    if data is None:
        return None
    return FinancialAmounts(**{key: _money_from_dict(data.get(key)) for key in FinancialAmounts.__dataclass_fields__})


def _awardee_from_dict(data: Mapping[str, Any] | None) -> Awardee | None:
    return Awardee(**data) if data is not None else None


def _procurement_from_dict(data: Mapping[str, Any] | None) -> ProcurementDetails | None:
    if data is None:
        return None
    return ProcurementDetails(
        expediente=data.get("expediente"),
        cpv=tuple(data.get("cpv", ())),
        awardee=_awardee_from_dict(data.get("awardee")),
    )


def _grant_from_dict(data: Mapping[str, Any] | None) -> GrantDetails | None:
    if data is None:
        return None
    return GrantDetails(
        call_id=data.get("call_id"),
        resolution_id=data.get("resolution_id"),
        beneficiary=_awardee_from_dict(data.get("beneficiary")),
    )


def _document_from_dict(data: Mapping[str, Any]) -> Document:
    return Document(
        source_url=data["source_url"],
        archive_status=DocumentArchiveStatus(data["archive_status"]),
        has_local_copy=data["has_local_copy"],
        publication_allowed=data["publication_allowed"],
        mime_type=data.get("mime_type"),
        sha256=data.get("sha256"),
    )


def _geography_from_dict(data: Mapping[str, Any] | None) -> Geography | None:
    return Geography(**data) if data is not None else None


def _candidate_technical_from_dict(
    data: Mapping[str, Any] | None,
) -> CandidateTechnicalMetadata | None:
    return CandidateTechnicalMetadata(**data) if data is not None else None


def _technical_from_dict(data: Mapping[str, Any] | None) -> TechnicalMetadata:
    if data is None:
        raise DataValidationError("technical es obligatorio en un Record final.")
    return TechnicalMetadata(**data)


def _schema_path(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "schemas" / name


def _validate_payload(payload: Mapping[str, Any], schema_name: str) -> None:
    try:
        schema = json.loads(_schema_path(schema_name).read_text(encoding="utf-8"))
        registry = Registry()
        if schema_name == "record_candidate.schema.json":
            record_schema = json.loads(_schema_path("record.schema.json").read_text(encoding="utf-8"))
            registry = registry.with_resource(record_schema["$id"], Resource.from_contents(record_schema))
        Draft202012Validator(schema, registry=registry, format_checker=FormatChecker()).validate(dict(payload))
    except ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "raíz"
        raise DataValidationError(f"Contrato inválido en {location}: {error.message}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"No se pudo cargar el schema {schema_name}.") from error


def validate_record_payload(payload: Mapping[str, Any]) -> None:
    _validate_payload(payload, "record.schema.json")


def validate_record_candidate_payload(payload: Mapping[str, Any]) -> None:
    _validate_payload(payload, "record_candidate.schema.json")


def validate_source_payload(payload: Mapping[str, Any]) -> None:
    _validate_payload(payload, "source.schema.json")
