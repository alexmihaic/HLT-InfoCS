"""Diagnósticos del workflow, sin invocar migración, Stores ni red."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/bdns-v1-v2-migration.yml"
COUNTS = (
    "inventory_count", "fresh_detail_count", "summary_resolved_count",
    "v1_match_count", "v2_prepared_count", "privacy_allowed_count",
    "publication_approved_count", "authorization_count", "evidence_count",
    "request_count",
)
KEYS = {"status", "migration_id", *COUNTS, "safe_reason"}


def fixture(status="blocked"):
    return {
        "status": status,
        "migration_id": "bdns-v1-v2-11111111-1111-4111-8111-111111111111",
        **{key: 32 for key in COUNTS},
        "request_count": 128,
        "safe_reason": "migration_v1_source_drift" if status == "blocked" else None,
    }


class BDNSMigrationWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.code = re.search(r"          python - <<'PY'\n(.*?)\n          PY\n", cls.workflow, re.S).group(1)
        cls.code = "\n".join(line[10:] for line in cls.code.splitlines())

    def diagnose(self, payload, rc=1, *, raw=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            if payload is not None:
                (root / "bdns-migration-result.json").write_text(payload if raw else json.dumps(payload), encoding="utf-8")
            env = dict(os.environ, RUNNER_TEMP=temporary, PREPARE_RC=str(rc),
                       GITHUB_OUTPUT=str(root / "outputs"), GITHUB_STEP_SUMMARY=str(root / "summary"))
            process = subprocess.run([sys.executable, "-c", self.code], env=env,
                                     capture_output=True, text=True, check=False)
            outputs = (root / "outputs").read_text(encoding="utf-8")
            summary = (root / "summary").read_text(encoding="utf-8")
            return process, outputs, summary

    def test_capture_restore_diagnose_then_original_exit(self):
        step = self.workflow.split("id: prepare", 1)[1].split("- name: Materialize", 1)[0]
        parts = ("set +e", "migration prepare", "prepare_rc=$?", "set -e",
                 "python - <<'PY'", 'exit "$prepare_rc"')
        positions = [step.index(part) for part in parts]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('echo "sha=$base_sha" >> "$GITHUB_OUTPUT"', step)
        self.assertNotIn("continue-on-error", self.workflow)

    def test_blocked_safe_result_then_failure_is_preserved(self):
        process, outputs, summary = self.diagnose(fixture())
        self.assertEqual(process.returncode, 0)  # Diagnostics succeed; shell still exits prepare_rc=1.
        lines = process.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("BDNS_MIGRATION_SAFE_RESULT="))
        result = json.loads(lines[0].split("=", 1)[1])
        self.assertEqual(set(result), KEYS)
        self.assertEqual(result["safe_reason"], "migration_v1_source_drift")
        self.assertIn("prepared=false\n", outputs)
        self.assertIn("status=blocked\n", outputs)
        self.assertIn("request_count=128\n", outputs)
        self.assertIn("Status: blocked", summary)
        self.assertIn("Requests: 128", summary)
        self.assertIn('exit "$prepare_rc"', self.workflow)

    def test_prepared_and_already_migrated_outputs(self):
        for status, expected in (("prepared", "true"), ("already_migrated", "false")):
            with self.subTest(status=status):
                process, outputs, _ = self.diagnose(fixture(status), rc=0)
                self.assertEqual(process.returncode, 0)
                self.assertIn(f"prepared={expected}\n", outputs)

    def test_materialize_guard_unchanged(self):
        self.assertIn("id: publish\n        if: steps.prepare.outputs.prepared == 'true'", self.workflow)
        self.assertNotIn("always()", self.workflow)

    def test_extra_source_fields_never_forwarded(self):
        payload = fixture()
        payload.update(batch={"title": "PRIVATE_SOURCE_SENTINEL"}, official_id="PRIVATE_SOURCE_SENTINEL")
        process, outputs, summary = self.diagnose(payload)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", process.stdout + process.stderr + outputs + summary)
        self.assertEqual(set(json.loads(process.stdout.split("=", 1)[1])), KEYS)
        self.assertNotIn("migration_id", summary)

    def test_missing_empty_or_invalid_json_fail_closed(self):
        for raw in (None, "", "{invalid", "[]", "null"):
            with self.subTest(raw=raw):
                process, outputs, summary = self.diagnose(raw, raw=True)
                self.assertEqual(process.returncode, 1)
                self.assertIn("migration_safe_result_invalid", process.stdout + summary)
                self.assertIn("prepared=false\n", outputs)
                self.assertEqual(process.stderr, "")

    def test_unsafe_shapes_fail_without_echoing_values(self):
        mutations = (
            {"status": "PRIVATE_SOURCE_SENTINEL"},
            {"migration_id": "PRIVATE_SOURCE_SENTINEL\n"},
            {"safe_reason": "migration_PRIVATE_SOURCE_SENTINEL"},
            {"inventory_count": True}, {"request_count": -1},
            {"safe_reason": {"title": "PRIVATE_SOURCE_SENTINEL"}},
            {"v1_match_count": "PRIVATE_SOURCE_SENTINEL"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                process, outputs, summary = self.diagnose(dict(fixture(), **mutation))
                self.assertEqual(process.returncode, 1)
                self.assertNotIn("PRIVATE_SOURCE_SENTINEL", process.stdout + process.stderr + outputs + summary)
                self.assertIn("migration_safe_result_invalid", process.stdout)

    def test_missing_required_field_fail_closed(self):
        payload = fixture()
        del payload["request_count"]
        process, outputs, _ = self.diagnose(payload)
        self.assertEqual(process.returncode, 1)
        self.assertIn("prepared=false\n", outputs)

    def test_status_exit_contradiction_fail_closed(self):
        for status, rc in (("prepared", 1), ("already_migrated", 1), ("blocked", 0), ("blocked", 2)):
            with self.subTest(status=status, rc=rc):
                process, outputs, _ = self.diagnose(fixture(status), rc=rc)
                self.assertEqual(process.returncode, 1)
                self.assertIn("migration_safe_result_invalid", process.stdout)
                self.assertIn("prepared=false\n", outputs)


if __name__ == "__main__":
    unittest.main()
