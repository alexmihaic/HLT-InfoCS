"""Contrato canónico offline; ningún dato real ni collector se escribe/ejecuta."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.diff.core import HashContractTransitionError, content_hash, diff, semantic_payload
from infocs.events import update_event
from infocs.finalize import finalize_record
from infocs.models import (
    BDNSApplicationPeriod, BDNSAuthorityHierarchy, BDNSBudgetTotal,
    BDNSCanonicalData, BDNSDocumentReference, BDNSExtractReference,
    BDNSOfficialClassification, BDNSRegulatoryBases, DataValidationError,
    Record, RecordCandidate, SourceData, SourceReference, validate_record_payload,
)
from tests.unit.test_bdns_normalize import normalized


def enriched_data():
    return BDNSCanonicalData(
        official_title_coofficial="Títol sintètic",
        authority_hierarchy=BDNSAuthorityHierarchy(nivel1="LOCAL", nivel3="Órgano sintético"),
        budget_total=BDNSBudgetTotal(Decimal("3.27E+3")),
        call_type="Concesión directa - instrumental",
        instruments=("Instrumento oficial sintético",),
        eligible_beneficiary_types=(BDNSOfficialClassification("Asociaciones", "A"),),
        sectors=(BDNSOfficialClassification("Sector A", "A"), BDNSOfficialClassification("Sector B", "B")),
        impact_regions=("ES522 - Castellón / Castelló",),
        received_date=date(2026, 9, 15),
        application=BDNSApplicationPeriod(start_date=date(2026, 9, 1), end_text="A la firma del convenio", abierto=False),
        purpose="Finalidad oficial sintética",
        regulatory_bases=BDNSRegulatoryBases("Bases oficiales sintéticas", "https://sede.example.invalid/bases"),
        electronic_office_url="https://sede.example.invalid/",
        extract_published_in_official_diary=False,
        documents=(BDNSDocumentReference(800001, "Documento sintético", "ejemplo.pdf", date(2026, 9, 15), "2026-09-16"),),
        extracts=(BDNSExtractReference(cve="CVE-SINTETICO", diary="Diario sintético", publication_date=date(2026, 9, 16)),),
    )


def candidate(data=None):
    return replace(normalized().candidate, source_data=SourceData(data) if data is not None else None)


class BDNSCanonicalEnrichmentTests(unittest.TestCase):
    def test_dropped_electronic_office_is_identical_to_source_absence_in_hash_and_payload(self):
        from infocs.fetch.bdns.enrichment import normalize_bdns_enriched
        from tests.unit.test_bdns_normalize import source_models, DETECTED, CHECKED
        summary, detail = source_models()
        records = [finalize_record(normalize_bdns_enriched(summary, replace(detail, electronic_office=value),
            detected_at=DETECTED, last_checked_at=CHECKED).candidate)
            for value in (None, "sede.example.invalid/path", "http://sede.example.invalid/")]
        for record in records:
            self.assertEqual(record.canonical_json(), records[0].canonical_json())
            self.assertEqual(semantic_payload(record.to_dict()), semantic_payload(records[0].to_dict()))
            self.assertEqual(record.technical.content_hash, records[0].technical.content_hash)
            self.assertEqual(record.technical.content_hash_version, 2)
            self.assertNotIn("electronic_office_url", record.source_data.bdns.to_dict())

    def test_valid_office_projection_keeps_existing_style_bytes_hash_and_materiality(self):
        from infocs.fetch.bdns.enrichment import project_bdns_electronic_office_url
        data = enriched_data()
        original = finalize_record(candidate(data))
        projected, warning = project_bdns_electronic_office_url(data.electronic_office_url)
        current = finalize_record(candidate(replace(data, electronic_office_url=projected)))
        self.assertIsNone(warning)
        self.assertEqual(current.canonical_json(), original.canonical_json())
        self.assertEqual(current.technical.content_hash, original.technical.content_hash)
        changed = finalize_record(candidate(replace(data, electronic_office_url="https://sede.example.invalid/changed")))
        self.assertNotEqual(changed.technical.content_hash, original.technical.content_hash)

    def test_legacy_record_and_boe_json_remain_unchanged(self):
        legacy = finalize_record(candidate())
        self.assertNotIn("source_data", legacy.to_dict())
        self.assertNotIn("content_hash_version", legacy.to_dict()["technical"])
        self.assertEqual(legacy.technical.content_hash_version, 1)
        self.assertEqual(Record.from_json(legacy.canonical_json()), legacy)
        for path in (ROOT / "data" / "records").glob("*/*.json"):
            with self.subTest(source=path.parent.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                record = Record.from_dict(payload)
                self.assertEqual(record.to_dict(), payload)
                self.assertEqual(content_hash(payload), record.technical.content_hash)

    def test_complete_roundtrip_candidate_and_record(self):
        value = candidate(enriched_data())
        self.assertEqual(RecordCandidate.from_dict(value.to_dict()), value)
        record = finalize_record(value)
        validate_record_payload(record.to_dict())
        self.assertEqual(Record.from_json(record.canonical_json()), record)
        self.assertEqual(record.technical.content_hash_version, 2)
        self.assertEqual(record.id, finalize_record(candidate()).id)
        self.assertEqual(record.source_data.bdns.application.end_text, "A la firma del convenio")

    def test_decimal_exponent_and_large_precision_roundtrip(self):
        for value in ("3.27E+3", "123456789012345678901234567890.123456789", "0.000000000000001", "0.00"):
            with self.subTest(value=value):
                budget = BDNSBudgetTotal(Decimal(value))
                self.assertNotIn("E", budget.to_dict()["value"])
                record = finalize_record(candidate(BDNSCanonicalData(budget_total=budget)))
                self.assertEqual(Record.from_json(record.canonical_json()).source_data.bdns.budget_total.value, Decimal(value))
                self.assertNotIn("currency", record.source_data.bdns.budget_total.to_dict())
        self.assertEqual(BDNSBudgetTotal(Decimal("3.27E+3")).to_dict(), {"value": "3270"})
        for value in (3270.0, "3270", Decimal("NaN"), Decimal("Infinity"), Decimal("-1")):
            with self.subTest(invalid=str(value)), self.assertRaises(DataValidationError):
                BDNSBudgetTotal(value)

    def test_currency_explicit_only_and_numeric_schema_rejected(self):
        data = BDNSCanonicalData(budget_total=BDNSBudgetTotal(Decimal("1"), "EUR"))
        record = finalize_record(candidate(data))
        self.assertEqual(Record.from_json(record.canonical_json()).source_data.bdns.budget_total.currency, "EUR")
        raw = candidate(data).to_dict()
        raw["source_data"]["bdns"]["budget_total"]["value"] = 1.0
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(raw)

    def test_equal_decimal_values_keep_hash_and_canonical_json(self):
        left = finalize_record(candidate(BDNSCanonicalData(budget_total=BDNSBudgetTotal(Decimal("3.27E+3")))))
        right = finalize_record(candidate(BDNSCanonicalData(budget_total=BDNSBudgetTotal(Decimal("3270.000")))))
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(diff(left.to_dict(), right.to_dict()), ())

    def test_nullables_are_omitted_without_inventing_values(self):
        raw = candidate(BDNSCanonicalData(call_type="Tipo oficial")).to_dict()
        raw["source_data"]["bdns"].update(purpose=None, budget_total=None, received_date=None)
        result = RecordCandidate.from_dict(raw).to_dict()["source_data"]["bdns"]
        self.assertEqual(result, {"extension_version": "1.0", "call_type": "Tipo oficial"})

    def test_structured_and_textual_periods_do_not_infer_dates(self):
        for period in (
            BDNSApplicationPeriod(start_date=date(2026, 1, 1), end_date=date(2026, 2, 1)),
            BDNSApplicationPeriod(start_text="Desde la firma", end_text="Según convenio"),
            BDNSApplicationPeriod(abierto=False),
        ):
            with self.subTest(period=period):
                record = finalize_record(candidate(BDNSCanonicalData(application=period)))
                self.assertEqual(Record.from_json(record.canonical_json()).source_data.bdns.application, period)
        with self.assertRaises(DataValidationError):
            BDNSApplicationPeriod(start_date="A la firma")
        with self.assertRaises(DataValidationError):
            BDNSApplicationPeriod(start_date=datetime.now(UTC))

    def test_document_metadata_no_url_mime_or_content_inference(self):
        reference = BDNSDocumentReference(1, filename="documento.pdf", modified_value="valor fuente sin interpretar")
        record = finalize_record(candidate(BDNSCanonicalData(documents=(reference,))))
        self.assertEqual(Record.from_json(record.canonical_json()).source_data.bdns.documents, (reference,))
        raw = reference.to_dict()
        for forbidden in ("official_url", "mime_type", "sha256", "local_path", "fulltext"):
            self.assertNotIn(forbidden, raw)
        with self.assertRaises(DataValidationError):
            BDNSCanonicalData(documents=(reference, replace(reference, filename="otro.pdf")))

    def test_source_and_category_binding_both_python_and_schema(self):
        enriched = candidate(enriched_data())
        for source in ("boe", "bop_castellon"):
            with self.subTest(source=source):
                with self.assertRaises(DataValidationError):
                    replace(enriched, source=SourceReference(source))
                raw = enriched.to_dict()
                raw["source"]["id"] = source
                with self.assertRaises(DataValidationError):
                    RecordCandidate.from_dict(raw)
        raw = enriched.to_dict()
        raw["category"] = "grants.resolution"
        with self.assertRaises(DataValidationError):
            RecordCandidate.from_dict(raw)

    def test_closed_schema_rejects_raw_ui_and_future_extensions(self):
        for path, key in (("bdns", "raw"), ("bdns", "summary"), ("bdns", "formatted_amount"), ("bdns", "ayudaEstado"), ("source_data", "pcsp")):
            with self.subTest(key=key):
                raw = candidate(enriched_data()).to_dict()
                target = raw["source_data"] if path == "source_data" else raw["source_data"]["bdns"]
                target[key] = "unexpected"
                with self.assertRaises(DataValidationError):
                    RecordCandidate.from_dict(raw)

    def test_schema_rejects_empty_and_null_only_blocks(self):
        from infocs.models import validate_record_candidate_payload
        for block in ({"extension_version": "1.0"}, {"extension_version": "1.0", "purpose": None},
            {"extension_version": "1.0", "sectors": []},
            {"extension_version": "1.0", "application": {"end_text": None}}):
            with self.subTest(block=block):
                raw = candidate(enriched_data()).to_dict()
                raw["source_data"]["bdns"] = block
                with self.assertRaises(DataValidationError):
                    validate_record_candidate_payload(raw)

    def test_immutable_typed_models_no_mutable_escape_hatch(self):
        with self.assertRaises(FrozenInstanceError):
            enriched_data().purpose = "another"
        for data in ({"sectors": []}, {"budget_total": {"value": "1"}}, {"documents": ({"id": 1},)}, {"application": {"start_date": "2026-01-01"}}):
            with self.subTest(data=data), self.assertRaises(DataValidationError):
                BDNSCanonicalData(**data)

    def test_bases_source_url_allows_http_without_changing_other_urls(self):
        for url in ("javascript:alert(1)", "https://user:password@example.invalid", "https://bad\thost/"):
            with self.subTest(url=url), self.assertRaises(DataValidationError):
                BDNSRegulatoryBases(source_locator=url)
        url = "http://public.example.invalid/bases"
        self.assertEqual(BDNSRegulatoryBases(source_locator=url).source_locator, url)
        with self.assertRaises(DataValidationError):
            BDNSExtractReference(source_url=url)
        with self.assertRaises(DataValidationError):
            BDNSCanonicalData(electronic_office_url=url)

    def test_material_changes_each_modify_hash(self):
        original = enriched_data()
        base = finalize_record(candidate(original))
        changes = {
            "budget_total": BDNSBudgetTotal(Decimal("3271")),
            "call_type": "Otro tipo oficial",
            "instruments": ("Otro instrumento",),
            "eligible_beneficiary_types": (BDNSOfficialClassification("Otro tipo", "B"),),
            "sectors": (BDNSOfficialClassification("Otro sector", "C"),),
            "purpose": "Otra finalidad oficial",
            "application": BDNSApplicationPeriod(end_text="Otra condición"),
            "regulatory_bases": BDNSRegulatoryBases("Otras bases"),
            "documents": (BDNSDocumentReference(800002),),
            "received_date": date(2026, 9, 16),
            "impact_regions": ("Otra región oficial",),
            "extract_published_in_official_diary": True,
            "authority_hierarchy": BDNSAuthorityHierarchy(nivel3="Otro órgano"),
            "extracts": (BDNSExtractReference(cve="OTRO-CVE"),),
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                current = finalize_record(candidate(replace(original, **{field: value})))
                self.assertNotEqual(base.technical.content_hash, current.technical.content_hash)
                self.assertTrue(any(change.path.startswith("source_data.bdns." + field) for change in diff(base.to_dict(), current.to_dict())))

    def test_document_metadata_changes_and_period_role_changes_are_material(self):
        data = enriched_data()
        original = finalize_record(candidate(data))
        document = data.documents[0]
        for changed in (
            replace(document, description="Otra descripción"),
            replace(document, filename="otro.pdf"),
            replace(document, published_date=date(2026, 9, 17)),
            replace(document, modified_value="2026-09-18"),
        ):
            with self.subTest(document=changed):
                current = finalize_record(candidate(replace(data, documents=(changed,))))
                self.assertNotEqual(original.technical.content_hash, current.technical.content_hash)
        start = finalize_record(candidate(BDNSCanonicalData(application=BDNSApplicationPeriod(start_date=date(2026, 1, 1)))))
        end = finalize_record(candidate(BDNSCanonicalData(application=BDNSApplicationPeriod(end_date=date(2026, 1, 1)))))
        self.assertNotEqual(start.technical.content_hash, end.technical.content_hash)

    def test_all_collection_ordering_and_duplicates_not_material(self):
        data = enriched_data()
        data = replace(data,
            instruments=("B", "A"), impact_regions=("Región B", "Región A"),
            eligible_beneficiary_types=(BDNSOfficialClassification("B"), BDNSOfficialClassification("A")),
            documents=(BDNSDocumentReference(2), BDNSDocumentReference(1)),
            extracts=(BDNSExtractReference(cve="B"), BDNSExtractReference(cve="A")))
        original = finalize_record(candidate(data))
        reordered = replace(data, **{key: tuple(reversed(getattr(data, key))) for key in (
            "instruments", "impact_regions", "eligible_beneficiary_types", "sectors", "documents", "extracts")})
        other = finalize_record(candidate(reordered))
        self.assertEqual(other.canonical_json(), original.canonical_json())
        self.assertEqual(diff(original.to_dict(), other.to_dict()), ())
        duplicate = finalize_record(candidate(replace(data, instruments=("B", "A", "A"))))
        self.assertEqual(duplicate.technical.content_hash, original.technical.content_hash)

    def test_non_material_metadata_and_extension_version_excluded(self):
        record = finalize_record(candidate(enriched_data()))
        raw = record.to_dict()
        raw["dates"]["last_checked_at"] = "2026-10-01T12:00:00Z"
        raw["technical"]["extraction_method"] = "synthetic_other_method"
        self.assertEqual(content_hash(raw), record.technical.content_hash)
        self.assertNotIn("extension_version", semantic_payload(raw)["source_data"]["bdns"])
        # El contenedor cerrado impide persistir labels UI/resumen/formato.
        self.assertNotIn("technical", semantic_payload(raw))

    def test_hash_transition_requires_explicit_baseline_no_update(self):
        legacy = finalize_record(candidate())
        enriched = finalize_record(candidate(enriched_data()))
        self.assertEqual(legacy.id, enriched.id)
        self.assertNotEqual(legacy.technical.content_hash, enriched.technical.content_hash)
        with self.assertRaises(HashContractTransitionError):
            diff(legacy.to_dict(), enriched.to_dict())
        with self.assertRaises(HashContractTransitionError):
            update_event(legacy, enriched, observed_at=datetime(2026, 10, 1, tzinfo=UTC), authorization=None)
        with self.assertRaises(HashContractTransitionError):
            diff(enriched.to_dict(), legacy.to_dict())
        # Baseline v2 validable en memoria; no modifica el Record/Event anterior.
        baseline = Record.from_json(enriched.canonical_json())
        self.assertEqual(diff(baseline.to_dict(), enriched.to_dict()), ())
        legacy_projection = enriched.to_dict()
        legacy_projection.pop("source_data")
        legacy_projection["technical"].pop("content_hash_version")
        self.assertEqual(content_hash(legacy_projection), legacy.technical.content_hash)

    def test_version_binding_cannot_be_downgraded_or_omitted(self):
        record = finalize_record(candidate(enriched_data()))
        for version in (None, 1, 3, True):
            with self.subTest(version=version):
                raw = record.to_dict()
                if version is None:
                    raw["technical"].pop("content_hash_version")
                else:
                    raw["technical"]["content_hash_version"] = version
                with self.assertRaises(DataValidationError):
                    Record.from_dict(raw)
                with self.assertRaises(HashContractTransitionError):
                    content_hash(raw)

    def test_schema_support_not_publication_authorization_without_v2_provenance(self):
        from infocs.fetch.bdns.publication import authorize_bdns_event, evaluate_bdns_publication
        from infocs.privacy import PrivacyGate
        record = finalize_record(candidate(enriched_data()))
        privacy = PrivacyGate.default().evaluate(record)
        publication = evaluate_bdns_publication(record, privacy)
        self.assertEqual(publication.metadata_publication.decision.value, "hold")
        self.assertIsNone(authorize_bdns_event(record, publication))


if __name__ == "__main__":
    unittest.main()
