# BDNS v1→v2 baseline migration — 10B-D1

Tooling offline implementado; **cutover no ejecutado**. D2 requerirá autorización
de ejecución separada. Nada aquí permite backfill ni ampliar el corpus.

## 1. Purpose

Preservar identidad e historia al enriquecer la representación canónica. No es
un cambio administrativo: cero create/update Event, cero reescritura histórica,
cero RunManifest de colección o Health artificial. Gates/hash v2 siguen los
contratos [canónico](CANONICAL_ENRICHMENT_CONTRACT.md) y
[de enrichment](ENRICHMENT_GATE_CONTRACT.md).

## 2. Fresh-v1 reconstruction

`migration.collect_fresh_observation` consulta sólo códigos del inventory.
Se usa el filtro **documentado** `numeroConvocatoria`, no se presupone que sea
exacto: todas sus páginas se validan y se resuelve un único summary por igualdad
de código. No reutiliza summary/authority del Record persistido.

Secuencia por código: detail → search page 0 (pageSize 50, order
numeroConvocatoria asc) → restantes páginas necesarias → control search page 0
→ segundo detail de control. Totales/offsets/flags/acumulado/IDs únicos coherentes,
summary exacto único, primera página de control igual y segundo detail igual.
Cualquier fallo/drift/ambigüedad/budget aborta el batch. IDs incidentales del
search no originan nuevos Records ni detalles adicionales.

No agrupar por fechaRecepcion: fechaDesde/fechaHasta tienen semántica provisional
y esa agrupación podría omitir un summary. El lookup por código elimina esa
dependencia. No presupone fechaRecepcion obligatoria. No hay snapshot SNPSAP:
controles detectan deriva observable, no garantizan un snapshot transaccional ni
detectan cambios transitorios que se reviertan entre lecturas.

Dependencias v1 verificadas en normalize: detail aporta código, título/fallback,
jerarquía/nombre, regiones/territorialidad y fecha de un extracto inequívoco;
summary aporta Código BDNS para el join y codigoInvente para identity de authority.
No deducir codigoInvente desde detail/Record. Timestamps son InfoCs.

Fresh summary+detail → normalize_bdns_detail → finalize v1. Se exige misma
identidad, source/official_id, identity_strategy y **hash v1 exacto**. La igualdad
se refiere a la proyección material v1 aprobada; no amplía sus exclusiones
históricas de authority/category/geography. v2 incorpora nuevos campos
materiales sin afirmar qué valores tuvieron antes.

## 3. Inventory and drift

`inventory_for_migration`: todos los JSON en RecordStore/bdns, schema/hash,
serialización/path canónicos, grants.call y official_id. JSON inesperados,
symlinks, versiones mixtas o evidencia incompleta fallan cerrado. README no es
un Record. No lista hardcoded ni nuevos IDs desde search.

Sin marker: sólo v1 sin source_data/evidencia. Drift material frente a fresh v1
→ `migration_v1_source_drift`, abort global, sin Events del migrador. Resolver
primero mediante el pipeline v1 y autorizar un nuevo intento posteriormente.

## 4. V2 preparation and completeness

Tras demostrar equivalencia de **todos** los v1, reutiliza
prepare_bdns_enriched_record: normalize v2, finalize, Privacy, Source ELIGIBLE,
PUBLISHABLE_METADATA, authorization y Store validation. Conserva id/source/
official_id/detected_at. last_checked_at es observación actual y no entra en hash.
source_data significa estado observado ahora, no estado reconstruido del pasado.

