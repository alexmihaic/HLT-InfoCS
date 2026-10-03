"""Locators sintéticos, sin red, migración ni datos productivos."""

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.models import BDNSRegulatoryBases, DataValidationError, Record
from infocs.fetch.bdns.enrichment import (
    build_bdns_source_data, prepare_bdns_enriched_record,
    valid_bdns_regulatory_bases_source_locator, clickable_bdns_regulatory_bases_url,
)
from infocs.finalize import finalize_record
from infocs.diff.core import diff
from infocs.privacy import PrivacyDecisionType, PrivacyGate
from infocs.store import RecordStore
from tests.unit.test_bdns_enrichment_gates import enriched_candidate
from tests.unit.test_bdns_normalize import source_models, DETECTED, CHECKED


class BDNSLocatorTests(unittest.TestCase):
    def setUp(self):
        self.summary, self.detail = source_models()

    def test_https_http_schemeless_literal_roundtrip_and_clickability(self):
        for value, clickable in (
            ("https://public.example.invalid/BASES?x=1#section", True),
            ("http://public.example.invalid/BASES?x=1#section", False),
            ("public.example.invalid/BASES?x=1#section", False),
        ):
            with self.subTest(kind=value.split('/')[0]):
                self.assertTrue(valid_bdns_regulatory_bases_source_locator(value))
                data = build_bdns_source_data(replace(self.detail, regulatory_bases_url=value))
                self.assertEqual(data.bdns.regulatory_bases.source_locator, value)
                self.assertEqual(clickable_bdns_regulatory_bases_url(value), value if clickable else None)
                record = finalize_record(enriched_candidate(replace(self.detail, regulatory_bases_url=value)))
                self.assertEqual(Record.from_json(record.canonical_json()), record)
                self.assertEqual(record.source_data.bdns.regulatory_bases.to_dict()["source_locator"], value)
                self.assertNotIn("official_source_url", record.source_data.bdns.regulatory_bases.to_dict())

    def test_invalid_storage_shapes_fail_in_helper_and_constructor(self):
        values = (None, 7, "", " public.example.invalid/", "example.invalid/a b ",
            "example.invalid/\t", "example.invalid/\x00", "example.invalid/\x1f",
            "example.invalid/\x7f", "example.invalid/\\x", "example.invalid/%GG",
            "example.invalid/%", "example.invalid/%FF", "example.invalid/\ud800",
            "a" * 2049, "https://user:secret@example.invalid/", "http://user@example.invalid/",
            "//user:secret@example.invalid/", "user@example.invalid/path",
            "user%40example.invalid/path", "user%2540example.invalid/path", "https://[broken@host]/",
            "javascript:alert(1)", "data:text/plain,example", "file:///example")
        for value in values:
            with self.subTest(kind=type(value).__name__):
                self.assertFalse(valid_bdns_regulatory_bases_source_locator(value))
                self.assertIsNone(clickable_bdns_regulatory_bases_url(value))
                if value is not None:
                    with self.assertRaises(DataValidationError):
                        BDNSRegulatoryBases(source_locator=value)

    def test_navigation_only_rules_do_not_reject_storage(self):
        for value in ("https://127.0.0.1/bases", "https://[::1]/bases", "https://singlelabel/bases",
                      "https://example.local/bases", "https://example.localhost/bases",
                      "https://bad_host.invalid/bases", "https://example.invalid:bad/bases",
                      "https://[broken]/bases"):
            with self.subTest(kind=value.split('/')[0]):
                self.assertTrue(valid_bdns_regulatory_bases_source_locator(value))
                self.assertEqual(BDNSRegulatoryBases(source_locator=value).source_locator, value)
                self.assertIsNone(clickable_bdns_regulatory_bases_url(value))

    def test_internal_ascii_spaces_preserve_literal_and_are_never_clickable(self):
        for value in ("https://example.invalid/A B", "http://example.invalid/A B",
                      "example.invalid/A B", "https://example.invalid/A  B",
                      "opaque locator/path text"):
            with self.subTest(value=value):
                self.assertTrue(valid_bdns_regulatory_bases_source_locator(value))
                self.assertEqual(BDNSRegulatoryBases(source_locator=value).source_locator, value)
                record = finalize_record(enriched_candidate(replace(self.detail, regulatory_bases_url=value)))
                restored = Record.from_json(record.canonical_json())
                self.assertEqual(restored.source_data.bdns.regulatory_bases.source_locator, value)
                self.assertEqual(build_bdns_source_data(replace(self.detail, regulatory_bases_url=value)).bdns.regulatory_bases.source_locator, value)
                self.assertIsNone(clickable_bdns_regulatory_bases_url(value))

    def test_edges_other_whitespace_and_all_c0_c1_controls_still_rejected(self):
        values = [" example.invalid/bases", "example.invalid/bases ", " ", "  "]
        values += ["example.invalid/A" + c + "B" for c in (
            "\t", "\n", "\r", "\v", "\f", "\u00a0", "\u2003", "\u2028",
            "\x00", "\x7f", "\x80", "\x9f",
        )]
        values += ["example.invalid/A" + chr(code) + "B" for code in (*range(32), *range(127,160))]
        for value in values:
            self.assertFalse(valid_bdns_regulatory_bases_source_locator(value))
            self.assertIsNone(clickable_bdns_regulatory_bases_url(value))
            with self.assertRaises(DataValidationError):
                BDNSRegulatoryBases(source_locator=value)

    def test_internal_space_privacy_inspects_full_literal_and_encoded_pii(self):
        for value, allowed in (
            ("https://example.invalid/official bases", True),
            ("https://example.invalid/official bases/12345678Z", False),
            ("example.invalid/official bases/%31%32%33%34%35%36%37%38%5A", False),
        ):
            with tempfile.TemporaryDirectory() as temp:
                result = prepare_bdns_enriched_record(self.summary, replace(self.detail, regulatory_bases_url=value),
                    detected_at=DETECTED, last_checked_at=CHECKED, record_store=RecordStore(Path(temp)/"records"))
                self.assertIsNotNone(result.record)
                self.assertEqual(result.record.source_data.bdns.regulatory_bases.source_locator, value)
                self.assertEqual(result.privacy.decision is PrivacyDecisionType.ALLOW, allowed)
                self.assertEqual(result.safe_reason, None if allowed else "privacy_source_data_blocked")
                self.assertEqual(result.authorization is not None, allowed)

    def test_internal_space_count_and_position_are_material_not_clickability(self):
        values = ("example.invalid/A BC", "example.invalid/A  BC", "example.invalid/AB C")
        records = [finalize_record(enriched_candidate(replace(self.detail, regulatory_bases_url=v))) for v in values]
        self.assertEqual(len({record.technical.content_hash for record in records}), 3)
        self.assertTrue(any(c.path == "source_data.bdns.regulatory_bases.source_locator"
            for c in diff(records[0].to_dict(), records[1].to_dict())))
        for record, value in zip(records, values, strict=True):
            self.assertEqual(Record.from_json(record.canonical_json()).source_data.bdns.regulatory_bases.source_locator, value)
            before = record.canonical_json()
            self.assertIsNone(clickable_bdns_regulatory_bases_url(value))
            self.assertEqual(record.canonical_json(), before)
        with patch("infocs.fetch.bdns.enrichment.clickable_bdns_regulatory_bases_url", return_value="derived"):
            rebuilt = finalize_record(enriched_candidate(replace(self.detail, regulatory_bases_url=values[0])))
        self.assertEqual(rebuilt.technical.content_hash, records[0].technical.content_hash)

    def test_not_clickable_does_not_hold_publication(self):
        for value in ("http://public.example.invalid/bases", "public.example.invalid/bases"):
            with tempfile.TemporaryDirectory() as temp:
                result = prepare_bdns_enriched_record(self.summary, replace(self.detail, regulatory_bases_url=value),
                    detected_at=DETECTED, last_checked_at=CHECKED, record_store=RecordStore(Path(temp) / "records"))
                self.assertIsNone(result.safe_reason)
                self.assertEqual(result.privacy.decision, PrivacyDecisionType.ALLOW)
                self.assertEqual(result.publication.metadata_publication.decision.value, "publishable_metadata")
                self.assertTrue(result.authorization.matches(result.record))

    def test_personal_data_blocked_for_every_locator_shape_and_encoding(self):
        for value in ("https://example.invalid/12345678Z", "http://example.invalid/12345678Z",
                      "example.invalid/12345678Z", "example.invalid/%31%32%33%34%35%36%37%38%5A",
                      "example.invalid/bases?email=persona%40gmail.com", "example.invalid/bases#persona%40gmail.com",
                      "https://[broken]/12345678Z"):
            with self.subTest(kind=value.split('/')[0]), tempfile.TemporaryDirectory() as temp:
                result = prepare_bdns_enriched_record(self.summary, replace(self.detail, regulatory_bases_url=value),
                    detected_at=DETECTED, last_checked_at=CHECKED, record_store=RecordStore(Path(temp) / "records"))
                self.assertIsNotNone(result.record)
                self.assertEqual(result.safe_reason, "privacy_source_data_blocked")
                self.assertNotEqual(result.privacy.decision, PrivacyDecisionType.ALLOW)
                self.assertIsNone(result.authorization)

    def test_locator_literal_is_material_and_clickability_is_not(self):
        records = [finalize_record(enriched_candidate(replace(self.detail, regulatory_bases_url=value)))
                   for value in ("https://example.invalid/bases", "http://example.invalid/bases", "example.invalid/bases")]
        self.assertEqual(len({r.technical.content_hash for r in records}), 3)
        changes = diff(records[0].to_dict(), records[1].to_dict())
        self.assertTrue(any(c.path == "source_data.bdns.regulatory_bases.source_locator" for c in changes))
        before = records[0].canonical_json()
        clickable_bdns_regulatory_bases_url(records[0].source_data.bdns.regulatory_bases.source_locator)
        self.assertEqual(records[0].canonical_json(), before)
        with patch("infocs.fetch.bdns.enrichment.clickable_bdns_regulatory_bases_url", return_value=None):
            again = finalize_record(enriched_candidate(replace(self.detail, regulatory_bases_url="https://example.invalid/bases")))
        self.assertEqual(again.technical.content_hash, records[0].technical.content_hash)
        for field in ("clickable", "is_secure", "normalized_url", "derived_scheme"):
            raw = records[0].to_dict()
            raw["source_data"]["bdns"]["regulatory_bases"][field] = True
            with self.assertRaises(DataValidationError):
                Record.from_dict(raw)

    def test_unparseable_locator_full_string_and_decoded_still_inspected(self):
        for value in ("https://[broken]/safe", "https://[broken]/%31%32%33%34%35%36%37%38%5A"):
            record = finalize_record(enriched_candidate(replace(self.detail, regulatory_bases_url=value)))
            decision = PrivacyGate().evaluate(record)
            if value.endswith('/safe'):
                self.assertEqual(decision.decision, PrivacyDecisionType.ALLOW)
            else:
                self.assertNotEqual(decision.decision, PrivacyDecisionType.ALLOW)

    def test_privacy_decodes_nested_locator_and_query_form_without_rewriting(self):
        for value in ("example.invalid/%2531%2532%2533%2534%2535%2536%2537%2538%255A",
                      "example.invalid/bases?contact=persona%2540gmail.com"):
            record = finalize_record(enriched_candidate(replace(self.detail, regulatory_bases_url=value)))
            self.assertEqual(record.source_data.bdns.regulatory_bases.source_locator, value)
            self.assertNotEqual(PrivacyGate().evaluate(record).decision, PrivacyDecisionType.ALLOW)

    def test_literal_case_path_and_escape_spelling_are_material(self):
        values = ("https://example.invalid/BASES?key=%41", "https://example.invalid/bases?key=%41",
                  "https://example.invalid/BASES?key=A")
        records = [finalize_record(enriched_candidate(replace(self.detail, regulatory_bases_url=v))) for v in values]
        self.assertEqual(len({r.technical.content_hash for r in records}), len(values))
        for record, value in zip(records, values, strict=True):
            self.assertEqual(record.source_data.bdns.regulatory_bases.source_locator, value)

    def test_old_prepublication_field_rejected_no_compatibility_alias(self):
        record = finalize_record(enriched_candidate())
        raw = record.to_dict()
        bases = raw["source_data"]["bdns"]["regulatory_bases"]
        bases["official_source_url"] = bases.pop("source_locator")
        with self.assertRaises(DataValidationError):
            Record.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
