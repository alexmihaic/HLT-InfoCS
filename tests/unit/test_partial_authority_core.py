from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.diff.core import content_hash, diff
from infocs.finalize import finalize_record
from infocs.identity.core import identify
from infocs.models import DataValidationError, Record, RecordCandidate, validate_record_payload


FIXTURES = ROOT / "tests" / "fixtures"
PERSISTED_BOE = ROOT / "data" / "records" / "boe" / (
    "r-infocs%3Aboe%3Aboe-a-2026-19457-9ef9a385857862bd.json"
)
PERSISTED_BOE_ID = "infocs:boe:boe-a-2026-19457-9ef9a385857862bd"
PERSISTED_BOE_HASH = "0adbb4ed0cd82590d257df0e60715e19477ad2d9751c082f951dc91921fb1523"


def candidate_payload() -> dict:
    payload = json.loads((FIXTURES / "record_minimal_valid.json").read_text(encoding="utf-8"))
    payload.pop("id", None)
    payload.pop("technical", None)
    payload["source"]["official_id"] = "FICT-ANNOUNCEMENT-001"
    return payload


class PartialAuthorityCoreTests(unittest.TestCase):
    def test_authority_and_level_both_unknown_are_valid_and_serialize_as_null(self) -> None:
        payload = candidate_payload()
        payload["authority"] = None
        payload["administration_level"] = None

        candidate = RecordCandidate.from_dict(payload)
        serialized = candidate.to_dict()

        self.assertIsNone(candidate.authority)
        self.assertIsNone(candidate.administration_level)
        self.assertIsNone(serialized["authority"])
        self.assertIsNone(serialized["administration_level"])
        self.assertIsInstance(finalize_record(candidate), Record)

    def test_known_authority_with_unclassified_level_is_valid_and_serializes_null(self) -> None:
        payload = candidate_payload()
        payload["authority"]["administration_level"] = None
        payload["administration_level"] = None

        candidate = RecordCandidate.from_dict(payload)
        round_trip = RecordCandidate.from_dict(candidate.to_dict())

        self.assertEqual(round_trip.authority.id, "fixture_authority")
        self.assertIsNone(round_trip.authority.administration_level)
        self.assertIsNone(round_trip.administration_level)
        self.assertIsNone(round_trip.to_dict()["authority"]["administration_level"])

    def test_known_authority_with_matching_level_remains_valid(self) -> None:
        candidate = RecordCandidate.from_dict(candidate_payload())
        self.assertEqual(candidate.authority.administration_level.value, "municipal")
        self.assertEqual(candidate.administration_level.value, "municipal")

    def test_level_without_authority_is_rejected(self) -> None:
        payload = candidate_payload()
        payload["authority"] = None
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(payload)

    def test_mismatched_authority_and_record_levels_are_rejected(self) -> None:
        payload = candidate_payload()
        payload["administration_level"] = "state"
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(payload)

    def test_record_schema_accepts_both_unknown_and_known_authority_without_level(self) -> None:
        for authority in (None, {"id": "observed-authority", "name": "Organismo Sintético", "administration_level": None}):
            with self.subTest(authority=authority):
                payload = candidate_payload()
                payload["authority"] = authority
                payload["administration_level"] = None
                record = finalize_record(RecordCandidate.from_dict(payload))
                validate_record_payload(record.to_dict())
                restored = Record.from_dict(record.to_dict())
                self.assertEqual(restored.to_dict(), record.to_dict())
                canonical = json.loads(restored.canonical_json())
                self.assertIsNone(canonical["administration_level"])
                if authority is None:
                    self.assertIsNone(canonical["authority"])
                else:
                    self.assertIsNone(canonical["authority"]["administration_level"])

    def test_finalizer_is_stable_for_partial_authority_and_official_identity(self) -> None:
        payload = candidate_payload()
        payload["authority"] = None
        payload["administration_level"] = None
        first = finalize_record(RecordCandidate.from_dict(payload))
        second = finalize_record(RecordCandidate.from_dict(deepcopy(payload)))

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.technical.identity_strategy, "official_id")
        self.assertEqual(first.technical.content_hash, second.technical.content_hash)
        self.assertEqual(identify(first.to_dict()).record_id, first.id)

    def test_null_authority_fallback_identity_does_not_crash(self) -> None:
        payload = candidate_payload()
        payload["source"].pop("official_id")
        payload["authority"] = None
        payload["administration_level"] = None
        first = identify(payload)
        second = identify(deepcopy(payload))
        self.assertEqual(first, second)
        self.assertEqual(first.strategy, "canonical_url")

    def test_authority_metadata_keeps_existing_hash_and_diff_exclusions(self) -> None:
        without_authority = candidate_payload()
        without_authority["authority"] = None
        without_authority["administration_level"] = None
        known_without_level = deepcopy(without_authority)
        known_without_level["authority"] = {
            "id": "observed-authority",
            "name": "Organismo Sintético",
            "administration_level": None,
        }
        known_with_level = deepcopy(known_without_level)
        known_with_level["authority"]["administration_level"] = "provincial"
        known_with_level["administration_level"] = "provincial"
        changed_authority = deepcopy(known_with_level)
        changed_authority["authority"]["id"] = "another-authority"
        changed_authority["authority"]["name"] = "Otro Organismo Sintético"

        payloads = (without_authority, known_without_level, known_with_level, changed_authority)
        hashes = [content_hash(payload) for payload in payloads]
        self.assertEqual(len(set(hashes)), 1)
        for previous, current in zip(payloads, payloads[1:]):
            self.assertEqual(diff(previous, current), ())

    def test_existing_persisted_boe_record_and_hash_are_unchanged(self) -> None:
        payload = json.loads(PERSISTED_BOE.read_text(encoding="utf-8"))
        record = Record.from_dict(payload)
        self.assertEqual(record.id, PERSISTED_BOE_ID)
        self.assertEqual(record.technical.content_hash, PERSISTED_BOE_HASH)
        self.assertEqual(content_hash(payload), PERSISTED_BOE_HASH)
        self.assertEqual(record.to_dict(), payload)


if __name__ == "__main__":
    unittest.main()
