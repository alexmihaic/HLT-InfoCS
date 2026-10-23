"""Barrera BOE: fallos de persistencia en Git/stores exclusivamente temporales."""

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.events import EventStore, event_identity
from infocs.fetch.boe.history import BOEHistoryError, validate_boe_history
from infocs.fetch.boe.runner import run_boe_collection, runner_exit_code
from infocs.fetch.boe.workflow_safety import WorkflowSafetyError, stage_validated_artifacts
from infocs.manifests import ManifestStore, SoftwareMetadata
from infocs.privacy import PrivacyGate
from infocs.publication.review import PublicationReviewConfig
from infocs.store import RecordStore
from tests.unit.test_boe_runner import START, FINISH, fetched


class PublicationBarrierTests(unittest.TestCase):
    def setUp(self):
        # Fail the test if any code accidentally attempts network I/O.
        for target in ("socket.socket.connect", "socket.create_connection"):
            guard = patch(target, side_effect=AssertionError("offline test"))
            guard.start()
            self.addCleanup(guard.stop)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / "schemas", self.root / "schemas")
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Synthetic fixture")
        self.git("add", "--", "schemas")
        self.git("commit", "-qm", "fixture baseline")
        self.gate = PrivacyGate.default()
        self.records = RecordStore(self.root / "data/records", privacy_gate=self.gate)
        self.events = EventStore(self.root / "data/events")
        self.sequence = 0

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE)

    def run_batch(self, *, title="Resolución relativa a Borriana", count=1):
        self.sequence += 1
        response = fetched(title=title)
        first = response.summary.items[0]
        items = tuple(replace(first, official_id=f"BOE-A-2099-{1801+i}") for i in range(count))
        department = replace(response.summary.diaries[0].sections[0].departments[0],
                              headings=(replace(response.summary.diaries[0].sections[0].departments[0].headings[0], items=items),))
        section = replace(response.summary.diaries[0].sections[0], departments=(department,))
        response = replace(response, summary=replace(response.summary, diaries=(replace(response.summary.diaries[0], sections=(section,)),)))
        config = PublicationReviewConfig.from_mapping({"schema_version": "1", "source_id": "boe", "records": [
            {"official_id": entry.official_id, "decision": "approved", "reason_code": "reviewed_safe"} for entry in items
        ]})
        return run_boe_collection(
            START.date(), started_at=START + timedelta(days=self.sequence),
            clock=lambda: FINISH + timedelta(days=self.sequence),
            run_id=f"run-v1-00000000-0000-4000-8000-{self.sequence:012d}",
            transport=SimpleNamespace(fetch_daily_summary=lambda _: response),
            record_store=self.records, event_store=self.events,
            manifest_store=ManifestStore(self.root / "data/manifests"),
            health_path=self.root / "data/health/boe.json",
            review_queue_path=self.root / "data/review/boe/pending.json",
            review_config=config, privacy_gate=self.gate,
            software_metadata=SoftwareMetadata("fixture", source_contract_version="1"),
        )

    def publish(self, result):
        manifest = ManifestStore(self.root / "data/manifests").get(f"run-v1-00000000-0000-4000-8000-{self.sequence:012d}")
        paths = stage_validated_artifacts(self.root, runner_exit_code(manifest.status))
        self.git("diff", "--cached", "--check")
        self.git("commit", "-qm", "synthetic publication")
        return paths

    def published_paths(self, prefix):
        return self.git("ls-tree", "-r", "--name-only", "HEAD", "--", prefix).decode().splitlines()

    def put_event(self, event):
        path = self.events.path_for(event.source_id, event.record_id, event.event_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    def remove_event(self, event):
        self.events.path_for(event.source_id, event.record_id, event.event_id).unlink()

    def test_interrupted_create_publishes_observability_only(self):
        with patch.object(self.records, "write", side_effect=OSError("synthetic")):
            result = self.run_batch()
        self.assertEqual(result.status.value, "source_failure")
        self.assertEqual(len(self.events.list_source("boe")), 1)
        paths = self.publish(result)
        self.assertTrue(all(p.startswith(("data/manifests/boe/", "data/health/")) for p in paths))
        self.assertEqual(self.published_paths("data/events"), [])
        self.assertEqual(self.published_paths("data/records"), [])
        self.assertEqual(self.published_paths("data/review"), [])
        health = json.loads(self.git("show", "HEAD:data/health/boe.json"))
        self.assertEqual(health["status"], "degraded")
        manifest = ManifestStore(self.root / "data/manifests").list_source("boe")[0]
        self.assertEqual(manifest.status.value, "failed")
        self.assertIsNotNone(manifest.error_summary)

    def test_multiple_create_failure_publishes_none_of_partial_batch(self):
        write = self.records.write
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic")
            return write(*args, **kwargs)
        with patch.object(self.records, "write", side_effect=fail_second):
            result = self.run_batch(count=3)
        self.assertEqual(len(self.records.list_source("boe")), 1)
        self.assertEqual(len(self.events.list_source("boe")), 3)
        self.publish(result)
        self.assertFalse(self.published_paths("data/records"))
        self.assertFalse(self.published_paths("data/events"))

    def test_interrupted_update_keeps_published_version(self):
        self.publish(self.run_batch())
        record_path = self.published_paths("data/records")[0]
        original = self.git("show", f"HEAD:{record_path}")
        with patch.object(self.records, "write", side_effect=OSError("synthetic")):
            failed = self.run_batch(title="Resolución modificada relativa a Borriana")
        self.publish(failed)
        self.assertEqual(original, self.git("show", f"HEAD:{record_path}"))
        self.assertEqual(len(self.published_paths("data/events")), 1)

    def test_identical_retry_recovers_and_publishes_together(self):
        with patch.object(self.records, "write", side_effect=OSError("synthetic")):
            failed = self.run_batch()
        self.publish(failed)
        self.publish(self.run_batch())
        self.assertEqual(len(self.published_paths("data/records")), 1)
        self.assertEqual(len(self.published_paths("data/events")), 1)
        validate_boe_history(self.root)

    def test_changed_source_next_ephemeral_checkout_uses_published_state(self):
        self.publish(self.run_batch())
        with patch.object(self.records, "write", side_effect=OSError("synthetic")):
            failed = self.run_batch(title="Resolución B relativa a Borriana")
        self.publish(failed)
        clone = self.root / "next-checkout"
        self.git("clone", "-q", "--no-hardlinks", str(self.root), str(clone))
        # A new Actions checkout contains no uncommitted Event from the failed run.
        self.root = clone
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Synthetic fixture")
        self.records = RecordStore(clone / "data/records", privacy_gate=self.gate)
        self.events = EventStore(clone / "data/events")
        self.publish(self.run_batch(title="Resolución C relativa a Borriana"))
        self.assertEqual(len(self.events.list_source("boe")), 2)
        validate_boe_history(clone)

    def test_changed_source_after_failed_create_publishes_only_new_create(self):
        with patch.object(self.records, "write", side_effect=OSError("synthetic")):
            failed = self.run_batch()
        self.publish(failed)
        clone = self.root / "next-checkout"
        self.git("clone", "-q", "--no-hardlinks", str(self.root), str(clone))
        self.root = clone
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Synthetic fixture")
        self.records = RecordStore(clone / "data/records", privacy_gate=self.gate)
        self.events = EventStore(clone / "data/events")
        self.publish(self.run_batch(title="Resolución B relativa a Borriana"))
        self.assertEqual(len(self.events.list_source("boe")), 1)
        validate_boe_history(clone)

    def test_event_failure_before_and_after_first_write_keeps_records_unpublished(self):
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at):
                write = self.events.write
                calls = 0
                def fail(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == fail_at:
                        raise OSError("synthetic")
                    return write(*args, **kwargs)
                with patch.object(self.events, "write", side_effect=fail):
                    result = self.run_batch(count=3)
                self.assertEqual(self.records.list_source("boe"), ())
                self.publish(result)
                self.assertFalse(self.published_paths("data/events"))

    def test_success_publishes_records_events_and_safe_review_together(self):
        paths = self.publish(self.run_batch())
        self.assertTrue(any(p.startswith("data/records/boe/") for p in paths))
        self.assertTrue(any(p.startswith("data/events/boe/") for p in paths))
        validate_boe_history(self.root)

    def test_no_change_and_repeated_transition_publish_safely(self):
        self.publish(self.run_batch())
        paths = self.publish(self.run_batch())
        self.assertFalse(any(p.startswith(("data/records/", "data/events/")) for p in paths))
        self.publish(self.run_batch(title="Resolución B relativa a Borriana"))
        self.publish(self.run_batch())
        self.publish(self.run_batch(title="Resolución B relativa a Borriana"))
        self.assertEqual(len(self.published_paths("data/events")), 3)

    def test_success_with_missing_record_or_stale_version_is_blocked(self):
        self.run_batch()
        path = next((self.root / "data/records").rglob("*.json"))
        path.unlink()
        with self.assertRaises((WorkflowSafetyError, BOEHistoryError)):
            stage_validated_artifacts(self.root, 0)
        self.assertFalse(self.git("diff", "--cached", "--name-only"))

    def test_failure_excludes_even_malformed_partial_records_events_and_review(self):
        with patch.object(self.records, "write", side_effect=OSError("synthetic")):
            result = self.run_batch()
        for relative in ("data/records/boe/partial.json", "data/events/boe/partial.json", "data/review/boe/pending.json"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not JSON", encoding="utf-8")
        paths = self.publish(result)
        self.assertEqual(len(paths), 2)

    def test_unexpected_changes_or_preexisting_index_are_blocked(self):
        self.run_batch()
        path = self.root / "data/records/bdns/partial.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(WorkflowSafetyError, "changed_path_not_boe"):
            stage_validated_artifacts(self.root, 0)
        path.unlink()
        self.git("add", "--", "data/events")
        with self.assertRaisesRegex(WorkflowSafetyError, "index_not_empty"):
            stage_validated_artifacts(self.root, 0)

    def test_invalid_exit_status_missing_observability_and_status_mismatch(self):
        for code in (-1, 256, True, "0"):
            with self.subTest(code=code), self.assertRaises(WorkflowSafetyError):
                stage_validated_artifacts(self.root, code)
        with self.assertRaisesRegex(WorkflowSafetyError, "observability_missing"):
            stage_validated_artifacts(self.root, 1)
        self.run_batch()
        with self.assertRaisesRegex(WorkflowSafetyError, "manifest_exit_code_mismatch"):
            stage_validated_artifacts(self.root, 1)

    def test_incorrect_health_is_blocked(self):
        self.run_batch()
        path = self.root / "data/health/boe.json"
        payload = json.loads(path.read_bytes())
        payload["last_run_id"] = "run-v1-00000000-0000-4000-8000-000000000999"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(WorkflowSafetyError, "health_manifest_history_mismatch"):
            stage_validated_artifacts(self.root, 0)

    def test_success_without_transition_event_is_blocked_even_for_legacy_record(self):
        self.publish(self.run_batch())
        self.run_batch(title="Resolución B relativa a Borriana")
        update = [e for e in self.events.list_source("boe") if e.type == "update"][0]
        self.remove_event(update)
        with self.assertRaises((WorkflowSafetyError, BOEHistoryError)):
            stage_validated_artifacts(self.root, 0)

    def test_existing_events_and_manifests_are_append_only(self):
        self.publish(self.run_batch())
        for prefix in ("data/events", "data/manifests"):
            relative = self.published_paths(prefix)[0]
            path = self.root / relative
            raw = path.read_bytes()
            path.write_bytes(raw + b" ")
            with self.assertRaisesRegex(WorkflowSafetyError, "append_only_artifact_modified"):
                stage_validated_artifacts(self.root, 1)
            path.write_bytes(raw)

    def test_legacy_record_without_create_then_update_is_accepted(self):
        self.run_batch()
        self.remove_event(self.events.list_source("boe")[0])
        validate_boe_history(self.root)
        self.run_batch(title="Resolución B relativa a Borriana")
        validate_boe_history(self.root)

    def test_stale_record_and_incompatible_creates_are_rejected(self):
        self.run_batch()
        path = next((self.root / "data/records").rglob("*.json"))
        original = path.read_bytes()
        self.run_batch(title="Resolución B relativa a Borriana")
        current = path.read_bytes()
        path.write_bytes(original)
        with self.assertRaisesRegex(BOEHistoryError, "tip_mismatch"):
            validate_boe_history(self.root)
        path.write_bytes(current)
        update = self.events.list_source("boe")[-1]
        self.put_event(replace(update, type="create", previous_content_hash=None, changed_fields=(),
                               event_id=event_identity(update.record_id, "create", update.content_hash)))
        with self.assertRaisesRegex(BOEHistoryError, "incompatible_creates"):
            validate_boe_history(self.root)

    def test_disconnected_updates_and_forks_are_rejected(self):
        self.run_batch()
        self.run_batch(title="Resolución B relativa a Borriana")
        self.run_batch(title="Resolución C relativa a Borriana")
        create, ab, bc = self.events.list_source("boe")
        self.remove_event(ab)
        with self.assertRaisesRegex(BOEHistoryError, "disconnected_or_forked"):
            validate_boe_history(self.root)
        self.put_event(ab)
        self.remove_event(bc)
        self.put_event(replace(bc, previous_content_hash=create.content_hash,
                               event_id=event_identity(bc.record_id, "update", bc.content_hash, create.content_hash)))
        with self.assertRaisesRegex(BOEHistoryError, "disconnected_or_forked"):
            validate_boe_history(self.root)

    def test_v1_repeated_transition_and_return_then_new_version_are_accepted(self):
        self.run_batch()
        self.run_batch(title="Resolución B relativa a Borriana")
        self.run_batch()  # B -> A
        self.run_batch(title="Resolución B relativa a Borriana")  # repeats A -> B
        self.assertEqual(len(self.events.list_source("boe")), 3)
        validate_boe_history(self.root)
        self.run_batch()  # repeats B -> A
        self.run_batch(title="Resolución C relativa a Borriana")
        validate_boe_history(self.root)

    def test_history_timestamp_tie_is_not_arbitrarily_ordered(self):
        self.run_batch()
        self.run_batch(title="Resolución B relativa a Borriana")
        create, update = self.events.list_source("boe")
        self.put_event(replace(update, observed_at=create.observed_at))
        with self.assertRaisesRegex(BOEHistoryError, "order_ambiguous"):
            validate_boe_history(self.root)

    def test_canonical_validator_rejects_boe_orphan_with_safe_reason(self):
        from tests.unit.test_validate_canonical_data import validate_canonical_data as validator
        self.run_batch()
        next((self.root / "data/records").rglob("*.json")).unlink()
        with self.assertRaises(validator.CanonicalDataError) as raised:
            validator.validate_canonical_data(self.root)
        self.assertIn("boe_event_without_record", str(raised.exception))
        self.assertNotIn("BOE-A-2099", str(raised.exception))
        self.assertNotIn(str(self.root), str(raised.exception))

    def test_bdns_historical_hash_does_not_enter_boe_history_rules(self):
        self.run_batch()
        # Deliberately unrelated source bytes: this helper must not read BDNS.
        path = self.root / "data/events/bdns/legacy.json"
        path.parent.mkdir(parents=True)
        path.write_text("not a BOE event", encoding="utf-8")
        validate_boe_history(self.root)

    def test_workflow_uses_barrier_and_keeps_final_failure_and_remote_sha_guard(self):
        workflow = (ROOT / ".github/workflows/boe-manual.yml").read_text(encoding="utf-8")
        self.assertIn('--runner-exit-code "$RUNNER_EXIT_CODE"', workflow)
        self.assertNotIn("git add -- data/records", workflow)
        self.assertIn("always() && steps.collection.outputs.exit_code != '0'", workflow)
        self.assertRegex(workflow, r"Propagate collection failure[\s\S]+run: exit 1")
        self.assertIn('if [[ "$remote_main" != "$GITHUB_SHA" ]]', workflow)


if __name__ == "__main__":
    unittest.main()
