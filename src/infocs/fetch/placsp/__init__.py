"""Canal 643 de PLACSP: transporte seguro y parser ATOM/CODICE (COLLECTOR-01A).

Sin Records, Events, Manifests ni persistencia.
"""

from infocs.fetch.placsp.config import (
    FEED_ID,
    PRODUCTION_POLICY,
    PROVISIONAL_TWO_ORIGIN_POLICY,
    ROOT_URL,
    TransportPolicy,
    UrlPolicyError,
    resolve_next_url,
    validate_feed_url,
)
from infocs.fetch.placsp.models import (
    CodeReference,
    EntryIssue,
    FeedMetadata,
    NoticeObservation,
    OfficialTemporalValue,
    ParserLimits,
    PlacspEntry,
    PlacspPage,
    PlacspParseError,
    Tombstone,
)
from infocs.fetch.placsp.parser import parse_feed_page, resolve_duplicates
from infocs.fetch.placsp.transport import FetchedPage, PlacspTransport, PlacspTransportError

__all__ = [
    "CodeReference", "EntryIssue", "FEED_ID", "FeedMetadata", "FetchedPage", "NoticeObservation",
    "OfficialTemporalValue", "PRODUCTION_POLICY", "PROVISIONAL_TWO_ORIGIN_POLICY", "ParserLimits",
    "PlacspEntry", "PlacspPage", "PlacspParseError", "PlacspTransport", "PlacspTransportError", "ROOT_URL",
    "Tombstone", "TransportPolicy", "UrlPolicyError", "parse_feed_page", "resolve_duplicates",
    "resolve_next_url", "validate_feed_url",
]
