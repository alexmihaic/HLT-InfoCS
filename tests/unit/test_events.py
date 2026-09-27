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
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.events import (
    Event,
    EventStore,
    EventStoreConflictError,
    EventStoreError,
    EventValidationError,
    create_event,
    event_identity,
    update_event,
    validate_event_payload,
)
from infocs.finalize import finalize_record
from infocs.models import RecordCandidate
from infocs.models import SourceReference
from infocs.privacy import PrivacyDecision, PrivacyDecisionType
from infocs.publication.review import PublicationDecision, PublicationDecisionType
from infocs.publication.authorization import PublicationAuthorization
from infocs.publication.authorization import PublicationAuthorizationError, _issue_publication_authorization
from infocs.fetch.boe.publication import authorize_boe_event


def load_record(name: str = "contract_v3_awardee_changed.json", *, title: str | None = None):
    payload = json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))
    payload["source"]["id"] = "boe"
    payload["source"]["official_id"] = "BOE-A-2099-12345"
    if title is not None:
        payload["title"] = title
    return finalize_record(RecordCandidate.from_dict(payload))


def decisions(record, *, privacy=PrivacyDecisionType.ALLOW, publication=PublicationDecisionType.APPROVED):
    return (
        PrivacyDecision(privacy, record.id),
        PublicationDecision(publication, "reviewed_safe" if publication is PublicationDecisionType.APPROVED else "personal_content_review", True),
    )


