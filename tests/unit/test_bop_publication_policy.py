"""Pruebas offline de prioridad Privacy → elegibilidad source-wide BOP."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bop_castellon.models import BOPAnnouncement, BOPIssue  # noqa: E402
from infocs.fetch.bop_castellon.normalize import normalize_bop_announcement  # noqa: E402
from infocs.fetch.bop_castellon.publication import (  # noqa: E402
    BOPPublicationEvaluation,
    BOPPublicationPolicyError,
    bop_source_publication_eligibility,
    evaluate_bop_publication,
)
from infocs.diff.core import diff  # noqa: E402
from infocs.finalize import finalize_record  # noqa: E402
from infocs.models import SourceReference  # noqa: E402
from infocs.privacy import PrivacyConfig, PrivacyDecisionType, PrivacyGate  # noqa: E402
from infocs.publication import SourcePublicationEligibilityType  # noqa: E402


OBSERVED = datetime(2026, 9, 26, 10, 15, tzinfo=UTC)
CHECKED = datetime(2026, 9, 26, 10, 16, tzinfo=UTC)


def make_record(
    official_id: str = "100001",
    *,
    title: str = "Anuncio sintético de prueba",
    heading_path: tuple[str, ...] = (),
):
    issue = BOPIssue("200001", date(2026, 9, 24), "115", "B260924")
    announcement = BOPAnnouncement(
        official_id,
        title,
        f"https://bop.dipcas.es/PortalBOP/api/descargarAnuncio?idAnuncio={official_id}&idioma=es",
        heading_path=heading_path,
    )
    candidate = normalize_bop_announcement(
        issue, announcement, detected_at=OBSERVED, last_checked_at=CHECKED
    )
    return finalize_record(candidate)


class BOPPublicationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = PrivacyGate.default()

    def test_allow_reaches_source_hold_with_exact_reason(self) -> None:
        record = make_record()
        privacy = self.gate.evaluate(record)
        self.assertEqual(privacy.decision, PrivacyDecisionType.ALLOW)

        result = evaluate_bop_publication(record, privacy)

        self.assertIsInstance(result, BOPPublicationEvaluation)
        self.assertIs(result.privacy_decision, privacy)
        self.assertEqual(result.source_eligibility.decision, SourcePublicationEligibilityType.HOLD)
        self.assertEqual(result.source_eligibility.reason_code, "reuse_policy_unresolved")

    def test_source_hold_is_independent_of_identity_category_authority_and_geography(self) -> None:
        variants = (
            make_record("100001"),
            make_record(
                "100002",
                title="Licitación sintética",
                heading_path=("AYUNTAMIENTO DE VILA-REAL",),
            ),
        )
        decisions = []
        for record in variants:
            privacy = self.gate.evaluate(record)
            decisions.append(evaluate_bop_publication(record, privacy).source_eligibility)
        self.assertEqual(decisions[0], decisions[1])
        self.assertEqual(decisions[0], bop_source_publication_eligibility())

    def test_quarantine_stops_before_source_policy_and_is_preserved(self) -> None:
        record = make_record(title="DNI ficticio 12345678Z")
        privacy = self.gate.evaluate(record)
        self.assertEqual(privacy.decision, PrivacyDecisionType.QUARANTINE)

        result = evaluate_bop_publication(record, privacy)

        self.assertIs(result.privacy_decision, privacy)
        self.assertEqual(result.privacy_decision.decision, PrivacyDecisionType.QUARANTINE)
        self.assertIsNone(result.source_eligibility)

    def test_reject_stops_before_source_policy_and_is_preserved(self) -> None:
        payload = json.loads((ROOT / "config" / "privacy-rules.json").read_text(encoding="utf-8"))
        payload["rules"]["spanish_personal_identifier"]["decision"] = "reject"
        reject_gate = PrivacyGate(PrivacyConfig.from_mapping(payload))
        record = make_record(title="DNI ficticio 12345678Z")
        privacy = reject_gate.evaluate(record)
        self.assertEqual(privacy.decision, PrivacyDecisionType.REJECT)

        result = evaluate_bop_publication(record, privacy)

        self.assertIs(result.privacy_decision, privacy)
        self.assertEqual(result.privacy_decision.decision, PrivacyDecisionType.REJECT)
        self.assertIsNone(result.source_eligibility)

    def test_mismatched_or_nonfinalized_input_fails_closed(self) -> None:
        record = make_record()
        privacy = self.gate.evaluate(record)
        with self.assertRaises(BOPPublicationPolicyError):
            evaluate_bop_publication(make_record("100099"), privacy)
        with self.assertRaises(BOPPublicationPolicyError):
            evaluate_bop_publication(object(), privacy)  # type: ignore[arg-type]

        wrong_source = replace(record, source=SourceReference("boe", "BOE-A-2099-1"))
        wrong_source_privacy = self.gate.evaluate(record)
        with self.assertRaises(BOPPublicationPolicyError):
            evaluate_bop_publication(wrong_source, wrong_source_privacy)

    def test_source_decision_is_not_record_content_and_skips_manual_review(self) -> None:
        record = make_record()
        privacy = self.gate.evaluate(record)
        before = (record.id, record.technical.content_hash, record.canonical_json())

        with patch("infocs.publication.review.review_publication") as manual_review:
            result = evaluate_bop_publication(record, privacy)

        self.assertEqual(before, (record.id, record.technical.content_hash, record.canonical_json()))
        self.assertEqual(diff(record.to_dict(), record.to_dict()), ())
        self.assertNotIn("source_publication_eligibility", record.to_dict())
        self.assertEqual(result.source_eligibility.reason_code, "reuse_policy_unresolved")
        manual_review.assert_not_called()
        self.assertFalse(hasattr(result, "review_item"))
        self.assertNotEqual(result.source_eligibility.reason_code, "not_in_allowlist")

    def test_privacy_decision_for_another_record_is_rejected(self) -> None:
        first = make_record("100010")
        second = make_record("100011")
        privacy = self.gate.evaluate(first)
        with self.assertRaises(BOPPublicationPolicyError):
            evaluate_bop_publication(second, privacy)


if __name__ == "__main__":
    unittest.main()
