"""Política BOE por reglas: precedencia, desactivación y garantías (datos sintéticos)."""

from __future__ import annotations

import copy
from datetime import UTC, date, datetime
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import hashlib
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.events import EventStore
from infocs.fetch.boe import (
    BOEDepartment,
    BOEDiary,
    BOEDocumentLinks,
    BOEHeading,
    BOEItem,
    BOESection,
    BOESummary,
    ingest_boe_summary,
    load_castellon_registry,
)
from infocs.fetch.boe.normalize import normalize_boe_item
from infocs.fetch.boe.policy_simulation import main as simulation_main, simulate_queue, simulate_summary
from infocs.fetch.boe.publication import BOE_EVENT_POLICY_ID, authorize_boe_event
from infocs.fetch.boe.publication_rules import (
    DEFAULT_BOE_RULES_CONFIG,
    RULE_APPROVED_REASON,
    BOEPublicationRulePolicy,
    BOERuleOutcome,
    BOERulePolicyError,
    evaluate_boe_publication,
    publication_decision_for,
)
from infocs.fetch.boe.territorial import decide_boe_territorial_inclusion
from infocs.finalize import finalize_record
from infocs.privacy import PrivacyDecision, PrivacyDecisionType, PrivacyGate
from infocs.publication.review import PublicationDecision, PublicationDecisionType, PublicationReviewConfig
from infocs.store import RecordStore
from infocs.events import EventStore as _EventStore


NOW = datetime(2099, 1, 2, 9, 0, tzinfo=UTC)
REGISTRY = load_castellon_registry()
LOCAL = "ADMINISTRACIÓN LOCAL"
EMPLOYMENT_2B = "Resolución de 1 de enero de 2099, del Ayuntamiento de Segorbe (Castellón/Castelló), referente a la convocatoria para proveer una plaza."
TENDER_5A = "Anuncio del Ayuntamiento de Segorbe por el que se convoca licitación pública del servicio de limpieza viaria."


def boe_item(official_id: str, *, section: str, title: str, department: str = LOCAL) -> BOEItem:
    return BOEItem(
        official_id=official_id,
        title=title,
        section_code=section,
        section_name=f"Sección {section}",
        department_code="9999",
        department_name=department,
        published_on=date(2099, 1, 2),
        documents=BOEDocumentLinks(
            xml_url=f"https://www.boe.es/diario_boe/xml.php?id={official_id}",
            html_url=f"https://www.boe.es/diario_boe/txt.php?id={official_id}",
            pdf_url=f"https://www.boe.es/boe/dias/2099/01/02/pdfs/{official_id}.pdf",
        ),
    )


def summary(*items: BOEItem) -> BOESummary:
    sections = []
    for code in sorted({entry.section_code for entry in items}):
        members = tuple(entry for entry in items if entry.section_code == code)
        department = BOEDepartment(code="9999", name=members[0].department_name, headings=(BOEHeading(name="Ficticio", items=members),), direct_items=())
        sections.append(BOESection(code=code, name=f"Sección {code}", departments=(department,)))
    return BOESummary(publication_date=date(2099, 1, 2), diaries=(BOEDiary(number="1", sections=tuple(sections)),))


def manual(*entries: tuple[str, str, str]) -> PublicationReviewConfig:
    return PublicationReviewConfig.from_mapping({
        "schema_version": "1", "source_id": "boe",
        "records": [{"official_id": i, "decision": d, "reason_code": r} for i, d, r in entries],
    })


def policy_payload(*, enabled: bool = True) -> dict:
    payload = json.loads(DEFAULT_BOE_RULES_CONFIG.read_text(encoding="utf-8"))
    payload = copy.deepcopy(payload)
    payload["enabled"] = enabled
    if enabled:
        payload["authorization"] = {"approved_by": "responsable-sintetico", "approved_on": "2099-01-01", "reference": "TEST-AUTH-1"}
        for rule in payload["rules"]:
            rule["enabled"] = True
    return payload


def active_policy() -> BOEPublicationRulePolicy:
    return BOEPublicationRulePolicy.from_mapping(policy_payload())


def evaluate(item: BOEItem, config: PublicationReviewConfig | None = None, policy=None, *, privacy=None, shadow=False):
    territorial = decide_boe_territorial_inclusion(item, REGISTRY)
    record = finalize_record(normalize_boe_item(item, territorial, detected_at=NOW, last_checked_at=NOW))
    decision = privacy or PrivacyGate.default().evaluate(record)
    if decision.record_id != record.id:
        decision = PrivacyDecision(decision.decision, record.id)
    return evaluate_boe_publication(
        item, territorial, record, decision, config or manual(), policy if policy is not None else active_policy(), shadow=shadow,
    ), record, decision


