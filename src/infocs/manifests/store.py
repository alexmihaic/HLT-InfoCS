"""Almacén append-only de Run Manifests JSON."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote

from infocs.manifests.model import ManifestValidationError, RunManifest, validate_manifest_payload


_RUN_ID_RE = re.compile(r"run-v1-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_SOURCE_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


class ManifestStoreError(ValueError):
    """Error seguro del almacén de manifests."""


class ManifestStoreConflictError(ManifestStoreError):
    """run_id existente asociado a un contenido distinto."""


class ManifestStore:
    """Store pequeño, sin ruta productiva implícita y append-only."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    def path_for(self, manifest: RunManifest) -> Path:
        if not isinstance(manifest, RunManifest):
            raise ManifestStoreError("path_for requiere un RunManifest validado.")
        source = manifest.source_id
        if not _SOURCE_ID_RE.fullmatch(source) or not _RUN_ID_RE.fullmatch(manifest.run_id):
            raise ManifestStoreError("Identificadores del manifest no válidos.")
        year, month = manifest.started_at[:4], manifest.started_at[5:7]
        path = (self.root / quote(source, safe="-_.") / year / month / f"{manifest.run_id}.json").resolve()
        root = self.root.resolve()
        if root != path and root not in path.parents:
            raise ManifestStoreError("El path calculado queda fuera del almacén.")
        return path

    def get(self, run_id: str) -> RunManifest | None:
        if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id) or not self.root.is_dir():
            return None
        matches = tuple(sorted(self.root.glob(f"**/{run_id}.json")))
        if len(matches) > 1:
            raise ManifestStoreError("run_id aparece en más de una ruta.")
        return self._read(matches[0]) if matches else None

    def exists(self, run_id: str) -> bool:
        return self.get(run_id) is not None

    def write(self, manifest: RunManifest) -> bool:
        """Añade el manifest; devuelve False ante repetición idéntica."""
        try:
            validated = validate_manifest_payload(manifest.to_dict())
        except Exception:
            raise ManifestStoreError("RunManifest inválido; no se escribió.") from None
        path = self.path_for(validated)
        previous = self.get(validated.run_id)
        if previous is not None:
            if previous.canonical_json() != validated.canonical_json():
                raise ManifestStoreConflictError("run_id existente con contenido diferente.")
            if self.path_for(previous) != path:
                raise ManifestStoreConflictError("run_id existente con una ruta incompatible.")
            return False

        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            temp_path = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(validated.canonical_json() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._read(temp_path)
            try:
                os.link(temp_path, path)
                created = True
            except FileExistsError:
                existing = self._read(path)
                if existing is None or existing.canonical_json() != validated.canonical_json():
                    raise ManifestStoreConflictError("run_id concurrente con contenido diferente.")
                created = False
            temp_path.unlink(missing_ok=True)
            return created
        except ManifestStoreError:
            raise
        except Exception as error:
            raise ManifestStoreError("No se pudo añadir el manifest de forma atómica.") from error
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def list_source(self, source_id: str) -> tuple[RunManifest, ...]:
        if not _SOURCE_ID_RE.fullmatch(source_id):
            raise ManifestStoreError("source_id no es válido.")
        directory = self.root / quote(source_id, safe="-_.")
        if not directory.is_dir():
            return ()
        manifests: list[RunManifest] = []
        for path in sorted(directory.glob("**/*.json")):
            manifest = self._read(path)
            if manifest.source_id != source_id:
                raise ManifestStoreError("Manifest encontrado bajo una fuente incompatible.")
            manifests.append(manifest)
        return tuple(sorted(manifests, key=lambda item: (item.started_at, item.finished_at, item.run_id)))

    def _read(self, path: Path) -> RunManifest:
        try:
            raw = path.read_text(encoding="utf-8")
            if not raw.endswith("\n") or raw.endswith("\n\n"):
                raise ValueError("newline")
            manifest = RunManifest.from_mapping(json.loads(raw))
            expected_path = self.path_for(manifest)
            path_matches = (
                path.parent.resolve() == expected_path.parent.resolve()
                and path.name.startswith(f".{expected_path.name}.")
                and path.suffix == ".tmp"
            ) if path.suffix == ".tmp" else path.resolve() == expected_path.resolve()
            if raw != manifest.canonical_json() + "\n" or not path_matches:
                raise ValueError("noncanonical")
            return manifest
        except Exception as error:
            if isinstance(error, ManifestStoreError):
                raise
            raise ManifestStoreError(f"Manifest ilegible o inválido: {path.name}.") from error
