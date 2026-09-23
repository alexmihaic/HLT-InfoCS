"""Pruebas offline del Privacy Gate v1 y su frontera de persistencia."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.finalize import finalize_record
from infocs.models import Record
from infocs.privacy import (
    PrivacyConfig,
    PrivacyDecisionType,
    PrivacyGate,
    PrivacyGateError,
    TaxIdentifierClassification,
    classify_spanish_tax_identifier,
)
from infocs.store import RecordStore, RecordStoreError


FIXTURES = ROOT / "tests" / "fixtures"


def candidate_payload() -> dict:
    payload = json.loads((FIXTURES / "record_minimal_valid.json").read_text(encoding="utf-8"))
    payload.pop("id", None)
    payload.pop("technical", None)
    return payload


def make_record(**changes: object) -> Record:
    payload = candidate_payload()
    payload.update(changes)
    return finalize_record(payload)


def procurement_record(*, awardee_name: str = "Empresa Ficticia S.L.", tax_identifier: str | None = None) -> Record:
    payload = json.loads((FIXTURES / "record_procurement_valid.json").read_text(encoding="utf-8"))
    payload.pop("id", None)
    payload.pop("technical", None)
    if tax_identifier is not None:
        payload["procurement"]["awardee"]["tax_identifier"] = tax_identifier
    payload["procurement"]["awardee"]["name"] = awardee_name
    return finalize_record(payload)


class PrivacyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = PrivacyGate.from_file(ROOT / "config" / "privacy-rules.json")

    def test_clean_public_record_is_allowed(self) -> None:
        decision = self.gate.evaluate(make_record(title="Resolución del expediente FIC-2026-001"))
        self.assertEqual(decision.decision, PrivacyDecisionType.ALLOW)
        self.assertEqual(decision.reasons, ())

    def test_dni_nie_iban_email_phone_and_address_are_quarantined(self) -> None:
        cases = (
            ("DNI ficticio 12345678Z", "spanish_personal_identifier"),
            ("NIE ficticio X1234567L", "spanish_personal_identifier"),
            ("IBAN ficticio ES9121000418450200051332", "iban"),
            ("Contacto publicado: cuenta de gmail ficticia contacto@gmail.com", "personal_email"),
            ("Teléfono particular: +34 612 345 678", "personal_phone"),
            ("Domicilio particular: Calle Ficticia 12", "structured_private_address"),
        )
        for title, rule in cases:
            with self.subTest(rule=rule):
                decision = self.gate.evaluate(make_record(title=title))
                self.assertEqual(decision.decision, PrivacyDecisionType.QUARANTINE)
                self.assertIn(rule, {reason.rule for reason in decision.reasons})
                serialized = json.dumps(decision.to_dict(), ensure_ascii=False)
                self.assertNotIn(title, serialized)

    def test_company_domain_and_institutional_email_are_allowed(self) -> None:
        record = make_record(
            title="Adjudicación a Empresa Ficticia S.L. expediente 2026/001",
            description="Contacto: unidad@boe.es y contacto@empresa-ficticia.example; importe 1000 EUR; CPV 12345678-9",
        )
        decision = self.gate.evaluate(record)
        self.assertEqual(decision.decision, PrivacyDecisionType.ALLOW)

    def test_company_tax_identifier_is_not_classified_as_personal_identifier(self) -> None:
        self.assertEqual(
            classify_spanish_tax_identifier("B00000000"),
            TaxIdentifierClassification.LEGAL_ENTITY_TAX_IDENTIFIER,
        )
        decision = self.gate.evaluate(procurement_record(tax_identifier="B00000000"))
        self.assertEqual(decision.decision, PrivacyDecisionType.ALLOW)
        self.assertEqual(decision.classifications[0].classification, TaxIdentifierClassification.LEGAL_ENTITY_TAX_IDENTIFIER)
        self.assertNotIn("spanish_personal_identifier", {reason.rule for reason in decision.reasons})

    def test_bad_company_checksum_is_ambiguous_and_not_called_personal(self) -> None:
        decision = self.gate.evaluate(procurement_record(tax_identifier="B00000001"))
        self.assertEqual(decision.decision, PrivacyDecisionType.QUARANTINE)
        self.assertEqual(decision.classifications[0].classification, TaxIdentifierClassification.AMBIGUOUS_TAX_IDENTIFIER)
        self.assertEqual(decision.reasons[0].rule, "ambiguous_tax_identifier")

    def test_structured_personal_tax_identifiers_are_quarantined_without_value_in_reason(self) -> None:
        for identifier in ("12345678Z", "X1234567L"):
            with self.subTest(identifier_kind=identifier[0]):
                decision = self.gate.evaluate(procurement_record(tax_identifier=identifier))
                self.assertEqual(decision.decision, PrivacyDecisionType.QUARANTINE)
                self.assertEqual(decision.classifications[0].classification, TaxIdentifierClassification.PERSONAL_IDENTIFIER)
                self.assertNotIn(identifier, json.dumps(decision.to_dict()))
        special_nif = self.gate.evaluate(procurement_record(tax_identifier="K0000000T"))
        self.assertEqual(special_nif.decision, PrivacyDecisionType.QUARANTINE)
        self.assertEqual(special_nif.classifications[0].classification, TaxIdentifierClassification.PERSONAL_IDENTIFIER)

    def test_ambiguous_tax_identifier_is_quarantined_without_asserting_personhood(self) -> None:
        identifier = "12345678A"  # Forma plausible con checksum inválido: no se atribuye a una persona.
        decision = self.gate.evaluate(procurement_record(tax_identifier=identifier))
        self.assertEqual(decision.decision, PrivacyDecisionType.QUARANTINE)
        self.assertEqual(decision.classifications[0].classification, TaxIdentifierClassification.AMBIGUOUS_TAX_IDENTIFIER)
        self.assertEqual(decision.reasons[0].rule, "ambiguous_tax_identifier")
        self.assertNotIn("personal_identifier", decision.classifications[0].classification.value)

    def test_disabling_identifier_rules_applies_to_structured_tax_fields(self) -> None:
        payload = json.loads((ROOT / "config" / "privacy-rules.json").read_text(encoding="utf-8"))
        payload["rules"]["spanish_personal_identifier"]["enabled"] = False
        payload["rules"]["ambiguous_tax_identifier"]["enabled"] = False
        gate = PrivacyGate(PrivacyConfig.from_mapping(payload))
        for identifier in ("12345678Z", "12345678A"):
            with self.subTest(identifier_shape=identifier[-1]):
                decision = gate.evaluate(procurement_record(tax_identifier=identifier))
                self.assertEqual(decision.decision, PrivacyDecisionType.ALLOW)
                self.assertEqual(decision.reasons, ())

    def test_false_positive_candidates_are_not_blocked(self) -> None:
        for title in (
            "BOE-A-2026-12345",
            "CPV 12345678-9 y código INE 12040",
            "Fecha 2026-09-23 e importe 12345678",
            "Hash a" * 64,
            "Expediente 12345678A con letra no válida",
            "Centralita del organismo: +34 964 123 456",
            "Teléfono de atención institucional: 964 123 456",
            "El teléfono particular figura en otro apartado; centralita: 964 123 456",
            "Email oficial: registro@boe.es",
            "Contacto de empresa: administracion@asociacion-ficticia.example",
            "Sede administrativa: Plaza Ficticia 1, Municipio Ficticio",
        ):
            with self.subTest(title=title):
                self.assertEqual(self.gate.evaluate(make_record(title=title)).decision, PrivacyDecisionType.ALLOW)

    def test_phone_email_and_address_rules_are_not_applied_to_awardee_names(self) -> None:
        record = procurement_record(
            awardee_name="Centralita +34 964 123 456 contacto@gmail.com Sede ficticia 12"
        )
        self.assertEqual(self.gate.evaluate(record).decision, PrivacyDecisionType.ALLOW)

    def test_multiple_detections_are_explicable_without_values(self) -> None:
        record = make_record(description="DNI 12345678Z y contacto@gmail.com; IBAN ES9121000418450200051332")
        decision = self.gate.evaluate(record)
        self.assertEqual(decision.decision, PrivacyDecisionType.QUARANTINE)
        self.assertGreaterEqual(len(decision.reasons), 3)
        payload = decision.to_dict()
        self.assertEqual(payload["record_id"], record.id)
        self.assertNotIn("12345678Z", json.dumps(payload))
        self.assertNotIn("gmail.com", json.dumps(payload))

    def test_config_can_escalate_a_rule_to_reject(self) -> None:
        payload = json.loads((ROOT / "config" / "privacy-rules.json").read_text(encoding="utf-8"))
        payload["rules"]["iban"]["decision"] = "reject"
        gate = PrivacyGate(PrivacyConfig.from_mapping(payload))
        self.assertEqual(
            gate.evaluate(make_record(title="IBAN ES9121000418450200051332")).decision,
            PrivacyDecisionType.REJECT,
        )

    def test_default_rules_do_not_emit_reject(self) -> None:
        decisions = {
            self.gate.evaluate(make_record(title="DNI 12345678Z")).decision,
            self.gate.evaluate(make_record(title="Resolución limpia" )).decision,
        }
        self.assertNotIn(PrivacyDecisionType.REJECT, decisions)

    def test_unknown_rule_fails_configuration_contract(self) -> None:
        payload = json.loads((ROOT / "config" / "privacy-rules.json").read_text(encoding="utf-8"))
        payload["rules"]["unknown_rule"] = {"enabled": True, "decision": "allow"}
        with self.assertRaises(PrivacyGateError):
            PrivacyConfig.from_mapping(payload)

    def test_store_never_writes_quarantined_record(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory, privacy_gate=self.gate)
            sensitive = make_record(title="DNI 12345678Z")
            with self.assertRaises(RecordStoreError):
                store.write(sensitive)
            self.assertEqual(tuple(Path(directory).rglob("*.json")), ())

    def test_store_writes_allowed_record_after_gate(self) -> None:
        with TemporaryDirectory() as directory:
            store = RecordStore(directory, privacy_gate=self.gate)
            safe = make_record(title="Resolución del expediente FIC-2026-002")
            path = store.write(safe)
            self.assertTrue(path.is_file())
            self.assertEqual(store.get(safe.id, source_id=safe.source.id), safe)

    def test_gate_failure_is_explicit(self) -> None:
        with self.assertRaises(PrivacyGateError):
            PrivacyGate.from_file(ROOT / "config" / "missing-privacy-rules.json")

    def test_store_construction_fails_closed_when_default_policy_is_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "records"
            with patch("infocs.store.PrivacyGate.default", side_effect=PrivacyGateError("config unavailable")):
                with self.assertRaises(PrivacyGateError):
                    RecordStore(root)
            self.assertFalse(root.exists())

    def test_store_construction_fails_closed_when_policy_is_invalid(self) -> None:
        class InvalidPolicyGate(PrivacyGate):
            def validate(self) -> None:
                raise PrivacyGateError("invalid policy")

        with TemporaryDirectory() as directory:
            root = Path(directory) / "records"
            with self.assertRaises(PrivacyGateError):
                RecordStore(root, privacy_gate=InvalidPolicyGate())
            self.assertFalse(root.exists())

    def test_store_with_gate_exception_performs_zero_writes(self) -> None:
        class BrokenGate(PrivacyGate):
            def evaluate(self, record):  # type: ignore[no-untyped-def]
                raise RuntimeError("unexpected internal failure")

        with TemporaryDirectory() as directory:
            root = Path(directory) / "records"
            store = RecordStore(root, privacy_gate=BrokenGate())
            with self.assertRaises(RecordStoreError) as raised:
                store.write(make_record(title="Record seguro sintético"))
            self.assertNotIn("unexpected internal failure", str(raised.exception))
            self.assertFalse(root.exists())

    def test_configured_phone_context_terms_must_be_adjacent_to_number(self) -> None:
        distant = "Teléfono particular consta en el expediente; para consultas llame a centralita 964 123 456"
        self.assertEqual(self.gate.evaluate(make_record(title=distant)).decision, PrivacyDecisionType.ALLOW)

    def test_privacy_decision_and_store_error_do_not_expose_sensitive_value(self) -> None:
        secret = "12345678Z"
        sensitive = make_record(description=f"DNI {secret}")
        decision = self.gate.evaluate(sensitive)
        self.assertNotIn(secret, repr(decision))
        self.assertNotIn(secret, json.dumps(decision.to_dict()))
        with TemporaryDirectory() as directory:
            store = RecordStore(directory, privacy_gate=self.gate)
            try:
                store.write(sensitive)
            except RecordStoreError as error:
                self.assertNotIn(secret, str(error))
                self.assertNotIn(secret, repr(error))
            else:
                self.fail("Store permitió escribir un Record en cuarentena.")
            self.assertEqual(tuple(Path(directory).rglob("*.json")), ())

    def test_boe_source_contract_requires_gate_and_disallows_mirroring(self) -> None:
        contract = (ROOT / "collectors" / "boe" / "source_contract.yaml").read_text(encoding="utf-8")
        self.assertIn("privacy_gate_required: true", contract)
        self.assertIn("mirror_documents: false", contract)
        self.assertIn("fulltext_publication: false", contract)


if __name__ == "__main__":
    unittest.main()
