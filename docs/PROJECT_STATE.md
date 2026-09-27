# Estado operativo de InfoCs

Actualizado: 2026-09-27. Este documento resume el estado presente; no es un
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
| BDNS/SNPSAP | Collector operativo; reutilización confirmada con condiciones; política de metadata; 1 Record real y 1 Event `create`; aún sin acción productiva propia, Manifest ni Health. |
| BOP Castellón | Transporte, normalización y barreras técnicas listos; `TECHNICALLY_READY_PUBLICATION_BLOCKED`, `reuse_policy_unresolved`; sin Records ni Events públicos. |

Conteos canónicos: **Records BOE: 1; Records BDNS: 1; Events BDNS: 1;
Records BOP: 0; Events BOP: 0.**

## Siguiente fase de producto

**Phase 09 — Portal Astro: 09A y 09B completos.** La capa build-time carga
Records/Events canónicos y genera portada cronológica, fichas estáticas y
directorio de fuentes con metodología breve. La presentación distingue fecha
de publicación de detección y conserva la procedencia; no usa JavaScript
cliente. `astro check`/`astro build` pasan. GitHub Pages, dominio y deployment
no están configurados ni se consideran listos. El
`IMPLEMENTATION_PLAN.md` es la hoja de ruta canónica; este documento es la
referencia para el estado operativo actual.

## Deuda operativa y publicación

Estos puntos no bloquean empezar Astro, pero deben resolverse antes de la
operación/publicación que corresponda:

- BDNS: automatización propia, Manifests/Health propios, semántica de run y
  exigir EventStore para operaciones `create`/`update` antes de automatizar.
- BOE: observar la fiabilidad del schedule en operación.
- BOP: confirmar base oficial de reutilización antes de publicar Records o
  Events.
- Antes de beta pública: incorporar PCSP y DOGV conforme a la hoja de ruta;
  resolver la licencia del código/documentación del proyecto (`pyproject.toml`
  conserva `license = TBD`).

**Estado de avance: `PHASE_09B_COMPLETE`.** Esto no implica que las deudas
anteriores estén cerradas ni habilita el deployment o la beta pública.
