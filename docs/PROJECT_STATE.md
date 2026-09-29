# Estado operativo de InfoCs

Actualizado: 2026-09-29. Este documento resume el estado presente; no es un
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
| BOE | Operativa; 1 Record real; workflow diario/manual, Manifests y Health; Publication Review manual. |
| BDNS/SNPSAP | Collector y runner productivo implementados para `discovery`, `incremental_update` y `complete_scope`; RunManifest por ejecución; EventStore obligatorio para `create`/`update`; 1 Record real y 1 Event `create`. Sin automatización, sin SourceHealth productivo y sin validación live del runner. |
| BOP Castellón | Transporte, normalización y barreras técnicas listos; `TECHNICALLY_READY_PUBLICATION_BLOCKED`, `reuse_policy_unresolved`; sin Records ni Events públicos. |

Conteos canónicos: **Records BOE: 1; Records BDNS: 1; Events BDNS: 1;
Records BOP: 0; Events BOP: 0.**

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
  debe permanecer visible. Siguen pendientes automatización propia,
  SourceHealth productivo y validación live controlada del runner.
- BOE: observar la fiabilidad del schedule en operación.
- BOP: confirmar base oficial de reutilización antes de publicar Records o
  Events.
- Antes de beta pública: incorporar PCSP y DOGV conforme a la hoja de ruta;
  resolver la licencia del código/documentación del proyecto (`pyproject.toml`
  conserva `license = TBD`).

**Estado de avance: `PHASE_09E_CUSTOM_DOMAIN_ACTIVE`; `PHASE_10A_STATIC_SEARCH_COMPLETE`.** Esto no implica
que las deudas anteriores estén cerradas ni habilita una beta pública.
