# BDNS productive runner contract — v1

The source-specific runner is invoked as `python -m infocs.fetch.bdns.runner`.
It supports three declared scopes: `discovery`, `incremental_update`, and
`complete_scope`. Every run requires a closed date range; an incremental run
uses the last successful incremental Manifest and its configured overlap, or
requires an explicit initial date when no compatible checkpoint exists.

## Completeness and limits

The runner requests pages serially, with `pageSize=50`, at most 5 data pages,
250 details, and a 600-second wall-clock budget. These are InfoCs safeguards,
not SNPSAP limits. A final control read checks that totals and first-page
identities still agree; it is an additional integrity request, not a sixth
data page. The time budget is checked between requests and after the control
read. An in-flight synchronous request is not interrupted; if it returns after
the deadline, the run is partial, not complete.

`complete_success` requires all pages and details in the declared scope,
stable page/element totals, unique `numeroConvocatoria` values, the expected
accumulated count, a coherent final control read, and no exhausted budget.
An empty scope is `no_results` only when the API totals confirm zero. A budget
exhaustion is `partial_success` with Manifest `partial` and
`error_summary=run_budget_exhausted`; drift or invalid source data is partial
or failed according to the failing contract. Partial/failed runs never advance
the incremental checkpoint. Only a successful compatible incremental
Manifest can do so; `discovery` and `complete_scope` do not become a daily
incremental watermark automatically.

## Persistence and publication

The productive runner always requires `EventStore` for create/update; the
legacy single-item ingestion compatibility path that can defer an Event is
not used here. `no_change` creates no Event. Privacy, source eligibility,
BDNS metadata publication, attribution, and Record/Event preflights remain
mandatory. No manual BOE Publication Review is used.

Manifest status mapping is `complete_success`/`no_results` → `success`,
`partial_success` → `partial`, and source/contract/persistence failure →
`failed`. The aggregate `publication_approved` counter means that a Record
passed the BDNS source-specific metadata publication policy; it is not a human
approval. The runner writes the Manifest first, then derives and atomically
writes `data/health/bdns.json` (or the injected test path) from BDNS Manifest
history. Health reflects collection outcomes, not whether new Records arrived
or whether reuse permits publication.

## CLI contract for automation

For each completed run, stdout contains exactly one compact JSON result with
run id, source id, status, safe aggregate metrics, request count, HTTP status
codes, and a stable error code when applicable. It does not contain titles,
authority labels, identifiers for individual calls, URLs, or payloads.
Unexpected invocation/observability exceptions emit only a generic safe error
object to stderr.

Exit codes are stable: `0` for `complete_success` and `no_results`, `2` for
`partial_success`, and `1` for source, contract, persistence, invocation, or
observability failure. The manual workflow preserves and validates run
artifacts before propagating a nonzero collection result. Its full publication
contract is in [AUTOMATION_CONTRACT.md](AUTOMATION_CONTRACT.md); no schedule is
implemented.

## Workflow artifact handling

The manual workflow captures both the process exit code and the runner's stdout
JSON as machine-readable values. It must branch on the JSON `status` and exit
code, never parse human-readable console text. A `partial_success` run has
valid, publishable observations and safe Manifest/Health observability, but is
not a complete execution: validate and publish only its valid canonical
artifacts, keep the checkpoint unchanged, then propagate the partial outcome
as a non-successful workflow result. The runner writes Manifest before Health;
if Manifest writing fails, it must not synthesize Health, and if Health writing
fails the command exits `1` as an observability failure.

The only BDNS data paths eligible for staging are:

- `data/records/bdns/**/*.json`
- `data/events/bdns/**/*.json`
- `data/manifests/bdns/**/*.json`
- `data/health/bdns.json`

No arbitrary additions, raw payloads, documents, or review-queue files are
eligible. Validate schemas, canonical paths, Record/Event integrity, attribution,
and the complete changed-path allowlist before staging.

Before publishing, capture the base SHA and fetch `origin/main`. A race may be
rebased only when every remote commit is a compatible `data(boe)` update and
the remote diff has no BDNS paths. Any BDNS change, unexpected code/config/schema/
workflow change, or conflict aborts publication. Never force-push. After a
compatible rebase, revalidate the combined generated artifacts before a normal
push. The workflow is manual-only; no schedule or cron is configured.

## Temporal scope and absence

`fechaDesde`/`fechaHasta` are an explicitly versioned, provisional temporal
policy based on the observed association with `fechaRecepcion`; they are not
described as publication-date filters, and the official semantic link remains
unconfirmed. The API has no modification cursor or stable snapshot guarantee,
so v1 accepts that retrospective corrections may be missed between overlapping
windows and periodic closed-scope revalidation.

OPS-B never emits `missing_from_source`, withdrawal, or reappeared transitions.
A successful enumeration does not authorize absence reconciliation; partial or
failed runs do not advance a checkpoint. No workflow or schedule is part of
this contract.