def authorization(record, *, privacy=PrivacyDecisionType.ALLOW, publication=PublicationDecisionType.APPROVED):
    privacy_decision, publication_decision = decisions(record, privacy=privacy, publication=publication)
    return authorize_boe_event(record, privacy_decision, publication_decision)


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
        create_b = create_event(b, observed_at=observed, authorization=authorization(b))
        create_b_retry = create_event(
            b, observed_at=observed.replace(hour=10), authorization=authorization(b)
        )
        a_to_b = update_event(a, b, observed_at=observed, authorization=authorization(b))
        a_to_b_retry = update_event(
            a, b, observed_at=observed.replace(hour=11), authorization=authorization(b)
        )
        c_to_b = update_event(c, b, observed_at=observed, authorization=authorization(b))
        assert create_b and create_b_retry and a_to_b and a_to_b_retry and c_to_b
        self.assertEqual(create_b.event_id, create_b_retry.event_id)
        self.assertNotEqual(create_b.event_id, a_to_b.event_id)
        self.assertEqual(a_to_b.event_id, a_to_b_retry.event_id)
        self.assertNotEqual(a_to_b.event_id, c_to_b.event_id)

    def test_create_and_update_schema_contracts(self) -> None:
        record = load_record()
        event = create_event(record, observed_at=datetime(2026, 9, 23, 9, tzinfo=UTC), authorization=authorization(record))
        assert event is not None
        schema = json.loads((ROOT / "schemas" / "event.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(event.to_dict())
        self.assertNotIn("changed_fields", event.to_dict())
        self.assertNotIn("authorization", event.to_dict())
        self.assertNotIn("policy_id", event.to_dict())

        changed = load_record(title="Contrato corregido")
        updated = update_event(record, changed, observed_at=datetime(2026, 9, 23, 10, tzinfo=UTC), authorization=authorization(changed))
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
        self.assertIsNone(create_event(record, observed_at=observed, authorization=authorization(record, privacy=PrivacyDecisionType.QUARANTINE)))
        self.assertIsNone(create_event(record, observed_at=observed, authorization=authorization(record, privacy=PrivacyDecisionType.REJECT)))
        self.assertIsNone(create_event(record, observed_at=observed, authorization=authorization(record, publication=PublicationDecisionType.HOLD)))
        self.assertIsNone(create_event(record, observed_at=observed, authorization=authorization(record, publication=PublicationDecisionType.REJECTED)))

    def test_authorization_is_opaque_bound_to_exact_record_and_hash(self) -> None:
        record = load_record()
        changed = load_record(title="Título administrativo actualizado")
        auth = authorization(record)
        self.assertIsNotNone(auth)
        self.assertTrue(auth.matches(record))
        self.assertFalse(auth.matches(changed))
        self.assertFalse(auth.matches(replace(record, id="infocs:boe:other")))
        self.assertFalse(auth.matches(replace(record, source=SourceReference("bdns", "900001"))))
        with self.assertRaises(EventValidationError):
            create_event(
                changed,
                observed_at=datetime(2026, 9, 23, 9, tzinfo=UTC),
                authorization=auth,
            )
        with self.assertRaises(TypeError):
            PublicationAuthorization("id", "source", "a" * 64, "policy.v1")  # type: ignore[call-arg]
        with self.assertRaises(PublicationAuthorizationError):
            _issue_publication_authorization(record, "")

    def test_missing_or_mismatched_authorization_fails_closed_in_eventstore(self) -> None:
        record = load_record()
        event = create_event(
            record,
            observed_at=datetime(2026, 9, 23, 9, tzinfo=UTC),
            authorization=authorization(record),
        )
        assert event is not None
        changed = load_record(title="Otra versión")
        stale_auth = authorization(record)
        with TemporaryDirectory() as directory:
            store = EventStore(directory)
            with self.assertRaises(EventStoreError):
                store.preflight(event, record=record, authorization=None)  # type: ignore[arg-type]
            with self.assertRaises(EventStoreError):
                store.preflight(event, record=changed, authorization=stale_auth)  # type: ignore[arg-type]
            altered_event = replace(event, content_hash="f" * 64)
            with self.assertRaises(EventValidationError):
                store.preflight(altered_event, record=record, authorization=authorization(record))
            self.assertEqual(store.list_source(record.source.id), ())

    def test_eventstore_does_not_reevaluate_privacy_or_source_policy(self) -> None:
        record = load_record()
        auth = authorization(record)
        event = create_event(
            record,
            observed_at=datetime(2026, 9, 23, 9, tzinfo=UTC),
            authorization=auth,
        )
        assert auth is not None and event is not None
        with TemporaryDirectory() as directory:
            store = EventStore(directory)
            with (
                patch("infocs.privacy.gate.PrivacyGate.evaluate", side_effect=AssertionError("must not run")) as privacy,
                patch("infocs.publication.review.review_publication", side_effect=AssertionError("must not run")) as review,
            ):
                self.assertTrue(store.write(event, record=record, authorization=auth).created)
            privacy.assert_not_called()
            review.assert_not_called()

    def test_derived_only_changes_do_not_create_update(self) -> None:
        first_payload = json.loads((ROOT / "tests" / "fixtures" / "contract_v3_awardee_changed.json").read_text(encoding="utf-8"))
        first_payload["source"]["id"] = "boe"
        second_payload = copy.deepcopy(first_payload)
        second_payload["provenance"]["territorial_matches"] = [{"reason": "municipality_match", "detail": "fixture municipality match"}]
        first = finalize_record(RecordCandidate.from_dict(first_payload))
        second = finalize_record(RecordCandidate.from_dict(second_payload))
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.technical.content_hash, second.technical.content_hash)
        self.assertIsNone(update_event(first, second, observed_at=datetime(2026, 9, 23, 9, tzinfo=UTC), authorization=authorization(second)))

    def test_event_store_append_only_idempotent_conflict_and_order(self) -> None:
        first = load_record()
        v2 = load_record(title="Versión 2")
        v3 = load_record(title="Versión 3")
        at1 = datetime(2026, 9, 23, 9, tzinfo=UTC)
        at2 = datetime(2026, 9, 23, 10, tzinfo=UTC)
        at3 = datetime(2026, 9, 23, 11, tzinfo=UTC)
        created = create_event(first, observed_at=at1, authorization=authorization(first))
        update2 = update_event(first, v2, observed_at=at2, authorization=authorization(v2))
        update3 = update_event(v2, v3, observed_at=at3, authorization=authorization(v3))
        assert created and update2 and update3
        self.assertEqual(update2.previous_content_hash, first.technical.content_hash)
        self.assertEqual(update2.content_hash, v2.technical.content_hash)
        self.assertEqual(update3.previous_content_hash, update2.content_hash)
        self.assertEqual(update3.content_hash, v3.technical.content_hash)

        with TemporaryDirectory() as directory:
            store = EventStore(directory)
            with self.assertRaises(TypeError):
                store.write(created)  # type: ignore[call-arg]
            first_auth = authorization(first)
            assert first_auth is not None
            self.assertTrue(store.write(created, record=first, authorization=first_auth).created)
            retry = replace(created, observed_at="2026-09-24T09:00:00Z")
            self.assertFalse(store.write(retry, record=first, authorization=first_auth).created)
            self.assertEqual(store.get(created.event_id).observed_at, created.observed_at)  # type: ignore[union-attr]
            store.write(update3, record=v3, authorization=authorization(v3))
            store.write(update2, record=v2, authorization=authorization(v2))
            self.assertEqual([event.event_id for event in store.list_record(first.id)], [created.event_id, update2.event_id, update3.event_id])
            self.assertEqual(store.get(update2.event_id), update2)
            self.assertTrue(store.exists(created.event_id))
            with self.assertRaises(EventStoreConflictError):
                store.write(replace(update2, changed_fields=("description",)), record=v2, authorization=authorization(v2))

    def test_path_components_are_encoded_and_event_id_is_validated(self) -> None:
        store = EventStore("C:/temporary/events")
        path = store.path_for("source/../other", "record/../../escape", "evt-v1-" + "a" * 64)
        self.assertIn("%2F", str(path))
        with self.assertRaises(Exception):
            store.path_for("boe", "record", "../../outside")

    def test_changed_fields_and_event_payload_never_contain_field_values(self) -> None:
        previous = load_record(title="Resolución ficticia")
        current = load_record(title="Resolución ficticia corregida")
        event = update_event(previous, current, observed_at=datetime(2026, 9, 23, 9, tzinfo=UTC), authorization=authorization(current))
        assert event is not None
        serialized = json.dumps(event.to_dict(), ensure_ascii=False)
        self.assertIn("title", serialized)
        for forbidden in ("DNI", "IBAN", "@gmail.com", "12345678Z"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(event.changed_fields, tuple(sorted(event.changed_fields)))


if __name__ == "__main__":
    unittest.main()
