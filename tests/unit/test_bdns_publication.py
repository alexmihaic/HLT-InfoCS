"""Policy BDNS: Privacy -> source eligibility -> metadata publication scope."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bdns.models import BDNSRegion  # noqa: E402
from infocs.fetch.bdns.normalize import normalize_bdns_detail  # noqa: E402
from infocs.fetch.bdns.parser import parse_bdns_detail, parse_bdns_search  # noqa: E402
from infocs.fetch.bdns.publication import (  # noqa: E402
    BDNSMetadataPublicationDecisionType,
    BDNSPublicationPolicyError,
    authorize_bdns_event,
    bdns_source_publication_eligibility,
    evaluate_bdns_publication,
)
from infocs.finalize import finalize_record  # noqa: E402
from infocs.models import (  # noqa: E402
    Awardee,
    Category,
    Document,
    DocumentArchiveStatus,
    GrantDetails,
    SourceReference,
)
from infocs.privacy import PrivacyDecision, PrivacyDecisionType, PrivacyGate  # noqa: E402
from infocs.publication import SourcePublicationEligibilityType  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures" / "bdns"
OBSERVED = datetime(2026, 9, 27, 11, 0, tzinfo=UTC)
CHECKED = datetime(2026, 9, 27, 11, 0, tzinfo=UTC)


def source_pair(*, title: str | None = None):
    search_payload = json.loads((FIXTURES / "search_success.json").read_text(encoding="utf-8"))
    detail_payload = json.loads(
        (FIXTURES / "detail_success.json").read_text(encoding="utf-8"), parse_float=Decimal
    )
    summary = parse_bdns_search(search_payload).items[0]
    detail_payload["regiones"] = [{"descripcion": "ES522 - Castellón / Castelló"}]
    if title is not None:
        detail_payload["descripcion"] = title
    return summary, parse_bdns_detail(detail_payload)


def finalized_record(*, title: str | None = None):
    summary, detail = source_pair(title=title)
    result = normalize_bdns_detail(
        summary, detail, detected_at=OBSERVED, last_checked_at=CHECKED
    )
    return finalize_record(result.candidate)


class BDNSPublicationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = PrivacyGate.default()

    def test_allow_flows_to_eligible_then_publishable_metadata(self) -> None:
        record = finalized_record()
        privacy = self.gate.evaluate(record)
        result = evaluate_bdns_publication(record, privacy)
        self.assertEqual(privacy.decision, PrivacyDecisionType.ALLOW)
        self.assertEqual(result.source_eligibility, bdns_source_publication_eligibility())
        self.assertEqual(result.source_eligibility.decision, SourcePublicationEligibilityType.ELIGIBLE)
        self.assertIsNone(result.source_eligibility.reason_code)
        self.assertEqual(
            result.metadata_publication.decision,
            BDNSMetadataPublicationDecisionType.PUBLISHABLE_METADATA,
        )
        self.assertIsNone(result.metadata_publication.reason_code)
        authorization = authorize_bdns_event(record, result)
        self.assertIsNotNone(authorization)
        self.assertTrue(authorization.matches(record))
        self.assertEqual(authorization.policy_id, "bdns.metadata-publication.v1")

    def test_quarantine_and_reject_stop_before_source_eligibility(self) -> None:
        quarantined = finalized_record(title="DNI sintético 12345678Z")
        privacy_quarantine = self.gate.evaluate(quarantined)
        quarantine_result = evaluate_bdns_publication(quarantined, privacy_quarantine)
        self.assertEqual(privacy_quarantine.decision, PrivacyDecisionType.QUARANTINE)
        self.assertIsNone(quarantine_result.source_eligibility)
        self.assertIsNone(quarantine_result.metadata_publication)
        self.assertIsNone(authorize_bdns_event(quarantined, quarantine_result))

        record = finalized_record()
        privacy_reject = PrivacyDecision(PrivacyDecisionType.REJECT, record.id)
        reject_result = evaluate_bdns_publication(record, privacy_reject)
        self.assertIsNone(reject_result.source_eligibility)
        self.assertIsNone(reject_result.metadata_publication)
        self.assertIsNone(authorize_bdns_event(record, reject_result))

    def test_source_contract_errors_and_identity_mismatch_raise(self) -> None:
        record = finalized_record()
        privacy = self.gate.evaluate(record)
        with self.assertRaises(BDNSPublicationPolicyError):
            evaluate_bdns_publication(replace(record, source=SourceReference("boe", "BOE-A-1")), privacy)
        with self.assertRaises(BDNSPublicationPolicyError):
            evaluate_bdns_publication(record, PrivacyDecision(PrivacyDecisionType.ALLOW, "different-record"))

    def test_non_metadata_shape_is_held_without_privacy_rejection(self) -> None:
        record = finalized_record()
        privacy = self.gate.evaluate(record)
        self.assertEqual(privacy.decision, PrivacyDecisionType.ALLOW)

        variants = (
            replace(record, category=Category.OTHER),
            replace(record, grant=GrantDetails(call_id="900001", beneficiary=Awardee("Entidad sintética", "legal_entity"))),
            replace(record, grant=GrantDetails(call_id="900001", resolution_id="resolución-sintética")),
            replace(
                record,
                documents=(Document(
                    source_url="https://www.infosubvenciones.es/documento",
                    archive_status=DocumentArchiveStatus.NOT_ARCHIVED,
                    has_local_copy=False,
                    publication_allowed=False,
                ),),
            ),
            replace(record, description="Texto extenso sintético"),
            replace(record, geography=replace(record.geography, province="Valencia")),
        )
        for variant in variants:
            with self.subTest(variant=variant.category):
                decision = self.gate.evaluate(variant)
                self.assertEqual(decision.decision, PrivacyDecisionType.ALLOW)
                result = evaluate_bdns_publication(variant, decision)
                self.assertEqual(result.source_eligibility.decision, SourcePublicationEligibilityType.ELIGIBLE)
                self.assertEqual(result.metadata_publication.decision, BDNSMetadataPublicationDecisionType.HOLD)
                self.assertEqual(result.metadata_publication.reason_code, "metadata_scope_not_publishable")
                self.assertIsNone(authorize_bdns_event(variant, result))

    def test_only_approved_territorial_provenance_is_publishable(self) -> None:
        record = finalized_record()
        match = record.provenance.territorial_matches[0]
        detail = json.loads(match.detail)
        detail["catalog_id"] = 54
        changed = replace(
            record,
            provenance=replace(
                record.provenance,
                territorial_matches=(replace(match, detail=json.dumps(detail, sort_keys=True)),),
            ),
        )
        result = evaluate_bdns_publication(changed, self.gate.evaluate(changed))
        self.assertEqual(result.metadata_publication.decision, BDNSMetadataPublicationDecisionType.HOLD)

    def test_policy_does_not_change_record_identity_hash_or_diff_and_skips_boe_review(self) -> None:
        record = finalized_record()
        privacy = self.gate.evaluate(record)
        before = (record.id, record.technical.content_hash, record.canonical_json())
        with patch("infocs.publication.review.review_publication") as boe_review:
            result = evaluate_bdns_publication(record, privacy)
        self.assertEqual(before, (record.id, record.technical.content_hash, record.canonical_json()))
        self.assertEqual(result.metadata_publication.decision, BDNSMetadataPublicationDecisionType.PUBLISHABLE_METADATA)
        boe_review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
