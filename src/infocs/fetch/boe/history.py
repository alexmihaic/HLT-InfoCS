"""Integridad BOE de sólo lectura; no aplica invariantes al historial BDNS.

Se toleran Records históricos sin CREATE y transiciones v1 repetidas (su ID
conserva la primera observación). No se infiere el extremo por nombre de fichero.
"""

from datetime import datetime
from pathlib import Path

from infocs.events import EventStore
from infocs.store import RecordStore


class BOEHistoryError(ValueError):
    """Sólo códigos cerrados, sin identificadores ni contenido fuente."""


def _reachable(start: str, edges: dict[str, set[str]]) -> set[str]:
    reached = {start}
    pending = [start]
    while pending:
        for target in edges.get(pending.pop(), ()):
            if target not in reached:
                reached.add(target)
                pending.append(target)
    return reached


def validate_boe_history(repo_root: str | Path) -> None:
    """Rechaza huérfanos, CREATE incompatibles, ramas y extremos incoherentes.

    Los Events v1 son transiciones únicas, no ocurrencias: se permite recorrer
    otra vez una transición previamente observada, pero nunca inventar una
    transición de retorno para justificar una bifurcación. Timestamps iguales
    de varias transiciones de una identidad no prueban su orden: fail-closed.
    """
    root = Path(repo_root)
    records = {r.id: r for r in RecordStore(root / "data/records").list_source("boe")}
    histories: dict[str, list] = {}
    for event in EventStore(root / "data/events").list_source("boe"):
        record = records.get(event.record_id)
        if record is None:
            raise BOEHistoryError("boe_event_without_record")
        if event.official_id != record.source.official_id:
            raise BOEHistoryError("boe_event_identity_mismatch")
        histories.setdefault(event.record_id, []).append(event)
    for record_id, events in histories.items():
        creates = [event for event in events if event.type == "create"]
        if len(creates) > 1:
            raise BOEHistoryError("boe_incompatible_creates")
        ordered = sorted(events, key=lambda e: datetime.fromisoformat(e.observed_at.replace("Z", "+00:00")))
        if len({e.observed_at for e in ordered}) != len(ordered):
            raise BOEHistoryError("boe_history_order_ambiguous")
        if creates and ordered[0] != creates[0]:
            raise BOEHistoryError("boe_create_after_update")
        # A legacy Record may start its recorded history with an UPDATE.
        current = ordered[0].content_hash if creates else ordered[0].previous_content_hash
        edges: dict[str, set[str]] = {}
        for event in ordered:
            if event.type == "create":
                continue
            if event.previous_content_hash not in _reachable(current, edges):
                raise BOEHistoryError("boe_history_disconnected_or_forked")
            edges.setdefault(event.previous_content_hash, set()).add(event.content_hash)
            current = event.content_hash
        if records[record_id].technical.content_hash not in _reachable(current, edges):
            raise BOEHistoryError("boe_record_history_tip_mismatch")
