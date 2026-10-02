"""Migración separada, preparada primero en staging. Nunca utiliza EventStore."""

import argparse
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import time
import uuid

from infocs.diff.core import content_hash
from infocs.finalize import finalize_record
from infocs.fetch.bdns.baseline import (
    BDNSBaselineError, BDNSBaselineTransition, BDNSCutover, canonical,
    evidence_filename, inventory_records, migration_directory, population_hash,
    read_control, validate_control,
)
from infocs.fetch.bdns.enrichment import prepare_bdns_enriched_record
from infocs.fetch.bdns.ingest import BDNS_ATTRIBUTION_PATH, _attribution_preflight
from infocs.fetch.bdns.models import BDNSConvocatoriaDetail, BDNSConvocatoriaSummary, BDNSRequestStatus, BDNSSearchQuery
from infocs.fetch.bdns.normalize import normalize_bdns_detail
from infocs.fetch.bdns.publication import authorize_bdns_event, evaluate_bdns_publication
from infocs.fetch.bdns.transport import BDNSTransport
from infocs.models import Record
from infocs.store import RecordStore

PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Códigos reales del preflight; nunca mensajes arbitrarios ni valores fuente.
SAFE_ENRICHMENT_DETAIL_REASONS = frozenset({
    "enrichment_invalid_model", "enrichment_invalid_decimal",
    "enrichment_duplicate_document_id", "enrichment_invalid_document_metadata",
    "enrichment_invalid_url", "enrichment_missing_required_label",
    "enrichment_contract_invalid", "enrichment_territorial_not_included",
    "enrichment_record_preflight_failed", "privacy_source_data_blocked",
    "publication_source_data_hold",
})


@dataclass(frozen=True, slots=True)
class FreshBDNSObservation:
    summary: BDNSConvocatoriaSummary
    detail: BDNSConvocatoriaDetail


@dataclass(frozen=True, slots=True)
class BDNSMigrationBatch:
    originals: tuple[Record, ...]
    prepared: tuple[Record, ...]
    evidences: tuple[BDNSBaselineTransition, ...]
    marker: BDNSCutover


@dataclass(frozen=True, slots=True)
class BDNSMigrationResult:
    status: str
    migration_id: str
    inventory_count: int = 0
    fresh_detail_count: int = 0
    summary_resolved_count: int = 0
    v1_match_count: int = 0
    v2_prepared_count: int = 0
    privacy_allowed_count: int = 0
    publication_approved_count: int = 0
    authorization_count: int = 0
    evidence_count: int = 0
    request_count: int = 0
    safe_reason: str | None = None
    safe_detail_reason: str | None = None
    failure_position: int | None = None
    batch: BDNSMigrationBatch | None = None

    def __post_init__(self):
        if self.safe_detail_reason is not None and (
            not isinstance(self.safe_detail_reason, str)
            or self.safe_detail_reason not in SAFE_ENRICHMENT_DETAIL_REASONS
        ):
            raise ValueError("migration_safe_result_invalid")
        if self.failure_position is not None and (
            type(self.failure_position) is not int or self.failure_position < 1
        ):
            raise ValueError("migration_safe_result_invalid")
        if self.status != "blocked" and (
            self.safe_detail_reason is not None or self.failure_position is not None
        ):
            raise ValueError("migration_safe_result_invalid")

    def to_dict(self):
        return {field.name: getattr(self, field.name) for field in fields(self) if field.name != "batch"}


def _snapshot(record: Record) -> str:
    return sha256((record.canonical_json() + "\n").encode("utf-8")).hexdigest()


def _stamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise BDNSBaselineError("migration_invalid_timestamp")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def inventory_for_migration(store: RecordStore):
    records = inventory_records(store)
    marker, evidence = read_control(store)
    if not records:
        raise BDNSBaselineError("migration_invalid_inventory")
    if marker is None:
        if evidence:
            raise BDNSBaselineError("migration_evidence_conflict")
        if any(record.technical.content_hash_version != 1 or record.source_data is not None for record in records):
            raise BDNSBaselineError("migration_mixed_hash_versions")
    else:
        validate_control(marker, evidence)
        if ({record.id for record in records} != {item.record_id for item in evidence}
            or any(record.technical.content_hash_version != 2 for record in records)
            or any(next(r for r in records if r.id == item.record_id).technical.content_hash != item.to_content_hash for item in evidence)):
            raise BDNSBaselineError("migration_evidence_conflict")
    return records, marker, evidence