def run_ingest(items, config=None, policy=None, root: Path | None = None):
    return ingest_boe_summary(
        summary(*items), registry=REGISTRY,
        store=RecordStore(root / "records"), event_store=EventStore(root / "events"),
        detected_at=NOW, last_checked_at=NOW,
        publication_review_config=config or manual(),
        run_id="run-v1-00000000-0000-4000-8000-000000000001",
        publication_rules=policy,
    )


class RulePolicyConfigurationTests(unittest.TestCase):
    def test_versioned_config_is_disabled_and_inert(self) -> None:
        policy = BOEPublicationRulePolicy.from_file()
        self.assertFalse(policy.enabled)
        self.assertEqual(policy.active_rules, ())
        self.assertTrue(all(not rule.enabled for rule in policy.rules))

    def test_activation_requires_flag_and_recorded_authorization(self) -> None:
        payload = policy_payload()
        payload["authorization"] = None
        with self.assertRaises(BOERulePolicyError):
            BOEPublicationRulePolicy.from_mapping(payload)
        payload = policy_payload(enabled=False)
        payload["rules"][0]["enabled"] = True
        with self.assertRaises(BOERulePolicyError):
            BOEPublicationRulePolicy.from_mapping(payload)
        payload = policy_payload()
        for rule in payload["rules"]:
            rule["enabled"] = False
        with self.assertRaises(BOERulePolicyError):
            BOEPublicationRulePolicy.from_mapping(payload)

    def test_rules_cannot_target_excluded_sections_or_omit_territorial_evidence(self) -> None:
        payload = policy_payload()
        payload["rules"][0]["section_code"] = "5B"
        with self.assertRaises(BOERulePolicyError):
            BOEPublicationRulePolicy.from_mapping(payload)
        payload = policy_payload()
        payload["rules"][0]["territorial_reasons_all"] = []
        payload["rules"][0]["territorial_reasons_any"] = []
        with self.assertRaises(BOERulePolicyError):
            BOEPublicationRulePolicy.from_mapping(payload)

    def test_unknown_keys_are_rejected(self) -> None:
        payload = policy_payload()
        payload["rules"][0]["publish_everything"] = True
        with self.assertRaises(BOERulePolicyError):
            BOEPublicationRulePolicy.from_mapping(payload)


