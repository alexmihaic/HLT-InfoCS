"""Estructuras tipadas del parser del canal 643.

Solo contienen campos permitidos por el contrato v0.2 §8. Ningún objeto ni
diagnóstico lleva NIF, contactos, adjudicatarios, direcciones, documentos, XML ni
contenido de lotes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from infocs.fetch.placsp.config import FEED_ID, OFFICIAL_ID_PREFIX


class PlacspParseError(ValueError):
    """Error de lote. `code` es un código estable; el mensaje nunca incluye contenido del XML."""

    def __init__(self, code: str, issues: "tuple[EntryIssue, ...]" = ()) -> None:
        super().__init__(code)
        self.code = code
        # Diagnóstico estructurado (posición, códigos, digest del id); nunca contenido del XML.
        self.issues = issues


@dataclass(frozen=True, slots=True)
class ParserLimits:
    max_bytes: int = 32 * 1024 * 1024
    max_depth: int = 64
    max_nodes: int = 2_000_000
    max_element_text_chars: int = 20_000
    max_entries: int = 5_000

    def __post_init__(self) -> None:
        if min(self.max_bytes, self.max_depth, self.max_nodes, self.max_element_text_chars, self.max_entries) <= 0:
            raise ValueError("los límites deben ser positivos.")


@dataclass(frozen=True, order=True, slots=True)
class CodeReference:
    """Código oficial tal cual, con la lista solo si el XML la trae."""

    value: str
    list_uri: str | None = None
    list_version: str | None = None


@dataclass(frozen=True, order=True, slots=True)
class OfficialTemporalValue:
    precision: str  # "date" | "date_time"
    value: str  # literal ISO validado; el offset no se infiere


@dataclass(frozen=True, order=True, slots=True)
class NoticeObservation:
    """Tipo y fecha de emisión de un aviso. No es un aviso con identidad propia."""

    notice_type: CodeReference | None
    issue_date: OfficialTemporalValue | None


@dataclass(frozen=True, slots=True)
class PlacspEntry:
    atom_id: str  # literal, sin normalizar
    updated: datetime  # con offset original
    title: str | None  # texto literal de atom:title, sin normalizar (espacios incluidos)
    title_state: str  # "present" | "absent" | "empty" | "blank" | "multiple"
    contract_folder_id: str
    id_plataforma: str | None
    dir3: str | None
    status: CodeReference | None
    contract_type: CodeReference | None
    procedure: CodeReference | None
    cpv_codes: tuple[str, ...]
    notices: tuple[NoticeObservation, ...]
    submission_deadline: OfficialTemporalValue | None
    execution_locations: tuple[CodeReference, ...]
    has_lots: bool

    @property
    def official_id(self) -> str:
        """Identificador oficial; nunca se usa como nombre de archivo."""
        return OFFICIAL_ID_PREFIX + self.atom_id

    @property
    def declares_castellon_province_execution(self) -> bool:
        """`ES522` exacto: acredita provincia de ejecución declarada, nunca municipio."""
        return any(location.value == "ES522" for location in self.execution_locations)

    def semantic_projection(self) -> tuple[Any, ...]:
        """Contenido comparable. Excluye `updated`, que es control técnico."""
        return (
            self.atom_id, self.title, self.title_state, self.contract_folder_id, self.id_plataforma, self.dir3, self.status,
            self.contract_type, self.procedure, self.cpv_codes, self.notices, self.submission_deadline,
            self.execution_locations, self.has_lots,
        )

    def __repr__(self) -> str:  # sin título ni identificadores en trazas
        return f"PlacspEntry(feed={FEED_ID}, updated={self.updated.isoformat()})"


@dataclass(frozen=True, slots=True)
class Tombstone:
    """Observación técnica de `at:deleted-entry`. No borra ni cancela nada."""

    ref: str
    when: datetime
    kind: str | None  # "ANULADA" | "CERRADA" | None

    @property
    def official_ref(self) -> str:
        return OFFICIAL_ID_PREFIX + self.ref

    def __repr__(self) -> str:
        return f"Tombstone(kind={self.kind}, when={self.when.isoformat()})"


@dataclass(frozen=True, slots=True)
class EntryIssue:
    """Entrada descartada. Solo posición, códigos y un digest del id; nunca contenido.

    `atom_id_digest` (16 hex de SHA-256 del `atom:id` literal) permite saber que
    la entrada descartada compartía id con otra sin conservar el identificador.
    """

    position: int
    codes: tuple[str, ...]
    atom_id_digest: str | None = None


@dataclass(frozen=True, slots=True)
class FeedMetadata:
    feed_atom_id: str | None
    updated: datetime | None
    next_href: str | None  # sin validar: lo valida el transporte
    xml_base_present: bool

    def __repr__(self) -> str:
        return f"FeedMetadata(updated={self.updated.isoformat() if self.updated else None})"


@dataclass(frozen=True, slots=True)
class PlacspPage:
    feed: FeedMetadata
    entries: tuple[PlacspEntry, ...]
    tombstones: tuple[Tombstone, ...]
    issues: tuple[EntryIssue, ...]
    entries_seen: int
    superseded_duplicates: int
    benign_duplicates: int
    nodes_seen: int
    diagnostics: tuple[str, ...] = field(default=())
    discarded_tombstones: int = 0
    withheld_entries: int = 0  # válidas retenidas por compartir id con una entrada descartada

    @property
    def complete(self) -> bool:
        """`True` solo si no se descartó ni retuvo nada.

        Haber parseado el XML sin error NO implica una lectura completa: un
        consumidor debe comprobar esta propiedad (el parser en modo estricto, el
        valor por defecto, ya falla cerrado en lugar de devolver páginas incompletas).
        """
        return not self.issues and self.discarded_tombstones == 0 and self.withheld_entries == 0
