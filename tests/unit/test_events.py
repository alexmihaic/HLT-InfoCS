"""Tests offline del contrato canónico y append-only de Events."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.events import (
    Event,
    EventStore,
    EventStoreConflictError,
    EventValidationError,
    create_event,
    event_identity,
    update_event,
    validate_event_payload,
)
from infocs.finalize import finalize_record
from infocs.models import RecordCandidate
from infocs.privacy import PrivacyDecision, PrivacyDecisionType
from infocs.publication.review import PublicationDecision, PublicationDecisionType
from infocs.publication.review import PublicationReviewConfig


def load_record(name: str = "contract_v3_awardee_changed.json", *, title: str | None = None):
    payload = json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))
    payload["source"]["official_id"] = "BOE-A-2099-12345"
    if title is not None:
        payload["title"] = title
    return finalize_record(RecordCandidate.from_dict(payload))


def decisions(record, *, privacy=PrivacyDecisionType.ALLOW, publication=PublicationDecisionType.APPROVED):
    return (
        PrivacyDecision(privacy, record.id),
        PublicationDecision(publication, "reviewed_safe" if publication is PublicationDecisionType.APPROVED else "personal_content_review", True),
    )


def review_config(record):
    return PublicationReviewConfig.from_mapping({
        "schema_version": "1",
        "source_id": record.source.id,
        "records": [{
            "official_id": record.source.official_id,
            "decision": "approved",
            "reason_code": "reviewed_safe",
        }],
    })


class CanonicalEventTests(unittest.TestCase):
    def test_event_identity_is_deterministic_and_content_versioned(self) -> None:
        first = event_identity("infocs:source:item", "create", "a" * 64)
        self.assertEqual(first, event_identity("infocs:source:item", "create", "a" * 64))
        self.assertNotEqual(first, event_identity("infocs:source:item", "update", "a" * 64, "b" * 64))

    def test_transition_identity_includes_previous_hash_but_not_observed_at(self) -> None:
        a = load_record(title="Estado A")
        c = load_record(title="Estado C")
        b = load_record(title="Estado B")
        observed = datetime(2026, 9, 23, 9, tzinfo=UTC)
        privacy_b, publication_b = decisions(b)
        create_b = create_event(b, observed_at=observed, privacy=privacy_b, publication=publication_b)
        privacy_b2, publication_b2 = decisions(b)
        create_b_retry = create_event(
            b, observed_at=observed.replace(hour=10), privacy=privacy_b2, publication=publication_b2
        )
        privacy_b3, publication_b3 = decisions(b)
        a_to_b = update_event(a, b, observed_at=observed, privacy=privacy_b3, publication=publication_b3)
        privacy_b4, publication_b4 = decisions(b)
        a_to_b_retry = update_event(
            a, b, observed_at=observed.replace(hour=11), privacy=privacy_b4, publication=publication_b4
        )
        privacy_b5, publication_b5 = decisions(b)
        c_to_b = update_event(c, b, observed_at=observed, privacy=privacy_b5, publication=publication_b5)
        assert create_b and create_b_retry and a_to_b and a_to_b_retry and c_to_b
        self.assertEqual(create_b.event_id, create_b_retry.event_id)
        self.assertNotEqual(create_b.event_id, a_to_b.event_id)
        self.assertEqual(a_to_b.event_id, a_to_b_retry.event_id)
        self.assertNotEqual(a_to_b.event_id, c_to_b.event_id)

    def test_create_and_update_schema_contracts(self) -> None:
        record = load_record()
        privacy, publication = decisions(record)
        event = create_event(record, observed_at=datetime(2026, 9, 23, 9, tzinfo=UTC), privacy=privacy, publication=publication)
        assert event is not None
        schema = json.loads((ROOT / "schemas" / "event.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(event.to_dict())
        self.assertNotIn("changed_fields", event.to_dict())

        changed = load_record(title="Contrato corregido")
        privacy, publication = decisions(changed)
        updated = update_event(record, changed, observed_at=datetime(2026, 9, 23, 10, tzinfo=UTC), privacy=privacy, publication=publication)
        assert updated is not None
        validator.validate(updated.to_dict())
        self.assertEqual(updated.previous_content_hash, record.technical.content_hash)
        self.assertEqual(updated.content_hash, changed.technical.content_hash)
        self.assertIn("title", updated.changed_fields)

        invalid = updated.to_dict()
        invalid.pop("previous_content_hash")
        with self.assertRaises(ValidationError):
            validator.validate(invalid)
        invalid = event.to_dict()
        invalid["previous_content_hash"] = "a" * 64
        with self.assertRaises(ValidationError):
            validator.validate(invalid)

    def test_privacy_or_publication_denial_produces_no_event(self) -> None:
        record = load_record()
        observed = datetime(2026, 9, 23, 9, tzinfo=UTC)
        privacy, publication = decisions(record, privacy=PrivacyDecisionType.QUARANTINE)
        self.assertIsNone(create_event(record, observed_at=observed, privacy=privacy, publication=publication))
        privacy, publication = decisions(record, privacy=PrivacyDecisionType.REJECT)
        self.assertIsNone(create_event(record, observed_at=observed, privacy=privacy, publication=publication))
        privacy, publication = decisions(record, publication=PublicationDecisionType.HOLD)
        self.assertIsNone(create_event(record, observed_at=observed, privacy=privacy, publication=publication))
        privacy, publication = decisions(record, publication=PublicationDecisionType.REJECTED)
        self.assertIsNone(create_event(record, observed_at=observed, privacy=privacy, publication=publication))

    def test_derived_only_changes_do_not_create_update(self) -> None:
        first_payload = json.loads((ROOT / "tests" / "fixtures" / "contract_v3_awardee_changed.json").read_text(encoding="utf-8"))
        second_payload = copy.deepcopy(first_payload)
        second_payload["provenance"]["territorial_matches"] = [{"reason": "municipality_match", "detail": "fixture municipality match"}]
        first = finalize_record(RecordCandidate.from_dict(first_payload))
        second = finalize_record(RecordCandidate.from_dict(second_payload))
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.technical.content_hash, second.technical.content_hash)
        privacy, publication = decisions(second)
        self.assertIsNone(update_event(first, second, observed_at=datetime(2026, 9, 23, 9, tzinfo=UTC), privacy=privacy, publication=publication))

    def test_event_store_append_only_idempotent_conflict_and_order(self) -> None:
        first = load_record()
        v2 = load_record(title="Versión 2")
        v3 = load_record(title="Versión 3")
        at1 = datetime(2026, 9, 23, 9, tzinfo=UTC)
        at2 = datetime(2026, 9, 23, 10, tzinfo=UTC)
        at3 = datetime(2026, 9, 23, 11, tzinfo=UTC)
        privacy, publication = decisions(first)
        created = create_event(first, observed_at=at1, privacy=privacy, publication=publication)
        privacy, publication = decisions(v2)
        update2 = update_event(first, v2, observed_at=at2, privacy=privacy, publication=publication)
        privacy, publication = decisions(v3)
        update3 = update_event(v2, v3, observed_at=at3, privacy=privacy, publication=publication)
        assert created and update2 and update3
        self.assertEqual(update2.previous_content_hash, first.technical.content_hash)
        self.assertEqual(update2.content_hash, v2.technical.content_hash)
        self.assertEqual(update3.previous_content_hash, update2.content_hash)
        self.assertEqual(update3.content_hash, v3.technical.content_hash)

        with TemporaryDirectory() as directory:
            store = EventStore(directory)
            with self.assertRaises(TypeError):
                store.write(created)  # type: ignore[call-arg]
            self.assertTrue(store.write(created, record=first, publication_review_config=review_config(first)).created)
            retry = replace(created, observed_at="2026-09-24T09:00:00Z")
            self.assertFalse(store.write(retry, record=first, publication_review_config=review_config(first)).created)
            self.assertEqual(store.get(created.event_id).observed_at, created.observed_at)  # type: ignore[union-attr]
            store.write(update3, record=v3, publication_review_config=review_config(v3))
            store.write(update2, record=v2, publication_review_config=review_config(v2))
            self.assertEqual([event.event_id for event in store.list_record(first.id)], [created.event_id, update2.event_id, update3.event_id])
            self.assertEqual(store.get(update2.event_id), update2)
            self.assertTrue(store.exists(created.event_id))
            with self.assertRaises(EventStoreConflictError):
                store.write(replace(update2, changed_fields=("description",)), record=v2, publication_review_config=review_config(v2))

    def test_path_components_are_encoded_and_event_id_is_validated(self) -> None:
        store = EventStore("C:/temporary/events")
        path = store.path_for("source/../other", "record/../../escape", "evt-v1-" + "a" * 64)
        self.assertIn("%2F", str(path))
        with self.assertRaises(Exception):
            store.path_for("boe", "record", "../../outside")

    def test_changed_fields_and_event_payload_never_contain_field_values(self) -> None:
        previous = load_record(title="Resolución ficticia")
        current = load_record(title="Resolución ficticia corregida")
        privacy, publication = decisions(current)
        event = update_event(previous, current, observed_at=datetime(2026, 9, 23, 9, tzinfo=UTC), privacy=privacy, publication=publication)
        assert event is not None
        serialized = json.dumps(event.to_dict(), ensure_ascii=False)
        self.assertIn("title", serialized)
        for forbidden in ("DNI", "IBAN", "@gmail.com", "12345678Z"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(event.changed_fields, tuple(sorted(event.changed_fields)))


if __name__ == "__main__":
    unittest.main()
