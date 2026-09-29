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
Manifest can do so.

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
approval. This runner writes a Manifest only. Deriving or persisting
`SourceHealth` is deferred to OPS-C.

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