def collect_fresh_observation(record: Record, client, request, *, max_search_pages: int = 5) -> FreshBDNSObservation:
    """Filtro oficial por código, join exacto y control; sin filtro temporal."""
    from infocs.fetch.bdns.runner import _page_contract_valid

    code = record.source.official_id
    first_detail = request(lambda: client.fetch_detail(code))
    if first_detail.status is not BDNSRequestStatus.SUCCESS or first_detail.payload is None or first_detail.payload.codigo_bdns != code:
        raise BDNSBaselineError("migration_detail_failure")
    query = BDNSSearchQuery(page_size=50, numero_convocatoria=code, order="numeroConvocatoria", direction="asc")
    first = request(lambda: client.search(query))
    if first.status is not BDNSRequestStatus.SUCCESS or first.payload is None:
        raise BDNSBaselineError("migration_summary_not_resolved")
    page = first.payload
    if not _page_contract_valid(page, expected_page=0, page_size=50) or not 1 <= page.total_pages <= max_search_pages:
        raise BDNSBaselineError("migration_summary_not_resolved")
    initial = page
    summaries = []
    for index in range(page.total_pages):
        if index:
            fetched = request(lambda: client.search(replace(query, page=index)))
            if fetched.status is not BDNSRequestStatus.SUCCESS or fetched.payload is None:
                raise BDNSBaselineError("migration_summary_not_resolved")
            page = fetched.payload
        if (not _page_contract_valid(page, expected_page=index, page_size=50)
            or (page.total_pages, page.total_elements) != (initial.total_pages, initial.total_elements)):
            raise BDNSBaselineError("migration_summary_not_resolved")
        summaries.extend(page.items)
    if len(summaries) != initial.total_elements or len({item.numero_convocatoria for item in summaries}) != len(summaries):
        raise BDNSBaselineError("migration_summary_not_resolved")
    exact = tuple(item for item in summaries if item.numero_convocatoria == code)
    if len(exact) != 1:
        raise BDNSBaselineError("migration_summary_not_resolved")
    control = request(lambda: client.search(query))
    if control.status is not BDNSRequestStatus.SUCCESS or control.payload != initial:
        raise BDNSBaselineError("migration_summary_not_resolved")
    # No snapshot SNPSAP: detección conservadora de cambios durante resolución.
    second_detail = request(lambda: client.fetch_detail(code))
    if second_detail.status is not BDNSRequestStatus.SUCCESS or second_detail.payload != first_detail.payload:
        raise BDNSBaselineError("migration_detail_failure")
    return FreshBDNSObservation(exact[0], first_detail.payload)


