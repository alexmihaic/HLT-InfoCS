"""Cliente source-specific de lectura para la API pública SNPSAP/BDNS."""

from infocs.fetch.bdns.models import (
    BDNSConvocatoriaDetail,
    BDNSConvocatoriaSummary,
    BDNSFetchResult,
    BDNSPage,
    BDNSRequestStatus,
)
from infocs.fetch.bdns.models import BDNSSearchQuery
from infocs.fetch.bdns.parser import BDNSContractError, parse_bdns_detail, parse_bdns_search
from infocs.fetch.bdns.transport import BDNSTransport

__all__ = [
    "BDNSContractError",
    "BDNSConvocatoriaDetail",
    "BDNSConvocatoriaSummary",
    "BDNSFetchResult",
    "BDNSPage",
    "BDNSRequestStatus",
    "BDNSSearchQuery",
    "BDNSTransport",
    "parse_bdns_detail",
    "parse_bdns_search",
]