class RuleEvaluationTests(unittest.TestCase):
    def test_2b_local_employment_call_with_exact_territory_is_candidate(self) -> None:
        evaluation, _, _ = evaluate(boe_item("BOE-A-2099-1", section="2B", title=EMPLOYMENT_2B))
        self.assertEqual(evaluation.outcome, BOERuleOutcome.CANDIDATE)
        self.assertEqual(evaluation.rule_id, "boe-2b-local-employment-call")
        self.assertTrue(evaluation.active)

    def test_5a_local_tender_is_candidate_but_award_notice_is_held(self) -> None:
        tender, _, _ = evaluate(boe_item("BOE-B-2099-1", section="5A", title=TENDER_5A))
        self.assertEqual(tender.outcome, BOERuleOutcome.CANDIDATE)
        award, _, _ = evaluate(boe_item("BOE-B-2099-2", section="5A", title="Anuncio del Ayuntamiento de Segorbe de formalización del contrato de licitación del servicio de limpieza."))
        self.assertEqual((award.outcome, award.reasons[0]), (BOERuleOutcome.HOLD, "rule_title_exclusion"))

    def test_5b_and_personal_title_terms_stay_held_even_with_matching_territory(self) -> None:
        notice, _, _ = evaluate(boe_item("BOE-B-2099-3", section="5B", title="Anuncio del Ayuntamiento de Segorbe sobre convocatoria ficticia."))
        self.assertEqual((notice.outcome, notice.reasons[0]), (BOERuleOutcome.HOLD, "excluded_section"))
        appointment, _, _ = evaluate(boe_item("BOE-A-2099-2", section="2B", title="Resolución del Ayuntamiento de Segorbe (Castellón/Castelló), por la que se nombra personal de la convocatoria."))
        self.assertEqual((appointment.outcome, appointment.reasons[0]), (BOERuleOutcome.HOLD, "excluded_title_term"))
        honorific, _, _ = evaluate(boe_item("BOE-A-2099-3", section="2B", title="Convocatoria del Ayuntamiento de Segorbe (Castellón/Castelló) a instancia de doña Ficticia."))
        self.assertEqual(honorific.outcome, BOERuleOutcome.HOLD)

    def test_ambiguous_or_weak_territory_is_held(self) -> None:
        province_only, _, _ = evaluate(boe_item("BOE-A-2099-4", section="2B", title="Resolución de la Diputación de ejemplo (Castellón/Castelló), convocatoria para proveer una plaza."))
        self.assertEqual(province_only.outcome, BOERuleOutcome.HOLD)
        no_marker, _, _ = evaluate(boe_item("BOE-A-2099-5", section="2B", title="Resolución del Ayuntamiento de Segorbe, convocatoria para proveer una plaza."))
        self.assertEqual((no_marker.outcome, no_marker.reasons[0]), (BOERuleOutcome.HOLD, "territorial_requirements_not_met"))

    def test_other_department_or_no_rule_section_defaults_to_hold(self) -> None:
        other_department, _, _ = evaluate(boe_item("BOE-A-2099-6", section="2B", title=EMPLOYMENT_2B, department="MINISTERIO FICTICIO"))
        self.assertEqual((other_department.outcome, other_department.reasons[0]), (BOERuleOutcome.HOLD, "department_not_allowed"))
        regulation, _, _ = evaluate(boe_item("BOE-A-2099-7", section="1", title="Orden ficticia sobre Segorbe (Castellón/Castelló), convocatoria."))
        self.assertEqual((regulation.outcome, regulation.reasons[0]), (BOERuleOutcome.HOLD, "no_rule_for_section"))

    def test_missing_mandatory_data_never_approves(self) -> None:
        missing_section, _, _ = evaluate(boe_item("BOE-A-2099-8", section=" ", title=EMPLOYMENT_2B))
        self.assertEqual((missing_section.outcome, missing_section.reasons[0]), (BOERuleOutcome.UNRESOLVED, "missing_section"))

    def test_privacy_not_allow_is_denied_and_cannot_be_rescued(self) -> None:
        item = boe_item("BOE-A-2099-9", section="2B", title=EMPLOYMENT_2B)
        evaluation, record, _ = evaluate(item, manual(("BOE-A-2099-9", "approved", "reviewed_safe")), privacy=PrivacyDecision(PrivacyDecisionType.QUARANTINE, "x"))
        self.assertEqual((evaluation.outcome, evaluation.reasons[0]), (BOERuleOutcome.DENY, "privacy_quarantine"))
        dni, _, decision = evaluate(boe_item("BOE-A-2099-10", section="2B", title=EMPLOYMENT_2B.replace("una plaza", "una plaza 12345678Z")))
        self.assertNotEqual(decision.decision, PrivacyDecisionType.ALLOW)
        self.assertEqual(dni.outcome, BOERuleOutcome.DENY)

    def test_manual_decisions_keep_precedence_over_rules(self) -> None:
        held, _, _ = evaluate(boe_item("BOE-A-2099-11", section="2B", title=EMPLOYMENT_2B), manual(("BOE-A-2099-11", "hold", "personal_content_review")))
        self.assertEqual((held.outcome, held.reasons[0]), (BOERuleOutcome.HOLD, "manual_hold_personal_content_review"))
        rejected, _, _ = evaluate(boe_item("BOE-A-2099-12", section="2B", title=EMPLOYMENT_2B), manual(("BOE-A-2099-12", "rejected", "privacy_quarantine")))
        self.assertEqual(rejected.outcome, BOERuleOutcome.DENY)
        approved, _, _ = evaluate(boe_item("BOE-B-2099-4", section="5B", title="Anuncio ficticio de Segorbe."), manual(("BOE-B-2099-4", "approved", "reviewed_safe")))
        self.assertEqual(approved.outcome, BOERuleOutcome.MANUAL_APPROVED)

    def test_integrity_failure_beats_manual_approval(self) -> None:
        item = boe_item("BOE-A-2099-13", section="2B", title=EMPLOYMENT_2B)
        other = boe_item("BOE-A-2099-14", section="2B", title=EMPLOYMENT_2B)
        territorial = decide_boe_territorial_inclusion(other, REGISTRY)
        record = finalize_record(normalize_boe_item(other, territorial, detected_at=NOW, last_checked_at=NOW))
        evaluation = evaluate_boe_publication(
            item, territorial, record, PrivacyDecision(PrivacyDecisionType.ALLOW, record.id),
            manual(("BOE-A-2099-14", "approved", "reviewed_safe")), active_policy(),
        )
        self.assertEqual((evaluation.outcome, evaluation.reasons[0]), (BOERuleOutcome.DENY, "record_integrity_failure"))

    def test_shadow_mode_never_produces_an_active_or_authorizing_result(self) -> None:
        disabled = BOEPublicationRulePolicy.from_file()
        evaluation, record, privacy = evaluate(boe_item("BOE-A-2099-15", section="2B", title=EMPLOYMENT_2B), policy=disabled, shadow=True)
        self.assertEqual(evaluation.outcome, BOERuleOutcome.CANDIDATE)
        self.assertFalse(evaluation.active)
        hold = PublicationDecision(PublicationDecisionType.HOLD, "not_in_allowlist", False)
        self.assertIs(publication_decision_for(evaluation, hold), hold)
        forged = PublicationDecision(PublicationDecisionType.APPROVED, RULE_APPROVED_REASON, False)
        self.assertIsNone(authorize_boe_event(record, privacy, forged, rule_evaluation=evaluation))
        self.assertIsNone(authorize_boe_event(record, privacy, forged))


