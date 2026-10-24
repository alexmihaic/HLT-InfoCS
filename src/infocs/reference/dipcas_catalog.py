"""Normalización y cruce territorial del dataset `ayuntamientos` de la Diputación de Castellón.

Allowlist estricta de campos. El cruce con el registro local usa únicamente el
código INE; nunca la semejanza de nombres. Sin acceso a red.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = _PROJECT_ROOT / "config" / "entities" / "castellon.json"

_INE_PATTERN = re.compile(r"12\d{3}\Z")
_DIR3_PATTERN = re.compile(r"L\d{8}\Z")
_HOST_PATTERN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f\s]")

# Valor oficial del campo `id` ("Tipo") -> tipo de entidad. Cualquier otro valor es desconocido.
_SOURCE_TYPE_KIND = {"Ayuntamiento": "municipality", "E.L. Menor": "sub_municipal"}


class EntityKind(str, Enum):
    MUNICIPALITY = "municipality"
    SUB_MUNICIPAL = "sub_municipal"


@dataclass(frozen=True, slots=True)
class AuditBaseline:
    """Resultado de la auditoría SOURCES-RESEARCH-01; cualquier desvío bloquea el snapshot."""

    entity_count: int = 136
    municipality_count: int = 135
    sub_municipal_dir3: frozenset[str] = frozenset({"L04120001"})


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    blocking: bool
    detail: str
    ine: str | None = None
    dir3: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "blocking": self.blocking, "detail": self.detail, "ine": self.ine, "dir3": self.dir3}


@dataclass(frozen=True, slots=True)
class LinkField:
    """Valor oficial y, si es un enlace utilizable, la URL derivada con su transformación."""

    official_value: str | None
    url: str | None
    transform: str  # "none" | "prefix_https_scheme" | "absent" | "rejected"


@dataclass(frozen=True, slots=True)
class MunicipalEntity:
    kind: EntityKind
    ine: str | None
    dir3: str
    source_name: str
    registry_name: str | None
    comarca: str | None
    web: LinkField
    sede_electronica: LinkField
    source_entity_type: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "ine": self.ine,
            "dir3": self.dir3,
            "source_name": self.source_name,
            "registry_name": self.registry_name,
            "comarca": self.comarca,
            "web": _link_dict(self.web),
            "sede_electronica": _link_dict(self.sede_electronica),
            "source_entity_type": self.source_entity_type,
        }


def _link_dict(link: LinkField) -> dict[str, Any]:
    return {"official_value": link.official_value, "url": link.url, "transform": link.transform}


@dataclass(frozen=True, slots=True)
class CatalogResult:
    entities: tuple[MunicipalEntity, ...]
    issues: tuple[Issue, ...]
    unknown_entries: tuple[dict[str, Any], ...] = field(default=())

    @property
    def blocking_issues(self) -> tuple[Issue, ...]:
        return tuple(issue for issue in self.issues if issue.blocking)

    @property
    def is_valid(self) -> bool:
        return not self.blocking_issues

    @property
    def municipalities(self) -> tuple[MunicipalEntity, ...]:
        return tuple(e for e in self.entities if e.kind is EntityKind.MUNICIPALITY)

    @property
    def sub_municipal(self) -> tuple[MunicipalEntity, ...]:
        return tuple(e for e in self.entities if e.kind is EntityKind.SUB_MUNICIPAL)


class RegistryError(ValueError):
    pass


def load_registry_municipalities(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, str]:
    """INE -> nombre oficial, desde `config/entities/castellon.json`."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw["municipalities"]
        registry = {str(item["code"]): str(item["official_name"]) for item in items}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RegistryError("Registro territorial ilegible o con estructura inesperada.") from error
    if not registry or len(registry) != len(items) or not all(_INE_PATTERN.match(code) for code in registry):
        raise RegistryError("Registro territorial vacío, con duplicados o con códigos INE inválidos.")
    return registry


