"""Cliente source-specific de lectura para la API pública SNPSAP/BDNS."""

from infocs.fetch.bdns.models import (
    BDNSConvocatoriaDetail,
    BDNSConvocatoriaSummary,
    BDNSFetchResult,
    BDNSPage,
    BDNSRequestStatus,
)
from infocs.fetch.bdns.models import BDNSSearchQuery
from infocs.fetch.bdns.normalize import (
    BDNSNormalizationError,
    BDNSNormalizationResult,
    BDNSTerritorialDecision,
    BDNSTerritorialStatus,
    evaluate_bdns_territory,
    normalize_bdns_detail,
)
from infocs.fetch.bdns.parser import BDNSContractError, parse_bdns_detail, parse_bdns_search
from infocs.fetch.bdns.transport import BDNSTransport

__all__ = [
    "BDNSContractError",
    "BDNSConvocatoriaDetail",
    "BDNSConvocatoriaSummary",
    "BDNSFetchResult",
    "BDNSNormalizationError",
    "BDNSNormalizationResult",
    "BDNSPage",
    "BDNSRequestStatus",
    "BDNSTerritorialDecision",
    "BDNSTerritorialStatus",
    "BDNSSearchQuery",
    "BDNSTransport",
    "evaluate_bdns_territory",
    "normalize_bdns_detail",
    "parse_bdns_detail",
    "parse_bdns_search",
]
