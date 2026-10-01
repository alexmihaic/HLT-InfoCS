"""Contratos durables de baseline y selector canónico; sin red ni migración."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from infocs.events import EventStore
from infocs.models import Category, Record
from infocs.store import RecordStore

SCHEMAS = Path(__file__).resolve().parents[4] / "schemas"
MIGRATION_RELATIVE = Path("migrations/bdns/v1-v2")
POLICY_ID = "bdns.enriched-metadata-publication.v2"


class BDNSBaselineError(ValueError):
    """Sólo códigos estáticos; no valores fuente en mensajes."""


def canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def _validate(kind: str, value: dict) -> None:
    try:
        schema = json.loads((SCHEMAS / f"bdns-{kind}.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
        if any(type(value[name]) is not int for name in ("from_content_hash_version", "to_content_hash_version", "target_hash_version", "record_count") if name in value):
            raise ValueError
        stamp = value.get("migrated_at", value.get("completed_at"))
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        if parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != stamp:
            raise ValueError
        if kind == "baseline-transition" and value["from_content_hash"] == value["to_content_hash"]:
            raise ValueError
    except Exception:
        raise BDNSBaselineError("migration_evidence_conflict" if kind == "baseline-transition" else "migration_cutover_marker_invalid") from None


@dataclass(frozen=True, slots=True)
class BDNSBaselineTransition:
    migration_id: str
    record_id: str
    from_content_hash: str
    to_content_hash: str
    migrated_at: str
    software_git_sha: str
    from_record_snapshot_hash: str
    schema_version: str = "1.0"
    source_id: str = "bdns"
    from_content_hash_version: int = 1
    to_content_hash_version: int = 2
    migration_reason: str = "canonical_enrichment_v1_to_v2"
    policy_id: str = POLICY_ID
    target_normalizer_version: str = "2.0.0"
    evidence_contract_version: str = "1.0"

    def __post_init__(self):
        _validate("baseline-transition", asdict(self))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict):
        _validate("baseline-transition", value)
        return cls(**value)


@dataclass(frozen=True, slots=True)
class BDNSCutover:
    migration_id: str
    completed_at: str
    record_count: int
    population_hash: str
    software_git_sha: str
    schema_version: str = "1.0"
    source_id: str = "bdns"
    target_hash_version: int = 2
    target_normalizer_version: str = "2.0.0"
    policy_id: str = POLICY_ID
    evidence_contract_version: str = "1.0"

    def __post_init__(self):
        _validate("cutover", asdict(self))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict):
        _validate("cutover", value)
        return cls(**value)


def evidence_filename(record_id: str) -> str:
    return "t-" + sha256(record_id.encode("utf-8")).hexdigest() + ".json"


def population_hash(evidences: tuple[BDNSBaselineTransition, ...]) -> str:
    return sha256("".join(canonical(item.to_dict()) for item in sorted(evidences, key=lambda item: item.record_id)).encode("utf-8")).hexdigest()


def migration_directory(store: RecordStore) -> Path:
    # Misma raíz data que RecordStore; temporales conservan este layout.
    return store.root.resolve().parent / MIGRATION_RELATIVE


def inventory_records(store: RecordStore) -> tuple[Record, ...]:
    """Incluye todo JSON BDNS, no sólo r-*.json; paths extra se rechazan."""
    directory = store.root / "bdns"
    result = []
    try:
        if directory.is_symlink():
            raise ValueError
        for path in sorted(directory.rglob("*.json")):
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != store.root.parent):
                raise ValueError
            raw = path.read_text(encoding="utf-8")
            record = store.validate(Record.from_json(raw))
            if (record.source.id != "bdns" or record.category is not Category.GRANTS_CALL
                or not record.source.official_id or path.resolve() != store.path_for("bdns", record.id)
                or raw != record.canonical_json() + "\n"):
                raise ValueError
            result.append(record)
        if len({item.id for item in result}) != len(result):
            raise ValueError
        return tuple(result)
    except Exception:
        raise BDNSBaselineError("migration_invalid_inventory") from None


def read_control(store: RecordStore) -> tuple[BDNSCutover | None, tuple[BDNSBaselineTransition, ...]]:
    directory = migration_directory(store)
    if not directory.exists():
        return None, ()
    marker = None
    evidences = []
    try:
        if directory.is_symlink():
            raise ValueError
        for path in sorted(directory.rglob("*")):
            if path.is_symlink() or not path.is_file() or path.parent != directory or path.suffix != ".json":
                raise ValueError
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if path.name == "CUTOVER.json":
                marker = BDNSCutover.from_dict(data)
                obj = marker
            else:
                obj = BDNSBaselineTransition.from_dict(data)
                if path.name != evidence_filename(obj.record_id):
                    raise ValueError
                evidences.append(obj)
            if raw != canonical(obj.to_dict()):
                raise ValueError
        if len({item.record_id for item in evidences}) != len(evidences):
            raise ValueError
    except BDNSBaselineError:
        raise
    except Exception:
        raise BDNSBaselineError("migration_evidence_conflict") from None
    return marker, tuple(evidences)


def validate_control(marker: BDNSCutover, evidences: tuple[BDNSBaselineTransition, ...]) -> None:
    if (marker.record_count != len(evidences) or population_hash(evidences) != marker.population_hash
        or len({item.record_id for item in evidences}) != len(evidences)
        or any(item.migration_id != marker.migration_id or item.migrated_at != marker.completed_at
               or item.software_git_sha != marker.software_git_sha for item in evidences)):
        raise BDNSBaselineError("migration_evidence_conflict")


def productive_hash_version(store: RecordStore, events: EventStore | None = None) -> int:
    """Único selector: marker. Fallo local antes de cualquier petición de fuente."""
    records = inventory_records(store)
    marker, evidence = read_control(store)
    if marker is None:
        if evidence:
            raise BDNSBaselineError("migration_evidence_conflict")
        if any(record.technical.content_hash_version != 1 or record.source_data is not None for record in records):
            raise BDNSBaselineError("migration_mixed_hash_versions")
        return 1
    validate_control(marker, evidence)
    if any(record.technical.content_hash_version != 2 or record.source_data is None for record in records):
        raise BDNSBaselineError("migration_mixed_hash_versions")
    known = {record.id: record for record in records}
    covered = {item.record_id for item in evidence}
    if not covered.issubset(known):
        raise BDNSBaselineError("migration_evidence_conflict")
    completed = datetime.fromisoformat(marker.completed_at.replace("Z", "+00:00"))
    for record in records:
        if record.id not in covered:
            # Nuevos Records posteriores nacen v2: no transición ni evidencia falsa.
            if record.dates.detected_at <= completed:
                raise BDNSBaselineError("migration_evidence_conflict")
    for item in evidence:
        record = known[item.record_id]
        if record.dates.detected_at > completed:
            raise BDNSBaselineError("migration_evidence_conflict")
        if record.technical.content_hash != item.to_content_hash:
            if events is None:
                raise BDNSBaselineError("migration_evidence_conflict")
            reachable = {item.to_content_hash}
            updates = tuple(event for event in events.list_record(record.id) if event.type == "update")
            for _ in range(len(updates)):
                reachable.update(event.content_hash for event in updates if event.previous_content_hash in reachable)
            if record.technical.content_hash not in reachable:
                raise BDNSBaselineError("migration_evidence_conflict")
    return 2
