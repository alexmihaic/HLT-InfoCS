from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.fetch.bdns.models import BDNSRequestStatus
from infocs.fetch.bdns.parser import BDNSContractError, parse_bdns_detail, parse_bdns_search


FIXTURES = ROOT / "tests" / "fixtures" / "bdns"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"), parse_float=Decimal)


class BDNSSearchParserTests(unittest.TestCase):
    def test_search_result_and_actual_pagination_shape(self) -> None:
        page = parse_bdns_search(load_fixture("search_success.json"))
        self.assertEqual(page.page_number, 0)
        self.assertEqual(page.page_size, 25)
        self.assertEqual(page.offset, 0)
        self.assertEqual(page.total_elements, 1)
        self.assertEqual(page.total_pages, 1)
        self.assertFalse(page.empty)
        item = page.items[0]
        self.assertEqual(item.numero_convocatoria, "900001")
        self.assertEqual(item.internal_id, 700001)
        self.assertEqual(item.title, "Convocatoria sintética de ejemplo")
        self.assertEqual(item.fecha_recepcion.isoformat(), "2026-09-25")
        self.assertEqual(item.nivel2, "ÓRGANO DE EJEMPLO")
        self.assertFalse(item.mrr)
        self.assertFalse(hasattr(item, "campoFuturo"))

    def test_empty_search_is_valid_zero_result_page(self) -> None:
        page = parse_bdns_search(load_fixture("search_empty.json"))
        self.assertEqual(page.items, ())
        self.assertEqual(page.total_elements, 0)
        self.assertTrue(page.empty)

    def test_required_external_code_and_pagination_types_are_strict(self) -> None:
        payload = load_fixture("search_success.json")
        del payload["content"][0]["numeroConvocatoria"]
        with self.assertRaises(BDNSContractError):
            parse_bdns_search(payload)
        payload = load_fixture("search_success.json")
        payload["pageable"]["pageSize"] = "25"
        with self.assertRaises(BDNSContractError):
            parse_bdns_search(payload)


class BDNSDetailParserTests(unittest.TestCase):
    def test_detail_preserves_relevant_structured_fields_and_exact_decimal(self) -> None:
        detail = parse_bdns_detail(load_fixture("detail_success.json"))
        self.assertEqual(detail.codigo_bdns, "900001")
        self.assertEqual(detail.internal_id, 700001)
        self.assertEqual(detail.authority.nivel1, "ADMINISTRACIÓN DE EJEMPLO")
        self.assertEqual(detail.fecha_recepcion.isoformat(), "2026-09-25")
        self.assertEqual(detail.application_start_date.isoformat(), "2026-10-01")
        self.assertEqual(detail.total_budget, Decimal("123456.78"))
        self.assertEqual(detail.regions[0].description, "ES - REGIÓN SINTÉTICA")
        self.assertEqual(detail.documents[0].document_id, 800001)
        self.assertEqual(detail.documents[0].length, 1024)
        self.assertEqual(detail.extracts[0].announcement_number, 1)
        self.assertEqual(detail.extracts[0].cve, "BOE-B-2026-90001")
        self.assertEqual(detail.extracts[0].publication_date.isoformat(), "2026-09-26")
        self.assertNotIn("campoFuturo", detail.__dataclass_fields__)

    def test_detail_optional_blocks_can_be_absent(self) -> None:
        payload = {"codigoBDNS": "900002", "descripcion": "Otra convocatoria sintética"}
        detail = parse_bdns_detail(payload)
        self.assertIsNone(detail.authority)
        self.assertIsNone(detail.total_budget)
        self.assertEqual(detail.documents, ())
        self.assertEqual(detail.extracts, ())

    def test_bad_date_and_unexpected_amount_type_fail_closed(self) -> None:
        payload = load_fixture("detail_success.json")
        payload["fechaRecepcion"] = "25/09/2026"
        with self.assertRaises(BDNSContractError):
            parse_bdns_detail(payload)
        payload = load_fixture("detail_success.json")
        payload["presupuestoTotal"] = 123.45
        with self.assertRaises(BDNSContractError):
            parse_bdns_detail(payload)


if __name__ == "__main__":
    unittest.main()
