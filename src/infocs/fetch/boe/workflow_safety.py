"""Validación fail-closed de cambios de datos generados por el workflow BOE."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Iterable

from jsonschema import Draft202012Validator, FormatChecker

from infocs.diff.core import content_hash
from infocs.events import Event, EventStore
from infocs.manifests import ManifestStore, RunManifest, SourceHealth
from infocs.models import Record, validate_record_payload
from infocs.store import RecordStore


_ALLOWED_ROOTS = ("data/records/", "data/events/", "data/manifests/", "data/health/")
_SCHEMA_FOR_ROOT = {
    "data/records/": "record.schema.json",
    "data/events/": "event.schema.json",
    "data/manifests/": "run-manifest.schema.json",
    "data/health/": "source-health.schema.json",
}


class WorkflowSafetyError(ValueError):
    """Un cambio o artefacto generado queda fuera de la política permitida."""


def validate_changed_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """Acepta sólo JSON bajo los cuatro directorios canónicos de datos."""
    normalized: set[str] = set()
    for raw in paths:
        if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
            raise WorkflowSafetyError("Git informó un path no permitido.")
        path = PurePosixPath(raw)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise WorkflowSafetyError("Git informó un path absoluto o con traversal.")
        candidate = path.as_posix()
        if not any(candidate.startswith(prefix) for prefix in _ALLOWED_ROOTS):
            raise WorkflowSafetyError("El workflow detectó cambios fuera de los directorios de datos permitidos.")
        if path.suffix.lower() != ".json":
            raise WorkflowSafetyError("Sólo se permiten artefactos JSON generados.")
        normalized.add(candidate)
    return tuple(sorted(normalized))


def changed_paths_from_git(repo_root: str | Path) -> tuple[str, ...]:
    """Incluye cambios staged/unstaged y ficheros nuevos, sin parsear texto porcelain."""
    root = Path(repo_root)
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "-z", "HEAD"], cwd=root, check=True, capture_output=True
    ).stdout.decode("utf-8").split("\x00")
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=root, check=True, capture_output=True,
    ).stdout.decode("utf-8").split("\x00")
    return validate_changed_paths(path for path in (*tracked, *untracked) if path)


def validate_generated_artifacts(repo_root: str | Path, paths: Iterable[str]) -> tuple[str, ...]:
    """Valida schema, contrato Python y layout de todos los paths observados."""
    root = Path(repo_root).resolve()
    accepted = validate_changed_paths(paths)
    for relative in accepted:
        path = (root / Path(*PurePosixPath(relative).parts)).resolve()
        if root not in path.parents or not path.is_file():
            raise WorkflowSafetyError("Un path generado no existe o sale del repositorio.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        data_root = next(prefix for prefix in _ALLOWED_ROOTS if relative.startswith(prefix))
        schema_path = root / "schemas" / _SCHEMA_FOR_ROOT[data_root]
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

        if data_root == "data/records/":
            record = Record.from_dict(payload)
            validate_record_payload(payload)
            if record.technical.content_hash != content_hash(payload):
                raise WorkflowSafetyError("Un Record no coincide con su content_hash.")
            expected = RecordStore(root / "data" / "records").path_for(record.source.id, record.id)
        elif data_root == "data/events/":
            event = Event.from_dict(payload)
            expected = EventStore(root / "data" / "events").path_for(event.source_id, event.record_id, event.event_id)
        elif data_root == "data/manifests/":
            manifest = RunManifest.from_mapping(payload)
            expected = ManifestStore(root / "data" / "manifests").path_for(manifest)
        else:
            health = SourceHealth.from_mapping(payload)
            if relative != "data/health/boe.json" or health.source_id != "boe":
                raise WorkflowSafetyError("El workflow manual sólo puede materializar Health de BOE.")
            expected = root / "data" / "health" / "boe.json"
        if expected.resolve() != path:
            raise WorkflowSafetyError("El artefacto no está en su ruta canónica.")
    return accepted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida los artefactos generados por una ejecución BOE.")
    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        paths = changed_paths_from_git(args.root)
        validate_generated_artifacts(args.root, paths)
    except Exception as error:
        print(f"Validación de artefactos BOE rechazada: {type(error).__name__}.", file=sys.stderr)
        return 1
    print(f"Artefactos BOE validados: {len(paths)}.")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised in workflow
    raise SystemExit(main())