def prepare_baseline_migration(*, record_store: RecordStore, transport,
    migration_id: str, software_git_sha: str, clock=lambda: datetime.now(UTC),
    monotonic=time.monotonic, attribution_path: Path = BDNS_ATTRIBUTION_PATH) -> BDNSMigrationResult:
    """Preflight global en memoria; no Record write ni Event/Manifest/Health."""
    counts = {name: 0 for name in ("inventory_count", "fresh_detail_count", "summary_resolved_count",
        "v1_match_count", "v2_prepared_count", "privacy_allowed_count", "publication_approved_count",
        "authorization_count", "evidence_count", "request_count")}
    detail_reason = None
    failure_position = None
    try:
        # Validar identidad/versiones software antes de cualquier red.
        BDNSCutover(migration_id, _stamp(clock()), 1, "0" * 64, software_git_sha)
        if not _attribution_preflight(attribution_path):
            raise BDNSBaselineError("migration_attribution_blocked")
        originals, marker, evidence = inventory_for_migration(record_store)
        counts["inventory_count"] = len(originals)
        if not originals:
            raise BDNSBaselineError("migration_invalid_inventory")
        marker, evidence = read_control(record_store)
        if marker is not None:
            validate_control(marker, evidence)
            if (len(originals) != len(evidence) or {item.id for item in originals} != {item.record_id for item in evidence}
                or any(item.technical.content_hash_version != 2 for item in originals)
                or any(next(item for item in originals if item.id == e.record_id).technical.content_hash != e.to_content_hash for e in evidence)):
                raise BDNSBaselineError("migration_evidence_conflict")
            return BDNSMigrationResult("already_migrated", marker.migration_id, inventory_count=len(originals))
        if evidence:
            raise BDNSBaselineError("migration_evidence_conflict")
        if any(item.technical.content_hash_version != 1 or item.source_data is not None for item in originals):
            raise BDNSBaselineError("migration_mixed_hash_versions")
        started = monotonic()

        def request(operation):
            # InfoCs D2 limits: 2 details + <=5 search pages + control per inventory ID.
            if counts["request_count"] >= 8 * len(originals) or monotonic() - started >= 600:
                raise BDNSBaselineError("migration_budget_exhausted")
            counts["request_count"] += 1
            result = operation()
            if monotonic() - started >= 600:
                raise BDNSBaselineError("migration_budget_exhausted")
            return result

        observations = []
        for old in originals:
            observation = collect_fresh_observation(old, transport, request)
            observations.append(observation)
            counts["fresh_detail_count"] += 1
            counts["summary_resolved_count"] += 1
        observed_at = clock()
        for old, observation in zip(originals, observations, strict=True):
            normalized = normalize_bdns_detail(observation.summary, observation.detail,
                detected_at=old.dates.detected_at, last_checked_at=observed_at)
            if normalized.candidate is None:
                raise BDNSBaselineError("migration_v1_source_drift")
            fresh = finalize_record(normalized.candidate)
            if (fresh.id != old.id or fresh.source != old.source or fresh.technical.identity_strategy != old.technical.identity_strategy
                or fresh.technical.content_hash != old.technical.content_hash):
                raise BDNSBaselineError("migration_v1_source_drift")
            counts["v1_match_count"] += 1
        prepared = []
        for position, (old, observation) in enumerate(zip(originals, observations, strict=True), start=1):
            result = prepare_bdns_enriched_record(observation.summary, observation.detail,
                detected_at=old.dates.detected_at, last_checked_at=observed_at, record_store=record_store)
            # Proyección cerrada: un nuevo código requiere revisión explícita.
            detail_reason = result.safe_reason if (
                isinstance(result.safe_reason, str)
                and result.safe_reason in SAFE_ENRICHMENT_DETAIL_REASONS
            ) else None
            failure_position = position
            if result.record is None:
                raise BDNSBaselineError("migration_enrichment_blocked")
            if result.privacy is None or result.privacy.decision.value != "allow":
                raise BDNSBaselineError("migration_privacy_blocked")
            counts["privacy_allowed_count"] += 1
            if result.publication is None or result.publication.metadata_publication is None or result.publication.metadata_publication.decision.value != "publishable_metadata":
                raise BDNSBaselineError("migration_publication_blocked")
            counts["publication_approved_count"] += 1
            if result.safe_reason is not None or result.authorization is None or not result.authorization.matches(result.record):
                raise BDNSBaselineError("migration_publication_blocked")
            counts["authorization_count"] += 1
            if result.record.id != old.id or result.record.dates.detected_at != old.dates.detected_at:
                raise BDNSBaselineError("migration_incomplete_batch")
            prepared.append(result.record)
            counts["v2_prepared_count"] += 1
        completed = _stamp(clock())
        if monotonic() - started >= 600 or datetime.fromisoformat(completed.replace("Z", "+00:00")) < observed_at:
            raise BDNSBaselineError("migration_budget_exhausted")
        evidence = tuple(BDNSBaselineTransition(migration_id, old.id, old.technical.content_hash,
            new.technical.content_hash, completed, software_git_sha, _snapshot(old)) for old, new in zip(originals, prepared, strict=True))
        counts["evidence_count"] = len(evidence)
        marker = BDNSCutover(migration_id, completed, len(evidence), population_hash(evidence), software_git_sha)
        if any(counts[name] != len(originals) for name in counts if name != "request_count"):
            raise BDNSBaselineError("migration_incomplete_batch")
        batch = BDNSMigrationBatch(originals, tuple(prepared), evidence, marker)
        validate_batch(batch, record_store)
        return BDNSMigrationResult("prepared", migration_id, **counts, batch=batch)
    except BDNSBaselineError as error:
        reason = str(error)
        preflight_blocked = reason in {
            "migration_enrichment_blocked", "migration_privacy_blocked", "migration_publication_blocked",
        }
        return BDNSMigrationResult("blocked", migration_id, **counts, safe_reason=reason,
            safe_detail_reason=detail_reason if preflight_blocked else None,
            failure_position=failure_position if preflight_blocked else None)
    except Exception:
        return BDNSMigrationResult("blocked", migration_id, **counts, safe_reason="migration_preflight_failed")


