"""Manual offline rechecks over temporary, synthetic stores.

This module has no CLI, default transport or publication operation. Successful
and partial batches return a validated temporary candidate tree. Input stores
are read-only. Terminal failures expose no candidate tree. Consumers must never
interpret a batch as source health or an incremental checkpoint.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from infocs.events import EventStore
from infocs.fetch.bdns.baseline import productive_hash_version
from infocs.fetch.bdns.ingest import (
    BDNS_ATTRIBUTION_PATH, BDNSIngestionStatus, BDNSRecordOperation, observe_bdns_record,
)
from infocs.fetch.bdns.models import BDNSFetchResult
from infocs.fetch.bdns.enrichment import BDNS_ENRICHED_NORMALIZER_VERSION
from infocs.fetch.bdns.normalize import BDNS_NORMALIZER_VERSION
from infocs.fetch.bdns.workflow_safety import validate_generated_artifacts
from infocs.privacy import PrivacyGate
from infocs.store import RecordStore


class OfflineBDNSTransport:
    """Finite search/detail responses, consumed serially without any network API.

    Each entry is ("search" | "detail", BDNSFetchResult). A logical request costs
    one budget unit, including control reads and failed simulated requests. A
    denied request costs zero. There are no retries. A 429 stops all later reads.
    """

    def __init__(self, responses: tuple[tuple[str, BDNSFetchResult], ...]):
        if not isinstance(responses, tuple) or any(
            operation not in {"search", "detail"} or type(result) is not BDNSFetchResult
            for operation, result in responses
        ):
            raise ValueError("offline_responses_invalid")
        self.responses = responses
        self.used = 0
        self.limit = 0
        self.rate_limited = False
        self.exhausted = False

    def search(self, query):
        return self._next("search")

    def fetch_detail(self, code):
        return self._next("detail")

    def _next(self, operation):
        if self.rate_limited:
            raise RuntimeError("offline_rate_limited")
        if self.used >= self.limit:
            self.exhausted = True
            raise RuntimeError("offline_budget_exhausted")
        position = self.used
        self.used += 1
        expected, result = self.responses[position]
        if expected != operation:
            raise ValueError("offline_response_order_invalid")
        self.rate_limited = result.http_status == 429
        return result


@dataclass(frozen=True)
class RecheckItemResult:
    position: int
    outcome: str
    reason: str | None = None


@dataclass(frozen=True)
class RecheckBatchResult:
    """accepted = identical + modified, both subsets of attempted.

    rejected = attempted - accepted; not_attempted = selected - attempted.
    Acceptance describes individual observations. Only validated_root exposes a
    coherent candidate set. In a terminal failure earlier acceptances are not
    materialized anywhere outside the disposable staging tree.
    """

    status: str
    selected: int
    attempted: int = 0
    accepted: int = 0
    identical: int = 0
    modified: int = 0
    rejected: int = 0
    not_attempted: int = 0
    requests_used: int = 0
    reason: str | None = None
    items: tuple[RecheckItemResult, ...] = ()
    validated_root: Path | None = None

    def to_dict(self):
        # No codes, hashes, source values, absolute paths or exception messages.
        return {
            "status": self.status, "selected": self.selected, "attempted": self.attempted,
            "accepted": self.accepted, "identical": self.identical, "modified": self.modified,
            "rejected": self.rejected, "not_attempted": self.not_attempted,
            "requests_used": self.requests_used, "reason": self.reason,
            "items": [{"position": item.position, "outcome": item.outcome, "reason": item.reason}
                for item in self.items],
            "candidate_available": self.validated_root is not None,
        }


def _fingerprint(records: RecordStore, events: EventStore) -> dict[str, bytes]:
    roots = (records.root / "bdns", events.root / "bdns", records.root.parent / "migrations" / "bdns")
    return {str(path): hashlib.sha256(path.read_bytes()).digest()
        for root in roots for path in root.rglob("*") if path.is_file()}


def run_offline_recheck(*, identifiers: tuple[str, ...], workspace: tempfile.TemporaryDirectory,
    record_store: RecordStore, event_store: EventStore, transport: OfflineBDNSTransport,
    started_at: datetime, clock: Callable[[], datetime], max_records: int = 3,
    max_requests: int = 16, privacy_gate: PrivacyGate | None = None) -> RecheckBatchResult:
    """Prepare up to three existing BDNS codes, stopping at the first rejection.

    workspace must be a live TemporaryDirectory under the system temporary root.
    Both input stores must resolve inside it. All writes stay in a newly-created
    sibling staging tree. Repeating a batch uses the previous validated tree as
    input. A workspace-wide exclusive lock rejects concurrent runners. A final
    input fingerprint also detects writers that do not respect this lock.
    """
    selected = len(identifiers) if isinstance(identifiers, tuple) else 0

    def invalid(reason):
        return RecheckBatchResult("blocked", selected, not_attempted=selected, reason=reason)

    if (type(workspace) is not tempfile.TemporaryDirectory or type(transport) is not OfflineBDNSTransport
            or type(max_records) is not int or not 1 <= max_records <= 3
            or type(max_requests) is not int or not 1 <= max_requests <= 16):
        return invalid("offline_arguments_invalid")
    root = Path(workspace.name).resolve()
    if (not root.is_dir() or Path(tempfile.gettempdir()).resolve() not in root.parents
            or root not in record_store.root.resolve().parents
            or root not in event_store.root.resolve().parents):
        return invalid("temporary_stores_required")
    if (not 1 <= selected <= max_records
            or any(not isinstance(code, str) or not code.isascii() or not code.isdecimal() for code in identifiers)
            or len(set(identifiers)) != selected
            or transport.used != 0):
        return invalid("selection_invalid")
    lock = root / "bdns-recheck.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return invalid("batch_busy")
    os.close(descriptor)
    try:
        return _prepare_batch(identifiers, root, record_store, event_store, transport,
            started_at, clock, max_requests, privacy_gate)
    finally:
        lock.unlink()


def _prepare_batch(identifiers, root, records, events, transport, started_at, clock, max_requests, gate):
    selected = len(identifiers)
    try:
        for folder in (records.root / "bdns", events.root / "bdns", records.root.parent / "migrations" / "bdns"):
            if root not in folder.resolve().parents or any(
                root not in path.resolve().parents for path in folder.rglob("*")
            ):
                raise ValueError("temporary_stores_required")
        version = productive_hash_version(records, events)
        inventory = records.list_source("bdns")
        by_code = {record.source.official_id: record for record in inventory}
        if len(by_code) != len(inventory) or any(
            code not in by_code or by_code[code].technical.content_hash_version != version
            or by_code[code].provenance.normalizer_version != {
                1: BDNS_NORMALIZER_VERSION, 2: BDNS_ENRICHED_NORMALIZER_VERSION,
            }[version]
            for code in identifiers
        ):
            raise ValueError("selection_invalid")
        before = _fingerprint(records, events)
    except Exception:
        return RecheckBatchResult("blocked", selected, not_attempted=selected, reason="selection_or_contract_invalid")

    stage = Path(tempfile.mkdtemp(prefix="bdns-recheck-", dir=root))
    items = []
    identical = modified = 0
    reason = None
    terminal = False
    transport.limit = max_requests
    try:
        staged_data = stage / "data"
        for source, target in (
            (records.root / "bdns", staged_data / "records" / "bdns"),
            (events.root / "bdns", staged_data / "events" / "bdns"),
            (records.root.parent / "migrations" / "bdns", staged_data / "migrations" / "bdns"),
        ):
            if source.exists():
                shutil.copytree(source, target)
        attribution = staged_data / "records" / "bdns" / "README.md"
        attribution.write_bytes(BDNS_ATTRIBUTION_PATH.read_bytes())
        schema_root = Path(__file__).resolve().parents[4] / "schemas"
        (stage / "schemas").mkdir()
        for name in ("record.schema.json", "event.schema.json"):
            shutil.copyfile(schema_root / name, stage / "schemas" / name)
        staged_records = RecordStore(staged_data / "records", privacy_gate=gate)
        staged_events = EventStore(staged_data / "events")
        initial = {path.relative_to(stage).as_posix(): path.read_bytes()
            for folder in (staged_records.root, staged_events.root) for path in folder.rglob("*.json")}
        for position, code in enumerate(identifiers, 1):
            if transport.used >= max_requests:
                reason = "budget_exhausted"
                break
            items.append(RecheckItemResult(position, "rejected", "observation_failed"))
            result = observe_bdns_record(record_id=by_code[code].id, record_store=staged_records,
                event_store=staged_events, transport=transport, started_at=started_at,
                clock=clock, privacy_gate=gate)
            if (result.status is BDNSIngestionStatus.COMPLETE_SUCCESS
                    and result.operation in {BDNSRecordOperation.NO_CHANGE, BDNSRecordOperation.UPDATE}):
                outcome = "identical" if result.operation is BDNSRecordOperation.NO_CHANGE else "modified"
                identical += outcome == "identical"
                modified += outcome == "modified"
                items[-1] = RecheckItemResult(position, outcome)
                continue
            reason = {
                "observation_incomplete": "incomplete_response",
                "observation_contract_mismatch": "contract_mismatch",
            }.get(result.safe_reason, "observation_rejected")
            if transport.exhausted:
                reason = "budget_exhausted"
            if transport.rate_limited:
                reason = "rate_limited"
            terminal = result.status is BDNSIngestionStatus.PERSISTENCE_BLOCKED
            items[-1] = RecheckItemResult(position, "rejected", reason)
            break
        entries = []
        for folder in (staged_records.root, staged_events.root):
            for path in folder.rglob("*.json"):
                relative = path.relative_to(stage).as_posix()
                if initial.get(relative) != path.read_bytes():
                    entries.append(("M" if relative in initial else "A", relative))
        validate_generated_artifacts(stage, entries, {})
        productive_hash_version(staged_records, staged_events)
        if _fingerprint(records, events) != before:
            terminal = True
            reason = "input_changed"
    except Exception:
        terminal = True
        reason = "candidate_validation_failed"
    attempted = len(items)
    accepted = identical + modified
    status = "complete" if accepted == selected else "partial" if accepted else "failed"
    if terminal:
        status = "blocked"
    return RecheckBatchResult(status, selected, attempted, accepted, identical, modified,
        attempted - accepted, selected - attempted, transport.used, reason, tuple(items),
        stage if accepted and not terminal else None)
