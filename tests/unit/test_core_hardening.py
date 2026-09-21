"""Regresiones de la frontera entre contenido de fuente y estado InfoCs."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.dedupe.core import ObservationStatus, reconcile
from infocs.diff.core import content_hash, diff, semantic_payload
from infocs.finalize import finalize_record
from infocs.models import DataValidationError, Record


def fixture(name: str = "record_procurement_valid.json") -> dict:
    payload = json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))
    payload.pop("id", None)
    technical = payload.get("technical")
    if technical is not None:
        technical.pop("content_hash", None)
        technical.pop("identity_strategy", None)
        if not technical:
            payload.pop("technical", None)
    return payload


SOURCE = "fixture_procurement"
BASE_TIME = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


def at(day: int) -> str:
    return (BASE_TIME + timedelta(days=day)).isoformat().replace("+00:00", "Z")


class SourceSemanticStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = fixture()

    def assert_internal_change_is_not_source_change(self, mutate) -> None:
        changed = deepcopy(self.base)
        mutate(changed)
        self.assertEqual(content_hash(self.base), content_hash(changed))
        self.assertEqual(diff(self.base, changed), ())

    def test_internal_status_is_excluded_including_quarantine(self) -> None:
        for status in ("missing_from_source", "withdrawn", "quarantine"):
            with self.subTest(status=status):
                self.assert_internal_change_is_not_source_change(lambda item: item.__setitem__("status", status))

    def test_tags_category_territory_and_relations_are_excluded(self) -> None:
        self.assert_internal_change_is_not_source_change(lambda item: item.__setitem__("tags", ["nuevo"]))
        self.assert_internal_change_is_not_source_change(lambda item: item.__setitem__("category", "other"))
        self.assert_internal_change_is_not_source_change(
            lambda item: item["provenance"].__setitem__(
                "territorial_matches", [{"reason": "explicit_text_match", "detail": "ficción"}]
            )
        )
        self.assert_internal_change_is_not_source_change(
            lambda item: item.__setitem__(
                "relations", [{"type": "same_event_as", "target_id": "infocs:fixture:other"}]
            )
        )

    def test_check_time_technical_and_document_archive_flags_are_excluded(self) -> None:
        self.assert_internal_change_is_not_source_change(
            lambda item: item["dates"].__setitem__("last_checked_at", at(1))
        )
        self.assert_internal_change_is_not_source_change(
            lambda item: item["technical"].__setitem__("raw_sha256", "a" * 64)
        )
        self.assert_internal_change_is_not_source_change(
            lambda item: item["documents"][0].__setitem__("has_local_copy", True)
        )
        self.assert_internal_change_is_not_source_change(
            lambda item: item["documents"][0].__setitem__("mime", "application/octet-stream")
        )

    def test_previous_hash_must_be_consistent(self) -> None:
        state, _ = reconcile({}, [self.base], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(0))
        record_id = next(iter(state))
        state[record_id]["technical"]["content_hash"] = "0" * 64
        with self.assertRaises(DataValidationError):
            reconcile(state, [], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(1))

    def test_source_amount_awardee_and_document_content_change_hash(self) -> None:
        for mutate, expected in (
            (lambda item: item["financial"]["award_amount"].__setitem__("value", "10000.00"), "financial.award_amount.value"),
            (lambda item: item["procurement"]["awardee"].__setitem__("name", "Otra Empresa Ficticia SL"), "procurement.awardee.name"),
            (lambda item: item["documents"][0].__setitem__("sha256", "e" * 64), "documents"),
        ):
            with self.subTest(path=expected):
                changed = deepcopy(self.base)
                mutate(changed)
                self.assertNotEqual(content_hash(self.base), content_hash(changed))
                self.assertIn(expected, {change.path for change in diff(self.base, changed)})

    def test_decimal_equivalence_and_set_order(self) -> None:
        changed = deepcopy(self.base)
        changed["financial"]["award_amount"]["value"] = "9876.540"
        changed["procurement"]["cpv"].reverse()
        changed["tags"].reverse()
        changed["provenance"]["territorial_matches"].reverse()
        self.assertEqual(content_hash(self.base), content_hash(changed))
        self.assertEqual(diff(self.base, changed), ())

    def test_finalizer_is_pure_and_persists_computed_hash(self) -> None:
        original = deepcopy(self.base)
        result = finalize_record(self.base)
        self.assertIsInstance(result, Record)
        self.assertEqual(self.base, original)
        self.assertEqual(result.technical.content_hash, content_hash(result.to_dict()))
        self.assertEqual(result.technical.identity_strategy, "official_id")
        self.assertTrue(result.id.startswith("infocs:fixture-procurement:"))
        self.assertEqual(result.financial.award_amount.value, "9876.54")
        self.assertEqual(Record.from_json(result.canonical_json()), result)

    def test_finalizer_normalizes_utc_and_decimal(self) -> None:
        candidate = deepcopy(self.base)
        candidate["dates"]["detected_at"] = "2026-09-21T11:00:00+02:00"
        candidate["financial"]["award_amount"]["value"] = "9876.5400"
        result = finalize_record(candidate)
        self.assertEqual(result.dates.to_dict()["detected_at"], "2026-09-21T09:00:00Z")
        self.assertEqual(result.financial.award_amount.value, "9876.54")

    def test_finalizer_rejects_cross_field_inconsistency(self) -> None:
        candidate = deepcopy(self.base)
        candidate["authority"]["administration_level"] = "state"
        with self.assertRaises(DataValidationError):
            finalize_record(candidate)


class ObservationLifecycleTests(unittest.TestCase):
    def test_repeated_absence_one_event_and_never_withdrawn(self) -> None:
        state, events = reconcile({}, [fixture()], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(0))
        self.assertEqual([event.type for event in events], ["create"])
        record_id = next(iter(state))
        initial_hash = state[record_id]["technical"]["content_hash"]
        for day in (1, 2, 3, 4):
            state, events = reconcile(state, [], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(day))
            self.assertEqual([event.type for event in events], ["missing_from_source"] if day == 1 else [])
            self.assertEqual(state[record_id]["status"], "missing_from_source")
            self.assertEqual(state[record_id]["technical"]["content_hash"], initial_hash)
            self.assertEqual(state[record_id]["dates"]["last_checked_at"], at(day))

    def test_reappearance_unchanged_is_single_event(self) -> None:
        state, _ = reconcile({}, [fixture()], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(0))
        state, _ = reconcile(state, [], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(1))
        record_id = next(iter(state))
        state, events = reconcile(state, [fixture()], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(2))
        self.assertEqual([event.type for event in events], ["reappeared"])
        self.assertEqual(events[0].changed_fields, ())
        self.assertEqual(events[0].previous_content_hash, events[0].new_content_hash)
        self.assertEqual(next(iter(state)), record_id)
        self.assertEqual(state[record_id]["status"], "active")

    def test_reappearance_changed_is_single_event_with_paths(self) -> None:
        state, _ = reconcile({}, [fixture()], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(0))
        state, _ = reconcile(state, [], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(1))
        changed = fixture()
        changed["financial"]["award_amount"]["value"] = "10000.00"
        state, events = reconcile(state, [changed], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(2))
        self.assertEqual([event.type for event in events], ["reappeared"])
        self.assertEqual(events[0].changed_fields, ("financial.award_amount.value",))
        self.assertNotEqual(events[0].previous_content_hash, events[0].new_content_hash)

    def test_derived_only_change_has_no_update(self) -> None:
        state, _ = reconcile({}, [fixture()], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(0))
        changed = fixture()
        changed["tags"] = ["reclasificado"]
        changed["relations"] = [{"type": "same_event_as", "target_id": "infocs:fixture:other"}]
        _, events = reconcile(state, [changed], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(1))
        self.assertEqual(events, ())

    def test_reobservation_does_not_clear_quarantine(self) -> None:
        state, _ = reconcile({}, [fixture()], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(0))
        record_id = next(iter(state))
        # Simula una decisión interna previa de privacidad sobre un Record final.
        state[record_id]["status"] = "quarantine"
        state[record_id] = Record.from_dict(state[record_id]).to_dict()
        state, events = reconcile(state, [fixture()], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(1))
        self.assertEqual(events, ())
        self.assertEqual(next(iter(state.values()))["status"], "quarantine")

    def test_observed_candidate_cannot_claim_to_be_missing(self) -> None:
        candidate = fixture()
        candidate["status"] = "missing_from_source"
        with self.assertRaises(DataValidationError):
            reconcile({}, [candidate], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(0))

    def test_failed_and_partial_runs_do_not_mark_absent(self) -> None:
        state, _ = reconcile({}, [fixture()], ObservationStatus.COMPLETE_SUCCESS, source_id=SOURCE, checked_at=at(0))
        for observation in (ObservationStatus.FAILED, ObservationStatus.PARTIAL_SUCCESS):
            state, events = reconcile(state, [], observation, source_id=SOURCE, checked_at=at(1))
            self.assertEqual(events, ())
            self.assertEqual(next(iter(state.values()))["status"], "active")