def validate_batch(batch: BDNSMigrationBatch, store: RecordStore) -> None:
    validate_control(batch.marker, batch.evidences)
    if not (len(batch.originals) == len(batch.prepared) == len(batch.evidences) == batch.marker.record_count):
        raise BDNSBaselineError("migration_incomplete_batch")
    original = {item.id: item for item in batch.originals}
    prepared = {item.id: item for item in batch.prepared}
    if len(original) != batch.marker.record_count or set(original) != set(prepared):
        raise BDNSBaselineError("migration_incomplete_batch")
    for e in batch.evidences:
        if e.record_id not in original:
            raise BDNSBaselineError("migration_evidence_conflict")
        old, new = original[e.record_id], prepared[e.record_id]
        if (old.technical.content_hash_version != 1 or new.technical.content_hash_version != 2
            or old.source != new.source or old.dates.detected_at != new.dates.detected_at
            or e.from_content_hash != old.technical.content_hash or e.to_content_hash != new.technical.content_hash
            or e.from_record_snapshot_hash != _snapshot(old)):
            raise BDNSBaselineError("migration_evidence_conflict")
        raw = new.to_dict()
        raw.pop("source_data")
        raw["technical"].pop("content_hash_version")
        if content_hash(raw) != e.from_content_hash:
            raise BDNSBaselineError("migration_v1_source_drift")
        store.validate(new)
        evaluation = evaluate_bdns_publication(new, store.privacy_gate.evaluate(new))
        authorization = authorize_bdns_event(new, evaluation)
        if authorization is None or not authorization.matches(new):
            raise BDNSBaselineError("migration_publication_blocked")


def stage_batch(batch: BDNSMigrationBatch, data_root: Path) -> None:
    """Staging explícito vacío, nunca data productivo. All gates antes de I/O."""
    root = Path(data_root).resolve()
    if root == PROJECT_ROOT or PROJECT_ROOT in root.parents or root in PROJECT_ROOT.parents:
        raise BDNSBaselineError("migration_invalid_staging")
    if root.exists() and any(root.iterdir()):
        raise BDNSBaselineError("migration_invalid_staging")
    store = RecordStore(root / "records")
    validate_batch(batch, store)
    for record in batch.prepared:
        store.write(record)
    directory = migration_directory(store)
    directory.mkdir(parents=True, exist_ok=True)
    for evidence in batch.evidences:
        with (directory / evidence_filename(evidence.record_id)).open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical(evidence.to_dict()))
    with (directory / "CUTOVER.json").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical(batch.marker.to_dict()))
    validate_staged_tree(root)


def validate_staged_tree(data_root: Path) -> tuple[tuple[Record, ...], BDNSCutover, tuple[BDNSBaselineTransition, ...]]:
    root = Path(data_root).resolve()
    store = RecordStore(root / "records")
    records = inventory_records(store)
    marker, evidence = read_control(store)
    if marker is None:
        raise BDNSBaselineError("migration_cutover_marker_invalid")
    validate_control(marker, evidence)
    by_id = {item.id: item for item in records}
    if set(by_id) != {item.record_id for item in evidence}:
        raise BDNSBaselineError("migration_incomplete_batch")
    allowed = {store.path_for("bdns", item.id) for item in records}
    directory = migration_directory(store)
    allowed.update(directory / evidence_filename(item.record_id) for item in evidence)
    allowed.add(directory / "CUTOVER.json")
    actual = {path.resolve() for path in root.rglob("*") if path.is_file()}
    if actual != allowed or any(path.is_symlink() for path in root.rglob("*")):
        raise BDNSBaselineError("migration_invalid_staging")
    for e in evidence:
        record = by_id[e.record_id]
        if record.technical.content_hash_version != 2 or record.technical.content_hash != e.to_content_hash:
            raise BDNSBaselineError("migration_evidence_conflict")
        evaluation = evaluate_bdns_publication(record, store.privacy_gate.evaluate(record))
        if authorize_bdns_event(record, evaluation) is None:
            raise BDNSBaselineError("migration_publication_blocked")
    return records, marker, evidence


