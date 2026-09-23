"""Pruebas offline de la cola segura y derivada de revisión BOE."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.boe.review_queue import (
    BOEReviewQueueStore,
    ReviewQueueEntry,
    ReviewQueueObservation,
    ReviewQueueError,
)


RUN_1 = "run-v1-00000000-0000-4000-8000-000000000018"
RUN_2 = "run-v1-00000000-0000-4000-8000-000000000019"
OFFICIAL_ID = "BOE-A-2099-1801"


def pending(run_id: str = RUN_1) -> ReviewQueueEntry:
    return ReviewQueueEntry(
        source_id="boe",
        official_id=OFFICIAL_ID,
        source_url=f"https://www.boe.es/doc.html?id={OFFICIAL_ID}",
        published_at="2026-09-18",
        run_id=run_id,
        territorial_reason_codes=("municipality_exact", "province_exact"),
        entity_codes=("12", "12040"),
        publication_decision="hold",
        reason_code="territorial_review_required",
    )


class BOEReviewQueueTests(unittest.TestCase):
    def test_unknown_privacy_allowed_hold_becomes_minimized_pending_entry(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "review" / "boe" / "pending.json"
            store = BOEReviewQueueStore(path)
            result = store.update((ReviewQueueObservation("boe", OFFICIAL_ID, pending()),))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result.pending_count, 1)
            entry = payload["records"][0]
            self.assertEqual(entry["publication_decision"], "hold")
            self.assertNotIn("title", entry)
            self.assertNotIn("description", entry)
            self.assertNotIn("authority", entry)
            self.assertNotIn("documents", entry)

    def test_rerun_deduplicates_and_updates_safe_last_seen_run_id(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pending.json"
            store = BOEReviewQueueStore(path)
            store.update((ReviewQueueObservation("boe", OFFICIAL_ID, pending()),))
            second = store.update((ReviewQueueObservation("boe", OFFICIAL_ID, pending(RUN_2)),))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(second.pending_count, 1)
            self.assertEqual(len(payload["records"]), 1)
            self.assertEqual(payload["records"][0]["run_id"], RUN_2)

    def test_approved_item_removes_existing_hold(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pending.json"
            store = BOEReviewQueueStore(path)
            store.update((ReviewQueueObservation("boe", OFFICIAL_ID, pending()),))
            result = store.update((ReviewQueueObservation("boe", OFFICIAL_ID, None),))
            self.assertEqual(result.pending_count, 0)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["records"], [])

    def test_quarantine_observation_never_adds_pending_and_clears_old_hold(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pending.json"
            store = BOEReviewQueueStore(path)
            store.update((ReviewQueueObservation("boe", OFFICIAL_ID, pending()),))
            store.update((ReviewQueueObservation("boe", OFFICIAL_ID, None),))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["records"], [])

    def test_incompatible_duplicate_observations_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pending.json"
            store = BOEReviewQueueStore(path)
            with self.assertRaises(ReviewQueueError):
                store.update((
                    ReviewQueueObservation("boe", OFFICIAL_ID, pending()),
                    ReviewQueueObservation("boe", OFFICIAL_ID, None),
                ))
            self.assertFalse(path.exists())

    def test_serialization_is_deterministic_and_uses_newline(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pending.json"
            store = BOEReviewQueueStore(path)
            store.update((ReviewQueueObservation("boe", OFFICIAL_ID, pending()),))
            first = path.read_bytes()
            store.update((ReviewQueueObservation("boe", OFFICIAL_ID, pending()),))
            self.assertEqual(path.read_bytes(), first)
            self.assertTrue(first.endswith(b"\n"))

    def test_unsafe_url_and_invalid_reason_rejected(self) -> None:
        with self.assertRaises(ReviewQueueError):
            replace(pending(), source_url="https://evil.example/doc")


if __name__ == "__main__":
    unittest.main()
