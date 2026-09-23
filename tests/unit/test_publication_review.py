"""Pruebas offline de la revisión explícita previa a la publicación."""

from __future__ import annotations

from datetime import UTC, date, datetime
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.boe.controlled import (
    BOEControlledPublicationError,
    persist_approved_preview,
    prepare_boe_publication_preview,
)
from infocs.fetch.boe.models import (
    BOEDepartment,
    BOEDiary,
    BOEDocumentLinks,
    BOEFetchResult,
    BOEFetchStatus,
    BOEHeading,
    BOEItem,
    BOESection,
    BOESummary,
)
from infocs.models import Record
from infocs.privacy import PrivacyDecisionType
from infocs.publication import (
    PublicationDecisionType,
    PublicationReviewConfig,
    PublicationReviewError,
    PublicationDecision,
    review_publication,
)
from infocs.store import RecordStore


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
TEST_CONFIG = {
    "schema_version": "1",
    "source_id": "boe",
    "records": [
        {"official_id": "BOE-A-2099-1", "decision": "approved", "reason_code": "reviewed_safe"},
        {"official_id": "BOE-A-2099-2", "decision": "hold", "reason_code": "personal_content_review"},
        {"official_id": "BOE-A-2099-3", "decision": "rejected", "reason_code": "privacy_quarantine"},
    ],
}


def item(
    official_id: str,
    title: str = "Resolución relativa a Borriana",
    *,
    valid_urls: bool = True,
    published_on: date = date(2026, 9, 23),
) -> BOEItem:
    host = "https://www.boe.es" if valid_urls else "https://example.invalid"
    return BOEItem(
        official_id=official_id,
        title=title,
        section_code="2B",
        section_name="II.B. Autoridades y personal",
        department_code="9999",
        department_name="ADMINISTRACIÓN LOCAL",
        published_on=published_on,
        documents=BOEDocumentLinks(
            xml_url=f"{host}/diario_boe/xml.php?id={official_id}",
            html_url=f"{host}/diario_boe/txt.php?id={official_id}",
            pdf_url=f"{host}/boe/dias/2026/09/23/pdfs/{official_id}.pdf",
        ),
    )


def fetched(*items: BOEItem, day: date = date(2026, 9, 23)) -> BOEFetchResult:
    department = BOEDepartment("9999", "ADMINISTRACIÓN LOCAL", (BOEHeading("Avisos", tuple(items)),), ())
    summary = BOESummary(day, (BOEDiary("1", (BOESection("2B", "II.B.", (department,)),)),))
    return BOEFetchResult(BOEFetchStatus.COMPLETE_SUCCESS, 200, summary=summary)


def config(payload=TEST_CONFIG) -> PublicationReviewConfig:
    return PublicationReviewConfig.from_mapping(payload)


def prepare(*items: BOEItem, review_config=None):
    day = date(2026, 9, 23)
    return prepare_boe_publication_preview(
        {day: fetched(*items, day=day)},
        review_config=review_config or config(),
        detected_at=NOW,
        last_checked_at=NOW,
    )


