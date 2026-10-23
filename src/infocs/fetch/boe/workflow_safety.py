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
from infocs.events import Event, EventStore, event_identity
from infocs.manifests import ManifestStore, RunManifest, SourceHealth, derive_source_health
from infocs.fetch.boe.history import validate_boe_history
from infocs.models import Record, validate_record_payload
from infocs.fetch.boe.review_queue import validate_review_queue_payload
from infocs.store import RecordStore


_ALLOWED_ROOTS = ("data/records/", "data/events/", "data/manifests/", "data/health/", "data/review/")
_SCHEMA_FOR_ROOT = {
    "data/records/": "record.schema.json",
    "data/events/": "event.schema.json",
    "data/manifests/": "run-manifest.schema.json",
    "data/health/": "source-health.schema.json",
    "data/review/": "review-queue.schema.json",
}


class WorkflowSafetyError(ValueError):
    """Un cambio o artefacto generado queda fuera de la política permitida."""


def validate_changed_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """Acepta sólo JSON bajo los directorios de artefactos permitidos."""
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
            if record.source.id != "boe":
                raise WorkflowSafetyError("record_source_invalid")
            validate_record_payload(payload)
            if record.technical.content_hash != content_hash(payload):
                raise WorkflowSafetyError("Un Record no coincide con su content_hash.")
            expected = RecordStore(root / "data" / "records").path_for(record.source.id, record.id)
        elif data_root == "data/events/":
            event = Event.from_dict(payload)
            if event.source_id != "boe":
                raise WorkflowSafetyError("event_source_invalid")
            expected = EventStore(root / "data" / "events").path_for(event.source_id, event.record_id, event.event_id)
        elif data_root == "data/manifests/":
            manifest = RunManifest.from_mapping(payload)
            if manifest.source_id != "boe":
                raise WorkflowSafetyError("manifest_source_invalid")
            expected = ManifestStore(root / "data" / "manifests").path_for(manifest)
        else:
            if data_root == "data/health/":
                health = SourceHealth.from_mapping(payload)
                if relative != "data/health/boe.json" or health.source_id != "boe":
                    raise WorkflowSafetyError("El workflow sólo puede materializar Health de BOE.")
                expected = root / "data" / "health" / "boe.json"
            else:
                validate_review_queue_payload(payload)
                if relative != "data/review/boe/pending.json":
                    raise WorkflowSafetyError("La review queue sólo puede materializarse en su ruta BOE canónica.")
                expected = root / "data" / "review" / "boe" / "pending.json"
        if expected.resolve() != path:
            raise WorkflowSafetyError("El artefacto no está en su ruta canónica.")
    return accepted


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout


def _head_bytes(root: Path, relative: str) -> bytes | None:
    # A missing HEAD path is expected for a newly generated artifact; all other
    # Git errors must block rather than being mistaken for an absent Record.
    tracked = _git(root, "ls-tree", "--name-only", "-z", "HEAD", "--", relative)
    return _git(root, "show", f"HEAD:{relative}") if tracked else None


