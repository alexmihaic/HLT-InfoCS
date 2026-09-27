"""Pruebas offline de normalización BDNS según las políticas v1."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.diff.core import diff  # noqa: E402
from infocs.fetch.bdns.models import BDNSRegion  # noqa: E402
from infocs.fetch.bdns.normalize import (  # noqa: E402
    BDNSNormalizationError,
    BDNSTerritorialStatus,
    evaluate_bdns_territory,
    normalize_bdns_detail,
)
from infocs.fetch.bdns.parser import parse_bdns_detail, parse_bdns_search  # noqa: E402
from infocs.finalize import finalize_record  # noqa: E402
from infocs.models import Category  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures" / "bdns"
DETECTED = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
CHECKED = datetime(2026, 9, 27, 9, 1, tzinfo=UTC)
CASTELLON = "ES522 - Castellón / Castelló"


def source_models():
    search = json.loads((FIXTURES / "search_success.json").read_text(encoding="utf-8"))
    detail_payload = json.loads(
        (FIXTURES / "detail_success.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )
    summary = parse_bdns_search(search).items[0]
    detail_payload["regiones"] = [{"descripcion": CASTELLON}]
    detail = parse_bdns_detail(detail_payload)
    return summary, detail


def normalized(*, summary=None, detail=None):
    source_summary, source_detail = source_models()
    return normalize_bdns_detail(
        summary or source_summary,
        detail or source_detail,
        detected_at=DETECTED,
        last_checked_at=CHECKED,
    )


class BDNSTerritorialPolicyTests(unittest.TestCase):
    def test_exact_catalog_province_is_the_only_local_match(self) -> None:
        _, detail = source_models()
        decision = evaluate_bdns_territory(detail)
        self.assertEqual(decision.status, BDNSTerritorialStatus.INCLUDE)
        self.assertEqual(decision.reason_code, "exact_castellon_province_region")

    def test_region_absent_broad_unknown_and_noncanonical_labels_are_unresolved(self) -> None:
        _, detail = source_models()
        for regions in (
            (),
            (BDNSRegion("ES52 - COMUNIDAD VALENCIANA"),),
            (BDNSRegion("ES - ESPAÑA"),),
            (BDNSRegion("ES522 - CASTELLÓN / CASTELLÓ"),),
            (BDNSRegion("ES - REGIÓN SINTÉTICA"),),
        ):
            with self.subTest(regions=regions):
                decision = evaluate_bdns_territory(replace(detail, regions=regions))
                self.assertEqual(decision.status, BDNSTerritorialStatus.UNRESOLVED)

    def test_exact_disjoint_province_is_out_of_scope_but_local_match_wins(self) -> None:
        _, detail = source_models()
        valencia = replace(detail, regions=(BDNSRegion("ES523 - Valencia / València"),))
        self.assertEqual(evaluate_bdns_territory(valencia).status, BDNSTerritorialStatus.OUT_OF_SCOPE)
        combined = replace(detail, regions=(*valencia.regions, BDNSRegion(CASTELLON)))
        self.assertEqual(evaluate_bdns_territory(combined).status, BDNSTerritorialStatus.INCLUDE)

    def test_nonincluded_decisions_return_no_candidate_and_no_data(self) -> None:
        summary, detail = source_models()
        for regions, expected in (
            ((), BDNSTerritorialStatus.UNRESOLVED),
            ((BDNSRegion("ES52 - COMUNIDAD VALENCIANA"),), BDNSTerritorialStatus.UNRESOLVED),
            ((BDNSRegion("ES523 - Valencia / València"),), BDNSTerritorialStatus.OUT_OF_SCOPE),
        ):
            result = normalized(summary=summary, detail=replace(detail, regions=regions))
            self.assertEqual(result.territorial_decision.status, expected)
            self.assertIsNone(result.candidate)


class BDNSNormalizationTests(unittest.TestCase):
    def test_core_candidate_uses_code_title_dates_and_official_source_url(self) -> None:
        summary, detail = source_models()
        result = normalized(summary=summary, detail=detail)
        candidate = result.candidate
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.source.id, "bdns")
        self.assertEqual(candidate.source.official_id, "900001")
        self.assertEqual(candidate.category, Category.GRANTS_CALL)
        self.assertEqual(candidate.title, detail.title)
        self.assertIsNone(candidate.description)
        self.assertEqual(candidate.dates.detected_at, DETECTED)
        self.assertEqual(candidate.dates.last_checked_at, CHECKED)
        self.assertIsNone(candidate.dates.event_at)
        self.assertEqual(candidate.dates.published_at.isoformat(), "2026-09-26")
        self.assertEqual(
            candidate.source_url,
            "https://www.infosubvenciones.es/bdnstrans/api/convocatorias?numConv=900001",
        )
        self.assertEqual(candidate.grant.call_id, "900001")
        self.assertIsNone(candidate.grant.beneficiary)
        self.assertIsNone(candidate.grant.resolution_id)
        self.assertEqual(candidate.geography.province, "Castellón/Castelló")
        self.assertIsNone(candidate.geography.municipality)
        self.assertEqual(candidate.provenance.territorial_matches[0].reason.value, "official_code_match")
        self.assertEqual(candidate.technical.extraction_method, "bdns_rest_json")
        self.assertIsNone(candidate.financial)
        self.assertEqual(candidate.documents, ())

    def test_authority_uses_joined_invente_code_and_unknown_core_level(self) -> None:
        summary, detail = source_models()
        candidate = normalized(summary=summary, detail=detail).candidate
        self.assertEqual(candidate.authority.id, "bdns:invente:INV00000001")
        self.assertEqual(
            candidate.authority.name,
            "ADMINISTRACIÓN DE EJEMPLO / ÓRGANO DE EJEMPLO",
        )
        self.assertIsNone(candidate.authority.administration_level)
        self.assertIsNone(candidate.administration_level)

    def test_authority_fallback_id_is_deterministic_and_explicitly_derived(self) -> None:
        summary, detail = source_models()
        without_code = replace(summary, codigo_invente=None)
        first = normalized(summary=without_code, detail=detail).candidate.authority
        second = normalized(summary=without_code, detail=detail).candidate.authority
        self.assertEqual(first.id, second.id)
        self.assertTrue(first.id.startswith("bdns:derived-authority:"))

        alternate_labels = replace(
            detail,
            authority=replace(
                detail.authority,
                nivel1="  Administración   de ejemplo ",
                nivel2="órgano de ejemplo",
            ),
        )
        alternate = normalized(summary=without_code, detail=alternate_labels).candidate.authority
        self.assertEqual(first.id, alternate.id)

    def test_missing_authority_stays_unknown_without_sentinel(self) -> None:
        summary, detail = source_models()
        candidate = normalized(summary=summary, detail=replace(detail, authority=None)).candidate
        self.assertIsNone(candidate.authority)
        self.assertIsNone(candidate.administration_level)
        self.assertNotIn("unknown", json.dumps(candidate.to_dict(), ensure_ascii=False).casefold())

    def test_title_fallback_is_literal_and_missing_titles_fail_closed(self) -> None:
        summary, detail = source_models()
        coofficial = replace(detail, title=None, title_coofficial="  Títol oficial sintètic  ")
        self.assertEqual(normalized(summary=summary, detail=coofficial).candidate.title, "  Títol oficial sintètic  ")
        missing = replace(detail, title=None, title_coofficial=None)
        with self.assertRaisesRegex(BDNSNormalizationError, "title_unavailable"):
            normalized(summary=summary, detail=missing)

    def test_only_one_identifiable_extract_can_supply_published_at(self) -> None:
        summary, detail = source_models()
        self.assertEqual(normalized(summary=summary, detail=detail).candidate.dates.published_at.isoformat(), "2026-09-26")
        two_extracts = replace(detail, extracts=detail.extracts * 2)
        self.assertIsNone(normalized(summary=summary, detail=two_extracts).candidate.dates.published_at)
        no_extract = replace(detail, extracts=())
        self.assertIsNone(normalized(summary=summary, detail=no_extract).candidate.dates.published_at)
        ambiguous = replace(detail.extracts[0], cve=None, url=None)
        self.assertIsNone(normalized(summary=summary, detail=replace(detail, extracts=(ambiguous,))).candidate.dates.published_at)

    def test_join_mismatch_fails_and_receipt_date_never_becomes_publication_date(self) -> None:
        summary, detail = source_models()
        with self.assertRaisesRegex(BDNSNormalizationError, "identity_mismatch"):
            normalized(summary=replace(summary, numero_convocatoria="900002"), detail=detail)
        without_receipt_date = replace(detail, fecha_recepcion=None)
        self.assertEqual(
            normalized(summary=summary, detail=without_receipt_date).candidate.dates.published_at,
            detail.extracts[0].publication_date,
        )

    def test_invalid_or_naive_observation_timestamps_fail_closed(self) -> None:
        summary, detail = source_models()
        with self.assertRaisesRegex(BDNSNormalizationError, "observation_timestamp_invalid"):
            normalize_bdns_detail(
                summary,
                detail,
                detected_at=datetime(2026, 9, 27, 9, 0),
                last_checked_at=CHECKED,
            )
        with self.assertRaisesRegex(BDNSNormalizationError, "observation_timestamp_order_invalid"):
            normalize_bdns_detail(summary, detail, detected_at=CHECKED, last_checked_at=DETECTED)

    def test_finalizer_identity_and_administrative_hash_follow_core_contract(self) -> None:
        summary, detail = source_models()
        candidate = normalized(summary=summary, detail=detail).candidate
        first = finalize_record(candidate)
        issue_only_change = finalize_record(
            normalized(summary=replace(summary, internal_id=812345), detail=detail).candidate
        )
        title_changed = finalize_record(
            normalized(summary=summary, detail=replace(detail, title="Título sintético actualizado")).candidate
        )
        self.assertEqual(first.id, issue_only_change.id)
        self.assertEqual(first.technical.content_hash, issue_only_change.technical.content_hash)
        self.assertEqual(first.id, title_changed.id)
        self.assertNotEqual(first.technical.content_hash, title_changed.technical.content_hash)
        self.assertIn("title", {change.path for change in diff(first.to_dict(), title_changed.to_dict())})


if __name__ == "__main__":
    unittest.main()