def normalize_link(value: Any) -> tuple[LinkField, str | None]:
    """Valida un enlace. Devuelve (campo, motivo de rechazo o None).

    La única transformación admitida es anteponer `https://` cuando el valor
    oficial no trae esquema (el dataset publica dominios sin esquema). Los
    espacios iniciales o finales se rechazan: recortarlos sería una
    transformación no registrada.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return LinkField(None, None, "absent"), None
    if not isinstance(value, str):
        return LinkField(None, None, "rejected"), "not_a_string"
    official = value
    candidate = value
    if candidate != candidate.strip():
        return LinkField(official, None, "rejected"), "whitespace_or_control_characters"
    has_scheme = "://" in candidate
    transform = "none" if has_scheme else "prefix_https_scheme"
    full = candidate if has_scheme else f"https://{candidate}"
    try:
        parts = urlsplit(full)
        port = parts.port
    except ValueError:
        return LinkField(official, None, "rejected"), "unparseable"
    host = (parts.hostname or "").lower()
    if _CONTROL.search(full):
        reason = "whitespace_or_control_characters"
    elif parts.scheme.lower() not in {"http", "https"}:
        reason = "scheme_not_allowed"
    elif parts.username is not None or parts.password is not None:
        reason = "userinfo_not_allowed"
    elif not _HOST_PATTERN.match(host):
        reason = "invalid_host"
    elif port is not None and not 0 < port < 65536:
        reason = "invalid_port"
    else:
        return LinkField(official, full, transform), None
    return LinkField(official, None, "rejected"), reason


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("not_a_string")
    return value if value.strip() and not re.search(r"[\x00-\x1f\x7f]", value) else None


def build_catalog(
    raw_records: list[Mapping[str, Any]],
    registry: Mapping[str, str],
    baseline: AuditBaseline | None = AuditBaseline(),
) -> CatalogResult:
    issues: list[Issue] = []
    parsed: list[dict[str, Any]] = []

    for index, raw in enumerate(raw_records):
        try:
            ine, dir3 = _text(raw.get("ine")), _text(raw.get("dir3"))
            name, source_type = _text(raw.get("nombre_poblacion")), _text(raw.get("id"))
            comarca = _text(raw.get("comarca"))
        except (ValueError, AttributeError):
            issues.append(Issue("invalid_record", True, f"registro {index}: tipo de campo inesperado"))
            continue
        if dir3 is None or name is None or source_type is None or (ine is not None and not _INE_PATTERN.match(ine)) or not _DIR3_PATTERN.match(dir3 or ""):
            issues.append(Issue("invalid_record", True, f"registro {index}: campo obligatorio ausente o con formato inválido", ine, dir3))
            continue
        web, web_reason = normalize_link(raw.get("web_ayuntamiento"))
        sede, sede_reason = normalize_link(raw.get("sede_electronica"))
        for label, reason in (("web", web_reason), ("sede_electronica", sede_reason)):
            if reason:
                issues.append(Issue("link_rejected", False, f"{label}: {reason}", ine, dir3))
        parsed.append({"ine": ine, "dir3": dir3, "name": name, "type": source_type, "comarca": comarca, "web": web, "sede": sede})

    ine_counts: dict[str, int] = {}
    dir3_counts: dict[str, int] = {}
    for item in parsed:
        if item["ine"]:
            ine_counts[item["ine"]] = ine_counts.get(item["ine"], 0) + 1
        dir3_counts[item["dir3"]] = dir3_counts.get(item["dir3"], 0) + 1
    duplicated_ine = {k for k, n in ine_counts.items() if n > 1}
    duplicated_dir3 = {k for k, n in dir3_counts.items() if n > 1}
    for ine in sorted(duplicated_ine):
        issues.append(Issue("duplicate_ine", True, "código INE repetido en el dataset", ine=ine))
    for dir3 in sorted(duplicated_dir3):
        issues.append(Issue("duplicate_dir3", True, "DIR3 repetido en el dataset", dir3=dir3))
    # Conflicto INE↔DIR3: mismo DIR3 con INE distintos, o mismo INE con DIR3 distintos.
    for dir3 in sorted(duplicated_dir3):
        if len({i["ine"] for i in parsed if i["dir3"] == dir3}) > 1:
            issues.append(Issue("ine_dir3_conflict", True, "un DIR3 aparece asociado a INE distintos", dir3=dir3))
    for ine in sorted(duplicated_ine):
        if len({i["dir3"] for i in parsed if i["ine"] == ine}) > 1:
            issues.append(Issue("ine_dir3_conflict", True, "un INE aparece asociado a DIR3 distintos", ine=ine))

    entities: list[MunicipalEntity] = []
    unknown: list[dict[str, Any]] = []
    for item in parsed:
        ine, dir3 = item["ine"], item["dir3"]
        if (ine and ine in duplicated_ine) or dir3 in duplicated_dir3:
            continue
        kind_value = _SOURCE_TYPE_KIND.get(item["type"])
        problem: str | None = None
        if kind_value is None:
            problem = "unknown_entity_type"
        elif kind_value == "municipality" and ine is None:
            problem = "municipality_without_ine"
        elif kind_value == "municipality" and ine not in registry:
            problem = "unknown_ine"
        elif kind_value == "sub_municipal" and ine is not None:
            problem = "sub_municipal_with_ine"
        if problem:
            issues.append(Issue(problem, True, f"entrada no clasificable (tipo oficial «{item['type']}»)", ine, dir3))
            unknown.append({"ine": ine, "dir3": dir3, "source_type": item["type"], "reason": problem})
            continue
        entities.append(
            MunicipalEntity(
                kind=EntityKind(kind_value),
                ine=ine,
                dir3=dir3,
                source_name=item["name"],
                registry_name=registry[ine] if ine else None,
                comarca=item["comarca"],
                web=item["web"],
                sede_electronica=item["sede"],
                source_entity_type=item["type"],
            )
        )

    present = {e.ine for e in entities if e.ine}
    for ine in sorted(set(registry) - present - duplicated_ine - {u["ine"] for u in unknown}):
        issues.append(Issue("missing_in_dataset", True, "código del registro local ausente en el dataset", ine=ine))

    entities.sort(key=lambda e: (e.kind.value, e.ine or "", e.dir3))
    result_entities = tuple(entities)

    if baseline is not None:
        sub_dir3 = frozenset(e.dir3 for e in result_entities if e.kind is EntityKind.SUB_MUNICIPAL)
        counts = (len(raw_records), sum(1 for e in result_entities if e.kind is EntityKind.MUNICIPALITY))
        if counts != (baseline.entity_count, baseline.municipality_count) or sub_dir3 != baseline.sub_municipal_dir3:
            issues.append(
                Issue(
                    "baseline_drift",
                    True,
                    f"difiere de la auditoría: entidades/municipios {counts} vs "
                    f"{(baseline.entity_count, baseline.municipality_count)}; ámbito inferior {sorted(sub_dir3)}",
                )
            )
    return CatalogResult(result_entities, tuple(issues), tuple(unknown))