class PublicationReviewTests(unittest.TestCase):
    def test_versioned_initial_config_has_exact_explicit_decisions(self) -> None:
        approved = PublicationReviewConfig.from_file(ROOT / "config/publication-review/boe-initial.json")
        self.assertEqual(approved.approved_ids, frozenset({"BOE-A-2026-19457"}))
        self.assertEqual(len(approved.entries), 7)
        self.assertEqual({entry.official_id for entry in approved.entries}, {
            "BOE-A-2026-19433", "BOE-A-2026-19457", "BOE-B-2026-30223",
            "BOE-B-2026-30232", "BOE-B-2026-30240", "BOE-B-2026-30520",
            "BOE-B-2026-30592",
        })

    def test_approved_record_is_written_only_after_privacy_and_review(self) -> None:
        preview = prepare(item("BOE-A-2099-1"))
        self.assertEqual(len(preview.approved), 1)
        self.assertEqual(preview.approved[0].privacy_decision.decision, PrivacyDecisionType.ALLOW)
        with TemporaryDirectory() as directory:
            result = persist_approved_preview(preview, store=RecordStore(directory), review_config=config())
            self.assertEqual(len(result.created_paths), 1)
            self.assertEqual(result.created_paths[0].read_bytes()[-1:], b"\n")

    def test_hold_rejected_and_unlisted_records_do_not_write(self) -> None:
        preview = prepare(
            item("BOE-A-2099-1"),
            item("BOE-A-2099-2"),
            item("BOE-A-2099-3"),
            item("BOE-A-2099-4"),
        )
        self.assertEqual([x.official_id for x in preview.approved], ["BOE-A-2099-1"])
        self.assertEqual({x.official_id for x in preview.holds}, {"BOE-A-2099-2", "BOE-A-2099-4"})
        self.assertEqual([x.official_id for x in preview.rejected], ["BOE-A-2099-3"])
        self.assertEqual(next(x for x in preview.holds if x.official_id == "BOE-A-2099-4").publication_decision.reason_code, "not_in_allowlist")
        with TemporaryDirectory() as directory:
            persist_approved_preview(preview, store=RecordStore(directory), review_config=config())
            self.assertEqual(len(list(Path(directory).rglob("r-*.json"))), 1)

    def test_privacy_quarantine_cannot_be_overridden_by_approved_entry(self) -> None:
        sensitive_config = {
            "schema_version": "1", "source_id": "boe", "records": [
                {"official_id": "BOE-A-2099-5", "decision": "approved", "reason_code": "reviewed_safe"}
            ]
        }
        with self.assertRaises(BOEControlledPublicationError):
            prepare(item("BOE-A-2099-5", "Aviso. DNI 12345678Z"), review_config=config(sensitive_config))
        with TemporaryDirectory() as directory:
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_invalid_config_and_missing_approved_id_fail_before_writes(self) -> None:
        with self.assertRaises(PublicationReviewError):
            config({"schema_version": "1", "source_id": "boe", "records": [
                {"official_id": "BOE-A-2099-1", "decision": "approved", "reason_code": "privacy_quarantine"}
            ]})
        with self.assertRaises(BOEControlledPublicationError):
            prepare(item("BOE-A-2099-2"))
        missing = config({"schema_version": "1", "source_id": "boe", "records": [
            {"official_id": "BOE-A-2099-99", "decision": "approved", "reason_code": "reviewed_safe"}
        ]})
        with self.assertRaises(BOEControlledPublicationError):
            prepare(item("BOE-A-2099-1"), review_config=missing)

    def test_persist_rechecks_versioned_approval_not_forgeable_preview_flag(self) -> None:
        preview = prepare(item("BOE-A-2099-1"))
        forged_item = replace(
            preview.items[0],
            publication_decision=PublicationDecision(PublicationDecisionType.APPROVED, "reviewed_safe", True),
        )
        forged_preview = replace(preview, items=(forged_item,))
        hold_config = config({"schema_version": "1", "source_id": "boe", "records": [
            {"official_id": "BOE-A-2099-1", "decision": "hold", "reason_code": "personal_content_review"}
        ]})
        with TemporaryDirectory() as directory:
            with self.assertRaises(BOEControlledPublicationError):
                persist_approved_preview(forged_preview, store=RecordStore(directory), review_config=hold_config)
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_batch_contract_failure_is_found_during_preflight(self) -> None:
        with self.assertRaises(BOEControlledPublicationError):
            prepare(item("BOE-A-2099-1"), item("BOE-A-2099-90", valid_urls=False))

    def test_duplicate_official_id_across_summaries_aborts_preflight(self) -> None:
        first_day = date(2026, 9, 22)
        second_day = date(2026, 9, 23)
        duplicate_config = config({"schema_version": "1", "source_id": "boe", "records": []})
        with self.assertRaises(BOEControlledPublicationError):
            prepare_boe_publication_preview(
                {
                    first_day: fetched(item("BOE-A-2099-4", published_on=first_day), day=first_day),
                    second_day: fetched(item("BOE-A-2099-4", published_on=second_day), day=second_day),
                },
                review_config=duplicate_config,
                detected_at=NOW,
                last_checked_at=NOW,
            )

    def test_province_only_match_is_not_approved_by_default(self) -> None:
        empty = config({"schema_version": "1", "source_id": "boe", "records": []})
        preview = prepare(item("BOE-A-2099-2", "Resolución para Castellón"), review_config=empty)
        self.assertEqual(len(preview.items), 1)
        self.assertEqual(preview.items[0].territorial_reasons, ("province_exact",))
        self.assertEqual(preview.items[0].publication_decision.decision, PublicationDecisionType.HOLD)

    def test_rerun_is_idempotent_and_keeps_record_id_hash_and_single_file(self) -> None:
        preview = prepare(item("BOE-A-2099-1"))
        with TemporaryDirectory() as directory:
            store = RecordStore(directory)
            first = persist_approved_preview(preview, store=store, review_config=config())
            stored = store.list_source("boe")[0]
            second = persist_approved_preview(preview, store=store, review_config=config())
            stored_again = store.list_source("boe")[0]
            self.assertEqual(len(first.created_paths), 1)
            self.assertEqual(second.created_paths, ())
            self.assertEqual(second.updated_paths, ())
            self.assertEqual(second.unchanged_ids, (stored.id,))
            self.assertEqual((stored.id, stored.technical.content_hash), (stored_again.id, stored_again.technical.content_hash))
            self.assertEqual(len(list(Path(directory).rglob("r-*.json"))), 1)

    def test_publication_decision_does_not_change_content_hash(self) -> None:
        preview = prepare(item("BOE-A-2099-1"))
        record = preview.items[0].record
        altered_review = PublicationReviewConfig.from_mapping({"schema_version": "1", "source_id": "boe", "records": [
            {"official_id": "BOE-A-2099-1", "decision": "hold", "reason_code": "personal_content_review"}
        ]})
        held = review_publication(record, preview.items[0].privacy_decision, altered_review)
        self.assertEqual(held.decision, PublicationDecisionType.HOLD)
        self.assertEqual(record.technical.content_hash, preview.items[0].record.technical.content_hash)

    def test_store_failure_in_preflight_creates_no_project_files(self) -> None:
        # La preparación no acepta un RecordStore, reforzando la frontera de fase.
        self.assertNotIn("store", prepare_boe_publication_preview.__annotations__)
        self.assertNotIn("store", prepare_boe_publication_preview.__code__.co_varnames)
        bad_config = {"schema_version": "1", "source_id": "boe", "records": [
            {"official_id": "BOE-A-2099-97", "decision": "approved", "reason_code": "reviewed_safe"}
        ]}
        with TemporaryDirectory() as directory:
            with self.assertRaises(BOEControlledPublicationError):
                prepare(item("BOE-A-2099-1"), review_config=config(bad_config))
            self.assertEqual(tuple(Path(directory).iterdir()), ())


if __name__ == "__main__":
    unittest.main()
