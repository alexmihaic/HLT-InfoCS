"""Normalización BOP offline; no contiene títulos ni datos de anuncios reales."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.diff.core import diff  # noqa: E402
from infocs.fetch.bop_castellon.models import BOPAnnouncement, BOPIssue  # noqa: E402
from infocs.fetch.bop_castellon.normalize import (  # noqa: E402
    BOPNormalizationError,
    category_for_bop_title,
    normalize_bop_announcement,
)
from infocs.finalize import finalize_record  # noqa: E402
from infocs.models import AdministrationLevel, Category  # noqa: E402


DETECTED = datetime(2026, 9, 26, 10, 15, tzinfo=UTC)
CHECKED = datetime(2026, 9, 26, 10, 16, tzinfo=UTC)


def issue(portal_id: str = "200001") -> BOPIssue:
    return BOPIssue(portal_id, date(2026, 9, 24), "115", "B260924")


def announcement(
    portal_id: str = "100001",
    *,
    title: str = "Anuncio sintético de prueba",
    heading_path: tuple[str, ...] = (),
) -> BOPAnnouncement:
    return BOPAnnouncement(
        portal_id,
        title,
        f"https://bop.dipcas.es/PortalBOP/api/descargarAnuncio?idAnuncio={portal_id}&idioma=es",
        heading_path=heading_path,
    )


def candidate(ann: BOPAnnouncement | None = None, *, source_issue: BOPIssue | None = None):
    return normalize_bop_announcement(
        source_issue or issue(),
        ann or announcement(),
        detected_at=DETECTED,
        last_checked_at=CHECKED,
    )


class BOPNormalizationTests(unittest.TestCase):
    def test_candidate_preserves_official_id_title_dates_and_document_link_only(self) -> None:
        ann = announcement(title="  Título sintético exacto  ")
        value = candidate(ann)
        self.assertEqual(value.source.id, "bop_castellon")
        self.assertEqual(value.source.official_id, "100001")
        self.assertEqual(value.title, "  Título sintético exacto  ")
        self.assertIsNone(value.description)
        self.assertEqual(value.dates.published_at, date(2026, 9, 24))
        self.assertEqual(value.dates.detected_at, DETECTED)
        self.assertEqual(value.dates.last_checked_at, CHECKED)
        self.assertIsNone(value.dates.event_at)
        self.assertEqual(value.source_url, ann.document_url)
        self.assertEqual(len(value.documents), 1)
        document = value.documents[0]
        self.assertEqual(document.source_url, ann.document_url)
        self.assertIsNone(document.mime_type)
        self.assertIsNone(document.sha256)
        self.assertFalse(document.has_local_copy)
        self.assertFalse(document.publication_allowed)
        self.assertEqual(value.technical.extraction_method, "bop_listing_html")

    def test_portal_announcement_id_is_record_identity_not_issue_identity(self) -> None:
        first = finalize_record(candidate(announcement("100007"), source_issue=issue("200001")))
        second = finalize_record(candidate(announcement("100007"), source_issue=issue("299999")))
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.technical.identity_strategy, "official_id")
        self.assertEqual(first.technical.content_hash, second.technical.content_hash)

    def test_title_change_keeps_identity_and_changes_administrative_hash(self) -> None:
        first = finalize_record(candidate(announcement(title="Título sintético A")))
        second = finalize_record(candidate(announcement(title="Título sintético B")))
        self.assertEqual(first.id, second.id)
        self.assertNotEqual(first.technical.content_hash, second.technical.content_hash)
        self.assertIn("title", {change.path for change in diff(first.to_dict(), second.to_dict())})

    def test_province_scope_is_present_for_every_candidate(self) -> None:
        value = candidate()
        self.assertEqual(value.geography.province, "Castellón/Castelló")
        self.assertIsNone(value.geography.municipality)
        self.assertEqual(value.provenance.territorial_matches[0].reason.value, "other_documented")
        self.assertIn('"province_code":"12"', value.provenance.territorial_matches[0].detail)

    def test_exact_municipal_headings_enrich_authority_and_geography(self) -> None:
        cases = (
            ("AYUNTAMIENTO DE VILA-REAL", "12135", "Vila-real"),
            ("AJUNTAMENT DE BORRIANA", "12032", "Borriana/Burriana"),
            ("castello de la plana", "12040", "Castell\u00f3 de la Plana/Castell\u00f3n de la Plana"),
        )
        for heading, code, municipality in cases:
            with self.subTest(heading=heading):
                value = candidate(announcement(heading_path=(heading,)))
                self.assertEqual(value.authority.id, f"bop-castellon:municipality:{code}")
                self.assertEqual(value.authority.administration_level, AdministrationLevel.MUNICIPAL)
                self.assertEqual(value.administration_level, AdministrationLevel.MUNICIPAL)
                self.assertEqual(value.geography.municipality, municipality)

    def test_title_never_supplies_municipality_and_near_match_is_not_fuzzy(self) -> None:
        title_only = candidate(announcement(title="Anuncio relativo a Vila-real"))
        self.assertIsNone(title_only.authority)
        self.assertIsNone(title_only.geography.municipality)

        near = candidate(announcement(heading_path=("AYUNTAMIENTO DE VILA-REAL DE EJEMPLO",)))
        self.assertIsNotNone(near.authority)  # el rótulo municipal explícito se conserva
        self.assertIsNone(near.geography.municipality)  # sin coincidencia exacta de registry

    def test_deputation_and_other_explicit_authority_headings(self) -> None:
        deputation = candidate(announcement(heading_path=("DIPUTACIÓN PROVINCIAL DE CASTELLÓN",)))
        self.assertEqual(deputation.authority.id, "bop-castellon:diputacion:12")
        self.assertEqual(deputation.administration_level, AdministrationLevel.PROVINCIAL)
        self.assertIsNone(deputation.geography.municipality)

        consortium = candidate(announcement(heading_path=("CONSORCIO DE EJEMPLO",)))
        self.assertEqual(consortium.authority.name, "CONSORCIO DE EJEMPLO")
        self.assertTrue(consortium.authority.id.startswith("bop-castellon:authority:"))
        self.assertIsNone(consortium.authority.administration_level)
        self.assertIsNone(consortium.administration_level)

        generalitat = candidate(announcement(heading_path=("GENERALITAT VALENCIANA",)))
        self.assertEqual(generalitat.administration_level, AdministrationLevel.AUTONOMOUS)

    def test_generic_or_missing_heading_keeps_authority_unknown(self) -> None:
        for path in ((), ("AYUNTAMIENTOS",), ("Grupo de ejemplo", "Anuncios")):
            with self.subTest(path=path):
                value = candidate(announcement(heading_path=path))
                self.assertIsNone(value.authority)
                self.assertIsNone(value.administration_level)
                self.assertNotIn("unknown", str(value.to_dict()).casefold())

    def test_category_rules_use_core_vocabulary_and_other_fallback(self) -> None:
        self.assertEqual(category_for_bop_title("Bases de oposiciones sintéticas"), Category.EMPLOYMENT)
        self.assertEqual(category_for_bop_title("Licitacion de prueba"), Category.PROCUREMENT)
        self.assertEqual(category_for_bop_title("Convocatoria de subvenciones ficticia"), Category.GRANTS)
        self.assertEqual(category_for_bop_title("Aprobación de ordenanza sintética"), Category.REGULATION)
        self.assertEqual(category_for_bop_title("Asunto administrativo genérico"), Category.OTHER)

    def test_derived_category_geography_and_authority_do_not_change_content_hash(self) -> None:
        base = finalize_record(candidate())
        changed_category = finalize_record(replace(candidate(), category=Category.EMPLOYMENT))
        changed_geography = finalize_record(replace(candidate(), geography=replace(candidate().geography, municipality="Vila-real")))
        known_authority = finalize_record(candidate(announcement(heading_path=("CONSORCIO DE EJEMPLO",))))
        self.assertEqual(base.technical.content_hash, changed_category.technical.content_hash)
        self.assertEqual(base.technical.content_hash, changed_geography.technical.content_hash)
        self.assertEqual(base.technical.content_hash, known_authority.technical.content_hash)

    def test_heading_metadata_does_not_change_record_identity_or_hash(self) -> None:
        without_heading = finalize_record(candidate(announcement("100009")))
        with_heading = finalize_record(candidate(announcement("100009", heading_path=("CONSORCIO DE EJEMPLO",))))
        self.assertEqual(without_heading.id, with_heading.id)
        self.assertEqual(without_heading.technical.content_hash, with_heading.technical.content_hash)

    def test_bad_timestamps_and_nonofficial_document_url_fail_closed(self) -> None:
        with self.assertRaisesRegex(BOPNormalizationError, "observation_timestamp_invalid"):
            normalize_bop_announcement(issue(), announcement(), detected_at=datetime(2026, 9, 26), last_checked_at=CHECKED)
        with self.assertRaisesRegex(BOPNormalizationError, "observation_timestamp_order_invalid"):
            normalize_bop_announcement(issue(), announcement(), detected_at=CHECKED, last_checked_at=DETECTED)
        with self.assertRaisesRegex(BOPNormalizationError, "announcement_url_invalid"):
            candidate(announcement().__class__("100001", "Título sintético", "https://example.invalid/documento"))


if __name__ == "__main__":
    unittest.main()
