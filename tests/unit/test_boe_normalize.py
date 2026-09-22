"""Pruebas offline de normalización BOE hacia el contrato InfoCs."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.boe import (
    BOEDocumentLinks,
    BOEItem,
    BOENormalizationError,
    BOETerritorialDecision,
    BOETerritorialDecisionStatus,
    BOETerritorialField,
    BOETerritorialMatch,
    BOETerritorialMatchReason,
    category_for_boe_section,
    normalize_boe_item,
)
from infocs.finalize import finalize_record
from infocs.models import (
    Category,
    RecordCandidate,
    validate_record_candidate_payload,
    validate_record_payload,
)


OBSERVED_AT = datetime(2026, 9, 22, 10, 30, tzinfo=UTC)


def boe_item(
    *,
    official_id: str = "BOE-A-2099-12345",
    title: str = "Resolución relativa a Borriana",
    section_code: str = "1",
    department_code: str = "9999",
    department_name: str = "MINISTERIO DE EJEMPLO",
    published_on: date | object = date(2099, 1, 1),
    documents: BOEDocumentLinks | None = None,
    heading_name: str | None = None,
) -> BOEItem:
    return BOEItem(
        official_id=official_id,
        title=title,
        section_code=section_code,
        section_name="I. Disposiciones generales",
        department_code=department_code,
        department_name=department_name,
        published_on=published_on,  # type: ignore[arg-type]
        documents=documents or BOEDocumentLinks(
            xml_url="https://www.boe.es/diario_boe/xml.php?id=BOE-A-2099-12345",
            html_url="https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-12345",
            pdf_url="https://www.boe.es/boe/dias/2099/01/01/pdfs/BOE-A-2099-12345.pdf",
            pdf_size_bytes=1200,
            pdf_first_page=10,
            pdf_last_page=11,
        ),
        heading_name=heading_name,
    )


def match(
    *,
    reason: BOETerritorialMatchReason = BOETerritorialMatchReason.MUNICIPALITY_EXACT,
    entity_code: str = "12031",
    entity_name: str = "Borriana",
    field: BOETerritorialField = BOETerritorialField.TITLE,
) -> BOETerritorialMatch:
    return BOETerritorialMatch(
        reason=reason,
        entity_code=entity_code,
        entity_name=entity_name,
        field=field,
        matched_text=entity_name,
        method="official_variant_casefolded_diacritic_insensitive_boundary",
    )


def include(*matches: BOETerritorialMatch) -> BOETerritorialDecision:
    return BOETerritorialDecision(BOETerritorialDecisionStatus.INCLUDE, matches)


def no_match() -> BOETerritorialDecision:
    return BOETerritorialDecision(BOETerritorialDecisionStatus.NO_MATCH, ())


class BOENormalizationTests(unittest.TestCase):
    def normalize(
        self,
        item: BOEItem | None = None,
        decision: BOETerritorialDecision | None = None,
        *,
        detected_at: datetime = OBSERVED_AT,
        last_checked_at: datetime = OBSERVED_AT,
    ) -> RecordCandidate | None:
        return normalize_boe_item(
            item or boe_item(),
            decision or include(match()),
            detected_at=detected_at,
            last_checked_at=last_checked_at,
        )

    def test_inclusion_produces_schema_valid_active_candidate(self) -> None:
        candidate = self.normalize()
        assert candidate is not None
        self.assertIsInstance(candidate, RecordCandidate)
        self.assertEqual(candidate.status.value, "active")
        self.assertEqual(candidate.source.id, "boe")
        self.assertEqual(candidate.source.official_id, "BOE-A-2099-12345")
        self.assertEqual(candidate.authority.id, "boe-department:9999")
        self.assertEqual(candidate.authority.name, "MINISTERIO DE EJEMPLO")
        self.assertEqual(candidate.authority.administration_level.value, "state")
        self.assertEqual(candidate.administration_level.value, "state")
        self.assertEqual(candidate.dates.published_at, date(2099, 1, 1))
        self.assertIsNone(candidate.dates.event_at)
        self.assertIsNone(candidate.description)
        self.assertIsNone(candidate.financial)
        self.assertIsNone(candidate.procurement)
        self.assertIsNone(candidate.grant)
        self.assertEqual(candidate.technical.extraction_method if candidate.technical else None, "boe_summary_json")
        self.assertNotIn("identity_strategy", candidate.technical.to_dict() if candidate.technical else {})
        self.assertNotIn("content_hash", candidate.technical.to_dict() if candidate.technical else {})
        validate_record_candidate_payload(candidate.to_dict())

    def test_no_match_produces_no_candidate(self) -> None:
        self.assertIsNone(self.normalize(decision=no_match()))

    def test_source_url_prefers_html_and_documents_remain_link_only(self) -> None:
        candidate = self.normalize()
        assert candidate is not None
        self.assertEqual(candidate.source_url, "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-12345")
        self.assertEqual(len(candidate.documents), 3)
        for document in candidate.documents:
            self.assertEqual(document.archive_status.value, "not_archived")
            self.assertFalse(document.has_local_copy)
            self.assertFalse(document.publication_allowed)
            self.assertIsNone(document.mime_type)
            self.assertIsNone(document.sha256)

    def test_source_url_falls_back_to_xml_then_pdf_when_an_alternative_is_absent(self) -> None:
        xml_fallback = boe_item(
            documents=BOEDocumentLinks(
                xml_url="https://www.boe.es/diario_boe/xml.php?id=BOE-A-2099-12345",
                html_url="",
                pdf_url="https://www.boe.es/boe/dias/2099/01/01/pdfs/BOE-A-2099-12345.pdf",
            )
        )
        pdf_fallback = boe_item(
            documents=BOEDocumentLinks(
                xml_url="",
                html_url="",
                pdf_url="https://www.boe.es/boe/dias/2099/01/01/pdfs/BOE-A-2099-12345.pdf",
            )
        )
        xml_candidate = self.normalize(xml_fallback)
        pdf_candidate = self.normalize(pdf_fallback)
        assert xml_candidate is not None and pdf_candidate is not None
        self.assertEqual(xml_candidate.source_url, xml_fallback.documents.xml_url)
        self.assertEqual(pdf_candidate.source_url, pdf_fallback.documents.pdf_url)

    def test_minimal_section_mapping_is_explicit(self) -> None:
        self.assertEqual(category_for_boe_section("1"), Category.REGULATION)
        self.assertEqual(category_for_boe_section("2B"), Category.EMPLOYMENT)
        self.assertEqual(category_for_boe_section("5A"), Category.PROCUREMENT)
        self.assertEqual(category_for_boe_section("5B"), Category.OTHER)
        self.assertEqual(category_for_boe_section("9"), Category.OTHER)
        candidate = self.normalize(boe_item(section_code="5A"))
        assert candidate is not None
        self.assertEqual(candidate.category, Category.PROCUREMENT)

    def test_territorial_provenance_preserves_boe_evidence_and_unique_municipality_sets_geography(self) -> None:
        candidate = self.normalize()
        assert candidate is not None
        self.assertEqual(candidate.provenance.territorial_matches[0].reason.value, "municipality_match")
        detail = json.loads(candidate.provenance.territorial_matches[0].detail or "{}")
        self.assertEqual(
            detail,
            {
                "boe_reason": "municipality_exact",
                "entity_code": "12031",
                "entity_name": "Borriana",
                "field": "title",
                "matched_text": "Borriana",
                "method": "official_variant_casefolded_diacritic_insensitive_boundary",
            },
        )
        self.assertEqual(candidate.geography.municipality if candidate.geography else None, "Borriana")

    def test_multiple_or_provincial_matches_do_not_invent_a_municipality(self) -> None:
        province = match(
            reason=BOETerritorialMatchReason.PROVINCE_EXACT,
            entity_code="12",
            entity_name="Castellón/Castelló",
        )
        for decision in (include(province), include(match(), province)):
            with self.subTest(decision=decision):
                candidate = self.normalize(decision=decision)
                assert candidate is not None
                self.assertIsNone(candidate.geography)

    def test_match_order_is_normalized_deterministically(self) -> None:
        province = match(
            reason=BOETerritorialMatchReason.PROVINCE_EXACT,
            entity_code="12",
            entity_name="Castellón/Castelló",
        )
        first = self.normalize(decision=include(match(), province))
        second = self.normalize(decision=include(province, match()))
        assert first is not None and second is not None
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_optional_heading_absence_does_not_change_normalization(self) -> None:
        candidate = self.normalize(boe_item(heading_name=None))
        assert candidate is not None
        self.assertIsNone(candidate.description)

    def test_finalizer_creates_valid_record_with_official_identity(self) -> None:
        candidate = self.normalize()
        assert candidate is not None
        record = finalize_record(candidate)
        validate_record_payload(record.to_dict())
        self.assertTrue(record.id.startswith("infocs:boe:"))
        self.assertEqual(record.technical.identity_strategy, "official_id")
        self.assertTrue(record.technical.content_hash)

    def test_equivalent_observations_produce_same_identity_and_hash(self) -> None:
        first_candidate = self.normalize()
        second_candidate = self.normalize(
            detected_at=OBSERVED_AT.astimezone(timezone(timedelta(hours=2))),
            last_checked_at=OBSERVED_AT.astimezone(timezone(timedelta(hours=2))),
        )
        assert first_candidate is not None and second_candidate is not None
        first = finalize_record(first_candidate)
        second = finalize_record(second_candidate)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.technical.content_hash, second.technical.content_hash)

    def test_administrative_title_change_keeps_id_and_changes_hash(self) -> None:
        first_candidate = self.normalize()
        changed_candidate = self.normalize(boe_item(title="Resolución corregida relativa a Borriana"))
        assert first_candidate is not None and changed_candidate is not None
        first = finalize_record(first_candidate)
        changed = finalize_record(changed_candidate)
        self.assertEqual(first.id, changed.id)
        self.assertNotEqual(first.technical.content_hash, changed.technical.content_hash)

    def test_territorial_change_keeps_identity_and_source_content_hash(self) -> None:
        first_candidate = self.normalize(decision=include(match()))
        changed_candidate = self.normalize(
            decision=include(match(entity_code="12089", entity_name="Peníscola"))
        )
        assert first_candidate is not None and changed_candidate is not None
        first = finalize_record(first_candidate)
        changed = finalize_record(changed_candidate)
        self.assertEqual(first.id, changed.id)
        self.assertEqual(first.technical.content_hash, changed.technical.content_hash)

    def test_invalid_contract_inputs_fail_explicitly(self) -> None:
        bad_documents = BOEDocumentLinks(
            xml_url="https://www.boe.es/diario_boe/xml.php?id=BOE-A-2099-12345",
            html_url="http://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-12345",
            pdf_url="https://www.boe.es/boe/dias/2099/01/01/pdfs/BOE-A-2099-12345.pdf",
        )
        cases = (
            (boe_item(official_id=""), include(match()), OBSERVED_AT, OBSERVED_AT),
            (boe_item(department_code=""), include(match()), OBSERVED_AT, OBSERVED_AT),
            (boe_item(department_name=""), include(match()), OBSERVED_AT, OBSERVED_AT),
            (boe_item(published_on="2099-01-01"), include(match()), OBSERVED_AT, OBSERVED_AT),
            (boe_item(documents=bad_documents), include(match()), OBSERVED_AT, OBSERVED_AT),
            (boe_item(), include(match()), datetime(2026, 9, 22, 10, 30), OBSERVED_AT),
            (boe_item(), include(match()), OBSERVED_AT + timedelta(days=1), OBSERVED_AT),
        )
        for item_value, decision, detected_at, last_checked_at in cases:
            with self.subTest(item=item_value):
                with self.assertRaises(BOENormalizationError):
                    self.normalize(
                        item_value,
                        decision,
                        detected_at=detected_at,
                        last_checked_at=last_checked_at,
                    )

    def test_include_without_matches_is_rejected_as_contract_drift(self) -> None:
        invalid = object.__new__(BOETerritorialDecision)
        object.__setattr__(invalid, "status", BOETerritorialDecisionStatus.INCLUDE)
        object.__setattr__(invalid, "matches", ())
        with self.assertRaises(BOENormalizationError):
            self.normalize(decision=invalid)


if __name__ == "__main__":
    unittest.main()
