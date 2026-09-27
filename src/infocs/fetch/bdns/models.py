"""Modelos source-specific mínimos para búsqueda y detalle SNPSAP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Generic, TypeVar


class BDNSRequestStatus(str, Enum):
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    INVALID_REQUEST = "invalid_request"
    SOURCE_FAILURE = "source_failure"


@dataclass(frozen=True, slots=True)
class BDNSSearchQuery:
    """Subset tipado de filtros documentados; no acepta parámetros arbitrarios."""

    page: int = 0
    page_size: int = 25
    order: str = "fechaRecepcion"
    direction: str = "desc"
    numero_convocatoria: str | None = None
    region_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class BDNSConvocatoriaSummary:
    numero_convocatoria: str
    internal_id: int | None
    title: str | None
    title_coofficial: str | None
    fecha_recepcion: date | None
    nivel1: str | None
    nivel2: str | None
    nivel3: str | None
    codigo_invente: str | None
    mrr: bool | None


@dataclass(frozen=True, slots=True)
class BDNSPage:
    items: tuple[BDNSConvocatoriaSummary, ...]
    page_number: int | None
    page_size: int | None
    offset: int | None
    total_pages: int | None
    total_elements: int | None
    number_of_elements: int | None
    first: bool | None
    last: bool | None
    empty: bool | None


@dataclass(frozen=True, slots=True)
class BDNSAuthority:
    nivel1: str | None
    nivel2: str | None
    nivel3: str | None


@dataclass(frozen=True, slots=True)
class BDNSCodeLabel:
    code: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class BDNSRegion:
    description: str


@dataclass(frozen=True, slots=True)
class BDNSDocumentMetadata:
    document_id: int
    filename: str | None
    description: str | None
    length: int | None
    modified_at: str | None
    publication_date: date | None


@dataclass(frozen=True, slots=True)
class BDNSExtractMetadata:
    announcement_number: int | None
    title: str | None
    title_coofficial: str | None
    cve: str | None
    official_diary: str | None
    publication_date: date | None
    url: str | None


@dataclass(frozen=True, slots=True)
class BDNSConvocatoriaDetail:
    codigo_bdns: str
    internal_id: int | None
    title: str | None
    title_coofficial: str | None
    authority: BDNSAuthority | None
    electronic_office: str | None
    fecha_recepcion: date | None
    total_budget: Decimal | None
    convocatoria_type: str | None
    instruments: tuple[str, ...]
    eligible_beneficiaries: tuple[BDNSCodeLabel, ...]
    sectors: tuple[BDNSCodeLabel, ...]
    regions: tuple[BDNSRegion, ...]
    purpose: str | None
    regulatory_bases_title: str | None
    regulatory_bases_url: str | None
    extract_published_in_official_diary: bool | None
    open_ended_application: bool | None
    application_start_date: date | None
    application_end_date: date | None
    application_start_text: str | None
    application_end_text: str | None
    documents: tuple[BDNSDocumentMetadata, ...]
    extracts: tuple[BDNSExtractMetadata, ...]


PayloadT = TypeVar("PayloadT")


@dataclass(frozen=True, slots=True)
class BDNSFetchResult(Generic[PayloadT]):
    status: BDNSRequestStatus
    http_status: int | None
    payload: PayloadT | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status in {BDNSRequestStatus.SUCCESS, BDNSRequestStatus.NO_RESULTS}:
            if self.payload is None:
                raise ValueError("Un resultado correcto requiere payload tipado.")
            if self.reason is not None:
                raise ValueError("Un resultado correcto no admite reason.")
        elif self.payload is not None:
            raise ValueError("Un fallo no puede incluir payload.")
