"""Transporte y listado mínimo del BOP de Castellón."""

from infocs.fetch.bop_castellon.models import (
    BOPAnnouncement,
    BOPFetchResult,
    BOPFetchStatus,
    BOPIssue,
)
from infocs.fetch.bop_castellon.ingest import (
    BOPIngestionMetrics,
    BOPIngestionResult,
    BOPIngestionStatus,
    ingest_bop_fetch_result,
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
    authorize_bop_event,
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
    "BOPIngestionMetrics",
    "BOPIngestionResult",
    "BOPIngestionStatus",
    "BOPNormalizationError",
    "BOPPublicationEvaluation",
    "BOPPublicationPolicyError",
    "authorize_bop_event",
    "BOPTransport",
    "bop_source_publication_eligibility",
    "category_for_bop_title",
    "evaluate_bop_publication",
    "ingest_bop_fetch_result",
    "normalize_bop_announcement",
    "parse_bop_partial_response",
]
