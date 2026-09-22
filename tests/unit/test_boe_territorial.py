"""Pruebas offline de la política territorial BOE v1."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.boe import (
    BOEDocumentLinks,
    BOEItem,
    BOETerritorialDecisionStatus,
    BOETerritorialEntity,
    BOETerritorialEntityKind,
    BOETerritorialField,
    BOETerritorialMatchReason,
    BOETerritorialRegistry,
    BOETerritorialRegistryError,
    decide_boe_territorial_inclusion,
    load_castellon_registry,
    parse_boe_summary,
)


OFFICIAL_INE_FIXTURE = ROOT / "tests" / "fixtures" / "ine_2026_castellon_municipalities.json"


def item(
    *,
    title: str = "Resolución estatal de alcance general",
    heading: str | None = None,
    department: str = "MINISTERIO DE EJEMPLO",
    section_name: str = "I. Disposiciones generales",
) -> BOEItem:
    return BOEItem(
        official_id="BOE-A-2099-1",
        title=title,
        section_code="1",
        section_name=section_name,
        department_code="9999",
        department_name=department,
        heading_name=heading,
        published_on=date(2099, 1, 1),
        documents=BOEDocumentLinks(
            xml_url="https://www.boe.es/diario_boe/xml.php?id=BOE-A-2099-1",
            html_url="https://www.boe.es/diario_boe/txt.php?id=BOE-A-2099-1",
            pdf_url="https://www.boe.es/boe/dias/2099/01/01/pdfs/BOE-A-2099-1.pdf",
        ),
    )


class BOETerritorialRegistryTests(unittest.TestCase):
    def test_registry_matches_the_versioned_current_official_ine_relationship(self) -> None:
        registry = load_castellon_registry()
        fixture = json.loads(OFFICIAL_INE_FIXTURE.read_text(encoding="utf-8"))
        registry_raw = json.loads((ROOT / "config" / "entities" / "castellon.json").read_text(encoding="utf-8"))

        self.assertEqual(fixture["expected_municipality_count"], 135)
        self.assertEqual(registry_raw["source"]["expected_municipality_count"], 135)
        self.assertEqual(len(registry.municipalities), 135)
        self.assertEqual(
            tuple(entity.code for entity in registry.municipalities),
            tuple(row["code"] for row in fixture["municipalities"]),
        )
        self.assertTrue(all(re.fullmatch(r"12\d{3}", entity.code) for entity in registry.municipalities))
        self.assertEqual(len({entity.code for entity in registry.municipalities}), 135)
        self.assertTrue(all(entity.official_name.strip() for entity in registry.municipalities))
        self.assertNotIn("12066", {entity.code for entity in registry.municipalities})

        self.assertEqual(registry.province.code, "12")
        self.assertEqual(registry.province.official_variants, ("Castellón", "Castelló"))
        city = next(entity for entity in registry.municipalities if entity.code == "12040")
        self.assertEqual(
            city.official_variants,
            ("Castelló de la Plana", "Castellón de la Plana"),
        )
        self.assertEqual(city.technical_aliases, ())
        self.assertEqual(
            registry_raw["source"]["canonical_source"]["url"],
            fixture["canonical_source"]["url"],
        )
        self.assertEqual(registry_raw["source"]["reference_date"], "2026-01-01")
        self.assertEqual(registry_raw["source"]["checked_at"], "2026-09-21")
        self.assertIn("api_source", registry_raw["source"])

    def test_registry_loader_rejects_non_castellon_municipality_code(self) -> None:
        raw = json.loads((ROOT / "config" / "entities" / "castellon.json").read_text(encoding="utf-8"))
        raw["municipalities"][0]["code"] = "13001"
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid_registry.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(BOETerritorialRegistryError):
                load_castellon_registry(path)

    def test_existing_real_boe_fixture_is_not_included_without_a_literal_match(self) -> None:
        fixture = ROOT / "collectors" / "boe" / "fixtures" / "summary_20240529_minimal.json"
        real_item = parse_boe_summary(json.loads(fixture.read_text(encoding="utf-8"))).items[0]
        decision = decide_boe_territorial_inclusion(real_item, load_castellon_registry())
        self.assertEqual(decision.status, BOETerritorialDecisionStatus.NO_MATCH)


class BOETerritorialPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_castellon_registry()

    def decide(self, **kwargs):
        return decide_boe_territorial_inclusion(item(**kwargs), self.registry)

    def test_official_municipal_name_and_linguistic_variant_are_included(self) -> None:
        valencian = self.decide(title="Anuncio relativo al municipio de Borriana")
        spanish = self.decide(title="Anuncio relativo al municipio de Burriana")
        for decision, observed in ((valencian, "Borriana"), (spanish, "Burriana")):
            with self.subTest(observed=observed):
                self.assertEqual(decision.status, BOETerritorialDecisionStatus.INCLUDE)
                self.assertEqual(decision.matches[0].reason, BOETerritorialMatchReason.MUNICIPALITY_EXACT)
                self.assertEqual(decision.matches[0].matched_text, observed)

    def test_case_and_diacritic_variation_match_without_changing_observed_text(self) -> None:
        decision = self.decide(title="Convenio en PENISCOLA")
        self.assertEqual(decision.status, BOETerritorialDecisionStatus.INCLUDE)
        self.assertEqual(decision.matches[0].entity_code, "12089")
        self.assertEqual(decision.matches[0].matched_text, "PENISCOLA")

    def test_both_compound_city_forms_are_municipalities_not_implicit_province_matches(self) -> None:
        for city_form in ("Castelló de la Plana", "Castellón de la Plana"):
            with self.subTest(city_form=city_form):
                decision = self.decide(title=f"Resolución del Ayuntamiento de {city_form}")
                self.assertEqual(decision.status, BOETerritorialDecisionStatus.INCLUDE)
                self.assertEqual(
                    tuple(match.reason for match in decision.matches),
                    (BOETerritorialMatchReason.MUNICIPALITY_EXACT,),
                )
                self.assertEqual(decision.matches[0].matched_text, city_form)

    def test_unqualified_castellon_is_province_not_municipality(self) -> None:
        decision = self.decide(title="Resolución para la provincia de Castellón")
        self.assertEqual(decision.status, BOETerritorialDecisionStatus.INCLUDE)
        self.assertEqual(decision.matches[0].reason, BOETerritorialMatchReason.PROVINCE_EXACT)
        self.assertEqual(decision.matches[0].entity_code, "12")

    def test_boundaries_prevent_substring_false_positive(self) -> None:
        decision = self.decide(title="Programa de Vila-realistas sin referencia municipal")
        self.assertEqual(decision.status, BOETerritorialDecisionStatus.NO_MATCH)
        self.assertEqual(decision.matches, ())

    def test_only_heading_department_and_title_are_inspected_in_documented_order(self) -> None:
        decision = self.decide(
            heading="Actuaciones en Borriana",
            department="MINISTERIO PARA LA PROVINCIA DE CASTELLÓN",
            title="Resolución de alcance general",
            section_name="Sección sobre Castellón que no debe inspeccionarse",
        )
        self.assertEqual(decision.status, BOETerritorialDecisionStatus.INCLUDE)
        self.assertEqual(
            tuple((match.field, match.reason) for match in decision.matches),
            (
                (BOETerritorialField.HEADING, BOETerritorialMatchReason.MUNICIPALITY_EXACT),
                (BOETerritorialField.DEPARTMENT, BOETerritorialMatchReason.PROVINCE_EXACT),
            ),
        )

    def test_registry_can_add_verified_authorities_without_mixing_them_with_municipalities(self) -> None:
        authority = BOETerritorialEntity(
            code="authority:example-city-council",
            official_name="Ayuntamiento de Castelló de la Plana",
            official_variants=("Ayuntamiento de Castelló de la Plana",),
            technical_aliases=(),
            kind=BOETerritorialEntityKind.AUTHORITY,
        )
        registry = replace(self.registry, authorities=(authority,))
        decision = decide_boe_territorial_inclusion(
            item(title="Resolución del Ayuntamiento de Castelló de la Plana"), registry
        )
        self.assertEqual(decision.status, BOETerritorialDecisionStatus.INCLUDE)
        self.assertEqual(decision.matches[0].reason, BOETerritorialMatchReason.AUTHORITY_EXACT)
        self.assertEqual(decision.matches[0].entity_code, "authority:example-city-council")

    def test_multiple_mentions_are_deduplicated_but_distinct_facts_are_retained(self) -> None:
        decision = self.decide(
            heading="Borriana y Borriana",
            title="Anuncio para la provincia de Castellón",
        )
        self.assertEqual(len(decision.matches), 2)
        self.assertEqual(
            tuple(match.reason for match in decision.matches),
            (BOETerritorialMatchReason.MUNICIPALITY_EXACT, BOETerritorialMatchReason.PROVINCE_EXACT),
        )

    def test_negative_cases_are_not_included(self) -> None:
        cases = (
            "Resolución estatal de alcance general",
            "Anuncio para la provincia de Valencia",
            "Actuación en Borrianense sin municipio explícito",
            "Referencia al alias no registrado CS",
        )
        for title in cases:
            with self.subTest(title=title):
                decision = self.decide(title=title)
                self.assertEqual(decision.status, BOETerritorialDecisionStatus.NO_MATCH)
                self.assertEqual(decision.matches, ())


if __name__ == "__main__":
    unittest.main()
