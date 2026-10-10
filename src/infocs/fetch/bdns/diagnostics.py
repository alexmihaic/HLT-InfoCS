"""Closed, source-free diagnostics; never changes BDNS gate decisions."""

from dataclasses import dataclass

from infocs.fetch.bdns.enrichment import BDNS_ELECTRONIC_OFFICE_DROPPED, valid_bdns_supplied_url
from infocs.fetch.bdns.models import BDNSConvocatoriaDetail
from infocs.models import valid_bdns_regulatory_bases_source_locator


BDNS_ENRICHMENT_REASONS = frozenset({
    "enrichment_invalid_model", "enrichment_invalid_decimal",
    "enrichment_duplicate_document_id", "enrichment_invalid_document_metadata",
    "enrichment_invalid_url", "enrichment_missing_required_label",
    "enrichment_contract_invalid",
})
BDNS_ITEM_DETAIL_REASONS = BDNS_ENRICHMENT_REASONS | frozenset({
    "normalization_error", "other_safe_internal_reason",
    "no_publishable_record_in_budget", "search_failure",
})
BDNS_SAFE_FIELD_CLASSES = frozenset({
    "regulatory_bases", "electronic_office", "extracts",
    "multiple_url_families", "other",
})
BDNS_WARNING_CODES = frozenset({BDNS_ELECTRONIC_OFFICE_DROPPED})


@dataclass(frozen=True, slots=True)
class BDNSDiagnosticCounts:
    """Closed source-specific non-error counters; never canonical metadata."""

    electronic_office_dropped_invalid_url: int = 0

    def __post_init__(self) -> None:
        value = self.electronic_office_dropped_invalid_url
        if type(value) is not int or value < 0:
            raise ValueError("invalid_bdns_diagnostic_count")

    def to_dict(self) -> dict[str, int]:
        count = self.electronic_office_dropped_invalid_url
        return {BDNS_ELECTRONIC_OFFICE_DROPPED: count} if count else {}


def safe_item_detail_reason(value: object) -> str:
    return value if isinstance(value, str) and value in BDNS_ITEM_DETAIL_REASONS else "other_safe_internal_reason"


def safe_item_field_class(value: object) -> str:
    return value if isinstance(value, str) and value in BDNS_SAFE_FIELD_CLASSES else "other"


def enrichment_url_field_class(detail: BDNSConvocatoriaDetail) -> str:
    """Read-only projection using the actual validators, never source values."""
    try:
        failed = []
        if detail.regulatory_bases_url is not None and not valid_bdns_regulatory_bases_source_locator(detail.regulatory_bases_url):
            failed.append("regulatory_bases")
        # Electronic office is a dropped optional projection, not a URL blocker.
        if any(item.url is not None and not valid_bdns_supplied_url(item.url) for item in detail.extracts):
            failed.append("extracts")
        return failed[0] if len(failed) == 1 else "multiple_url_families" if failed else "other"
    except Exception:
        return "other"