class RuleIngestionTests(unittest.TestCase):
    ITEMS = (
        boe_item("BOE-A-2099-20", section="2B", title=EMPLOYMENT_2B),
        boe_item("BOE-B-2099-20", section="5B", title="Anuncio del Ayuntamiento de Segorbe de notificación ficticia."),
        boe_item("BOE-A-2099-21", section="2B", title="Resolución del Ayuntamiento de Segorbe, convocatoria para proveer una plaza."),
    )

    def test_disabled_policy_keeps_current_behaviour_exactly(self) -> None:
        with TemporaryDirectory() as a, TemporaryDirectory() as b:
            baseline = run_ingest(self.ITEMS, root=Path(a))
            disabled = run_ingest(self.ITEMS, policy=BOEPublicationRulePolicy.from_file(), root=Path(b))
        self.assertEqual(baseline.metrics, disabled.metrics)
        self.assertEqual(baseline.operations, disabled.operations)
        self.assertEqual(baseline.review_queue_observations, disabled.review_queue_observations)
        self.assertEqual(baseline.metrics.publication_approved, 0)

    def test_active_policy_publishes_only_the_eligible_record_with_rule_authorization(self) -> None:
        with TemporaryDirectory() as directory:
            result = run_ingest(self.ITEMS, policy=active_policy(), root=Path(directory))
            self.assertEqual(result.metrics.publication_approved, 1)
            self.assertEqual(result.metrics.publication_hold, 2)
            self.assertEqual(len(result.events), 1)
            held = {obs.official_id: obs.entry.reason_code for obs in result.review_queue_observations if obs.entry}
            self.assertEqual(held, {"BOE-B-2099-20": "personal_content_review", "BOE-A-2099-21": "territorial_review_required"})
            events = list((Path(directory) / "events").rglob("*.json"))
            self.assertEqual(len(events), 1)
            self.assertEqual(json.loads(events[0].read_text(encoding="utf-8"))["type"], "create")

    def test_rerun_is_idempotent_and_hashes_are_stable(self) -> None:
        with TemporaryDirectory() as directory:
            first = run_ingest(self.ITEMS[:1], policy=active_policy(), root=Path(directory))
            second = run_ingest(self.ITEMS[:1], policy=active_policy(), root=Path(directory))
            self.assertEqual((first.metrics.created, second.metrics.created, second.metrics.unchanged), (1, 0, 1))
            self.assertEqual(second.events, ())
            self.assertEqual(len(list((Path(directory) / "events").rglob("*.json"))), 1)
        with TemporaryDirectory() as a, TemporaryDirectory() as b:
            manual_run = run_ingest(self.ITEMS[:1], manual(("BOE-A-2099-20", "approved", "reviewed_safe")), root=Path(a))
            rule_run = run_ingest(self.ITEMS[:1], policy=active_policy(), root=Path(b))
        self.assertEqual(manual_run.operations[0].record.technical.content_hash, rule_run.operations[0].record.technical.content_hash)

    def test_manual_approval_still_uses_manual_authorization_policy(self) -> None:
        item = self.ITEMS[0]
        evaluation, record, privacy = evaluate(item, manual(("BOE-A-2099-20", "approved", "reviewed_safe")))
        decision = PublicationDecision(PublicationDecisionType.APPROVED, "reviewed_safe", True)
        self.assertIs(publication_decision_for(evaluation, decision), decision)
        self.assertEqual(authorize_boe_event(record, privacy, decision).policy_id, BOE_EVENT_POLICY_ID)


