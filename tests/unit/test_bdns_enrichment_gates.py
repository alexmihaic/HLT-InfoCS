"""Enrichment offline; sólo fixtures sintéticas y Stores temporales."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.diff.core import HashContractTransitionError, diff
from infocs.events import EventStore, create_event, update_event
from infocs.finalize import finalize_record
from infocs.fetch.bdns.enrichment import (
    BDNSEnrichmentError, build_bdns_source_data, normalize_bdns_enriched,
    prepare_bdns_enriched_record, valid_bdns_supplied_url,
    valid_bdns_regulatory_bases_source_locator, clickable_bdns_regulatory_bases_url,
)
from infocs.fetch.bdns.models import BDNSCodeLabel, BDNSRegion
from infocs.fetch.bdns.publication import (
    BDNSPublicationPolicyError, authorize_bdns_event, evaluate_bdns_publication,
)
from infocs.fetch.bdns.runner import BDNSRunMode, run_bdns_productive_collection
from infocs.manifests import ManifestStore
from infocs.models import BDNSBudgetTotal, DataValidationError, Record, SourceData, SourceReference
from infocs.privacy import PrivacyDecisionType, PrivacyGate, PrivacyGateError
from infocs.privacy.gate import PrivacyRule
from infocs.store import RecordStore, RecordStoreError
from tests.unit.test_bdns_normalize import CHECKED, DETECTED, normalized, source_models
from tests.unit.test_bdns_runner import FakeTransport, START, fixture_models


def enriched_candidate(detail=None):
    summary, fixture = source_models()
    return normalize_bdns_enriched(summary, detail or fixture,
        detected_at=DETECTED, last_checked_at=CHECKED).candidate


class BDNSEnrichmentMappingTests(unittest.TestCase):
    def setUp(self):
        self.summary, self.detail = source_models()

    def test_full_mapping_roundtrip_and_exact_values(self):
        detail = replace(self.detail, total_budget=Decimal("3.27E+3"), title_coofficial="Títol oficial sintètic")
        record = finalize_record(enriched_candidate(detail))
        data = record.source_data.bdns
        self.assertEqual(record.technical.content_hash_version, 2)
        self.assertEqual(record.provenance.normalizer_version, "2.0.0")
        self.assertEqual(data.official_title_coofficial, detail.title_coofficial)
        self.assertEqual(data.authority_hierarchy.nivel1, detail.authority.nivel1)
        self.assertEqual(data.authority_hierarchy.nivel2, detail.authority.nivel2)
        self.assertEqual(data.budget_total.value, Decimal("3270"))
        self.assertEqual(data.budget_total.to_dict(), {"value": "3270"})
        self.assertIsNone(data.budget_total.currency)
        self.assertIsNone(record.financial)
        self.assertEqual(data.call_type, detail.convocatoria_type)
        self.assertEqual(data.instruments, detail.instruments)
        self.assertEqual(data.received_date, detail.fecha_recepcion)
        self.assertEqual(data.application.start_date, detail.application_start_date)
        self.assertEqual(data.application.end_date, detail.application_end_date)
        self.assertEqual(data.application.start_text, detail.application_start_text)
        self.assertEqual(data.application.end_text, detail.application_end_text)
        self.assertIs(data.application.abierto, False)
        self.assertEqual(data.purpose, detail.purpose)
        self.assertEqual(data.regulatory_bases.description, detail.regulatory_bases_title)
        self.assertEqual(data.electronic_office_url, detail.electronic_office)
        self.assertTrue(data.extract_published_in_official_diary)
        self.assertEqual(data.documents[0].source_document_id, detail.documents[0].document_id)
        self.assertEqual(data.documents[0].modified_value, detail.documents[0].modified_at)
        self.assertEqual(data.documents[0].published_date, detail.documents[0].publication_date)
        self.assertEqual(data.extracts[0].cve, detail.extracts[0].cve)
        self.assertEqual(data.extracts[0].diary, detail.extracts[0].official_diary)
        self.assertEqual(data.extracts[0].publication_date, detail.extracts[0].publication_date)
        self.assertEqual(data.extracts[0].source_url, detail.extracts[0].url)
        self.assertEqual(Record.from_json(record.canonical_json()), record)
        self.assertEqual(record.documents, ())
        for excluded in ("length", "long", "announcement_number", "numAnuncio", "fulltext", "official_url"):
            self.assertNotIn(excluded, data.documents[0].to_dict())
            self.assertNotIn(excluded, data.extracts[0].to_dict())

    def test_classifications_preserve_official_label_and_code(self):
        data = build_bdns_source_data(self.detail).bdns
        for mapped, source in ((data.eligible_beneficiary_types, self.detail.eligible_beneficiaries),
                               (data.sectors, self.detail.sectors)):
            self.assertEqual(mapped[0].label, source[0].description)
            self.assertEqual(mapped[0].code, source[0].code)

    def test_absent_optional_fields_valid_without_invention(self):
        detail = replace(self.detail, internal_id=None, title_coofficial=None, authority=None,
            electronic_office=None, fecha_recepcion=None, total_budget=None, convocatoria_type=None,
            instruments=(), eligible_beneficiaries=(), sectors=(), purpose=None, regulatory_bases_title=None,
            regulatory_bases_url=None, extract_published_in_official_diary=None, open_ended_application=None,
            application_start_date=None, application_end_date=None, application_start_text=None,
            application_end_text=None, documents=(), extracts=())
        record = finalize_record(enriched_candidate(detail))
        self.assertIsNone(record.authority)
        self.assertIsNone(record.dates.published_at)
        self.assertEqual(record.source_data.bdns.to_dict(), {
            "extension_version": "1.0", "impact_regions": ["ES522 - Castellón / Castelló"]})
        self.assertEqual(evaluate_bdns_publication(record, PrivacyGate.default().evaluate(record)).metadata_publication.decision.value,
                         "publishable_metadata")

    def test_application_structured_textual_and_coexistent(self):
        for start, end, text_start, text_end in (
            (date(2026, 1, 1), date(2026, 2, 1), None, None),
            (None, None, "Desde la firma", "A la firma del convenio"),
            (date(2026, 1, 1), date(2026, 2, 1), "Texto inicial", "Texto final"),
        ):
            with self.subTest(structured=start is not None, textual=text_start is not None):
                detail = replace(self.detail, application_start_date=start, application_end_date=end,
                    application_start_text=text_start, application_end_text=text_end)
                result = build_bdns_source_data(detail).bdns.application
                self.assertEqual((result.start_date, result.end_date, result.start_text, result.end_text),
                    (start, end, text_start, text_end))
                self.assertIs(result.abierto, False)

    def test_missing_label_fails_entire_enrichment_not_partial_list(self):
        for field in ("eligible_beneficiaries", "sectors"):
            for label in (None, "", "   "):
                with self.subTest(field=field, label=label):
                    items = getattr(self.detail, field) + (BDNSCodeLabel("CODE-ONLY", label),)
                    with self.assertRaisesRegex(BDNSEnrichmentError, "^enrichment_missing_required_label$"):
                        build_bdns_source_data(replace(self.detail, **{field: items}))

    def test_duplicate_document_id_fails_closed(self):
        with self.assertRaisesRegex(BDNSEnrichmentError, "^enrichment_duplicate_document_id$"):
            build_bdns_source_data(replace(self.detail, documents=self.detail.documents * 2))

    def test_invalid_document_metadata_safe_reason(self):
        for changes in ({"document_id": True}, {"filename": ""}, {"publication_date": "bad-date"}, {"modified_at": 123}):
            with self.subTest(field=next(iter(changes))):
                document = replace(self.detail.documents[0], **changes)
                with self.assertRaisesRegex(BDNSEnrichmentError, "^enrichment_invalid_document_metadata$"):
                    build_bdns_source_data(replace(self.detail, documents=(document,)))

    def test_invalid_decimal_rejected_without_float_or_truncation(self):
        for value in (3270.0, Decimal("NaN"), Decimal("Infinity"), Decimal("-1")):
            with self.subTest(value=str(value)), self.assertRaisesRegex(BDNSEnrichmentError, "^enrichment_invalid_decimal$"):
                build_bdns_source_data(replace(self.detail, total_budget=value))

    def test_invalid_urls_all_three_fields_fail_closed(self):
        for value in ("http://example.invalid/", "https://u:p@example.invalid/", "javascript:alert(1)",
                      "https://example.invalid:bad/", "https://example.invalid/%GG", "https://127.0.0.1/",
                      "data:text/plain,test", "file:///bases", "https://localhost/", "https://example.local/",
                      "https://example.localhost/", "https://singlelabel/", "https://bad_host.invalid/",
                      "https://example.invalid/with space", "https://example.invalid/\n",
                      "https://example.invalid/\\path", "https://example.invalid/" + "a" * 2048):
            for field in ("regulatory_bases_url", "electronic_office", "extract"):
                if field == "regulatory_bases_url" and valid_bdns_regulatory_bases_source_locator(value):
                    self.assertEqual(build_bdns_source_data(replace(self.detail, regulatory_bases_url=value)).bdns.regulatory_bases.source_locator, value)
                    self.assertIsNone(clickable_bdns_regulatory_bases_url(value))
                    continue  # Persistencia no equivale a navegabilidad.
                with self.subTest(field=field, url_kind=value.split(":")[0]):
                    detail = replace(self.detail, extracts=(replace(self.detail.extracts[0], url=value),)) if field == "extract" else replace(self.detail, **{field: value})
                    with self.assertRaisesRegex(BDNSEnrichmentError, "^enrichment_invalid_url$"):
                        build_bdns_source_data(detail)

    def test_supplied_urls_not_rewritten_or_certified(self):
        value = "https://sede.example.invalid:443/BASES?x=1&y=2#section"
        self.assertTrue(valid_bdns_supplied_url(value))
        self.assertEqual(build_bdns_source_data(replace(self.detail, regulatory_bases_url=value)).bdns.regulatory_bases.source_locator, value)

    def test_http_bases_source_value_preserved_but_not_clickable(self):
        value = "http://public.example.invalid/bases?reference=public#section"
        detail = replace(self.detail, regulatory_bases_url=value)
        data = build_bdns_source_data(detail).bdns
        self.assertEqual(data.regulatory_bases.source_locator, value)
        self.assertFalse(valid_bdns_supplied_url(value))
        record = finalize_record(enriched_candidate(detail))
        self.assertEqual(Record.from_json(record.canonical_json()), record)
        with tempfile.TemporaryDirectory() as temporary:
            result = prepare_bdns_enriched_record(self.summary, detail, detected_at=DETECTED,
                last_checked_at=CHECKED, record_store=RecordStore(Path(temporary) / "records"))
            self.assertIsNone(result.safe_reason)
            self.assertIsNotNone(result.record)
            self.assertEqual(result.privacy.decision, PrivacyDecisionType.ALLOW)
            self.assertEqual(result.publication.metadata_publication.decision.value, "publishable_metadata")
            self.assertTrue(result.authorization.matches(result.record))

    def test_http_bases_rejected_shapes_and_privacy_unchanged(self):
        for value in ("http://u:p@example.invalid/", "http://example.invalid/with space",
                      "http://example.invalid/%GG", "http://example.invalid/\x01"):
            with self.subTest(kind=value.split(":")[0]), self.assertRaisesRegex(BDNSEnrichmentError, "^enrichment_invalid_url$"):
                build_bdns_source_data(replace(self.detail, regulatory_bases_url=value))
        for value in ("http://example.invalid/persona%40gmail.com",
                      "http://example.invalid/bases?email=persona%40gmail.com",
                      "http://example.invalid/bases#persona%40gmail.com"):
            with self.subTest(position=value.count("?")):
                with tempfile.TemporaryDirectory() as temporary:
                    result = prepare_bdns_enriched_record(self.summary,
                        replace(self.detail, regulatory_bases_url=value), detected_at=DETECTED,
                        last_checked_at=CHECKED, record_store=RecordStore(Path(temporary) / "records"))
                    self.assertIsNotNone(result.record)
                    self.assertNotEqual(result.privacy.decision, PrivacyDecisionType.ALLOW)
                    self.assertIsNone(result.authorization)
                    self.assertEqual(result.safe_reason, "privacy_source_data_blocked")

    def test_unrepresentable_extract_not_silently_dropped(self):
        extract = replace(self.detail.extracts[0], announcement_number=1, title=None, title_coofficial=None,
            cve=None, official_diary=None, publication_date=None, url=None)
        with self.assertRaisesRegex(BDNSEnrichmentError, "^enrichment_contract_invalid$"):
            build_bdns_source_data(replace(self.detail, extracts=(extract,)))

    def test_reception_date_does_not_become_publication_date(self):
        record = finalize_record(enriched_candidate(replace(self.detail, extracts=())))
        self.assertIsNone(record.dates.published_at)
        self.assertEqual(record.source_data.bdns.received_date, self.detail.fecha_recepcion)

    def test_unordered_collections_stable_hash_and_output(self):
        detail = replace(self.detail, instruments=("B", "A"), sectors=(BDNSCodeLabel("B", "Sector B"), BDNSCodeLabel("A", "Sector A")),
            eligible_beneficiaries=(BDNSCodeLabel("B", "Tipo B"), BDNSCodeLabel("A", "Tipo A")),
            regions=self.detail.regions + (BDNSRegion("Otra región oficial"),),
            documents=self.detail.documents + (replace(self.detail.documents[0], document_id=800002),),
            extracts=self.detail.extracts + (replace(self.detail.extracts[0], cve="OTRO-CVE"),))
        other = replace(detail, **{key: tuple(reversed(getattr(detail, key))) for key in (
            "instruments", "sectors", "eligible_beneficiaries", "regions", "documents", "extracts")})
        self.assertEqual(finalize_record(enriched_candidate(detail)).canonical_json(),
                         finalize_record(enriched_candidate(other)).canonical_json())


class BDNSEnrichmentGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = RecordStore(self.root / "records")
        self.summary, self.detail = source_models()
        self.candidate = enriched_candidate()
        self.record = finalize_record(self.candidate)
        self.data = self.record.source_data.bdns

    def preflight(self, detail=None, store=None):
        return prepare_bdns_enriched_record(self.summary, detail or self.detail, detected_at=DETECTED,
            last_checked_at=CHECKED, record_store=store or self.store)

    def record_with(self, **changes):
        return finalize_record(replace(self.candidate, source_data=SourceData(replace(self.data, **changes))))

    def test_clean_preflight_authorization_exact_v2_no_write(self):
        with patch.object(self.store, "write", side_effect=AssertionError("preflight must not write")):
            result = self.preflight()
        self.assertIsNone(result.safe_reason)
        self.assertEqual(result.privacy.decision, PrivacyDecisionType.ALLOW)
        self.assertEqual(result.publication.source_eligibility.decision.value, "eligible")
        self.assertEqual(result.publication.metadata_publication.decision.value, "publishable_metadata")
        self.assertTrue(result.authorization.matches(result.record))
        self.assertEqual(result.authorization.policy_id, "bdns.enriched-metadata-publication.v2")
        self.assertEqual(result.record.technical.content_hash_version, 2)
        self.assertFalse(self.root.joinpath("records").exists())

    def test_enriched_record_temp_store_roundtrip_after_gates(self):
        result = self.preflight()
        self.assertIsNotNone(result.authorization)
        path = self.store.write(result.record)
        self.assertEqual(Record.from_json(path.read_text(encoding="utf-8")), result.record)

    def test_privacy_all_explicit_human_text_fields(self):
        token = "12345678Z"
        data = self.data
        changes = {
            "official_title_coofficial": {"official_title_coofficial": token},
            **{f"authority_hierarchy.{key}": {"authority_hierarchy": replace(data.authority_hierarchy, **{key: token})} for key in ("nivel1", "nivel2", "nivel3")},
            "call_type": {"call_type": token}, "instruments[0]": {"instruments": (token,)},
            **{f"eligible_beneficiary_types[0].{key}": {"eligible_beneficiary_types": (replace(data.eligible_beneficiary_types[0], **{key: token}),)} for key in ("label", "code")},
            **{f"sectors[0].{key}": {"sectors": (replace(data.sectors[0], **{key: token}),)} for key in ("label", "code")},
            "impact_regions[0]": {"impact_regions": (token,)},
            **{f"application.{key}": {"application": replace(data.application, **{key: token})} for key in ("start_text", "end_text")},
            "purpose": {"purpose": token},
            "regulatory_bases.description": {"regulatory_bases": replace(data.regulatory_bases, description=token)},
            "regulatory_bases.source_locator": {"regulatory_bases": replace(data.regulatory_bases, source_locator=f"https://example.invalid/{token}")},
            "electronic_office_url": {"electronic_office_url": f"https://example.invalid/?dni={token}"},
            **{f"documents[0].{key}": {"documents": (replace(data.documents[0], **{key: token}),)} for key in ("description", "filename", "modified_value")},
            **{f"extracts[0].{key}": {"extracts": (replace(data.extracts[0], **{key: token}),)} for key in ("cve", "diary", "title", "title_coofficial")},
            "extracts[0].source_url": {"extracts": (replace(data.extracts[0], source_url=f"https://example.invalid/#{token}"),)},
        }
        for field, change in changes.items():
            with self.subTest(field=field):
                record = self.record_with(**change)
                privacy = PrivacyGate.default().evaluate(record)
                self.assertEqual(privacy.decision, PrivacyDecisionType.QUARANTINE)
                self.assertTrue(any(reason.field == "source_data.bdns." + field for reason in privacy.reasons))
                self.assertNotIn(token, str(privacy.to_dict()))
                publication = evaluate_bdns_publication(record, privacy)
                self.assertIsNone(publication.source_eligibility)
                self.assertIsNone(publication.metadata_publication)
                self.assertIsNone(authorize_bdns_event(record, publication))
                with self.assertRaises(RecordStoreError):
                    self.store.validate(record)

    def test_purpose_personal_email_phone_address_and_nominative_identifier_blocked(self):
        for text in ("persona@gmail.com", "teléfono personal: 612 345 678", "domicilio particular: Calle Sintética 7", "Beneficiario individual NIF 12345678Z"):
            with self.subTest(kind=text.split(":")[0]):
                result = self.preflight(replace(self.detail, purpose=text))
                self.assertEqual(result.safe_reason, "privacy_source_data_blocked")
                self.assertIsNone(result.authorization)
                self.assertFalse(self.root.joinpath("records").exists())

    def test_urls_raw_decoded_path_query_fragment_blocked(self):
        for url in ("https://example.invalid/12345678Z", "https://example.invalid/?dni=%31%32%33%34%35%36%37%38%5A",
                    "https://example.invalid/#12345678Z", "https://example.invalid/?email=persona%40gmail.com",
                    "https://example.invalid/?contacto=tel%C3%A9fono+personal%3A+612+345+678",
                    "https://example.invalid/?contacto=domicilio+particular%3A+Calle+Sint%C3%A9tica+7",
                    "https://example.invalid/?dni=%2531%2532%2533%2534%2535%2536%2537%2538%255A"):
            with self.subTest(surface=url.split("invalid/")[1]):
                result = self.preflight(replace(self.detail, electronic_office=url))
                self.assertEqual(result.safe_reason, "privacy_source_data_blocked")
                self.assertIsNone(result.authorization)

    def test_invalid_url_encoding_fails_before_store_write(self):
        result = self.preflight(replace(self.detail, electronic_office="https://example.invalid/?x=%FF"))
        self.assertEqual(result.safe_reason, "privacy_source_data_blocked")
        self.assertIsNone(result.authorization)
        with self.assertRaises(PrivacyGateError):
            PrivacyGate.default().evaluate(result.record)

    def test_reject_keeps_precedence_before_publication(self):
        gate = PrivacyGate.default()
        rules = dict(gate.config.rules)
        rules["spanish_personal_identifier"] = PrivacyRule(True, PrivacyDecisionType.REJECT)
        store = RecordStore(self.root / "reject", privacy_gate=PrivacyGate(replace(gate.config, rules=rules)))
        result = self.preflight(replace(self.detail, purpose="12345678Z"), store)
        self.assertEqual(result.privacy.decision, PrivacyDecisionType.REJECT)
        self.assertIsNone(result.publication.source_eligibility)
        self.assertIsNone(result.authorization)

    def test_mapping_failure_safe_result_no_partial_candidate_or_write(self):
        result = self.preflight(replace(self.detail, sectors=(BDNSCodeLabel("B", None),)))
        self.assertEqual(result.safe_reason, "enrichment_missing_required_label")
        self.assertIsNone(result.record)
        self.assertIsNone(result.authorization)

    def test_wrong_territory_and_join_fail_closed(self):
        result = self.preflight(replace(self.detail, regions=(BDNSRegion("ES52 - Comunitat Valenciana"),)))
        self.assertEqual(result.safe_reason, "enrichment_territorial_not_included")
        self.assertIsNone(result.record)
        result = self.preflight(replace(self.detail, codigo_bdns="900002"))
        self.assertEqual(result.safe_reason, "enrichment_contract_invalid")
        self.assertIsNone(result.record)

    def test_stale_allow_cannot_authorize_new_unsafe_surface(self):
        allow = PrivacyGate.default().evaluate(self.record)
        unsafe = self.record_with(purpose="12345678Z")
        supplied = evaluate_bdns_publication(unsafe, allow)
        with self.assertRaisesRegex(BDNSPublicationPolicyError, "privacy_source_data_decision_mismatch"):
            authorize_bdns_event(unsafe, supplied)

    def test_authorization_cannot_bind_v1_or_later_v2_hash(self):
        auth = self.preflight().authorization
        legacy = finalize_record(normalized().candidate)
        self.assertFalse(auth.matches(legacy))
        legacy_auth = authorize_bdns_event(legacy, evaluate_bdns_publication(legacy, PrivacyGate.default().evaluate(legacy)))
        self.assertFalse(legacy_auth.matches(self.record))
        self.assertFalse(auth.matches(self.record_with(purpose="Otra finalidad oficial")))

    def test_same_contract_v2_events_supported_without_real_writes(self):
        auth = self.preflight().authorization
        created = create_event(self.record, observed_at=CHECKED, authorization=auth)
        self.assertEqual(created.content_hash, self.record.technical.content_hash)
        updated = self.record_with(purpose="Finalidad oficial modificada")
        evaluation = evaluate_bdns_publication(updated, PrivacyGate.default().evaluate(updated))
        updated_auth = authorize_bdns_event(updated, evaluation)
        event = update_event(self.record, updated, observed_at=CHECKED, authorization=updated_auth)
        self.assertEqual(event.previous_content_hash, self.record.technical.content_hash)
        self.assertEqual(event.content_hash, updated.technical.content_hash)
        self.assertFalse(self.root.joinpath("events").exists())

    def test_source_specific_holds_currency_region_hierarchy_and_provenance(self):
        records = (
            self.record_with(budget_total=BDNSBudgetTotal(Decimal("1"), "EUR")),
            self.record_with(impact_regions=("Otra región",)),
            self.record_with(authority_hierarchy=replace(self.data.authority_hierarchy, nivel1="Otro órgano")),
            finalize_record(replace(self.candidate, provenance=replace(self.candidate.provenance, normalizer_version="1.0.0"))),
            self.record_with(electronic_office_url="https://127.0.0.1/"),
        )
        for record in records:
            with self.subTest(hash=record.technical.content_hash[:8]):
                publication = evaluate_bdns_publication(record, PrivacyGate.default().evaluate(record))
                self.assertEqual(publication.metadata_publication.decision.value, "hold")
                self.assertEqual(publication.metadata_publication.reason_code, "publication_source_data_hold")
                self.assertIsNone(authorize_bdns_event(record, publication))

    def test_source_extension_binding_and_unknown_data_remain_closed(self):
        for source in ("boe", "bop_castellon"):
            with self.subTest(source=source), self.assertRaises(DataValidationError):
                replace(self.candidate, source=SourceReference(source))
        raw = self.record.to_dict()
        raw["source_data"]["unknown"] = {"raw": "not permitted"}
        with self.assertRaises(DataValidationError):
            Record.from_dict(raw)

    def test_cross_contract_transition_never_fabricates_update_event(self):
        legacy = finalize_record(normalized().candidate)
        auth = self.preflight().authorization
        for before, after in ((legacy, self.record), (self.record, legacy)):
            with self.subTest(version=before.technical.content_hash_version):
                with self.assertRaises(HashContractTransitionError):
                    diff(before.to_dict(), after.to_dict())
                with self.assertRaises(HashContractTransitionError):
                    update_event(before, after, observed_at=CHECKED, authorization=auth)
        self.assertFalse(self.root.joinpath("events").exists())

    def test_productive_runner_firewall_remains_v1_with_enrichment_installed(self):
        page, detail = fixture_models()
        page = replace(page, items=(page.items[0],), page_number=0, page_size=50, offset=0,
            total_pages=1, total_elements=1, number_of_elements=1, first=True, last=True, empty=False)
        with patch("infocs.fetch.bdns.enrichment.normalize_bdns_enriched", side_effect=AssertionError("v2 forbidden in runner")), \
             patch("infocs.fetch.bdns.enrichment.build_bdns_source_data", side_effect=AssertionError("v2 forbidden in runner")):
            result = run_bdns_productive_collection(mode=BDNSRunMode.COMPLETE_SCOPE,
                from_date=date(2026, 9, 1), through_date=date(2026, 9, 29), started_at=START,
                run_id="run-v1-11111111-1111-4111-8111-111111111111", clock=lambda: START.replace(second=10),
                transport=FakeTransport(page, detail), record_store=self.store,
                event_store=EventStore(self.root / "events"), manifest_store=ManifestStore(self.root / "manifests"),
                health_path=self.root / "health" / "bdns.json", privacy_gate=PrivacyGate.default())
        self.assertEqual(result.status, "complete_success")
        paths = list(self.root.joinpath("records").rglob("*.json"))
        self.assertEqual(len(paths), 1)
        record = Record.from_json(paths[0].read_text(encoding="utf-8"))
        self.assertIsNone(record.source_data)
        self.assertEqual(record.technical.content_hash_version, 1)
        self.assertNotIn("content_hash_version", record.to_dict()["technical"])
        self.assertEqual(record.provenance.normalizer_version, "1.0.0")


if __name__ == "__main__":
    unittest.main()