def stage_validated_artifacts(repo_root: str | Path, runner_exit_code: int) -> tuple[str, ...]:
    """Publication barrier. Never discard partial work or stage whole data roots.

    Failure selects only validated failed observability; success additionally
    checks the whole BOE history and the exact transition from the public HEAD.
    An existing index is forbidden, including otherwise allowed partial data.
    """
    root = Path(repo_root).resolve()
    if type(runner_exit_code) is not int or not 0 <= runner_exit_code <= 255:
        raise WorkflowSafetyError("runner_exit_code_invalid")
    if _git(root, "diff", "--cached", "--name-only", "-z", "HEAD"):
        raise WorkflowSafetyError("index_not_empty")
    paths = changed_paths_from_git(root)
    for relative in paths:
        if not relative.startswith(("data/records/boe/", "data/events/boe/", "data/manifests/boe/")) and relative not in {
            "data/health/boe.json", "data/review/boe/pending.json",
        }:
            raise WorkflowSafetyError("changed_path_not_boe")
        path = root / relative
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
            raise WorkflowSafetyError("deleted_or_symlink_artifact")
        if relative.startswith(("data/events/", "data/manifests/")) and _head_bytes(root, relative) is not None:
            raise WorkflowSafetyError("append_only_artifact_modified")
    selected = tuple(p for p in paths if runner_exit_code == 0 or p.startswith(("data/manifests/boe/", "data/health/")))
    validated = {p: (root / p).read_bytes() for p in selected}
    validate_generated_artifacts(root, selected)
    manifests = [RunManifest.from_mapping(json.loads((root / p).read_bytes()))
                 for p in selected if p.startswith("data/manifests/")]
    if len(manifests) != 1 or "data/health/boe.json" not in selected:
        raise WorkflowSafetyError("run_observability_missing_or_ambiguous")
    manifest = manifests[0]
    if (manifest.status.value == "failed") != (runner_exit_code != 0):
        raise WorkflowSafetyError("manifest_exit_code_mismatch")
    history = ManifestStore(root / "data/manifests").list_source("boe")
    expected_health = derive_source_health(history, source_id="boe")
    health = SourceHealth.from_mapping(json.loads((root / "data/health/boe.json").read_bytes()))
    if health.to_dict() != expected_health.to_dict() or health.last_run_id != manifest.run_id:
        raise WorkflowSafetyError("health_manifest_history_mismatch")
    if runner_exit_code == 0:
        validate_boe_history(root)
        events = {e.event_id: e for e in EventStore(root / "data/events").list_source("boe")}
        expected_events = set()
        for relative in selected:
            if not relative.startswith("data/records/"):
                continue
            current = Record.from_dict(json.loads((root / relative).read_bytes()))
            previous_bytes = _head_bytes(root, relative)
            previous = Record.from_dict(json.loads(previous_bytes)) if previous_bytes is not None else None
            old_hash = previous.technical.content_hash if previous is not None else None
            if previous is not None and (previous.id != current.id or previous.source.id != "boe"):
                raise WorkflowSafetyError("record_identity_changed")
            if old_hash == current.technical.content_hash:
                continue
            identity = event_identity(current.id, "update" if previous else "create", current.technical.content_hash, old_hash)
            if identity not in events:
                raise WorkflowSafetyError("record_transition_event_missing")
            expected_events.add(identity)
        for relative in selected:
            if relative.startswith("data/events/") and Path(relative).stem not in expected_events:
                raise WorkflowSafetyError("event_without_published_transition")
    # Validate everything before touching the index; then prove staged bytes are
    # exactly the bytes validated above, not partial artifacts left in the tree.
    if any((root / p).read_bytes() != validated[p] for p in selected):
        raise WorkflowSafetyError("artifact_changed_during_validation")
    if selected:
        _git(root, "add", "--", *selected)
    staged = tuple(sorted(p for p in _git(root, "diff", "--cached", "--name-only", "-z", "HEAD").decode("utf-8").split("\0") if p))
    if staged != selected or any(_git(root, "show", f":{p}") != validated[p] for p in selected):
        raise WorkflowSafetyError("staged_artifact_mismatch")
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida los artefactos generados por una ejecución BOE.")
    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)
    parser.add_argument("--runner-exit-code", type=int, help="Valida y prepara sólo los artefactos publicables.")
    args = parser.parse_args(argv)
    try:
        if args.runner_exit_code is None:
            paths = changed_paths_from_git(args.root)
            validate_generated_artifacts(args.root, paths)
        else:
            paths = stage_validated_artifacts(args.root, args.runner_exit_code)
    except Exception as error:
        print(f"Validación de artefactos BOE rechazada: {type(error).__name__}.", file=sys.stderr)
        return 1
    print(f"Artefactos BOE validados: {len(paths)}.")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised in workflow
    raise SystemExit(main())
