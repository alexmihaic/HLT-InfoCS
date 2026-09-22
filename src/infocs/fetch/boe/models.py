"""Modelos internos, inmutables y específicos del sumario BOE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


@dataclass(frozen=True, slots=True)
class BOEDocumentLinks:
    xml_url: str
    html_url: str
    pdf_url: str
    pdf_size_bytes: int | None = None
    pdf_size_kbytes: int | None = None
    pdf_first_page: int | None = None
    pdf_last_page: int | None = None


@dataclass(frozen=True, slots=True)
class BOEItem:
    official_id: str
    title: str
    section_code: str
    section_name: str
    department_code: str
    department_name: str
    published_on: date
    documents: BOEDocumentLinks
    heading_name: str | None = None
    control: str | None = None


@dataclass(frozen=True, slots=True)
class BOEHeading:
    name: str
    items: tuple[BOEItem, ...]


@dataclass(frozen=True, slots=True)
class BOEDepartment:
    code: str
    name: str
    headings: tuple[BOEHeading, ...]
    direct_items: tuple[BOEItem, ...]


@dataclass(frozen=True, slots=True)
class BOESection:
    code: str
    name: str
    departments: tuple[BOEDepartment, ...]


@dataclass(frozen=True, slots=True)
class BOEDiary:
    number: str
    sections: tuple[BOESection, ...]


@dataclass(frozen=True, slots=True)
class BOESummary:
    publication_date: date
    diaries: tuple[BOEDiary, ...]

    @property
    def items(self) -> tuple[BOEItem, ...]:
        """Ítems en el orden expresado por las colecciones del sumario."""
        flattened: list[BOEItem] = []
        for diary in self.diaries:
            for section in diary.sections:
                for department in section.departments:
                    flattened.extend(department.direct_items)
                    for heading in department.headings:
                        flattened.extend(heading.items)
        return tuple(flattened)


class BOEFetchStatus(str, Enum):
    COMPLETE_SUCCESS = "complete_success"
    NO_DAILY_PUBLICATION = "no_daily_publication"
    INVALID_REQUEST = "invalid_request"
    SOURCE_FAILURE = "source_failure"


class BOETerritorialDecisionStatus(str, Enum):
    """Resultado auditable de la política territorial específica del BOE."""

    INCLUDE = "include"
    NO_MATCH = "no_match"


class BOETerritorialMatchReason(str, Enum):
    """Hechos observables que justifican la inclusión territorial."""

    MUNICIPALITY_EXACT = "municipality_exact"
    PROVINCE_EXACT = "province_exact"
    AUTHORITY_EXACT = "authority_exact"


class BOETerritorialField(str, Enum):
    """Campos de ``BOEItem`` que la política v1 está autorizada a examinar."""

    HEADING = "heading"
    DEPARTMENT = "department"
    TITLE = "title"


@dataclass(frozen=True, slots=True)
class BOETerritorialMatch:
    """Una coincidencia literal y explicable, no una inferencia de aplicabilidad."""

    reason: BOETerritorialMatchReason
    entity_code: str
    entity_name: str
    field: BOETerritorialField
    matched_text: str
    method: str


@dataclass(frozen=True, slots=True)
class BOETerritorialDecision:
    """Decisión source-specific previa a cualquier normalización InfoCs."""

    status: BOETerritorialDecisionStatus
    matches: tuple[BOETerritorialMatch, ...]

    def __post_init__(self) -> None:
        if self.status is BOETerritorialDecisionStatus.INCLUDE and not self.matches:
            raise ValueError("include requiere al menos una coincidencia territorial.")
        if self.status is BOETerritorialDecisionStatus.NO_MATCH and self.matches:
            raise ValueError("no_match no puede incluir coincidencias territoriales.")


@dataclass(frozen=True, slots=True)
class BOEFetchResult:
    status: BOEFetchStatus
    http_status: int | None
    summary: BOESummary | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status is BOEFetchStatus.COMPLETE_SUCCESS:
            if self.summary is None:
                raise ValueError("complete_success requiere un BOESummary.")
            if self.reason is not None:
                raise ValueError("complete_success no admite una razón de fallo.")
        elif self.summary is not None:
            raise ValueError("Sólo complete_success puede incluir un BOESummary.")
