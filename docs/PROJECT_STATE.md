# Estado operativo de InfoCs

Actualizado: 2026-10-06. Este documento resume el estado presente; no es un
registro de fases ni sustituye la hoja de ruta canónica.

## Arquitectura

Objetivo: **static data pipeline + Astro + GitHub Pages**. “Data Pipeline”
significa collectors → normalización → privacidad/publicación →
Records/Events/Manifests/Health → Git → build estático. No hay ni se prevé un
backend web/runtime, servicio API ni base de datos de producción.

## Core

Implementados: `Record`/`RecordCandidate`, identidad/hash/diff, Privacy Gate,
políticas de publicación, `RecordStore`, `EventStore` y
`PublicationAuthorization` transitoria ligada al Record y su hash. Los
adaptadores de fuente aplican las políticas; EventStore valida el binding y
no decide políticas BOE/BDNS/BOP.

## Fuentes y datos públicos actuales

| Fuente | Estado operativo |
| --- | --- |
| BOE | Operativa; 1 Record real; workflow diario/manual, Manifests y Health; Publication Review manual; commits de datos despachan Pages explícitamente. |
| BDNS/SNPSAP | Runner, Privacy/Publication gates, Records/Events, Manifests y Health operativos. OPS-E.2 validó `complete_scope` y la cadena automática a Pages; OPS-F validó incremental e idempotencia. OPS-G programa incremental diario a las 08:17 `Europe/Madrid`, con `through_date` de ayer y checkpoint Manifest obligatorio. Baseline v2 activo; 10B-D3 cerrado: `BDNS_FIRST_SCHEDULED_V2_RUN_VALIDATED`. El schedule normal v2 y la publicación automática hasta Pages quedaron validados tras el hardening. Se conserva el disparo manual. |
| BOP Castellón | Transporte, normalización y barreras técnicas listos; `TECHNICALLY_READY_PUBLICATION_BLOCKED`, `reuse_policy_unresolved`; sin Records ni Events públicos. |

Conteos canónicos a 2026-10-06: **Records BOE: 1; Records BDNS: 42; Events BDNS: 42;
Records BOP: 0; Events BOP: 0.**

### BDNS — baseline canónico v2

Phase 10B-D2.9 migró los 40 Records BDNS existentes a baselines enriquecidos
v2 tras demostrar equivalencia fresh-source de todos los hashes v1 y superar
Privacy, publicación y autorización. El commit canónico
`27224e9b685c2080b02a9dc7ccd7682a203bac0a` publica conjuntamente los 40
reemplazos, 40 transition evidences y `data/migrations/bdns/v1-v2/CUTOVER.json`.
El marker y el population hash son válidos; `productive_hash_version() = 2`
y el normalizer target es `2.0.0`; los Records tienen
`content_hash_version = 2` y `source_data.bdns`. La migración generó **0 Events
administrativos** y conservó intactos los 40 Events históricos.

Las bases reguladoras usan `source_locator`: valor literal suministrado por
BDNS, material para hash/diff, separado de la clickability derivada. HTTP y
locators sin esquema se conservan sin rewriting; sólo HTTPS estricto puede
ser navegable. Clickability no se persiste ni participa en hash.

La migración despachó Pages automáticamente; deployment y smoke público
PASS (portada, búsqueda Pagefind y tres fichas BDNS). La presentación
Human Readability del frontend sigue pendiente. No se ejecutó ningún
collector manual para probar v2.

### 10B-D3 — FIRST SCHEDULED V2 RUN VALIDATION — cerrado

Milestone: **`BDNS_FIRST_SCHEDULED_V2_RUN_VALIDATED`**.
Después del cutover, el schedule v2 `37120640143` falló por ingestión de un
item (`item_ingestion_failure`), sin nuevos Records ni Events, y dejó Health
`degraded`, con `consecutive_failures = 1`. El hardening posterior se publicó
en `7ecb34a9468057c53110cdab2c88dafbafd77f5b`
(`fix: harden BDNS v2 ingestion and diagnostics`); este cierre no oculta ese
incidente ni reevalúa la migración.

El run **`37202195786`**, número **8**, de **BDNS collection**, trigger
**`schedule`**, branch `main`, sobre ese SHA de código, terminó **success**.
Preflight, collector, validación/staging canónico, commit/publicación,
dispatch de Pages y propagación del resultado original terminaron
correctamente, sin intervención manual para convertir el run en válido.

Manifest: `run-v1-dc37a849-8b24-418d-93de-4c44c6b294ec`, `status = success`.
Scope: `region=56;from=2026-09-17;to=2026-10-03;temporal_policy=fecha-recepcion-provisional-v1`.

