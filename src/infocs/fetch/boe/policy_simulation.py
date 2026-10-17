"""Simulación offline de la política BOE por reglas, sin red ni escrituras.

Evalúa en modo shadow (las reglas desactivadas se evalúan, pero nunca
autorizan) y devuelve sólo recuentos agregados: ningún identificador, título,
URL ni payload sale de este módulo.

- ``simulate_queue`` usa el snapshot de la cola BOE. La cola, por contrato
  (ADR-020), no guarda sección, título ni categoría, así que sin decisión
  manual previa el resultado honesto es UNRESOLVED.
- ``simulate_summary`` evalúa sumarios BOE ya guardados localmente con el mismo
  pipeline que la ingesta (territorialidad, normalización, Privacy Gate).
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from infocs.finalize import finalize_record
from infocs.fetch.boe.models import BOETerritorialDecisionStatus
from infocs.fetch.boe.normalize import normalize_boe_item
from infocs.fetch.boe.parser import parse_boe_summary
from infocs.fetch.boe.publication_rules import (
    BOEPublicationRulePolicy,
    BOERuleOutcome,
    evaluate_boe_publication,
)
from infocs.fetch.boe.territorial import (
    BOETerritorialRegistry,
    decide_boe_territorial_inclusion,
    load_castellon_registry,
)
from infocs.privacy import PrivacyDecisionType, PrivacyGate
from infocs.publication.review import PublicationDecisionType, PublicationReviewConfig


SIMULATION_OUTCOMES = ("candidate", "hold", "deny", "unresolved", "manual_approved")


def simulate_queue(
    queue: Mapping[str, Any],
    manual_config: PublicationReviewConfig,
) -> dict[str, Any]:
    """Clasifica la cola con la evidencia que realmente contiene."""
    records = queue.get("records") if isinstance(queue, Mapping) else None
    if not isinstance(records, list):
        raise ValueError("La cola BOE no tiene la forma esperada.")
    manual = {entry.official_id: entry for entry in manual_config.entries}
    rows: Counter[tuple[str, str, str, str]] = Counter()
    for entry in records:
        official_id = entry.get("official_id", "") if isinstance(entry, Mapping) else ""
        group = _id_group(official_id)
        territorial = "+".join(sorted(entry.get("territorial_reason_codes", []))) or "none"
        listed = manual.get(official_id)
        if listed is None:
            outcome, reason = "unresolved", "queue_lacks_section_title_category"
        elif listed.decision is PublicationDecisionType.APPROVED:
            outcome, reason = "manual_approved", "manual_approved"
        elif listed.decision is PublicationDecisionType.REJECTED:
            outcome, reason = "deny", "manual_rejected"
        else:
            outcome, reason = "hold", f"manual_hold_{listed.reason_code}"
        rows[(group, territorial, outcome, reason)] += 1
    return {
        "mode": "queue_snapshot",
        "total": sum(rows.values()),
        "rows": [
            {"id_group": g, "territorial": t, "outcome": o, "reason": r, "count": n}
            for (g, t, o, r), n in sorted(rows.items())
        ],
        "outcomes": _outcome_totals(rows, index=2),
    }


def simulate_summary(
    summary_payload: Mapping[str, Any],
    manual_config: PublicationReviewConfig,
    policy: BOEPublicationRulePolicy,
    *,
    registry: BOETerritorialRegistry | None = None,
    privacy_gate: PrivacyGate | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Evalúa un sumario local en shadow; sólo agrega por sección y motivo."""
    summary = parse_boe_summary(summary_payload)
    active_registry = registry or load_castellon_registry()
    gate = privacy_gate or PrivacyGate.default()
    gate.validate()
    when = observed_at or datetime.now(UTC)
    rows: Counter[tuple[str, str, str]] = Counter()
    sufficiency: Counter[str] = Counter()
    excluded_territorially = 0
    for item in summary.items:
        territorial = decide_boe_territorial_inclusion(item, active_registry)
        if territorial.status is BOETerritorialDecisionStatus.NO_MATCH:
            excluded_territorially += 1
            continue
        candidate = normalize_boe_item(item, territorial, detected_at=when, last_checked_at=when)
        record = finalize_record(candidate)
        privacy = gate.evaluate(record)
        evaluation = evaluate_boe_publication(
            item, territorial, record, privacy, manual_config, policy, shadow=True,
        )
        if evaluation.active:  # pragma: no cover - defensa: shadow nunca autoriza
            raise RuntimeError("Una simulación shadow produjo una evaluación activa.")
        section = (item.section_code or "?").strip().upper() or "?"
        rows[(section, evaluation.outcome.value, evaluation.reasons[0] if evaluation.reasons else "none")] += 1
        if privacy.decision is not PrivacyDecisionType.ALLOW:
            sufficiency["privacy_not_allow"] += 1
        if evaluation.outcome is BOERuleOutcome.CANDIDATE:
            sufficiency["candidate_published_fields_title_authority_date_url"] += 1
            if len(item.title) > 300:
                sufficiency["candidate_title_over_300_chars"] += 1
    return {
        "mode": "summary_shadow",
        "publication_date": summary.publication_date.isoformat(),
        "seen": len(summary.items),
        "territorially_excluded": excluded_territorially,
        "rows": [
            {"section": s, "outcome": o, "reason": r, "count": n}
            for (s, o, r), n in sorted(rows.items())
        ],
        "outcomes": _outcome_totals(rows, index=1),
        "sufficiency": dict(sorted(sufficiency.items())),
    }


def _id_group(official_id: str) -> str:
    parts = official_id.split("-") if isinstance(official_id, str) else []
    return f"BOE-{parts[1]}" if len(parts) > 2 and parts[0] == "BOE" and len(parts[1]) == 1 else "unknown"


def _outcome_totals(rows: Counter, *, index: int) -> dict[str, int]:
    totals = {outcome: 0 for outcome in SIMULATION_OUTCOMES}
    for key, count in rows.items():
        totals[key[index]] = totals.get(key[index], 0) + count
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulación offline y agregada de la política BOE por reglas.")
    parser.add_argument("--queue", type=Path, help="Snapshot local de la cola BOE (sólo lectura).")
    parser.add_argument("--summary", type=Path, action="append", default=[], help="Sumario BOE JSON guardado localmente.")
    parser.add_argument("--rules", type=Path, default=None, help="Configuración de reglas (por defecto la versionada).")
    args = parser.parse_args(argv)
    if args.queue is None and not args.summary:
        parser.error("Indica --queue y/o --summary.")
    try:
        manual = PublicationReviewConfig.from_file()
        policy = BOEPublicationRulePolicy.from_file(args.rules) if args.rules else BOEPublicationRulePolicy.from_file()
        report: dict[str, Any] = {"policy_id": policy.policy_id, "policy_enabled": policy.enabled, "shadow": True}
        if args.queue is not None:
            report["queue"] = simulate_queue(json.loads(args.queue.read_text(encoding="utf-8")), manual)
        report["summaries"] = [
            simulate_summary(json.loads(path.read_text(encoding="utf-8")), manual, policy)
            for path in args.summary
        ]
    except Exception as error:  # noqa: BLE001 - diagnóstico sin payloads
        print(f"Simulación rechazada: {type(error).__name__}.", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