Se requieren N inventories = N detalles únicos validados = N summaries resueltos
= N v1 equivalentes = N v2 = N Privacy ALLOW = N publicaciones autorizadas
= N authorizations = N evidencias. Un fallo devuelve status blocked y ningún batch.
Output JSON explícito excluye el batch y todo payload: migration_id, counts,
request_count y safe_reason. Un safe_reason es código estático, nunca valores.
Para un bloqueo de preflight se conserva el motivo principal estable y se añade
`safe_detail_reason` opcional, limitado a los códigos estáticos reales del
enrichment mediante allowlist cerrada, más `failure_position` opcional (entero
1-based del inventory de ese checkout). No son identificadores fuente. El
workflow valida/proyecta ambos en logs y Step Summary antes de propagar exit 1;
prepared/already_migrated no contienen detalle de fallo. No cambia gates,
all-or-nothing ni materialización. Códigos internos desconocidos no se publican.

## 5. Evidence

Tipo frozen BDNSBaselineTransition; schema cerrado
`schemas/bdns-baseline-transition.schema.json`. Path:
`data/migrations/bdns/v1-v2/t-<sha256(record_id)>.json`.

Contiene schema_version, migration_id UUIDv4, source_id, record_id, hashes y
versiones 1→2, from_record_snapshot_hash, motivo canonical_enrichment_v1_to_v2,
migrated_at UTC técnico, SHA software, policy/normalizer/evidence versions.
Sin official_id redundante, títulos, órganos, URLs, documentos ni payload.
Snapshot hash de JSON v1 completo detecta también cambios de metadata/observación
entre preparación y materialización; no modifica content_hash administrativo.

Binding: mismo Record, from_hash=stored v1, to_hash=exact v2, snapshot exacto,
proyección v1 de v2 igual a from_hash. Paths/IDs únicos. Evidencia no se
sobrescribe. No eventos de tipo migration.

## 6. Idempotency and recovery

v1 sin control → preparable. v2 + evidencia + marker matching → already_migrated,
sin red ni writes. v2 sin evidencia/marker, evidencia huérfana/divergente,
v1 con evidencia terminada, marker incompleto → fail closed.

El rerun one-shot sólo reconoce el baseline exacto; si posteriormente hubo
updates administrativos v2 o nuevos Records, no remigra ni reemplaza estado:
requiere revisión y aborta. El collector, en cambio, permite evolución normal
desde baseline: verifica continuidad de update Events hasta el hash actual.
Records nacidos v2 después de completed_at no necesitan transición ficticia.

Preparación falla: ningún write de destino. Staging incompleto: descartable,
no materializable. Materialización falla: puede dejar working tree parcial,
**nunca commit/push**; runner detectará estado mixto local antes de red.
Recuperar desde checkout limpio del main todavía v1 en una nueva ejecución
autorizada; no autorepair, reset destructivo ni transaction multiarchivo.
Commit publicado pero Pages falla: no revertir baselines ni reconsultar fuente;
restaurar sólo deployment. Push rechazado: abortar, no retry loop.

## 7. Staging and cutover

stage_batch escribe sólo en directorio temporal explícito **fuera del repo**,
vacío, todos los Records/evidencias/marker. validate_staged_tree comprueba paths,
gates, hashes y conjunto exacto; no archivos extra. materialize_staged_tree
recomprueba inventory/snapshots y binding antes de reemplazar, con marker al
final. RecordStore mantiene sus escrituras atómicas individuales.

Global marker: `data/migrations/bdns/v1-v2/CUTOVER.json`, schema cerrado
`schemas/bdns-cutover.schema.json`. Migration ID, source, versión hash 2,
normalizer 2.0.0, policy v2, completed_at UTC, record_count, software SHA,
evidence version y population_hash (digest determinista de todas las evidencias).
Sólo un commit publica N v2 + N evidencias + marker conjuntamente.

## 8. Productive runner switch

baseline.productive_hash_version es el único selector; no fecha/flag/env.
Ausencia de marker y todos v1 → ruta legacy exacta. Marker válido + todos v2
+ evidencia completa → normalize_bdns_enriched en ingest. Marker inválido,
v2 sin marker o marker con cualquier v1 → abort antes de requests.

