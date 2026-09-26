"""Contrato común para elegibilidad source-wide, separado de revisión manual."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.publication.source_policy import (  # noqa: E402
    SourcePublicationEligibilityDecision,
    SourcePublicationEligibilityError,
    SourcePublicationEligibilityType,
    source_eligible,
    source_hold,
)


class SourcePublicationPolicyTests(unittest.TestCase):
    def test_eligible_is_not_approval_and_has_no_reason(self) -> None:
        decision = source_eligible()
        self.assertEqual(decision.decision, SourcePublicationEligibilityType.ELIGIBLE)
        self.assertIsNone(decision.reason_code)
        self.assertNotEqual(decision.decision.value, "approved")

    def test_hold_requires_known_source_reason(self) -> None:
        self.assertEqual(source_hold("reuse_policy_unresolved").reason_code, "reuse_policy_unresolved")
        with self.assertRaises(SourcePublicationEligibilityError):
            source_hold("not_in_allowlist")

    def test_eligible_rejects_reason_code_and_unknown_enum_values(self) -> None:
        with self.assertRaises(SourcePublicationEligibilityError):
            SourcePublicationEligibilityDecision(SourcePublicationEligibilityType.ELIGIBLE, "reviewed_safe")
        with self.assertRaises(SourcePublicationEligibilityError):
            SourcePublicationEligibilityDecision("approved")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
