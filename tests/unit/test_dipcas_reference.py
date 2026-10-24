"""DIPCAS-REF-01: catálogo municipal de referencia. Solo datos ficticios y mocks; sin red."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from infocs.reference import dipcas_snapshot as snap
from infocs.reference.dipcas_catalog import AuditBaseline, EntityKind, build_catalog, load_registry_municipalities, normalize_link
from infocs.reference.dipcas_transport import (
    DIPCAS_DATASET_URL,
    DIPCAS_PAGE_SIZE,
    DIPCAS_SELECT_FIELDS,
    DipcasFetchError,
    DipcasTransport,
    records_url,
)

REGISTRY = {"12001": "Alfa", "12002": "Beta", "12003": "Gamma"}
BASELINE = AuditBaseline(entity_count=4, municipality_count=3, sub_municipal_dir3=frozenset({"L04120900"}))
NOW = lambda: datetime(2026, 10, 24, 10, 30, 15, 999, tzinfo=timezone.utc)  # noqa: E731

EXCLUDED_EXTRAS = {
    "alcalde": "Persona Ficticia",
    "partido": "Partido Ficticio",
    "cif": "P0000000X",
    "telefono": "000000000",
    "correo_electronico_ayuntamiento": "alguien@example.invalid",
    "habitantes": 10,
    "campo_nuevo": "no autorizado",
}


def rec(ine, dir3, name, kind="Ayuntamiento", comarca="Comarca X", web="www.alfa.example", sede="alfa.sede.example", **extra):
    return {"id": kind, "ine": ine, "dir3": dir3, "nombre_poblacion": name, "comarca": comarca, "web_ayuntamiento": web, "sede_electronica": sede, **extra}


def good_records():
    return [
        rec("12001", "L01120011", "Alfa", **EXCLUDED_EXTRAS),
        rec("12002", "L01120022", "Beta", web="https://www.beta.example", sede=None),
        rec("12003", "L01120033", "Gamma", comarca=None),
        rec(None, "L04120900", "Delta (aldea)", kind="E.L. Menor", **EXCLUDED_EXTRAS),
    ]


def metadata(total=4, **overrides):
    default = {
        "title": "Ayuntamientos",
        "publisher": "Entidad Ficticia",
        "license": "http://example.invalid/licenses/cc-by",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "modified": "2026-06-18T07:14:44+00:00",
        "records_count": total,
    }
    default.update(overrides)
    return {"dataset_id": "ayuntamientos", "fields": [{"name": n} for n in DIPCAS_SELECT_FIELDS + ("alcalde",)], "metas": {"default": default}}


class FakeResponse:
    def __init__(self, status=200, body=b"{}", content_type="application/json", declared=None):
        self.status = status
        self.body = body
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body) if declared is None else declared)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def read(self, size=-1):
        return self.body[:size] if size >= 0 else self.body


def json_response(payload, **kw):
    return FakeResponse(body=json.dumps(payload).encode("utf-8"), **kw)


class ScriptedOpener:
    """Sirve metadatos y páginas de `records` a partir de una lista de registros."""

    def __init__(self, records, meta=None, page_size=DIPCAS_PAGE_SIZE):
        self.records, self.meta, self.page_size = records, meta if meta is not None else metadata(len(records)), page_size
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        url = request.full_url
        if url == DIPCAS_DATASET_URL:
            return json_response(self.meta)
        query = parse_qs(urlsplit(url).query)
        offset, limit = int(query["offset"][0]), min(int(query["limit"][0]), self.page_size)
        return json_response({"total_count": len(self.records), "results": self.records[offset : offset + limit]})


def failing(error):
    def opener(request, timeout):
        raise error

    return opener


def snapshot_for(records=None, **kw):
    records = good_records() if records is None else records
    return snap.build_snapshot(DipcasTransport(opener=ScriptedOpener(records)), REGISTRY, now=NOW, baseline=BASELINE, **kw)


class TransportTests(unittest.TestCase):
    def test_request_shape_is_read_only_https_get_with_explicit_timeout(self):
        opener = ScriptedOpener(good_records())
        result = DipcasTransport(opener=opener, timeout_seconds=7).fetch_records()
        request, timeout = opener.requests[0]
        self.assertEqual((request.get_method(), timeout), ("GET", 7))
        parts = urlsplit(request.full_url)
        query = parse_qs(parts.query)
        self.assertEqual((parts.scheme, parts.hostname), ("https", "dipcas.opendatasoft.com"))
        self.assertEqual(query["select"], [",".join(DIPCAS_SELECT_FIELDS)])
        self.assertNotIn("Authorization", {k.title() for k in request.headers})
        self.assertEqual(len(result.records), 4)

    def test_pagination_collects_all_pages_in_order(self):
        records = [rec(f"12{i:03d}", f"L01120{i:03d}", f"N{i}") for i in range(1, 8)]
        opener = ScriptedOpener(records, page_size=3)
        with mock.patch("infocs.reference.dipcas_transport.DIPCAS_PAGE_SIZE", 3):
            result = DipcasTransport(opener=opener).fetch_records()
        self.assertEqual([r["ine"] for r in result.records], [r["ine"] for r in records])
        self.assertEqual(len(result.request_urls), 3)
        self.assertEqual(parse_qs(urlsplit(result.request_urls[1]).query)["offset"], ["3"])

    def test_pagination_is_bounded(self):
        records = [rec(f"12{i:03d}", f"L01120{i:03d}", f"N{i}") for i in range(1, 8)]
        with mock.patch("infocs.reference.dipcas_transport.DIPCAS_PAGE_SIZE", 2):
            with self.assertRaises(DipcasFetchError) as ctx:
                DipcasTransport(opener=ScriptedOpener(records, page_size=2), max_pages=2).fetch_records()
        self.assertEqual(ctx.exception.reason, "too_many_pages")

    def test_empty_response(self):
        result = DipcasTransport(opener=ScriptedOpener([])).fetch_records()
        self.assertEqual((result.records, result.total_count), ((), 0))

    def test_truncated_pagination_and_inconsistent_total(self):
        class Short(ScriptedOpener):
            def __call__(self, request, timeout):
                return json_response({"total_count": 5, "results": []})

        with self.assertRaises(DipcasFetchError) as ctx:
            DipcasTransport(opener=Short([])).fetch_records()
        self.assertEqual(ctx.exception.reason, "truncated_pagination")

    def test_http_failures_timeout_and_network(self):
        cases = [
            (failing(HTTPError("https://x", 429, "Too Many", {}, None)), "rate_limited"),
            (failing(HTTPError("https://x", 503, "Unavailable", {}, None)), "server_error"),
            (failing(HTTPError("https://x", 404, "Nope", {}, None)), "http_failure"),
            (failing(socket.timeout()), "timeout"),
            (failing(URLError("boom")), "network_failure"),
        ]
        for opener, reason in cases:
            with self.subTest(reason=reason), self.assertRaises(DipcasFetchError) as ctx:
                DipcasTransport(opener=opener).fetch_metadata()
            self.assertEqual(ctx.exception.reason, reason)

    def test_non_200_wrong_mime_oversize_and_bad_json(self):
        cases = [
            (FakeResponse(status=204), "http_failure"),
            (FakeResponse(content_type="text/html"), "mime_incompatible"),
            (FakeResponse(body=b"{}", declared=10_000_000), "body_too_large"),
            (FakeResponse(body=b"x" * 50), "body_too_large"),
            (FakeResponse(body=b"{no json"), "invalid_json"),
            (FakeResponse(body=b"[1]"), "invalid_payload"),
        ]
        for response, reason in cases:
            with self.subTest(reason=reason), self.assertRaises(DipcasFetchError) as ctx:
                DipcasTransport(opener=lambda r, t, resp=response: resp, max_response_bytes=40).fetch_metadata()
            self.assertEqual(ctx.exception.reason, reason)

    def test_unexpected_contract_in_records_page(self):
        for payload in ({"results": []}, {"total_count": "3", "results": []}, {"total_count": 1, "results": "x"}, {"total_count": 1, "results": [1]}):
            with self.subTest(payload=payload), self.assertRaises(DipcasFetchError) as ctx:
                DipcasTransport(opener=lambda r, t, p=payload: json_response(p)).fetch_records()
            self.assertEqual(ctx.exception.reason, "invalid_payload")

    def test_rejects_non_pinned_host_and_bad_paging_arguments(self):
        with self.assertRaises(DipcasFetchError):
            DipcasTransport(opener=ScriptedOpener([]))._get_json("http://dipcas.opendatasoft.com/x")
        with self.assertRaises(ValueError):
            records_url(offset=0, limit=DIPCAS_PAGE_SIZE + 1)


class CatalogTests(unittest.TestCase):
    def catalog(self, records, baseline=BASELINE):
        return build_catalog(records, REGISTRY, baseline)

    def codes(self, result):
        return {i.code for i in result.blocking_issues}

    def test_valid_catalog_separates_municipalities_and_sub_municipal(self):
        result = self.catalog(good_records())
        self.assertTrue(result.is_valid, result.issues)
        self.assertEqual([e.ine for e in result.municipalities], ["12001", "12002", "12003"])
        (delta,) = result.sub_municipal
        self.assertEqual((delta.kind, delta.ine, delta.registry_name), (EntityKind.SUB_MUNICIPAL, None, None))
        self.assertEqual(result.municipalities[0].registry_name, "Alfa")

    def test_no_name_similarity_join(self):
        records = good_records()
        records[0] = rec("12099", "L01120011", "Alfa")  # mismo nombre que el registro, INE distinto
        result = self.catalog(records)
        self.assertIn("unknown_ine", self.codes(result))
        self.assertIn("missing_in_dataset", self.codes(result))
        self.assertTrue(all(e.ine != "12099" for e in result.entities))

    def test_missing_registry_municipality_blocks(self):
        result = self.catalog(good_records()[:2] + good_records()[3:])
        self.assertIn("missing_in_dataset", self.codes(result))
        self.assertIn("baseline_drift", self.codes(result))

    def test_duplicates_and_dir3_conflicts(self):
        records = good_records() + [rec("12001", "L01120099", "Alfa bis")]
        self.assertTrue({"duplicate_ine", "ine_dir3_conflict"} <= self.codes(self.catalog(records)))
        records = good_records() + [rec("12002", "L01120011", "Otro")]
        self.assertTrue({"duplicate_dir3", "ine_dir3_conflict"} <= self.codes(self.catalog(records)))
        self.assertTrue(all(e.ine not in {"12001"} for e in self.catalog(records).entities))

    def test_required_fields_missing_or_malformed(self):
        for patch in ({"dir3": None}, {"dir3": "XX1"}, {"nombre_poblacion": " "}, {"id": None}, {"ine": "99999"}, {"ine": 12001}):
            records = good_records()
            records[0] = {**records[0], **patch}
            with self.subTest(patch=patch):
                self.assertIn("invalid_record", self.codes(self.catalog(records)))

    def test_entity_type_inconsistencies(self):
        cases = [
            (rec("12001", "L01120011", "Alfa", kind="Mancomunidad"), "unknown_entity_type"),
            (rec(None, "L01120011", "Alfa"), "municipality_without_ine"),
            (rec("12001", "L01120011", "Alfa", kind="E.L. Menor"), "sub_municipal_with_ine"),
        ]
        for record, code in cases:
            with self.subTest(code=code):
                result = self.catalog([record] + good_records()[1:])
                self.assertIn(code, self.codes(result))
                self.assertTrue(result.unknown_entries)

    def test_baseline_drift_when_new_sub_municipal_entity_appears(self):
        extra = rec(None, "L04129999", "Nueva", kind="E.L. Menor")
        self.assertIn("baseline_drift", self.codes(self.catalog(good_records() + [extra])))
        self.assertTrue(self.catalog(good_records() + [extra], baseline=None).is_valid)

    def test_extra_and_personal_fields_are_not_propagated(self):
        result = self.catalog(good_records())
        dumped = json.dumps([e.as_dict() for e in result.entities], ensure_ascii=False)
        for value in EXCLUDED_EXTRAS.values():
            self.assertNotIn(str(value), dumped)
        for key in ("alcalde", "partido", "cif", "telefono", "campo_nuevo"):
            self.assertNotIn(key, dumped)

    def test_link_validation_and_documented_transform(self):
        link, reason = normalize_link("www.alfa.example")
        self.assertEqual((link.url, link.transform, link.official_value, reason), ("https://www.alfa.example", "prefix_https_scheme", "www.alfa.example", None))
        link, _ = normalize_link("http://www.alfa.example/a")
        self.assertEqual((link.url, link.transform), ("http://www.alfa.example/a", "none"))
        self.assertEqual(normalize_link(None)[0].transform, "absent")
        for bad in ("javascript:alert(1)", "ftp://a.example", "https://u:p@a.example", "no es url", "https://localhost", "a.example:99999", 5, "https://a.example/\nx"):
            with self.subTest(bad=bad):
                link, reason = normalize_link(bad)
                self.assertIsNone(link.url)
                self.assertTrue(reason)

    def test_surrounding_whitespace_is_rejected_not_trimmed(self):
        for value in (" www.alfa.example", "www.alfa.example ", "\thttps://www.alfa.example", "https://www.alfa.example\n", "www.alfa .example"):
            with self.subTest(value=value):
                link, reason = normalize_link(value)
                self.assertEqual((link.official_value, link.url, link.transform), (value, None, "rejected"))
                self.assertEqual(reason, "whitespace_or_control_characters")
        self.assertEqual(normalize_link("   ")[0].transform, "absent")

    def test_rejected_link_keeps_record_with_warning(self):
        records = good_records()
        records[0] = {**records[0], "web_ayuntamiento": "javascript:alert(1)"}
        result = self.catalog(records)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.entities[0].web.transform, "rejected")
        self.assertIn("link_rejected", {i.code for i in result.issues})

    def test_registry_loader_reads_real_local_registry(self):
        registry = load_registry_municipalities()
        self.assertEqual(len(registry), 135)


class SnapshotTests(unittest.TestCase):
    def test_provenance_and_license_metadata(self):
        snapshot = snapshot_for()
        prov = snapshot["provenance"]
        self.assertEqual(prov["consulted_at"], "2026-10-24T10:30:15Z")
        self.assertEqual(prov["source_modified_at"], "2026-06-18T07:14:44+00:00")
        self.assertNotEqual(prov["consulted_at"], prov["source_modified_at"])
        self.assertEqual(prov["license"]["declared_url"], "https://creativecommons.org/licenses/by/4.0/")
        self.assertIn("CC BY 4.0", prov["license"]["attribution_text"])
        self.assertIn("Entidad Ficticia", prov["license"]["attribution_text"])
        self.assertEqual(prov["query"]["metadata_url"], DIPCAS_DATASET_URL)
        self.assertEqual(snapshot["publication_status"], snap.PUBLICATION_STATUS)
        self.assertEqual(snapshot["summary"], {"entity_count": 4, "municipality_count": 3, "sub_municipal_count": 1, "links_valid": 7, "links_rejected": 0})
        self.assertNotIn("records", snapshot)
        self.assertNotIn("events", snapshot)

    def test_source_update_date_may_be_absent(self):
        opener = ScriptedOpener(good_records(), meta=metadata(modified=None))
        snapshot = snap.build_snapshot(DipcasTransport(opener=opener), REGISTRY, now=NOW, baseline=BASELINE)
        self.assertIsNone(snapshot["provenance"]["source_modified_at"])

    def test_missing_license_or_fields_in_metadata_blocks(self):
        for meta in (metadata(license_url=None), metadata(license_url="http://insecure.example/"), {"dataset_id": "otro", "fields": [], "metas": {}}):
            with self.subTest(), self.assertRaises(snap.SnapshotBlocked):
                snap.build_snapshot(DipcasTransport(opener=ScriptedOpener(good_records(), meta=meta)), REGISTRY, now=NOW, baseline=BASELINE)
        meta = metadata()
        meta["fields"] = [f for f in meta["fields"] if f["name"] != "dir3"]
        with self.assertRaises(snap.SnapshotBlocked):
            snap.build_snapshot(DipcasTransport(opener=ScriptedOpener(good_records(), meta=meta)), REGISTRY, now=NOW, baseline=BASELINE)

    def test_metadata_count_mismatch_blocks(self):
        opener = ScriptedOpener(good_records(), meta=metadata(total=99))
        with self.assertRaises(snap.SnapshotBlocked) as ctx:
            snap.build_snapshot(DipcasTransport(opener=opener), REGISTRY, now=NOW, baseline=BASELINE)
        self.assertIn("metadata_count_mismatch", {i.code for i in ctx.exception.issues})

    def test_territorial_conflicts_block_snapshot(self):
        with self.assertRaises(snap.SnapshotBlocked):
            snapshot_for(good_records()[:3])

    def test_serialization_is_deterministic_and_hash_ignores_consultation_time(self):
        first = snapshot_for()
        shuffled = list(reversed(good_records()))
        later = snap.build_snapshot(DipcasTransport(opener=ScriptedOpener(shuffled)), REGISTRY, now=lambda: datetime(2027, 1, 1, tzinfo=timezone.utc), baseline=BASELINE)
        self.assertEqual(first["content_hash"], later["content_hash"])
        self.assertEqual(first["entities"], later["entities"])
        self.assertEqual(snap.serialize_snapshot(first), snap.serialize_snapshot(snapshot_for()))
        self.assertTrue(snap.serialize_snapshot(first).endswith(b"}\n"))
        self.assertEqual(json.loads(snap.serialize_snapshot(first)), first)

    def test_validation_rejects_tampering(self):
        base = snapshot_for()
        tampers = {
            "hash": lambda s: s.update(content_hash="sha256:" + "0" * 64),
            "extra_key": lambda s: s["entities"][0].update(alcalde="x"),
            "status": lambda s: s.update(publication_status="published"),
            "duplicate": lambda s: s["entities"].append(dict(s["entities"][0])),
            "scheme": lambda s: s["entities"][0]["web"].update(url="javascript:alert(1)"),
        }
        for name, tamper in tampers.items():
            candidate = json.loads(json.dumps(base))
            tamper(candidate)
            with self.subTest(name), self.assertRaises(snap.SnapshotValidationError):
                snap.validate_snapshot(candidate)

    def test_link_validation_matches_normalize_link_with_recomputed_hash(self):
        tampers = {
            "credentials": {"official_value": "https://u:p@www.alfa.example", "url": "https://u:p@www.alfa.example", "transform": "none"},
            "scheme": {"official_value": "ftp://www.alfa.example", "url": "ftp://www.alfa.example", "transform": "none"},
            "invalid_host": {"official_value": "https://localhost", "url": "https://localhost", "transform": "none"},
            "https_without_host": {"official_value": "https://", "url": "https://", "transform": "none"},
            "https_empty_host_path": {"official_value": "https:///alfa", "url": "https:///alfa", "transform": "none"},
            "control_char": {"official_value": "https://www.alfa.example/\x07", "url": "https://www.alfa.example/\x07", "transform": "none"},
            "inner_space": {"official_value": "https://www.alfa .example", "url": "https://www.alfa .example", "transform": "none"},
            "trimmed_silently": {"official_value": " www.alfa.example ", "url": "https://www.alfa.example", "transform": "prefix_https_scheme"},
            "url_differs_from_official": {"official_value": "www.alfa.example", "url": "https://www.otro.example", "transform": "prefix_https_scheme"},
            "transform_mismatch": {"official_value": "www.alfa.example", "url": "https://www.alfa.example", "transform": "none"},
            "valid_link_marked_rejected": {"official_value": "www.alfa.example", "url": None, "transform": "rejected"},
            "absent_with_value": {"official_value": "www.alfa.example", "url": None, "transform": "absent"},
            "non_string_official": {"official_value": 5, "url": None, "transform": "rejected"},
        }
        for name, link in tampers.items():
            with self.subTest(name), self.assertRaises(snap.SnapshotValidationError):
                snap.validate_snapshot(resealed(snapshot_for(), lambda s: s["entities"][0].update(web=dict(link))))

    def test_recomputed_snapshot_with_coherent_links_still_validates(self):
        snap.validate_snapshot(resealed(snapshot_for(), lambda s: None))
        rejected = resealed(snapshot_for(), lambda s: s["entities"][0].update(web={"official_value": "javascript:alert(1)", "url": None, "transform": "rejected"}))
        snap.validate_snapshot(rejected)
        self.assertEqual(rejected["summary"]["links_rejected"], 1)

    def test_link_summary_must_match_entities(self):
        candidate = json.loads(json.dumps(snapshot_for()))
        candidate["summary"]["links_valid"] += 1
        with self.assertRaises(snap.SnapshotValidationError):
            snap.validate_snapshot(candidate)


def resealed(snapshot, tamper):
    """Copia sintética modificada, con resumen de enlaces y hash recalculados para aislar la comprobación de enlaces."""
    candidate = json.loads(json.dumps(snapshot))
    tamper(candidate)
    links = [e[k] for e in candidate["entities"] for k in ("web", "sede_electronica")]
    candidate["summary"]["links_valid"] = sum(1 for link in links if link["url"])
    candidate["summary"]["links_rejected"] = sum(1 for link in links if link["transform"] == "rejected")
    candidate["content_hash"] = snap.content_hash(candidate["entities"])
    return candidate


def _link_directory(link: Path, target: Path) -> None:
    """Enlace simbólico; en Windows sin privilegios, junction como equivalente."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if os.name != "nt":
            raise
    import _winapi

    _winapi.CreateJunction(str(target), str(link))


class WriteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = Path(self._tmp.name) / "out"

    def test_writes_validated_snapshot(self):
        path = snap.write_snapshot(snapshot_for(), self.out)
        self.assertEqual(path.read_bytes(), snap.serialize_snapshot(snapshot_for()))
        self.assertEqual([p.name for p in self.out.iterdir()], [snap.DEFAULT_FILENAME])

    def test_failure_preserves_previous_snapshot_and_leaves_no_temporary(self):
        path = snap.write_snapshot(snapshot_for(), self.out)
        before = path.read_bytes()
        changed = snapshot_for(good_records()[:1] + good_records()[1:])
        changed["provenance"]["consulted_at"] = "2030-01-01T00:00:00Z"
        with mock.patch("infocs.reference.dipcas_snapshot.os.replace", side_effect=OSError("disco")):
            with self.assertRaises(OSError):
                snap.write_snapshot(changed, self.out)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual([p.name for p in self.out.iterdir()], [snap.DEFAULT_FILENAME])

    def test_invalid_snapshot_is_never_written(self):
        path = snap.write_snapshot(snapshot_for(), self.out)
        before = path.read_bytes()
        broken = snapshot_for()
        broken["content_hash"] = "sha256:bad"
        with self.assertRaises(snap.SnapshotValidationError):
            snap.write_snapshot(broken, self.out)
        self.assertEqual(path.read_bytes(), before)

    def test_blocked_fetch_preserves_previous_snapshot(self):
        path = snap.write_snapshot(snapshot_for(), self.out)
        before = path.read_bytes()
        with self.assertRaises(snap.SnapshotBlocked):
            snapshot_for(good_records()[:2])
        with self.assertRaises(DipcasFetchError):
            snap.build_snapshot(DipcasTransport(opener=failing(socket.timeout())), REGISTRY, now=NOW)
        self.assertEqual(path.read_bytes(), before)

    def test_refuses_repository_data_directory_and_path_filenames(self):
        with self.assertRaises(ValueError):
            snap.write_snapshot(snapshot_for(), ROOT / "data" / "reference")
        with self.assertRaises(ValueError):
            snap.write_snapshot(snapshot_for(), self.out, filename="../x.json")
        self.assertFalse((ROOT / "data" / "reference").exists())

    def test_refuses_any_directory_inside_repository(self):
        targets = {
            "root": ROOT,
            "subdirectory": ROOT / "src" / "infocs" / "reference",
            "new_subdirectory": ROOT / "tests" / "dipcas-out-should-not-exist",
            "data": ROOT / "data",
            "data_nested": ROOT / "data" / "records" / "reference-should-not-exist",
            "dot_segments": ROOT / "data" / ".." / "data",
        }
        before = {p.name for p in ROOT.iterdir()}
        for name, target in targets.items():
            with self.subTest(name), self.assertRaises(ValueError):
                snap.write_snapshot(snapshot_for(), target)
        self.assertFalse((ROOT / "tests" / "dipcas-out-should-not-exist").exists())
        self.assertFalse((ROOT / "data" / "records" / "reference-should-not-exist").exists())
        self.assertEqual({p.name for p in ROOT.iterdir()}, before)

    def test_external_temporary_directory_is_allowed(self):
        self.assertFalse(snap._is_within(self.out.resolve(), ROOT.resolve()))
        path = snap.write_snapshot(snapshot_for(), self.out)
        self.assertTrue(path.is_file())

    def test_refuses_external_link_pointing_into_repository(self):
        for name, target in (("root", ROOT), ("data", ROOT / "data")):
            link = Path(self._tmp.name) / f"link-{name}"
            try:
                _link_directory(link, target)
            except OSError as error:
                self.skipTest(f"no se pudo crear el enlace: {error}")
            # Retirar sólo el enlace antes de limpiar el temporal: nunca recorrer el repositorio.
            self.addCleanup(os.rmdir if os.name == "nt" else os.unlink, link)
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    snap.write_snapshot(snapshot_for(), link / "snapshots")
                self.assertFalse((target / "snapshots").exists())


if __name__ == "__main__":
    unittest.main()
