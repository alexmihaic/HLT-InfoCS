from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.finalize import finalize_record
from infocs.models import (
    AdministrationLevel,
    Category,
    DataValidationError,
    Money,
    Record,
    RecordCandidate,
    RecordStatus,
    SourceDefinition,
    TechnicalMetadata,
    validate_record_candidate_payload,
    validate_record_payload,
)


FIXTURES = ROOT / "tests" / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def candidate_fixture(name: str) -> dict:
    payload = fixture(name)
    payload.pop("id", None)
    technical = payload.get("technical")
    if technical is not None:
        technical.pop("content_hash", None)
        technical.pop("identity_strategy", None)
        if not technical:
            payload.pop("technical", None)
    return payload


class RecordModelTests(unittest.TestCase):
    def test_minimal_candidate_is_valid(self) -> None:
        candidate = candidate_fixture("record_minimal_valid.json")
        self.assertNotIn("id", candidate)
        self.assertNotIn("technical", candidate)
        self.assertIsInstance(RecordCandidate.from_dict(candidate), RecordCandidate)

    def test_candidate_rejects_final_only_fields(self) -> None:
        candidate = candidate_fixture("record_minimal_valid.json")
        candidate["id"] = "infocs:incorrect:provisional"
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(candidate)
        candidate.pop("id")
        candidate["technical"] = {"content_hash": "a" * 64}
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(candidate)
        candidate["technical"] = {"identity_strategy": "official_id"}
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(candidate)

    def test_candidate_accepts_only_active_status(self) -> None:
        candidate = candidate_fixture("record_minimal_valid.json")
        self.assertIsInstance(RecordCandidate.from_dict(candidate), RecordCandidate)
        for status in ("missing_from_source", "withdrawn", "quarantine"):
            with self.subTest(status=status):
                invalid = deepcopy(candidate)
                invalid["status"] = status
                with self.assertRaises(DataValidationError):
                    RecordCandidate.from_dict(invalid)

    def test_all_valid_record_fixtures_are_valid_candidates_and_finalize(self) -> None:
        for name in (
            "record_minimal_valid.json",
            "record_regulation_valid.json",
            "record_procurement_valid.json",
            "record_grant_valid.json",
        ):
            with self.subTest(name=name):
                candidate = candidate_fixture(name)
                validate_record_candidate_payload(candidate)
                self.assertIsInstance(RecordCandidate.from_dict(candidate), RecordCandidate)
                self.assertIsInstance(finalize_record(candidate), Record)

    def test_complete_procurement_preserves_distinct_exact_amounts(self) -> None:
        record = finalize_record(candidate_fixture("record_procurement_valid.json"))
        self.assertEqual(record.financial.award_amount.value, "9876.54")
        self.assertEqual(record.financial.base_budget.currency, "EUR")
        self.assertEqual(record.procurement.expediente, "FICT-EXP-2026-001")

    def test_persistible_record_requires_id_hash_and_identity_strategy(self) -> None:
        candidate = candidate_fixture("record_minimal_valid.json")
        with self.assertRaises(DataValidationError):
            Record.from_dict(candidate)
        record = finalize_record(candidate).to_dict()
        without_id = deepcopy(record)
        del without_id["id"]
        with self.assertRaises(DataValidationError):
            Record.from_dict(without_id)
        without_hash = deepcopy(record)
        del without_hash["technical"]["content_hash"]
        with self.assertRaises(DataValidationError):
            Record.from_dict(without_hash)
        without_strategy = deepcopy(record)
        del without_strategy["technical"]["identity_strategy"]
        with self.assertRaises(DataValidationError):
            Record.from_dict(without_strategy)

    def test_technical_identity_strategy_uses_controlled_values(self) -> None:
        metadata = TechnicalMetadata("a" * 64, "official_id")
        self.assertEqual(metadata.identity_strategy, "official_id")
        with self.assertRaises(DataValidationError):
            TechnicalMetadata("a" * 64, "invented_strategy")

    def test_final_record_validates_against_portable_schema(self) -> None:
        record = finalize_record(candidate_fixture("record_procurement_valid.json"))
        validate_record_payload(record.to_dict())
        self.assertEqual(Record.from_json(record.canonical_json()), record)

    def test_equivalent_candidates_finalize_to_same_identity_and_hash(self) -> None:
        first = candidate_fixture("record_procurement_valid.json")
        second = deepcopy(first)
        second["financial"]["award_amount"]["value"] = "9876.540"
        second["procurement"]["cpv"].reverse()
        self.assertEqual(finalize_record(first).id, finalize_record(second).id)
        self.assertEqual(
            finalize_record(first).technical.content_hash,
            finalize_record(second).technical.content_hash,
        )

    def test_missing_required_field_is_rejected(self) -> None:
        payload = candidate_fixture("record_minimal_valid.json")
        del payload["title"]
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(payload)

    def test_invalid_category_is_rejected(self) -> None:
        payload = candidate_fixture("record_minimal_valid.json")
        payload["category"] = "political.judgement"
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(payload)

    def test_invalid_administration_level_fixture_is_rejected(self) -> None:
        payload = candidate_fixture("record_invalid.json")
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(payload)

    def test_money_is_exact_and_rejects_float(self) -> None:
        money = Money(value="12.30", currency="EUR")
        self.assertEqual(money.value, "12.30")
        with self.assertRaises(DataValidationError):
            Money(value=12.30, currency="EUR")  # type: ignore[arg-type]

    def test_invalid_timestamp_is_rejected(self) -> None:
        payload = candidate_fixture("record_minimal_valid.json")
        payload["dates"]["detected_at"] = "2026-09-21"
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(payload)

    def test_unarchived_document_without_copy_is_valid(self) -> None:
        record = finalize_record(candidate_fixture("record_procurement_valid.json"))
        document = record.documents[0]
        self.assertFalse(document.has_local_copy)
        self.assertEqual(document.archive_status.value, "not_archived")

    def test_source_definition_contract_loads(self) -> None:
        source = SourceDefinition.from_dict(fixture("source_definition_valid.json"))
        self.assertFalse(source.reuse.mirror_documents)
        self.assertEqual(source.reuse.default_document_policy, "link_and_hash")

    def test_json_schema_and_model_reject_the_same_invalid_fixture(self) -> None:
        invalid_payload = candidate_fixture("record_invalid.json")
        with self.assertRaises(DataValidationError):
            validate_record_candidate_payload(invalid_payload)
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(invalid_payload)

    def test_schema_controlled_vocabularies_match_python_models(self) -> None:
        schema = json.loads((ROOT / "schemas" / "record.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(schema["$defs"]["category"]["enum"]), {item.value for item in Category})
        self.assertEqual(
            set(schema["$defs"]["administration_level"]["enum"]),
            {item.value for item in AdministrationLevel},
        )
        self.assertEqual(
            set(schema["$defs"]["candidate_core"]["properties"]["status"]["enum"]),
            {item.value for item in RecordStatus},
        )
        candidate_schema = json.loads(
            (ROOT / "schemas" / "record_candidate.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            candidate_schema["allOf"][1]["properties"]["status"]["const"],
            RecordStatus.ACTIVE.value,
        )
        self.assertEqual(
            set(schema["$defs"]["final_technical"]["properties"]["identity_strategy"]["enum"]),
            {"official_id", "case_number", "canonical_url", "composite_fingerprint"},
        )
