"""Transporte y listado mínimo del BOP de Castellón."""

from infocs.fetch.bop_castellon.models import (
    BOPAnnouncement,
    BOPFetchResult,
    BOPFetchStatus,
    BOPIssue,
)
from infocs.fetch.bop_castellon.parser import (
    BOPContractError,
    parse_bop_partial_response,
)
from infocs.fetch.bop_castellon.transport import BOPTransport

__all__ = [
    "BOPAnnouncement",
    "BOPContractError",
    "BOPFetchResult",
    "BOPFetchStatus",
    "BOPIssue",
    "BOPTransport",
    "parse_bop_partial_response",
]
