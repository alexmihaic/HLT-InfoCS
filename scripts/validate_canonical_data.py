"""Valida todos los artefactos canónicos públicos de ``data/`` en CI.

Reutiliza los contratos existentes (JSON Schema en ``schemas/`` y los stores y
modelos de ``infocs``) para que la validación no diverja de la escritura. Es de
sólo lectura y no consulta la red. Los diagnósticos son públicos en CI: nunca
incluyen payloads, identificadores oficiales ni rutas que los contengan. Cada
fallo se identifica por tipo de artefacto, fuente y ordinal del archivo dentro
de esa fuente (orden lexicográfico de rutas), más un código de causa.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from infocs.diff.core import content_hash
from infocs.events import EventStore
from infocs.fetch.boe.review_queue import validate_review_queue_payload
from infocs.fetch.boe.history import BOEHistoryError, validate_boe_history
from infocs.manifests import ManifestStore, RunManifest, SourceHealth
from infocs.models import Record, validate_record_payload
from infocs.store import RecordStore


_SCHEMAS = {
    "records": "record.schema.json",
    "events": "event.schema.json",
    "manifests": "run-manifest.schema.json",
    "health": "source-health.schema.json",
    "review": "review-queue.schema.json",
}


class CanonicalDataError(ValueError):
    """Un artefacto canónico no cumple su contrato."""


_SAFE_SEGMENT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_SAFE_FIELD = re.compile(r"[a-z_][a-z0-9_]{0,63}\Z")


def _safe_segment(value: str) -> str:
    return value if _SAFE_SEGMENT.match(value) else "?"


def artifact_label(data: Path, path: Path, ordinals: dict[Path, int]) -> str:
    """Etiqueta pública sin identificadores: ``tipo/fuente#ordinal``."""
    parts = path.relative_to(data).parts
    kind = _safe_segment(parts[0]) if parts else "?"
    if kind == "health":
        source = _safe_segment(path.stem)
    else:
        source = _safe_segment(parts[1]) if len(parts) > 2 or (len(parts) == 2 and path.is_dir()) else "-"
    ordinal = ordinals.get(path)
    return f"{kind}/{source}" + (f"#{ordinal}" if ordinal is not None else "")


def failure_reason(error: Exception) -> str:
    """Código de causa sin valores de datos."""
    if isinstance(error, CanonicalDataError):
        return f"CanonicalDataError({error})"
    if isinstance(error, ValidationError):
        field = ".".join(
            str(part) if isinstance(part, int) or _SAFE_FIELD.match(str(part)) else "*"
            for part in error.absolute_path
        ) or "raíz"
        return f"SchemaValidationError({error.validator}@{field})"
    return type(error).__name__


def _ordinals(files: list[Path], data: Path) -> dict[Path, int]:
    counters: dict[tuple[str, ...], int] = {}
    result: dict[Path, int] = {}
    for path in files:
        group = path.relative_to(data).parts[:2]
        counters[group] = counters.get(group, 0) + 1
        result[path] = counters[group]
    return result


def _json_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*.json") if path.is_file())


def _validator(root: Path, kind: str) -> Draft202012Validator:
    schema = json.loads((root / "schemas" / _SCHEMAS[kind]).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_canonical_data(root: Path) -> dict[str, int]:
    """Devuelve conteos por tipo; acumula errores y los lanza al final."""
    data = root / "data"
    errors: list[str] = []
    counts = {kind: 0 for kind in _SCHEMAS}
    record_hashes: dict[str, str] = {}

    ordinals: dict[Path, int] = {}
    for kind in _SCHEMAS:
        ordinals.update(_ordinals(_json_files(data / kind), data))

    def fail(path: Path, error: Exception) -> None:
        errors.append(f"{artifact_label(data, path, ordinals)}: {failure_reason(error)}")

    record_store = RecordStore(data / "records")
    record_schema = _validator(root, "records")
    for path in _json_files(data / "records"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            record_schema.validate(payload)
            validate_record_payload(payload)
            record = Record.from_dict(payload)
            if record.technical.content_hash != content_hash(payload):
                raise CanonicalDataError("content_hash")
            if record_store.path_for(record.source.id, record.id) != path.resolve():
                raise CanonicalDataError("non_canonical_path")
            if record.id in record_hashes:
                raise CanonicalDataError("duplicate_record_id")
            record_hashes[record.id] = record.technical.content_hash
            counts["records"] += 1
        except Exception as error:  # noqa: BLE001 - diagnóstico agregado
            fail(path, error)

    event_store = EventStore(data / "events")
    event_schema = _validator(root, "events")
    for path in _json_files(data / "events"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            event_schema.validate(payload)
            counts["events"] += 1
        except Exception as error:  # noqa: BLE001
            fail(path, error)
    # list_source valida serialización canónica, identidad determinista y ruta.
    event_sources = sorted(p for p in (data / "events").iterdir() if p.is_dir()) if (data / "events").is_dir() else []
    for source_dir in event_sources:
        try:
            for event in event_store.list_source(source_dir.name):
                # El último Event no tiene por qué coincidir con el hash actual:
                # la migración BDNS v1→v2 conservó los Events v1 sin crear otros.
                if event.record_id not in record_hashes:
                    raise CanonicalDataError("event_without_record")
        except Exception as error:  # noqa: BLE001
            fail(source_dir, error)

    # BOE only: BDNS retains its documented v1→v2 historical hash exception.
    try:
        validate_boe_history(root)
    except BOEHistoryError as error:
        errors.append(f"events/boe: {error}")
    except Exception:
        errors.append("events/boe: history_validation_failed")

    manifest_store = ManifestStore(data / "manifests")
    manifest_schema = _validator(root, "manifests")
    for path in _json_files(data / "manifests"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            manifest_schema.validate(payload)
            manifest = RunManifest.from_mapping(payload)
            if manifest_store.path_for(manifest) != path.resolve():
                raise CanonicalDataError("non_canonical_path")
            counts["manifests"] += 1
        except Exception as error:  # noqa: BLE001
            fail(path, error)

    health_schema = _validator(root, "health")
    for path in _json_files(data / "health"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            health_schema.validate(payload)
            health = SourceHealth.from_mapping(payload)
            if path.name != f"{health.source_id}.json":
                raise CanonicalDataError("non_canonical_path")
            counts["health"] += 1
        except Exception as error:  # noqa: BLE001
            fail(path, error)

    for path in _json_files(data / "review"):
        try:
            validate_review_queue_payload(json.loads(path.read_text(encoding="utf-8")))
            counts["review"] += 1
        except Exception as error:  # noqa: BLE001
            fail(path, error)

    if errors:
        raise CanonicalDataError("\n".join(errors))
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida los artefactos canónicos públicos de data/.")
    parser.add_argument("--root", default=".", help="Raíz del repositorio.")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        counts = validate_canonical_data(root)
    except CanonicalDataError as error:
        print("Validación de datos canónicos rechazada:", file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 1
    summary = ", ".join(f"{kind}={count}" for kind, count in counts.items())
    print(f"Datos canónicos válidos: {summary}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
