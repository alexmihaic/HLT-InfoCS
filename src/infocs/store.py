"""Almacén canónico de records JSON, pequeño y seguro para el MVP."""

from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote

from infocs.diff.core import content_hash
from infocs.models import DataValidationError, Record, validate_record_payload


_SAFE_SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class RecordStoreError(ValueError):
    """Error de validación o de acceso al almacén canónico."""


class RecordStore:
    """Guarda records finalizados como JSON individual y reemplazo atómico.

    ``root`` es el directorio de records de una ejecución. El constructor no
    crea ni modifica el directorio; las pruebas pueden usar un temporal y una
    ejecución futura podrá apuntar a ``data/records`` explícitamente.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    def path_for(self, source_id: str, record_id: str) -> Path:
        """Devuelve el path estable sin interpolar IDs externos como rutas."""
        source_segment = _safe_source_segment(source_id)
        filename = f"r-{_encoded_component(_required_text(record_id, 'record_id'))}.json"
        source_directory = self.root / source_segment
        path = (source_directory / filename).resolve()
        root = self.root.resolve()
        if root != path and root not in path.parents:
            raise RecordStoreError("El path calculado queda fuera del almacén.")
        return path

    def get(self, record_id: str, source_id: str | None = None) -> Record | None:
        """Carga un record; sin fuente busca de forma determinista en el root."""
        if source_id is not None:
            path = self.path_for(source_id, record_id)
            return self._read_path(path) if path.is_file() else None

        if not self.root.is_dir():
            return None
        for source_directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
            for path in sorted(source_directory.glob("r-*.json")):
                record = self._read_path(path)
                if record is not None and record.id == record_id:
                    return record
        return None

    def exists(self, record_id: str, source_id: str | None = None) -> bool:
        return self.get(record_id, source_id=source_id) is not None

    def write(self, record: Record) -> Path:
        """Valida y reemplaza un JSON completo mediante un temporal del mismo dir."""
        validated = _validated_record(record)
        path = self.path_for(validated.source.id, validated.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = validated.canonical_json() + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            # Se vuelve a cargar antes de reemplazar para que el mismo contrato
            # que se usa al leer valide exactamente el artefacto preparado.
            _validated_record(Record.from_json(temporary_path.read_bytes()))
            os.replace(temporary_path, path)
        except Exception as error:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            if isinstance(error, (DataValidationError, RecordStoreError)):
                raise
            raise RecordStoreError(f"No se pudo escribir {path.name} de forma atómica.") from error
        return path

    def list_source(self, source_id: str) -> tuple[Record, ...]:
        """Lista records válidos de una fuente en orden estable por identidad."""
        source_segment = _safe_source_segment(source_id)
        source_directory = self.root / source_segment
        if not source_directory.is_dir():
            return ()
        records = [
            record
            for path in sorted(source_directory.glob("r-*.json"))
            if (record := self._read_path(path)) is not None
        ]
        return tuple(sorted(records, key=lambda record: record.id))

    def _read_path(self, path: Path) -> Record | None:
        try:
            return _validated_record(Record.from_json(path.read_bytes()))
        except (OSError, DataValidationError, RecordStoreError) as error:
            raise RecordStoreError(f"Record inválido o ilegible: {path.name}.") from error


def _validated_record(record: Record) -> Record:
    if not isinstance(record, Record):
        raise RecordStoreError("RecordStore.write() requiere un Record finalizado.")
    payload = record.to_dict()
    try:
        validate_record_payload(payload)
        validated = Record.from_dict(payload)
    except DataValidationError as error:
        raise RecordStoreError("El Record no cumple el schema persistible.") from error
    if validated.technical.content_hash != content_hash(payload):
        raise RecordStoreError("technical.content_hash no coincide con el contenido semántico.")
    return validated


def _safe_source_segment(source_id: str) -> str:
    value = _required_text(source_id, "source_id")
    if _SAFE_SOURCE.fullmatch(value) and value.upper() not in _WINDOWS_RESERVED:
        return value
    return f"s-{_encoded_component(value)}"


def _encoded_component(value: str) -> str:
    """Codifica separadores, puntos y caracteres reservados en un segmento."""
    return quote(value, safe="-_~").replace(".", "%2E")


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RecordStoreError(f"{field} debe ser texto no vacío.")
    if "\x00" in value:
        raise RecordStoreError(f"{field} contiene un carácter no permitido.")
    return value
