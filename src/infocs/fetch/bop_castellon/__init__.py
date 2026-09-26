"""Transporte y listado mínimo del BOP de Castellón."""

from infocs.fetch.bop_castellon.models import (
    BOPAnnouncement,
    BOPFetchResult,
    BOPFetchStatus,
    BOPIssue,
)
from infocs.fetch.bop_castellon.normalize import (
    BOPNormalizationError,
    category_for_bop_title,
    normalize_bop_announcement,
)
from infocs.fetch.bop_castellon.parser import (
    BOPContractError,
    parse_bop_partial_response,
)
from infocs.fetch.bop_castellon.publication import (
    BOPPublicationEvaluation,
    BOPPublicationPolicyError,
    bop_source_publication_eligibility,
    evaluate_bop_publication,
)
from infocs.fetch.bop_castellon.transport import BOPTransport

__all__ = [
    "BOPAnnouncement",
    "BOPContractError",
    "BOPFetchResult",
    "BOPFetchStatus",
    "BOPIssue",
    "BOPNormalizationError",
    "BOPPublicationEvaluation",
    "BOPPublicationPolicyError",
    "BOPTransport",
    "bop_source_publication_eligibility",
    "category_for_bop_title",
    "evaluate_bop_publication",
    "normalize_bop_announcement",
    "parse_bop_partial_response",
]
