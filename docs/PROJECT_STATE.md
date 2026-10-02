# Estado operativo de InfoCs

Actualizado: 2026-10-02. Este documento resume el estado presente; no es un
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
| BDNS/SNPSAP | OPS-B productive runner, OPS-C SourceHealth/CLI y OPS-D manual Action publicados. OPS-E.1 añade dispatch explícito de Pages tras commits de datos. OPS-E.2 validó `complete_scope` (2026-09-29): `complete_success`, 3 Records y 3 Events creados; Health `healthy` y cadena automática a Pages PASS. OPS-F validó en producción `incremental_update` (2026-09-28..2026-09-29): `complete_success`, 7 vistos, 7 sin cambios, 0 altas, 0 actualizaciones y 0 Events; creó el primer Manifest incremental `success`, ahora checkpoint compatible, con Health `healthy` y cadena automática a Pages PASS. OPS-G implementa la ejecución diaria incremental a las 08:17 `Europe/Madrid`, con `through_date` de ayer y checkpoint Manifest obligatorio; está pendiente de la primera validación programada. BDNS mantiene el disparo manual y aún no declara el schedule validado. |
| BOP Castellón | Transporte, normalización y barreras técnicas listos; `TECHNICALLY_READY_PUBLICATION_BLOCKED`, `reuse_policy_unresolved`; sin Records ni Events públicos. |

Conteos canónicos: **Records BOE: 1; Records BDNS: 40; Events BDNS: 40;
Records BOP: 0; Events BOP: 0.**

### BDNS — baseline canónico v2

Phase 10B-D2.9 migró los 40 Records BDNS existentes a baselines enriquecidos
v2 tras demostrar equivalencia fresh-source de todos los hashes v1 y superar
Privacy, publicación y autorización. El commit canónico
`27224e9b685c2080b02a9dc7ccd7682a203bac0a` publica conjuntamente los 40
reemplazos, 40 transition evidences y `data/migrations/bdns/v1-v2/CUTOVER.json`.
El marker y el population hash son válidos; `productive_hash_version() = 2`
y el normalizer target es `2.0.0`. La migración generó **0 Events
administrativos** y conservó intactos los 40 Events históricos.

Las bases reguladoras usan `source_locator`: valor literal suministrado por
BDNS, material para hash/diff, separado de la clickability derivada. HTTP y
locators sin esquema se conservan sin rewriting; sólo HTTPS estricto puede
ser navegable. Clickability no se persiste ni participa en hash.

La migración despachó Pages automáticamente; deployment y smoke público
PASS (portada, búsqueda Pagefind y tres fichas BDNS). La presentación
Human Readability del frontend sigue pendiente. La primera colección
scheduled **v2** sigue pendiente de validación: el último run scheduled
observado (`37008541972`, 2026-10-02, success) fue anterior al cutover y
operó sobre v1. No se ejecutó ningún collector manual para probar v2.

## Siguiente fase de producto

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
  diario implementado en OPS-G ya tiene ejecuciones v1 success observadas;
  la primera ejecución programada posterior al cutover v2 sigue pendiente.
  BDNS sigue ofreciendo el modo manual.
- BOE: observar la fiabilidad del schedule en operación.
- BOP: confirmar base oficial de reutilización antes de publicar Records o
  Events.
- Antes de beta pública: incorporar PCSP y DOGV conforme a la hoja de ruta;
  resolver la licencia del código/documentación del proyecto (`pyproject.toml`
  conserva `license = TBD`).

**Estado de avance: `PHASE_09E_CUSTOM_DOMAIN_ACTIVE`; `PHASE_10A_STATIC_SEARCH_COMPLETE`.** Esto no implica
que las deudas anteriores estén cerradas ni habilita una beta pública.
