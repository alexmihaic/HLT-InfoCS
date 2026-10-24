"""Snapshot local, determinista y con procedencia del catálogo municipal de la Diputación.

No genera Records ni Events y no escribe dentro del repositorio (incluido `data/**`). La publicación está
bloqueada hasta revisar las condiciones de reutilización (ver `PUBLICATION_STATUS`).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

from infocs.reference.dipcas_catalog import (
    DEFAULT_REGISTRY_PATH,
    AuditBaseline,
    CatalogResult,
    Issue,
    build_catalog,
    load_registry_municipalities,
    normalize_link,
)
from infocs.reference.dipcas_transport import (
    DIPCAS_DATASET_ID,
    DIPCAS_HOST,
    DIPCAS_SELECT_FIELDS,
    DipcasFetchError,
    DipcasTransport,
)

SCHEMA_VERSION = "1.0.0"
SNAPSHOT_KIND = "infocs.reference.dipcas_municipal"
DEFAULT_FILENAME = "dipcas-municipal-catalog.json"
PUBLICATION_STATUS = "blocked_pending_reuse_review"
REUSE_REVIEW_NOTE = (
    "Pendiente: documentar la tensión entre la licencia específica del dataset (CC BY 4.0) "
    "y el aviso legal general de la Diputación antes de cualquier publicación."
)
_CC_BY_4 = "https://creativecommons.org/licenses/by/4.0/"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

_TOP_KEYS = {"schema_version", "kind", "publication_status", "provenance", "summary", "content_hash", "entities", "warnings"}
_ENTITY_KEYS = {"kind", "ine", "dir3", "source_name", "registry_name", "comarca", "web", "sede_electronica", "source_entity_type"}
_LINK_KEYS = {"official_value", "url", "transform"}
_FORBIDDEN_KEY_PARTS = ("alcalde", "partido", "cif", "telefono", "correo", "email", "salario", "sueldo", "retribu", "domicilio", "twitter", "facebook")


class SnapshotBlocked(RuntimeError):
    """El cruce territorial o la procedencia impiden generar un snapshot válido."""

    def __init__(self, issues: tuple[Issue, ...]) -> None:
        super().__init__("; ".join(f"{i.code}" for i in issues if i.blocking) or "snapshot bloqueado")
        self.issues = issues


class SnapshotValidationError(ValueError):
    pass


def canonical_json(value: Any, *, indent: int | None = None) -> str:
    separators = (",", ": ") if indent else (",", ":")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=indent, separators=separators)


def content_hash(entities: list[dict[str, Any]]) -> str:
    return "sha256:" + sha256(canonical_json(entities).encode("utf-8")).hexdigest()


def _provenance(metadata: Mapping[str, Any], metadata_url: str, records_urls: tuple[str, ...], total: int, consulted_at: str, registry_count: int) -> tuple[dict[str, Any], list[Issue]]:
    issues: list[Issue] = []
    metas = metadata.get("metas")
    default = metas.get("default") if isinstance(metas, Mapping) else None
    fields = metadata.get("fields")
    if metadata.get("dataset_id") != DIPCAS_DATASET_ID or not isinstance(default, Mapping) or not isinstance(fields, list):
        raise SnapshotBlocked((Issue("metadata_contract", True, "metadatos del dataset con estructura inesperada"),))
    names = {f.get("name") for f in fields if isinstance(f, Mapping)}
    missing = [f for f in DIPCAS_SELECT_FIELDS if f not in names]
    if missing:
        raise SnapshotBlocked((Issue("metadata_contract", True, f"campos oficiales ausentes en el metadato: {missing}"),))
    license_url, publisher, title = default.get("license_url"), default.get("publisher"), default.get("title")
    if not all(isinstance(v, str) and v for v in (license_url, publisher, title)) or not str(license_url).startswith("https://"):
        raise SnapshotBlocked((Issue("license_undeclared", True, "licencia, editor o título no declarados en el metadato"),))
    modified = default.get("modified")
    if modified is not None and not isinstance(modified, str):
        modified = None
    declared_count = default.get("records_count")
    if declared_count != total:
        issues.append(Issue("metadata_count_mismatch", True, f"records_count del metadato ({declared_count}) distinto del total paginado ({total})"))
    license_label = "CC BY 4.0" if license_url == _CC_BY_4 else license_url
    provenance = {
        "source": {
            "publisher": publisher,
            "portal_url": f"https://{DIPCAS_HOST}/",
            "dataset_id": DIPCAS_DATASET_ID,
            "dataset_title": title,
        },
        "query": {"metadata_url": metadata_url, "records_urls": list(records_urls)},
        "license": {
            "declared_url": license_url,
            "declared_definition_url": default.get("license") if isinstance(default.get("license"), str) else None,
            "attribution_text": f"{publisher}. Dataset «{title}» ({DIPCAS_HOST}). Licencia {license_label}.",
            "reuse_review": REUSE_REVIEW_NOTE,
        },
        "consulted_at": consulted_at,
        "source_modified_at": modified,
        "source_records_count": total,
        "registry": {"path": "config/entities/castellon.json", "municipality_count": registry_count},
    }
    return provenance, issues


def build_snapshot(
    transport: DipcasTransport,
    registry: Mapping[str, str],
    *,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    baseline: AuditBaseline | None = AuditBaseline(),
) -> dict[str, Any]:
    """Obtiene, cruza y valida. Lanza `SnapshotBlocked` si no puede ser un snapshot válido."""
    consulted_at = now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    metadata, metadata_url = transport.fetch_metadata()
    fetched = transport.fetch_records()
    provenance, issues = _provenance(metadata, metadata_url, fetched.request_urls, fetched.total_count, consulted_at, len(registry))
    catalog = build_catalog(list(fetched.records), registry, baseline)
    all_issues = tuple(issues) + catalog.issues
    if any(i.blocking for i in all_issues):
        raise SnapshotBlocked(all_issues)
    return assemble_snapshot(catalog, provenance, all_issues)


def assemble_snapshot(catalog: CatalogResult, provenance: dict[str, Any], issues: tuple[Issue, ...]) -> dict[str, Any]:
    entities = [e.as_dict() for e in catalog.entities]
    links = [e.web for e in catalog.entities] + [e.sede_electronica for e in catalog.entities]
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "kind": SNAPSHOT_KIND,
        "publication_status": PUBLICATION_STATUS,
        "provenance": provenance,
        "summary": {
            "entity_count": len(entities),
            "municipality_count": len(catalog.municipalities),
            "sub_municipal_count": len(catalog.sub_municipal),
            "links_valid": sum(1 for link in links if link.url),
            "links_rejected": sum(1 for link in links if link.transform == "rejected"),
        },
        "content_hash": content_hash(entities),
        "entities": entities,
        "warnings": [i.as_dict() for i in issues if not i.blocking],
    }
    validate_snapshot(snapshot)
    return snapshot


def _scan_forbidden(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if any(part in str(key).lower() for part in _FORBIDDEN_KEY_PARTS):
                raise SnapshotValidationError(f"campo excluido presente: {key}")
            _scan_forbidden(item)
    elif isinstance(value, list):
        for item in value:
            _scan_forbidden(item)


def _validate_link(link: Mapping[str, Any]) -> None:
    """Reaplica `normalize_link` al valor oficial: el enlace guardado debe ser exactamente su resultado."""
    official = link["official_value"]
    if official is None and link["url"] is None and link["transform"] == "rejected":
        return  # valor fuente no textual: normalize_link no conserva el original
    if official is not None and not isinstance(official, str):
        raise SnapshotValidationError("valor oficial de enlace no textual")
    expected, _ = normalize_link(official)
    if (link["official_value"], link["url"], link["transform"]) != (expected.official_value, expected.url, expected.transform):
        raise SnapshotValidationError("enlace incoherente con su valor oficial y transformación")


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    if set(snapshot) != _TOP_KEYS or snapshot["kind"] != SNAPSHOT_KIND or snapshot["schema_version"] != SCHEMA_VERSION:
        raise SnapshotValidationError("estructura de snapshot inesperada")
    if snapshot["publication_status"] != PUBLICATION_STATUS:
        raise SnapshotValidationError("la publicación debe permanecer bloqueada en esta fase")
    _scan_forbidden(snapshot)
    prov = snapshot["provenance"]
    if not isinstance(prov, Mapping) or not prov.get("license", {}).get("declared_url") or not prov.get("license", {}).get("attribution_text") or not prov.get("consulted_at"):
        raise SnapshotValidationError("procedencia o licencia incompletas")
    entities = snapshot["entities"]
    if not isinstance(entities, list) or not entities:
        raise SnapshotValidationError("catálogo vacío")
    for entity in entities:
        if set(entity) != _ENTITY_KEYS or set(entity["web"]) != _LINK_KEYS or set(entity["sede_electronica"]) != _LINK_KEYS:
            raise SnapshotValidationError("entidad fuera de la allowlist")
        for link in (entity["web"], entity["sede_electronica"]):
            _validate_link(link)
    dir3s = [e["dir3"] for e in entities]
    ines = [e["ine"] for e in entities if e["ine"] is not None]
    if len(set(dir3s)) != len(dir3s) or len(set(ines)) != len(ines):
        raise SnapshotValidationError("identificadores duplicados")
    if any((e["kind"] == "municipality") != (e["ine"] is not None) for e in entities):
        raise SnapshotValidationError("INE incoherente con el tipo de entidad")
    summary = snapshot["summary"]
    if summary["entity_count"] != len(entities) or summary["municipality_count"] + summary["sub_municipal_count"] != len(entities):
        raise SnapshotValidationError("resumen incoherente")
    links = [e[key] for e in entities for key in ("web", "sede_electronica")]
    if summary["links_valid"] != sum(1 for link in links if link["url"]) or summary["links_rejected"] != sum(1 for link in links if link["transform"] == "rejected"):
        raise SnapshotValidationError("resumen de enlaces incoherente")
    if snapshot["content_hash"] != content_hash(entities):
        raise SnapshotValidationError("hash del contenido normalizado incorrecto")


def serialize_snapshot(snapshot: Mapping[str, Any]) -> bytes:
    return (canonical_json(snapshot, indent=2) + "\n").encode("utf-8")


def _is_within(path: Path, root: Path) -> bool:
    """Compara rutas ya resueltas (enlaces simbólicos incluidos), sin distinguir mayúsculas donde el SO no lo hace."""
    path_text, root_text = os.path.normcase(str(path)), os.path.normcase(str(root))
    try:
        return os.path.commonpath([path_text, root_text]) == root_text
    except ValueError:  # distinta unidad en Windows
        return False


def write_snapshot(snapshot: Mapping[str, Any], output_dir: Path, filename: str = DEFAULT_FILENAME) -> Path:
    """Valida y escribe de forma atómica. Ante un fallo conserva el archivo anterior."""
    validate_snapshot(snapshot)
    directory = Path(output_dir).resolve()
    if _is_within(directory, _PROJECT_ROOT.resolve()):
        raise ValueError("DIPCAS-REF-01 no escribe snapshots dentro del repositorio (incluido data/**).")
    if Path(filename).name != filename:
        raise ValueError("filename no puede contener rutas.")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    payload = serialize_snapshot(snapshot)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera localmente el catálogo municipal de la Diputación (sin publicar).")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        snapshot = build_snapshot(DipcasTransport(), load_registry_municipalities(DEFAULT_REGISTRY_PATH))
        path = write_snapshot(snapshot, args.output_dir)
    except SnapshotBlocked as blocked:
        print("Snapshot bloqueado:", file=sys.stderr)
        for issue in blocked.issues:
            if issue.blocking:
                print(f"  {issue.code} ine={issue.ine} dir3={issue.dir3}: {issue.detail}", file=sys.stderr)
        return 2
    except DipcasFetchError as error:
        print(f"Fallo de la fuente: {error.reason}", file=sys.stderr)
        return 1
    print(f"{path} {snapshot['content_hash']} entidades={snapshot['summary']['entity_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
