"""Fail-closed validation of BDNS artifacts prepared by the manual Action."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from zoneinfo import ZoneInfo
from typing import Any, Iterable, Mapping

from infocs.diff.core import content_hash
from infocs.events import Event, EventStore
from infocs.fetch.bdns.ingest import BDNS_ATTRIBUTION_PATH, _attribution_preflight
from infocs.fetch.bdns.diagnostics import BDNS_ITEM_DETAIL_REASONS, BDNS_SAFE_FIELD_CLASSES
from infocs.fetch.bdns.runner import (
    BDNS_DEFAULT_OVERLAP_DAYS,
    BDNS_INCREMENTAL_SCOPE_TYPE,
    BDNS_REGION_ID,
    BDNS_TEMPORAL_POLICY_VERSION,
    BDNSRunnerStatus,
    resolve_incremental_window,
)
from infocs.manifests import (
    ManifestStore,
    RunManifest,
    SourceHealth,
    derive_source_health,
)
from infocs.models import Record, validate_record_payload
from infocs.store import RecordStore


PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_RUN_ID_RE = re.compile(r"run-v1-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_SAFE_CODE_RE = re.compile(r"[a-z0-9][a-z0-9_]{0,63}\Z")
_STATUS_EXIT = {
    BDNSRunnerStatus.COMPLETE_SUCCESS: 0,
    BDNSRunnerStatus.NO_RESULTS: 0,
    BDNSRunnerStatus.PARTIAL_SUCCESS: 2,
    BDNSRunnerStatus.SOURCE_FAILURE: 1,
    BDNSRunnerStatus.TERRITORIAL_CONTRACT_DRIFT: 1,
    BDNSRunnerStatus.PERSISTENCE_BLOCKED: 1,
    "failed": 1,
}
_MANIFEST_STATUS = {
    BDNSRunnerStatus.COMPLETE_SUCCESS: "success",
    BDNSRunnerStatus.NO_RESULTS: "success",
    BDNSRunnerStatus.PARTIAL_SUCCESS: "partial",
    BDNSRunnerStatus.SOURCE_FAILURE: "failed",
    BDNSRunnerStatus.TERRITORIAL_CONTRACT_DRIFT: "failed",
    BDNSRunnerStatus.PERSISTENCE_BLOCKED: "failed",
}
_BDNS_ROOTS = (
    "data/records/bdns/",
    "data/events/bdns/",
    "data/manifests/bdns/",
)
_HEALTH_PATH = "data/health/bdns.json"
_MADRID = ZoneInfo("Europe/Madrid")
_SCHEMAS = {
    "data/records/bdns/": "record.schema.json",
    "data/events/bdns/": "event.schema.json",
    "data/manifests/bdns/": "run-manifest.schema.json",
    "data/health/bdns.json": "source-health.schema.json",
}


class WorkflowSafetyError(ValueError):
    """BDNS result or artifact is outside the reviewed publication contract."""


def scheduled_through_date(now: datetime | None = None) -> date:
    """Return yesterday using the Europe/Madrid calendar, never the runner's UTC date."""
    current = now if now is not None else datetime.now(_MADRID)
    if current.tzinfo is None or current.utcoffset() is None:
        raise WorkflowSafetyError("scheduled_clock_must_be_timezone_aware")
    return current.astimezone(_MADRID).date() - timedelta(days=1)