def materialize_staged_tree(staged_data_root: Path, target: RecordStore) -> str:
    """Escritura futura D2 explícita. No transacción; mixed state nunca publicable."""
    records, marker, evidence = validate_staged_tree(staged_data_root)
    current = inventory_records(target)
    prior_marker, prior_evidence = read_control(target)
    if prior_marker is not None:
        if prior_marker != marker or prior_evidence != evidence or {r.canonical_json() for r in current} != {r.canonical_json() for r in records}:
            raise BDNSBaselineError("migration_evidence_conflict")
        return "already_migrated"
    if prior_evidence or set(item.id for item in current) != set(item.id for item in records):
        raise BDNSBaselineError("migration_incomplete_batch")
    if any(item.technical.content_hash_version != 1 for item in current):
        raise BDNSBaselineError("migration_mixed_hash_versions")
    batch = BDNSMigrationBatch(current, records, evidence, marker)
    validate_batch(batch, target)  # Recomprueba snapshots completos frente a cualquier write.
    directory = migration_directory(target)
    for record in records:
        target.write(record)
    directory.mkdir(parents=True, exist_ok=True)
    for item in evidence:
        with (directory / evidence_filename(item.record_id)).open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical(item.to_dict()))
    with (directory / "CUTOVER.json").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical(marker.to_dict()))
    return "materialized"


def validate_migration_entries(entries, target: RecordStore, *, base_ref: str | None = None, repo_root: Path | None = None) -> tuple[str, ...]:
    """Commit/staging exactos; replacements + evidencias + marker, nunca Events."""
    marker, evidence = read_control(target)
    if marker is None:
        raise BDNSBaselineError("migration_cutover_marker_invalid")
    validate_control(marker, evidence)
    records = inventory_records(target)
    if set(item.id for item in records) != {item.record_id for item in evidence}:
        raise BDNSBaselineError("migration_incomplete_batch")
    expected = {}
    for item in evidence:
        record = next(r for r in records if r.id == item.record_id)
        if record.technical.content_hash != item.to_content_hash or record.technical.content_hash_version != 2:
            raise BDNSBaselineError("migration_evidence_conflict")
        root = target.root.resolve().parent.parent
        expected[target.path_for("bdns", record.id).relative_to(root).as_posix()] = "M"
        expected[(migration_directory(target) / evidence_filename(item.record_id)).relative_to(root).as_posix()] = "A"
    expected[(migration_directory(target) / "CUTOVER.json").relative_to(root).as_posix()] = "A"
    entries = tuple(entries)
    if len(entries) != len(expected) or {path: status for status, path in entries} != expected:
        raise BDNSBaselineError("migration_incomplete_batch")
    if base_ref is not None:
        from infocs.fetch.bdns.workflow_safety import _git
        olds = []
        for item in evidence:
            path = target.path_for("bdns", item.record_id).relative_to(root).as_posix()
            raw = _git(repo_root or root, "show", f"{base_ref}:{path}").stdout
            olds.append(Record.from_json(raw))
        validate_batch(BDNSMigrationBatch(tuple(olds), records, evidence, marker), target)
    return tuple(sorted(expected))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BDNS baseline tooling; ejecutar prepare sólo en D2 autorizado")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--staged-data-root", required=True)
    prepare.add_argument("--git-sha", required=True)
    materialize = sub.add_parser("materialize")
    materialize.add_argument("--staged-data-root", required=True)
    validate = sub.add_parser("validate-git")
    validate.add_argument("--base-ref", required=True)
    validate.add_argument("--commit")
    args = parser.parse_args(argv)
    store = RecordStore(PROJECT_ROOT / "data" / "records")
    try:
        if args.command == "inventory":
            records, marker, _ = inventory_for_migration(store)
            print(json.dumps({"status": "already_migrated" if marker else "inventoried", "inventory_count": len(records)}))
        elif args.command == "prepare":
            result = prepare_baseline_migration(record_store=store, transport=BDNSTransport(),
                migration_id="bdns-v1-v2-" + str(uuid.uuid4()), software_git_sha=args.git_sha)
            if result.batch is not None:
                stage_batch(result.batch, Path(args.staged_data_root))
            print(json.dumps(result.to_dict()))
            return 0 if result.status in {"prepared", "already_migrated"} else 1
        elif args.command == "materialize":
            print(json.dumps({"status": materialize_staged_tree(Path(args.staged_data_root), store)}))
        else:
            from infocs.fetch.bdns.workflow_safety import _git_name_status
            entries = _git_name_status(PROJECT_ROOT, "diff-tree", "--no-commit-id", "--name-status", "-z", "--no-renames", "-r", args.commit) if args.commit else _git_name_status(PROJECT_ROOT, "diff", "--cached", "--name-status", "-z", "--no-renames")
            validate_migration_entries(entries, store, base_ref=args.base_ref)
            print(json.dumps({"status": "validated", "artifact_count": len(entries)}))
        return 0
    except Exception as error:
        reason = str(error) if isinstance(error, BDNSBaselineError) else "migration_preflight_failed"
        print(json.dumps({"status": "blocked", "safe_reason": reason}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