def synthetic_payload() -> dict:
    def entry(official_id: str, title: str) -> dict:
        return {
            "identificador": official_id, "control": "1", "titulo": title,
            "url_pdf": {"szBytes": "1", "szKBytes": "1", "pagina_inicial": "1", "pagina_final": "1",
                        "texto": f"https://www.boe.es/boe/dias/2099/01/02/pdfs/{official_id}.pdf"},
            "url_html": f"https://www.boe.es/diario_boe/txt.php?id={official_id}",
            "url_xml": f"https://www.boe.es/diario_boe/xml.php?id={official_id}",
        }

    def section(code: str, entries: list[dict]) -> dict:
        return {"codigo": code, "nombre": f"Sección {code}", "departamento": [
            {"codigo": "9999", "nombre": LOCAL, "epigrafe": [{"nombre": "Ficticio", "item": entries}]},
        ]}

    return {"status": {"code": "200", "text": "ok"}, "data": {"sumario": {
        "metadatos": {"publicacion": "BOE", "fecha_publicacion": "20990102"},
        "diario": [{"numero": "1", "seccion": [
            section("2B", [entry("BOE-A-2099-40", EMPLOYMENT_2B), entry("BOE-A-2099-41", "Resolución ficticia de Madrid sin relación territorial.")]),
            section("5A", [entry("BOE-B-2099-40", TENDER_5A)]),
            section("5B", [entry("BOE-B-2099-41", "Anuncio del Ayuntamiento de Segorbe de notificación ficticia.")]),
        ]}],
    }}}


class SimulationTests(unittest.TestCase):
    def test_queue_simulation_reports_unresolved_without_identifiers(self) -> None:
        report = simulate_queue({"records": [
            {"official_id": "BOE-A-2099-30", "territorial_reason_codes": ["municipality_exact"]},
            {"official_id": "BOE-B-2099-31", "territorial_reason_codes": ["province_exact"]},
        ]}, manual(("BOE-B-2099-31", "hold", "personal_content_review")))
        self.assertEqual(report["outcomes"]["unresolved"], 1)
        self.assertEqual(report["outcomes"]["hold"], 1)
        self.assertNotIn("2099-3", json.dumps(report))

    def test_summary_simulation_is_shadow_aggregate_and_never_leaks_content(self) -> None:
        report = simulate_summary(synthetic_payload(), manual(), BOEPublicationRulePolicy.from_file(), observed_at=NOW)
        self.assertEqual(report["seen"], 4)
        self.assertEqual(report["territorially_excluded"], 1)
        self.assertEqual(report["outcomes"]["candidate"], 2)
        self.assertEqual(report["outcomes"]["hold"], 1)
        text = json.dumps(report, ensure_ascii=False)
        for leaked in ("BOE-A-2099-40", "BOE-B-2099-41", "Segorbe", "limpieza", "https://"):
            self.assertNotIn(leaked, text)


class WordBoundaryTests(unittest.TestCase):
    def outcome(self, title: str) -> BOERuleOutcome:
        evaluation, _, _ = evaluate(boe_item("BOE-A-2099-60", section="2B", title=title))
        return evaluation.outcome

    def test_terms_match_whole_words_without_substring_false_positives(self) -> None:
        base = "Resolución del Ayuntamiento de Segorbe (Castellón/Castelló), convocatoria para proveer una plaza"
        self.assertEqual(self.outcome(base + " con donación ficticia."), BOERuleOutcome.CANDIDATE)
        self.assertEqual(self.outcome(base + " de la sesión de cesión ficticia."), BOERuleOutcome.CANDIDATE)

    def test_terms_match_accents_case_and_plurals(self) -> None:
        base = "Resolución del Ayuntamiento de Segorbe (Castellón/Castelló), convocatoria"
        for suffix in (" a instancia de DOÑA Ficticia.", " a instancia de Don Ficticio.", " y nombramientos.", " de subastas ficticias.", " y notificación ficticia."):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.outcome(base + suffix), BOERuleOutcome.HOLD)