Runner mantiene EventStore obligatorio, gates y event-first→record. Ingest v2
tampoco admite EventStore ausente. Conserva detected_at de existentes;
new v2 → create, mismo hash → no Event, cambio v2→v2 → update con hash previo
baseline/current v2. EventStore/identity/schema Event no cambian. HashContractTransitionError
sigue rechazando v1↔v2. Evidencia conecta Events v1 intactos con baseline v2.
No marker real en D1: schedule actual permanece v1.

## 9. Workflow, race and Pages

`.github/workflows/bdns-v1-v2-migration.yml`: workflow_dispatch only, main guard,
ubuntu-24.04/Python3.12, contents write/actions write, sin PAT/secrets nuevos.
**Mismo concurrency group bdns-collection-main, cancel-in-progress false** que
collector manual/schedule: no ejecución simultánea entre ambos.

Checkout main actual → inventory → collect fresh/preflight → stage RUNNER_TEMP
→ materialize → stage whitelist exacta → fetch/race → commit único → como máximo
un rebase BOE → revalidate contra parent del commit → push normal → dispatch Pages.
No refetch tras rebase. El helper workflow_safety existente verifica todos los
commits/pathsets automáticos data(boe) compatibles; cualquier BDNS/code/schema/
workflow/docs/frontend/migration remote → abort. No force, merge ni retry push.

El workflow captura el exit code de `prepare` y valida/proyecta su JSON mediante
una allowlist cerrada antes de propagar ese exit code. Expone un único
`BDNS_MIGRATION_SAFE_RESULT` en logs y counts/status/safe reason en Step Summary,
nunca contenido fuente. `blocked` conserva exit 1 y no materializa. Resultado
ausente, inválido o inconsistente → `migration_safe_result_invalid`, exit 1.

Commit: `data(bdns): migrate canonical records to v2 baseline`. Exactamente M de
todos los Records inventariados, A de evidencias y marker. No Events/Manifest/
Health/README/code/frontend. validate-git valida snapshots del parent/base y gates
del tree final. Ya migrado → no commit vacío, no dispatch. Dispatch Pages sólo
después de push correcto, vía GITHUB_TOKEN/gh API workflow_dispatch ref=main.

## 10. D2 procedure and limits

1. Revisar/publicar D1 como commit de código separado; no disparar migración.
2. Autorizar D2 explícitamente, comprobar main/árbol limpio y Action correcta.
3. Una ejecución manual desde main; su concurrency excluye schedule BDNS.
4. Inventariar corpus actual (incluye v1 creados mientras se desarrollaba D1).
5. Observar counts, gates/evidencia, único commit y Pages. Si blocked, detenerse;
   no ampliar scopes/forzar hashes ni repetir sin autorización.
6. Verificar todos v2 y evidencia/marker, Events históricos sin cambios y portal.
   La validación del próximo schedule v2 es una operación posterior, no D1.

Límites D2 source-specific: por ID inventariado 2 details y <=5 páginas search
de 50 + 1 control; máximo **8N GET**, habitual **4N GET**, serial, sin retries;
wall-clock 600s. Son protecciones InfoCs, no cuotas oficiales. Budget/drift falla
todo el batch, nunca publica parcial. No PDFs, concessions ni corpus adicional.

CLI: inventory; prepare --git-sha <base> --staged-data-root <temporal>;
materialize --staged-data-root <temporal>; validate-git --base-ref <base/parent>
[--commit <sha>]. Prepare es la única fase de source access, reservada para D2.

Safe codes principales: migration_invalid_inventory, migration_v1_source_drift,
migration_summary_not_resolved, migration_detail_failure,
migration_enrichment_blocked, migration_privacy_blocked,
migration_publication_blocked, migration_evidence_conflict,
migration_mixed_hash_versions, migration_cutover_marker_invalid,
migration_incomplete_batch, migration_budget_exhausted,
migration_invalid_staging, migration_attribution_blocked,
migration_preflight_failed. Carrera usa los códigos seguros del helper Git actual.

No PROJECT_STATE actualizado; no migration/live run ni datos reales escritos en D1.