| Métricas del run validado | Resultado |
| --- | --- |
| seen / normalized / finalized / included | 39 / 39 / 39 / 39 |
| privacy_allowed / publication_approved | 39 / 39 |
| created / unchanged / updated | 1 / 38 / 0 |
| events_created / events_updated / errors | 1 / 0 / 0 |
| privacy_quarantined / privacy_rejected | 0 / 0 |
| publication_hold / publication_rejected | 0 / 0 |

El scope observado se procesó completo, sin partial batch. El nuevo Record
`infocs:bdns:933177-30be812baeccb5e3` (`source.id = bdns`,
`source.official_id = 933177`) nació directamente con
`normalizer_version = 2.0.0`, `content_hash_version = 2` y `source_data.bdns`,
Privacy ALLOW y Publication approved. Generó exactamente un Event `create`,
no un Event artificial por transición v1→v2.

Su `regulatory_bases.source_locator` real, que motivó el hardening, se
preservó literalmente como dato fuente material del hash, sin rewriting,
eliminación ni conversión artificial en enlace navegable, y no bloqueó el
batch. Privacy y Publication gates permanecieron activos.

El schedule recuperó Health automáticamente: `healthy`,
`consecutive_failures = 0`,
`last_run_id = run-v1-dc37a849-8b24-418d-93de-4c44c6b294ec`,
`last_success_at = 2026-10-04T12:28:54.060583Z` al finalizar ese run.

Publicó automáticamente `656257011951c010df532c9f6cbeed60131f45a7`
(`data(bdns): scheduled incremental through 2026-10-03`): un Record nuevo,
un Event create, un Manifest y Health. Después disparó **Deploy InfoCs
portal**, run `37202250403`, event `workflow_dispatch`, deployment del mismo
SHA, conclusión **success**. Queda validada la cadena
schedule → collector → canonical commit → Pages dispatch → deployment.

Baseline v2 operativo y validación programada cerrada; no hace falta otra
migración ni un collector manual de validación. El snapshot actual incorpora
además una alta automática posterior; no debe confundirse con los conteos
históricos del run que cierra D3. La presentación enriquecida sigue pendiente.

## Siguiente fase de producto

Siguiente bloque funcional: **10B-E — BDNS HUMAN READABILITY**.
ViewModels, presentación y frontend enriquecidos todavía no implementados.

**Phase 09D — Public Product Surfaces complete. Phase 09E — GitHub Pages deployment complete.**
El portal estático se despliega con GitHub Actions y el dominio personalizado
activo es `https://infocs.hazlotuyo.pro`. Esto describe un deployment técnico,
no una beta pública. El portal estático carga
Records/Events canónicos y ofrece portada, fichas de registro, índice y detalle
de fuentes, cambios, metodología y 404 con el sistema visual aprobado. Usa
JavaScript mínimo para el tema oscuro/claro y la búsqueda estática. Phase 10A
implementa búsqueda textual con Pagefind; siguen pendientes los filtros,
facetas y refinamientos de orden de Phase 10B, el estado multi-source y los
datasets/exports. Phase 10 y Phase 09 no están completas. El
`IMPLEMENTATION_PLAN.md` es la hoja de ruta canónica; este documento es la
referencia para el estado operativo actual.

## Deuda operativa y publicación

Estos puntos no bloquean empezar Astro, pero deben resolverse antes de la
operación/publicación que corresponda:

- BDNS: la política v1 acepta que no existe garantía absoluta de detección
  inmediata de todas las modificaciones retrospectivas. El runner declara
  explícitamente su scope y cobertura; la limitación no impide avanzar, pero
  debe permanecer visible. La Action manual y la propagación automática
  data(bdns) → Pages quedaron validadas en producción en OPS-E.2. El schedule
  diario implementado en OPS-G quedó validado también sobre v2 en 10B-D3,
  incluida la recuperación automática de Health tras el hardening. GitHub
  Actions schedule sigue siendo best-effort: Manifests y Health son la
  evidencia de cada ejecución. BDNS sigue ofreciendo el modo manual.
- BOE: observar la fiabilidad del schedule en operación.
- BOP: confirmar base oficial de reutilización antes de publicar Records o
  Events.
- Antes de beta pública: incorporar PCSP y DOGV conforme a la hoja de ruta;
  resolver la licencia del código/documentación del proyecto (`pyproject.toml`
  conserva `license = TBD`).

**Estado de avance: `PHASE_09E_CUSTOM_DOMAIN_ACTIVE`; `PHASE_10A_STATIC_SEARCH_COMPLETE`; `BDNS_FIRST_SCHEDULED_V2_RUN_VALIDATED`.** Esto no implica
que las deudas anteriores estén cerradas ni habilita una beta pública.