class MandatoryRestrictionPrecedenceTests(unittest.TestCase):
    APPROVED = ("BOE-A-2099-70", "approved", "reviewed_safe")

    def test_missing_territorial_evidence_beats_manual_approval_when_active(self) -> None:
        item = boe_item("BOE-A-2099-70", section="2B", title=EMPLOYMENT_2B)
        territorial = decide_boe_territorial_inclusion(item, REGISTRY)
        record = finalize_record(normalize_boe_item(item, territorial, detected_at=NOW, last_checked_at=NOW))
        no_match = type(territorial)(status=type(territorial.status)("no_match"), matches=())
        privacy = PrivacyDecision(PrivacyDecisionType.ALLOW, record.id)
        config = manual(self.APPROVED)
        evaluation = evaluate_boe_publication(item, no_match, record, privacy, config, active_policy())
        self.assertEqual((evaluation.outcome, evaluation.reasons[0]), (BOERuleOutcome.UNRESOLVED, "missing_territorial_inclusion"))
        approved = PublicationDecision(PublicationDecisionType.APPROVED, "reviewed_safe", True)
        mapped = publication_decision_for(evaluation, approved)
        self.assertEqual((mapped.decision, mapped.reason_code), (PublicationDecisionType.HOLD, "territorial_review_required"))
        self.assertIsNone(authorize_boe_event(record, privacy, mapped))

    def test_privacy_restriction_beats_manual_approval_when_active(self) -> None:
        item = boe_item("BOE-A-2099-70", section="2B", title=EMPLOYMENT_2B)
        evaluation, _, _ = evaluate(item, manual(self.APPROVED), privacy=PrivacyDecision(PrivacyDecisionType.QUARANTINE, "x"))
        approved = PublicationDecision(PublicationDecisionType.APPROVED, "reviewed_safe", True)
        self.assertEqual(publication_decision_for(evaluation, approved).decision, PublicationDecisionType.HOLD)

    def test_integrity_failure_aborts_fail_closed_when_active(self) -> None:
        item = boe_item("BOE-A-2099-70", section="2B", title=EMPLOYMENT_2B)
        other = boe_item("BOE-A-2099-71", section="2B", title=EMPLOYMENT_2B)
        territorial = decide_boe_territorial_inclusion(other, REGISTRY)
        record = finalize_record(normalize_boe_item(other, territorial, detected_at=NOW, last_checked_at=NOW))
        evaluation = evaluate_boe_publication(item, territorial, record, PrivacyDecision(PrivacyDecisionType.ALLOW, record.id), manual(), active_policy())
        with self.assertRaises(BOERulePolicyError):
            publication_decision_for(evaluation, PublicationDecision(PublicationDecisionType.APPROVED, "reviewed_safe", True))

    def test_manual_rejection_is_never_downgraded(self) -> None:
        item = boe_item("BOE-A-2099-72", section="2B", title=EMPLOYMENT_2B)
        evaluation, _, _ = evaluate(item, manual(("BOE-A-2099-72", "rejected", "privacy_quarantine")))
        rejected = PublicationDecision(PublicationDecisionType.REJECTED, "privacy_quarantine", True)
        self.assertIs(publication_decision_for(evaluation, rejected), rejected)


class SimulationSideEffectTests(unittest.TestCase):
    def test_cli_queue_simulation_is_read_only_and_aggregate(self) -> None:
        with TemporaryDirectory() as directory:
            queue = Path(directory) / "pending.json"
            queue.write_text(json.dumps({"schema_version": "1", "source_id": "boe", "records": [
                {"official_id": "BOE-A-2099-80", "territorial_reason_codes": ["municipality_exact"]},
            ]}), encoding="utf-8")
            before = hashlib.sha256(queue.read_bytes()).hexdigest()
            output = io.StringIO()
            with redirect_stdout(output):
                code = simulation_main(["--queue", str(queue)])
            self.assertEqual(code, 0)
            self.assertEqual(hashlib.sha256(queue.read_bytes()).hexdigest(), before)
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["pending.json"])
            self.assertNotIn("2099-80", output.getvalue())
            self.assertNotIn(directory, output.getvalue())

    def test_summary_simulation_never_calls_stores(self) -> None:
        def forbidden(*_args, **_kwargs):
            raise AssertionError("La simulación no debe escribir.")

        with patch.object(RecordStore, "write", forbidden), patch.object(_EventStore, "write", forbidden),                 patch.object(_EventStore, "preflight", forbidden):
            report = simulate_summary(synthetic_payload(), manual(), BOEPublicationRulePolicy.from_file(), observed_at=NOW)
        self.assertEqual(report["outcomes"]["candidate"], 2)


if __name__ == "__main__":
    unittest.main()
