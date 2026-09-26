"""Modelos inmutables source-specific del listado del BOP Castellón."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import re


class BOPFetchStatus(str, Enum):
    COMPLETE_SUCCESS = "complete_success"
    NO_PUBLICATION = "no_publication"
    INVALID_REQUEST = "invalid_request"
    SOURCE_FAILURE = "source_failure"


@dataclass(frozen=True, slots=True)
class BOPAnnouncement:
    """Anuncio listado; su ID es técnico del portal, no identificador jurídico."""

    portal_id: str
    title: str
    document_url: str
    group_heading: str | None = None

    def __post_init__(self) -> None:
        if not self.portal_id or not re.fullmatch(r"\d+", self.portal_id):
            raise ValueError("portal_id de anuncio debe ser un identificador numérico del portal.")
        if not self.title.strip():
            raise ValueError("El título del anuncio no puede estar vacío.")
        if not self.document_url:
            raise ValueError("El anuncio requiere una URL documental oficial.")


@dataclass(frozen=True, slots=True)
class BOPIssue:
    """Edición del BOP y anuncios en el orden presentado por el portal."""

    portal_id: str
    published_date: date
    issue_number: str
    issue_code: str
    announcements: tuple[BOPAnnouncement, ...] = ()

    def __post_init__(self) -> None:
        if not self.portal_id or not re.fullmatch(r"\d+", self.portal_id):
            raise ValueError("portal_id de edición debe ser un identificador numérico del portal.")
        if not self.issue_number.strip() or not self.issue_code.strip():
            raise ValueError("La edición requiere número y código observados.")


@dataclass(frozen=True, slots=True)
class BOPFetchResult:
    status: BOPFetchStatus
    requested_date: str
    issue: BOPIssue | None = None
    http_status: int | None = None
    reason: str | None = None
    diagnostic: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.status is BOPFetchStatus.COMPLETE_SUCCESS:
            if self.issue is None or self.reason is not None:
                raise ValueError("complete_success requiere edición y no admite error.")
        elif self.issue is not None:
            raise ValueError("Sólo complete_success puede incluir una edición.")
        if self.reason is not None and not re.fullmatch(r"[a-z][a-z0-9_]*", self.reason):
            raise ValueError("reason debe ser un código técnico seguro.")