def resolve_scheduled_parameters(
    manifests: Iterable[RunManifest],
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Fail closed without a current successful incremental checkpoint; do not bootstrap."""
    through_date = scheduled_through_date(now)
    if BDNS_REGION_ID != 56:
        raise WorkflowSafetyError("territorial_scope_changed")
    checkpoint_candidates = tuple(
        item for item in manifests
        if item.source_id == "bdns"
        and item.status.value == "success"
        and item.requested_scope.type == BDNS_INCREMENTAL_SCOPE_TYPE
        and f"region={BDNS_REGION_ID}" in item.requested_scope.value.split(";")
        and f"temporal_policy={BDNS_TEMPORAL_POLICY_VERSION}" in item.requested_scope.value.split(";")
    )
    try:
        resolve_incremental_window(
            checkpoint_candidates,
            through_date=through_date,
            initial_from_date=None,
            overlap_days=BDNS_DEFAULT_OVERLAP_DAYS,
        )
    except (TypeError, ValueError) as error:
        raise WorkflowSafetyError("compatible_incremental_checkpoint_required") from error
    return {"run_class": "incremental_update", "through_date": through_date.isoformat()}


def write_scheduled_parameters(
    github_output: str | Path,
    manifests: Iterable[RunManifest],
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """Validate schedule parameters and write only safe GitHub step outputs."""
    parameters = resolve_scheduled_parameters(manifests, now=now)
    output_path = Path(github_output)
    try:
        with output_path.open("a", encoding="utf-8", newline="\n") as output:
            output.write(f"run_class={parameters['run_class']}\n")
            output.write("from_date=\n")
            output.write(f"through_date={parameters['through_date']}\n")
            output.write("trigger=schedule\n")
    except OSError as error:
        raise WorkflowSafetyError("github_output_write_failed") from error
    return parameters


def validate_inputs(run_class: str, from_date: str, through_date: str) -> None:
    """Validate the manual scope locally, before the runner can make requests."""
    allowed = {"discovery", "incremental_update", "complete_scope"}
    if run_class not in allowed:
        raise WorkflowSafetyError("invalid_run_class")
    start = _parse_iso_date(from_date, "invalid_from_date")
    end = _parse_iso_date(through_date, "invalid_through_date")
    if start > end:
        raise WorkflowSafetyError("date_range_reversed")
    if BDNS_REGION_ID != 56:
        raise WorkflowSafetyError("territorial_scope_changed")


def validate_runner_result(stdout_text: str, stderr_text: str, exit_code: int) -> dict[str, Any]:
    """Read only machine JSON and check it agrees with the runner exit code."""
    if isinstance(exit_code, bool) or exit_code not in {0, 1, 2}:
        raise WorkflowSafetyError("invalid_runner_exit_code")
    if not isinstance(stdout_text, str) or not isinstance(stderr_text, str):
        raise WorkflowSafetyError("invalid_runner_output")
    if stdout_text.strip():
        serialized = stdout_text.strip()
    elif exit_code == 1 and stderr_text.strip():
        # Early, terminal runner failures use a safe JSON diagnostic on stderr.
        # Human-readable argparse output is deliberately not parsed or accepted.
        serialized = stderr_text.strip()
    else:
        raise WorkflowSafetyError("runner_result_missing")
    try:
        result = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise WorkflowSafetyError("runner_result_not_json") from error
    if not isinstance(result, dict):
        raise WorkflowSafetyError("runner_result_not_object")
    required = {"run_id", "source_id", "status", "error_code"}
    diagnostic_keys = {"safe_detail_reason", "failure_position", "safe_field_class"}
    optional = {"metrics", "request_count", "http_statuses"} | diagnostic_keys
    if not required.issubset(result) or set(result) - required - optional:
        raise WorkflowSafetyError("runner_result_shape_invalid")
    if result.get("source_id") != "bdns" or not isinstance(result.get("run_id"), str) or not _RUN_ID_RE.fullmatch(result["run_id"]):
        raise WorkflowSafetyError("runner_result_identity_invalid")
    status = result.get("status")
    if not isinstance(status, str) or status not in _STATUS_EXIT or _STATUS_EXIT[status] != exit_code:
        raise WorkflowSafetyError("runner_status_exit_mismatch")
    error_code = result.get("error_code")
    if error_code is not None and (not isinstance(error_code, str) or not _SAFE_CODE_RE.fullmatch(error_code)):
        raise WorkflowSafetyError("runner_error_code_invalid")
    if status in {BDNSRunnerStatus.COMPLETE_SUCCESS, BDNSRunnerStatus.NO_RESULTS}:
        if error_code is not None:
            raise WorkflowSafetyError("successful_runner_has_error_code")
    elif not error_code:
        raise WorkflowSafetyError("non_success_runner_missing_error_code")
    if diagnostic_keys & result.keys():
        if (not diagnostic_keys.issubset(result) or error_code != "item_ingestion_failure"
            or status != BDNSRunnerStatus.SOURCE_FAILURE):
            raise WorkflowSafetyError("runner_failure_diagnostic_shape_invalid")
        detail = result["safe_detail_reason"]
        field_class = result["safe_field_class"]
        position = result["failure_position"]
        if not isinstance(detail, str) or detail not in BDNS_ITEM_DETAIL_REASONS:
            raise WorkflowSafetyError("runner_safe_detail_reason_invalid")
        if not isinstance(field_class, str) or field_class not in BDNS_SAFE_FIELD_CLASSES:
            raise WorkflowSafetyError("runner_safe_field_class_invalid")
        if isinstance(position, bool) or not isinstance(position, int) or position < 1:
            raise WorkflowSafetyError("runner_failure_position_invalid")
    if "metrics" in result:
        metrics = result["metrics"]
        if not isinstance(metrics, dict) or any(
            not isinstance(name, str)
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for name, value in metrics.items()
        ):
            raise WorkflowSafetyError("runner_metrics_invalid")
    if "request_count" in result:
        count = result["request_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise WorkflowSafetyError("runner_request_count_invalid")
    if "http_statuses" in result:
        statuses = result["http_statuses"]
        if not isinstance(statuses, list) or any(
            isinstance(code, bool) or not isinstance(code, int) or not 100 <= code <= 599
            for code in statuses
        ):
            raise WorkflowSafetyError("runner_http_statuses_invalid")
    if exit_code != 1 and not {"metrics", "request_count", "http_statuses"}.issubset(result):
        raise WorkflowSafetyError("runner_result_incomplete")
    return result


def write_runner_summary(path: str | Path, result: Mapping[str, Any], exit_code: int) -> None:
    """Validate again, then expose only a closed diagnostic projection."""
    safe = validate_runner_result(json.dumps(dict(result)), "", exit_code)
    lines = ["## BDNS collection result", "", f"Status: `{safe['status']}`"]
    if "failure_position" in safe:
        lines.extend([
            "Primary error: `item_ingestion_failure`",
            f"Safe detail reason: `{safe['safe_detail_reason']}`",
            f"Failure position: {safe['failure_position']}",
            f"Safe field class: `{safe['safe_field_class']}`",
        ])
    with Path(path).open("a", encoding="utf-8", newline="\n") as summary:
        summary.write("\n".join(lines) + "\n")


def validate_changed_entries(entries: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """Allow only added/modified BDNS JSON artifacts; all deletes fail closed."""
    accepted: set[tuple[str, str]] = set()
    for status, raw_path in entries:
        if status not in {"A", "M"}:
            raise WorkflowSafetyError("artifact_change_type_forbidden")
        path = _validate_bdns_path(raw_path)
        accepted.add((status, path))
    return tuple(sorted(accepted, key=lambda item: item[1]))


def validate_generated_artifacts(
    repo_root: str | Path,
    entries: Iterable[tuple[str, str]],
    result: Mapping[str, Any],
) -> tuple[str, ...]:
    """Validate changed BDNS artifacts against schemas, Stores and each other."""
    root = Path(repo_root).resolve()
    accepted = validate_changed_entries(entries)
    paths = tuple(path for _status, path in accepted)
    changed_records: dict[str, Record] = {}
    changed_events: list[Event] = []
    changed_manifests: list[RunManifest] = []
    health_changed = False

    for _status, relative in accepted:
        path = (root / Path(*PurePosixPath(relative).parts)).resolve()
        if root not in path.parents or not path.is_file():
            raise WorkflowSafetyError("artifact_missing_or_outside_repo")
        payload = _read_json(path)
        _validate_schema(root / "schemas" / _SCHEMAS[_schema_key(relative)], payload)
        if relative.startswith("data/records/bdns/"):
            record = Record.from_dict(payload)
            validate_record_payload(payload)
            if record.source.id != "bdns" or record.technical.content_hash != content_hash(payload):
                raise WorkflowSafetyError("record_source_or_hash_invalid")
            if path != RecordStore(root / "data" / "records").path_for("bdns", record.id).resolve():
                raise WorkflowSafetyError("record_path_noncanonical")
            if path.read_text(encoding="utf-8") != record.canonical_json() + "\n":
                raise WorkflowSafetyError("record_serialization_noncanonical")
            changed_records[record.id] = record
        elif relative.startswith("data/events/bdns/"):
            event = Event.from_dict(payload)
            if event.source_id != "bdns":
                raise WorkflowSafetyError("event_source_invalid")
            if path != EventStore(root / "data" / "events").path_for("bdns", event.record_id, event.event_id).resolve():
                raise WorkflowSafetyError("event_path_noncanonical")
            canonical = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
            if path.read_text(encoding="utf-8") != canonical:
                raise WorkflowSafetyError("event_serialization_noncanonical")
            changed_events.append(event)
        elif relative.startswith("data/manifests/bdns/"):
            manifest = RunManifest.from_mapping(payload)
            if manifest.source_id != "bdns":
                raise WorkflowSafetyError("manifest_source_invalid")
            if path != ManifestStore(root / "data" / "manifests").path_for(manifest).resolve():
                raise WorkflowSafetyError("manifest_path_noncanonical")
            if path.read_text(encoding="utf-8") != manifest.canonical_json() + "\n":
                raise WorkflowSafetyError("manifest_serialization_noncanonical")
            changed_manifests.append(manifest)
        else:
            health = SourceHealth.from_mapping(payload)
            if relative != _HEALTH_PATH or health.source_id != "bdns":
                raise WorkflowSafetyError("health_source_or_path_invalid")
            canonical = json.dumps(health.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            if path.read_text(encoding="utf-8") != canonical:
                raise WorkflowSafetyError("health_serialization_noncanonical")
            health_changed = True

    if changed_records and not _attribution_preflight(root / "data" / "records" / "bdns" / "README.md"):
        raise WorkflowSafetyError("attribution_preflight_failed")

    record_store = RecordStore(root / "data" / "records")
    for event in changed_events:
        record = record_store.get(event.record_id, source_id="bdns")
        if (
            record is None
            or event.content_hash != record.technical.content_hash
            or event.official_id != record.source.official_id
        ):
            raise WorkflowSafetyError("event_record_binding_invalid")

    manifest_store = ManifestStore(root / "data" / "manifests")
    current_result = dict(result)
    # A terminal generic diagnostic can occur before a RunManifest exists.
    has_full_runner_result = "metrics" in current_result
    if has_full_runner_result:
        matching = [item for item in changed_manifests if item.run_id == current_result["run_id"]]
        if len(matching) != 1:
            raise WorkflowSafetyError("run_manifest_missing_or_ambiguous")
        expected_status = _MANIFEST_STATUS.get(current_result["status"])
        if expected_status is None or matching[0].status.value != expected_status:
            raise WorkflowSafetyError("run_manifest_status_mismatch")
        if matching[0].metrics.to_dict() != current_result["metrics"]:
            raise WorkflowSafetyError("run_manifest_metrics_mismatch")
    if health_changed or changed_manifests:
        health_path = root / "data" / "health" / "bdns.json"
        if not health_path.is_file():
            raise WorkflowSafetyError("health_missing_after_manifest")
        try:
            actual_health = SourceHealth.from_mapping(_read_json(health_path))
            expected_health = derive_source_health(manifest_store.list_source("bdns"), source_id="bdns")
        except Exception as error:
            raise WorkflowSafetyError("health_derivation_failed") from error
        if actual_health.to_dict() != expected_health.to_dict():
            raise WorkflowSafetyError("health_manifest_history_mismatch")
    if health_changed and not changed_manifests:
        raise WorkflowSafetyError("health_without_manifest_forbidden")
    return paths


def stage_validated_artifacts(repo_root: str | Path, result: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate the complete run diff, stage only its allowed BDNS JSON paths."""
    root = Path(repo_root).resolve()
    entries = _working_tree_entries(root)
    paths = validate_generated_artifacts(root, entries, result)
    for relative in paths:
        _git(root, "add", "--", relative)
    staged = _git_name_status(root, "diff", "--cached", "--name-status", "-z", "HEAD")
    staged_paths = tuple(path for _status, path in validate_changed_entries(staged))
    if set(staged_paths) != set(paths):
        raise WorkflowSafetyError("staged_path_set_mismatch")
    validate_generated_artifacts(root, staged, result)
    if _git(root, "diff", "--quiet", check=False).returncode != 0:
        raise WorkflowSafetyError("unstaged_changes_remain")
    if _git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout:
        raise WorkflowSafetyError("untracked_files_remain")
    return staged_paths


def validate_remote_race(repo_root: str | Path, base_sha: str, remote_ref: str = "origin/main") -> tuple[str, ...]:
    """Permit only linear remote races made exclusively of verified BOE data commits."""
    root = Path(repo_root).resolve()
    if _git(root, "merge-base", "--is-ancestor", base_sha, remote_ref, check=False).returncode != 0:
        raise WorkflowSafetyError("remote_not_descendant_of_base")
    commits = _git(root, "rev-list", "--reverse", f"{base_sha}..{remote_ref}").stdout.decode("ascii").splitlines()
    for commit in commits:
        parents = _git(root, "rev-list", "--parents", "-n", "1", commit).stdout.decode("ascii").split()
        if len(parents) != 2:
            raise WorkflowSafetyError("remote_merge_commit_forbidden")
        subject = _git(root, "show", "-s", "--format=%s", commit).stdout.decode("utf-8").strip()
        entries = _git_name_status(root, "diff-tree", "--root", "--no-commit-id", "--name-status", "-z", "--no-renames", commit)
        validate_remote_boe_commit(subject, entries)
    return tuple(commits)


def validate_remote_boe_commit(subject: str, entries: Iterable[tuple[str, str]]) -> tuple[str, ...]:
    """Verify a remote commit by both its automatic BOE label and exact data paths."""
    if not isinstance(subject, str) or not re.fullmatch(r"data\(boe\): collect \d{4}-\d{2}-\d{2}", subject):
        raise WorkflowSafetyError("remote_commit_not_automatic_boe_data")
    changed = tuple(entries)
    if not changed or any(status not in {"A", "M"} or not _is_allowed_boe_data_path(path) for status, path in changed):
        raise WorkflowSafetyError("remote_commit_paths_not_boe_data_only")
    return tuple(sorted(path for _status, path in changed))


def validate_committed_artifacts(repo_root: str | Path, commit: str, result: Mapping[str, Any]) -> tuple[str, ...]:
    """Revalidate the BDNS commit after a compatible BOE rebase, without refetching BDNS."""
    root = Path(repo_root).resolve()
    entries = _git_name_status(root, "diff-tree", "--no-commit-id", "--name-status", "-z", "--no-renames", "-r", commit)
    accepted = validate_changed_entries(entries)
    paths = tuple(path for _status, path in accepted)
    if not paths:
        raise WorkflowSafetyError("bdns_commit_has_no_artifacts")
    validate_generated_artifacts(root, accepted, result)
    return paths


def validate_staged_entries(entries: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """Public pure helper used by tests and by the workflow stage operation."""
    return validate_changed_entries(entries)


def _working_tree_entries(root: Path) -> tuple[tuple[str, str], ...]:
    entries = list(_git_name_status(root, "diff", "--name-status", "-z", "HEAD"))
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout.decode("utf-8").split("\x00")
    entries.extend(("A", path) for path in untracked if path)
    return tuple(entries)


def _git_name_status(root: Path, *args: str) -> tuple[tuple[str, str], ...]:
    raw = _git(root, *args).stdout.decode("utf-8")
    fields = raw.split("\x00")
    entries: list[tuple[str, str]] = []
    index = 0
    while index < len(fields) - 1:
        status = fields[index]
        index += 1
        if status.startswith(("R", "C")):
            raise WorkflowSafetyError("rename_or_copy_forbidden")
        if index >= len(fields):
            raise WorkflowSafetyError("git_name_status_malformed")
        entries.append((status, fields[index]))
        index += 1
    return tuple(entries)


def _validate_bdns_path(raw_path: str) -> str:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path or "\x00" in raw_path:
        raise WorkflowSafetyError("artifact_path_invalid")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise WorkflowSafetyError("artifact_path_traversal")
    candidate = path.as_posix()
    if candidate != raw_path:
        raise WorkflowSafetyError("artifact_path_noncanonical")
    if candidate == _HEALTH_PATH:
        return candidate
    if path.suffix.lower() != ".json" or not any(candidate.startswith(root) for root in _BDNS_ROOTS):
        raise WorkflowSafetyError("artifact_path_not_allowlisted")
    parts = path.parts
    if candidate.startswith("data/records/bdns/") and len(parts) != 4:
        raise WorkflowSafetyError("record_layout_invalid")
    if candidate.startswith("data/events/bdns/") and len(parts) != 5:
        raise WorkflowSafetyError("event_layout_invalid")
    if candidate.startswith("data/manifests/bdns/") and len(parts) != 6:
        raise WorkflowSafetyError("manifest_layout_invalid")
    return candidate


def _is_allowed_boe_data_path(raw_path: str) -> bool:
    try:
        path = PurePosixPath(raw_path)
    except TypeError:
        return False
    candidate = path.as_posix()
    if path.is_absolute() or candidate != raw_path or "\\" in raw_path or path.suffix.lower() != ".json":
        return False
    if candidate == "data/health/boe.json" or candidate == "data/review/boe/pending.json":
        return True
    parts = path.parts
    return (
        candidate.startswith("data/records/boe/") and len(parts) == 4
    ) or (
        candidate.startswith("data/events/boe/") and len(parts) == 5
    ) or (
        candidate.startswith("data/manifests/boe/") and len(parts) == 6
    )


def _parse_iso_date(value: str, error_code: str) -> date:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise WorkflowSafetyError(error_code)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise WorkflowSafetyError(error_code) from error


def _schema_key(relative: str) -> str:
    if relative == _HEALTH_PATH:
        return _HEALTH_PATH
    return next(prefix for prefix in _BDNS_ROOTS if relative.startswith(prefix))


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkflowSafetyError("artifact_json_invalid") from error


def _validate_schema(schema_path: Path, payload: Any) -> None:
    try:
        from jsonschema import Draft202012Validator, FormatChecker

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    except Exception as error:
        raise WorkflowSafetyError("artifact_schema_invalid") from error


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(["git", *args], cwd=root, check=False, capture_output=True)
    except OSError as error:
        raise WorkflowSafetyError("git_command_unavailable") from error
    if check and result.returncode != 0:
        raise WorkflowSafetyError("git_operation_failed")
    return result


def _read_text_file(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise WorkflowSafetyError("workflow_result_file_missing") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validador fail-closed para artefactos de la Action BDNS.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inputs = subparsers.add_parser("validate-inputs")
    inputs.add_argument("--run-class", required=True)
    inputs.add_argument("--from-date", required=True)
    inputs.add_argument("--through-date", required=True)
    result = subparsers.add_parser("validate-result")
    result.add_argument("--stdout-file", required=True)
    result.add_argument("--stderr-file", required=True)
    result.add_argument("--exit-code", required=True, type=int)
    result.add_argument("--github-summary")
    stage = subparsers.add_parser("stage")
    stage.add_argument("--result-file", required=True)
    race = subparsers.add_parser("validate-remote")
    race.add_argument("--base-sha", required=True)
    race.add_argument("--remote-ref", default="origin/main")
    commit = subparsers.add_parser("validate-commit")
    commit.add_argument("--commit", required=True)
    commit.add_argument("--result-file", required=True)
    scheduled = subparsers.add_parser("prepare-scheduled")
    scheduled.add_argument("--github-output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-inputs":
            validate_inputs(args.run_class, args.from_date, args.through_date)
        elif args.command == "prepare-scheduled":
            write_scheduled_parameters(
                args.github_output,
                ManifestStore(PROJECT_ROOT / "data" / "manifests").list_source("bdns"),
            )
        elif args.command == "validate-result":
            result = validate_runner_result(
                _read_text_file(args.stdout_file),
                _read_text_file(args.stderr_file),
                args.exit_code,
            )
            if args.github_summary:
                write_runner_summary(args.github_summary, result, args.exit_code)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        elif args.command == "stage":
            result = json.loads(_read_text_file(args.result_file))
            paths = stage_validated_artifacts(PROJECT_ROOT, result)
            print(json.dumps({"staged_count": len(paths)}, separators=(",", ":")))
        elif args.command == "validate-remote":
            commits = validate_remote_race(PROJECT_ROOT, args.base_sha, args.remote_ref)
            print(json.dumps({"compatible_boe_commits": len(commits)}, separators=(",", ":")))
        elif args.command == "validate-commit":
            result = json.loads(_read_text_file(args.result_file))
            paths = validate_committed_artifacts(PROJECT_ROOT, args.commit, result)
            print(json.dumps({"validated_count": len(paths)}, separators=(",", ":")))
        else:  # pragma: no cover - argparse constrains commands
            raise WorkflowSafetyError("unknown_command")
    except Exception as error:
        code = error.args[0] if isinstance(error, WorkflowSafetyError) and error.args else "validation_failed"
        safe_code = code if isinstance(code, str) and _SAFE_CODE_RE.fullmatch(code) else "validation_failed"
        print(f"bdns_workflow_safety:{safe_code}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by Actions
    raise SystemExit(main())
