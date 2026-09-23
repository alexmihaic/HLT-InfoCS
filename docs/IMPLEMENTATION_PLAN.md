# Plan de implementación verificable

## Regla de avance

Cada fase termina con revisión de cambios y tests reales. Ninguna fase habilita por sí misma archivo público de documentos ni publicación de datos personales. PCSP se incorpora antes de la beta pública y DOGV se intentará incorporar también antes de ella, conforme a la resolución de `OPEN-001`.

## Fase 00 — Bootstrap

- **Objetivo:** establecer contrato de trabajo, estructura, empaquetado mínimo y documentación arquitectónica.
- **Dependencias:** `docs/INFOCS_SPEC_v1.md`.
- **Entregables:** `AGENTS.md`, arquitectura, registro de decisiones, plan, árbol base, `pyproject.toml`, `.gitignore` y prueba de bootstrap.
- **Tests necesarios:** importación del paquete y comprobación de ficheros fundacionales.
- **Criterio de aceptación:** no hay collectors, datos reales, workflows ni portal funcional; las decisiones abiertas están documentadas.
- **Fuera de alcance:** cualquier consulta de fuente, esquema funcional, despliegue o automatización.

## Fase 01 — Core y modelo de datos

- **Objetivo:** definir contratos versionados de records, fuentes, eventos y manifiestos, además de configuración declarativa vacía o de ejemplo no real.
- **Dependencias:** Fase 00; revisión del modelo de datos de la especificación.
- **Entregables:** JSON Schemas portables, modelos Python inmutables, reglas de categorías, serialización canónica y fixtures exclusivamente ficticios.
- **Tests necesarios:** validación positiva y negativa de schemas; serialización de importes decimales; compatibilidad de versión; round-trip Python → JSON → Python.
- **Criterio de aceptación:** un record sintético válido expresa procedencia, identidad reservada, fechas, estado y distinción entre campos oficiales y derivados; no existen collectors ni comunicaciones de red.
- **Fuera de alcance:** collectors, endpoints, contenido administrativo real, base de datos y portal.

## Fase 02 — Identidad, deduplicación y eventos (cerrada, con endurecimiento previo a Fase 03)

- **Objetivo:** implementar identidad estable, hash del contenido observado, cambios y política de ausencias. Las relaciones entre fuentes quedan para una fase posterior.
- **Dependencias:** Fase 01.
- **Entregables:** motor de identidad/diff, eventos normalizados, reconciliación de observaciones sintéticas y finalizador central que inserta `technical.content_hash`. Los manifiestos quedan para Fase 07.
- **Tests necesarios:** idempotencia; actualización con `changed_fields`; IDs oficiales/fallback; frontera entre contenido observado y estado derivado; ausencia tras éxito completo y repetición sin evento; fallo que conserva estado previo; reaparición con y sin modificación; finalización sin mutación.
- **Criterio de aceptación:** la misma entrada no crea duplicados; estado, tags, categoría, territorio o relaciones InfoCs no producen falsos `update`; un fallo no produce ausencias; el record final tiene hash correcto.
- **Fuera de alcance:** integración real con fuentes, relaciones automáticas entre fuentes, commits automáticos, consultas analíticas y UI.

## Fase 03 — BOE

- **Objetivo:** añadir el primer collector estructurado usando exclusivamente el mecanismo oficial que se verifique al iniciar la fase.
- **Dependencias:** Fases 01 y 02, incluido su endurecimiento del finalizador y las transiciones; documentación oficial vigente y policy de fuente aprobada.
- **Entregables:** collector aislado, fixtures contractuales permitidos, normalización BOE, health y documentación de procedencia.
- **Tests necesarios:** unitarios de parser; contract tests; integración con estado previo; smoke test manual o CI separado si está autorizado.
- **Criterio de aceptación:** entradas verificadas producen records y eventos conformes sin scraping ni archivo público indiscriminado.
- **Fuera de alcance:** clasificación jurídica de aplicabilidad, PDF mirroring, otros collectors y portal.

### Fase 03E — Ingesta incremental y persistencia canónica (cerrada en fixtures)

- **Objetivo:** distinguir el sumario BOE incremental de un snapshot y validar un store JSON individual, determinista y atómico.
- **Dependencias:** Fases 01–03D, transport, parser, política territorial, normalizador y finalizador aprobados.
- **Entregables:** `RecordStore`, orquestador `ingest_boe_summary()`, operaciones create/update/no_change, métricas y policy de privacidad de persistencia.
- **Tests necesarios:** idempotencia, actualización con `changed_fields`, ausencia entre días sin missing, no_daily_publication, fallos sin writes, invalid_request, paths seguros, atomicidad y round-trip de records.
- **Criterio de aceptación:** los datos sintéticos se escriben como JSON individual válido y estable; un fallo contractual aborta el batch antes de escribir; no se persisten records o events BOE reales.
- **Fuera de alcance:** ejecución diaria, GitHub Actions, manifests, health real, Privacy Gate v1 (Fase 03F), XML/PDF crawling y cualquier otra fuente.

### Fase 03F — Privacy Gate v1 (cerrada)

- **Objetivo:** impedir técnicamente que un `Record` llegue al almacén público sin una decisión de privacidad explícita.
- **Dependencias:** Fases 01–03E y política de reutilización de cada fuente.
- **Entregables:** gate configurable en JSON, decisiones `allow`/`quarantine`/`reject`, integración obligatoria con ingesta BOE y `RecordStore`, métricas y documentación.
- **Tests necesarios:** patrones de alto riesgo y negativos, datos institucionales permitidos, cero writes para quarantine/reject, fallo del gate sin writes y coexistencia de records seguros y aislados.
- **Criterio de aceptación:** ninguna escritura pasa sin `allow`; no se almacenan valores sensibles en razones ni logs; `data/records/` y `data/events/` no reciben datos BOE reales.
- **Fuera de alcance:** redacción automática, OCR, IA, mirroring, DLP completo, automatización diaria y siguiente fuente.

### Fase 03F.1 — Endurecimiento de falsos positivos (cerrada)

- **Objetivo:** reducir cuarentenas indebidas antes de evaluar datos reales con el gate.
- **Dependencias:** Fase 03F y corpus sintético de patrones.
- **Entregables:** separación estructural de identificadores personales/empresariales/ambiguos, teléfonos con contexto explícito, emails de proveedores personales conocidos, fallos cerrados y pruebas anti-bypass.
- **Tests necesarios:** positivos y negativos sintéticos para los patrones y configuraciones; cero escrituras ante error de privacidad.
- **Criterio de aceptación:** teléfonos genéricos y dominios organizativos desconocidos no se clasifican como personales; reglas ambiguas son explícitas; errores del gate no permiten escritura.
- **Fuera de alcance:** run BOE real, persistencia de datos reales, DLP completo, OCR, IA y otra fuente.

### Fase 03G — BOE Live Dry Run (cerrada)

- **Objetivo:** ejecutar el pipeline BOE real en memoria hasta Privacy Gate, sin store ni archivos de salida.
- **Dependencias:** Fases 03B–03F.1.
- **Entregables:** dry-run aislado, informe saneado y comprobación de transporte, parser, territorialidad, identidad y privacidad.
- **Tests necesarios:** métricas, decisiones, errores, no filtración y garantía anti-write.
- **Criterio de aceptación:** las fechas autorizadas se procesan sin persistencia real y el informe recomienda o rechaza explícitamente la primera persistencia.
- **Fuera de alcance:** records, events, respuestas raw, documentos y automatización.

### Fase 03H — Primera persistencia BOE controlada (cerrada)

- **Objetivo:** persistir sólo IDs aprobados explícitamente tras revisión humana separada de Privacy Gate.
- **Dependencias:** Fases 03E–03G y allowlist versionada por `official_id`.
- **Entregables:** Publication Review fail-closed, preflight completo de tres sumarios, primer lote mínimo de Records canónicos e informe de auditoría; sin Events.
- **Tests necesarios:** allow/hold/rejected, gate que prevalece, ID desconocido en hold, aprobación ausente, preflight sin escrituras parciales, idempotencia y hash/ID estables.
- **Criterio de aceptación:** sólo Records aprobados y con Privacy Gate `allow` llegan a `RecordStore`; el segundo procesamiento es `no_change`; no hay automatización ni contenido documental.
- **Fuera de alcance:** aprobación automática, Events reales, manifests, health, Actions, UI, documentos BOE y siguientes fuentes.

### Fase 03I — Events canónicos v1

- **Objetivo:** definir Events persistibles append-only `create`/`update` y su almacén común sin backfill ni ejecución BOE real.
- **Dependencias:** RecordStore, Privacy Gate, Publication Review y diff semántico.
- **Entregables:** schema estricto, identidad determinista de Event, EventStore seguro, preflight Record/Event y documentación del límite transaccional.
- **Tests necesarios:** schema condicional, idempotencia, colisión append-only, orden por Record, create/update/no_change, hash continuity, metadata derivada sin evento, privacy/publication denial y cero datos reales.
- **Criterio de aceptación:** Records/Eventos sintéticos pasan contrato; sólo `create`/`update` aprobados llegan a EventStore; `data/events/` no recibe backfill en esta fase.
- **Fuera de alcance:** backfill del Record BOE real existente, llamadas de red, daily ingestion, manifests, health, automation, nuevas fuentes y rollback multiarchivo.

## Fase 04 — BDNS

- **Objetivo:** incorporar subvenciones mediante el canal oficial estructurado que se vuelva a verificar en esta fase.
- **Dependencias:** Fases 01–03; ficha de reutilización y privacidad de BDNS.
- **Entregables:** collector BDNS independiente, fixture contractual, mapeo de ayudas/convocatorias y health.
- **Tests necesarios:** parser y normalización; importes exactos; identidad; no duplicación con ejecuciones repetidas; preservación ante fallo.
- **Criterio de aceptación:** las subvenciones normalizadas mantienen URL, identificación y procedencia sin scraping municipal sustitutivo.
- **Fuera de alcance:** extracción de páginas municipales, perfiles de personas físicas y publicación de documentos completos.

## Fase 05 — BOP Castellón

- **Objetivo:** incorporar el boletín provincial con el nivel de acceso documentado que se valide en la fase.
- **Dependencias:** Fases 01–02; revisión renovada de estabilidad y condiciones de reutilización.
- **Entregables:** collector BOP aislado, fixture HTML/estructurado permitido, política de fuente y health.
- **Tests necesarios:** contract tests resistentes a cambios de estructura; controles de input; anomalías; fallo aislado que conserva records.
- **Criterio de aceptación:** se publican metadatos, enlaces y hashes permitidos; no se presenta un endpoint observado como API oficial ni se espejan PDFs sin autorización.
- **Fuera de alcance:** scraping municipal general, documento íntegro público y inferencia de eliminación.

## Fase 06 — Privacidad y políticas por fuente

- **Objetivo:** convertir las restricciones de privacidad y reutilización en controles verificables antes de cualquier commit de datos.
- **Dependencias:** Fases 01–05; revisión jurídica cuando el alcance afecte a datos de personas o documentos completos.
- **Entregables:** políticas por fuente, detección conservadora, flujo de cuarentena, reglas de publicación y documentación de rectificaciones.
- **Tests necesarios:** patrones de riesgo; paso a cuarentena; bloqueo de mirroring con política no aprobada; minimización; no regresión de metadatos válidos.
- **Criterio de aceptación:** un posible dato sensible no llega a datos públicos y las políticas bloquean técnicamente acciones prohibidas.
- **Fuera de alcance:** dictamen jurídico sustitutivo, OCR masivo, índice de personas y archivo universal.

## Fase 07 — Manifests y health (core reusable offline cerrado)

- **Objetivo:** hacer visibles y reproducibles las ejecuciones, cambios y salud por fuente.
- **Dependencias:** Fases 01–06.
- **Entregables:** RunManifest v1 append-only, ManifestStore JSON atómico, adaptador BOE en memoria y SourceHealth derivado con estados y umbral documentados.
- **Tests necesarios:** validación de timestamps y métricas; idempotencia/conflicto de run ID; paths; orden independiente del filesystem; health sin runs, éxito, no publicación, fallos y reset; sanitización de error BOE.
- **Criterio de aceptación:** manifests sintéticos describen runs sin copiar Records/Events; Health es regenerable y determinista; directorios productivos siguen vacíos.
- **Fuera de alcance:** hash chain de manifests, persistencia productiva de manifests/health, monitorización SaaS, notificaciones, GitHub Actions y dashboard público funcional.

## Fase 08 — GitHub Actions

- **Objetivo:** automatizar validación y recopilación futura con permisos mínimos y aislamiento por fuente.
- **Dependencias:** Fases 01–07; revisión de seguridad de Actions.
- **Entregables:** workflows no productivos inicialmente, matriz aislada, permisos mínimos, pinning y documentación de ejecución manual/programada.
- **Tests necesarios:** validación estática de workflows; ejecución controlada con fixtures; prueba de agregación `always`; revisión de permisos.
- **Criterio de aceptación:** una fuente fallida no bloquea el agregado de resultados válidos y ningún job de parsing recibe permisos de escritura o secretos.
- **Fuera de alcance:** despliegue de producción, acciones de terceros sin pin, almacenamiento de artefactos documentales y `pull_request_target`.

## Fase 09 — Portal Astro

- **Objetivo:** construir el portal estático a partir de datos validados, mostrando trazabilidad y separación de capas.
- **Dependencias:** Fases 01, 02, 06 y 07; decisión sobre alcance de datos de muestra seguros.
- **Entregables:** estructura Astro, fichas, metodología, fuentes, estado de fuentes y etiquetas de dato oficial/normalizado/cálculo.
- **Tests necesarios:** build estático; enlaces internos; renderizado escapado; pruebas de accesibilidad básicas; no inclusión de HTML externo sin sanear.
- **Criterio de aceptación:** el portal puede generarse con datos sintéticos y no requiere backend, cuentas ni analítica.
- **Fuera de alcance:** despliegue, dominio, búsqueda final, RSS, datos administrativos no aprobados y rankings editoriales.

## Fase 10 — Búsqueda, RSS y exports

- **Objetivo:** generar índices y salidas abiertas estáticas a partir de records validados.
- **Dependencias:** Fases 02, 07 y 09.
- **Entregables:** índice de búsqueda estático, filtros precalculados, RSS y exports JSON/JSONL/CSV generados.
- **Tests necesarios:** reproducibilidad de exports; validez de RSS/CSV; coherencia entre resultados e índice; ausencia de campos bloqueados por privacidad.
- **Criterio de aceptación:** búsquedas, filtros y exports se crean durante el build sin servicio remoto ni mantenimiento manual.
- **Fuera de alcance:** Elasticsearch, Algolia, API permanente, alertas personalizadas y cuentas de usuario.

## Fase 11 — Preparación pre-beta

- **Objetivo:** preparar las condiciones metodológicas y de publicación sin abrir aún la beta.
- **Dependencias:** Fases 03–10; revisión jurídica aplicable.
- **Entregables:** checklist de publicación, metodología, privacidad, fuentes, limitaciones, estado y mecanismo de corrección.
- **Tests necesarios:** smoke end-to-end de build; revisión manual de muestras; controles de privacidad; verificación de enlaces y accesibilidad.
- **Criterio de aceptación:** el portal queda listo para integrar PCSP/DOGV y una persona puede conocer origen, fecha, transformación y limitaciones de cada resultado.
- **Fuera de alcance:** beta pública, ampliación temática sin evaluación, mirroring generalizado, análisis político y promesas de certificación jurídica.

## Fase 12 — PCSP y DOGV

- **Objetivo:** integrar contratación y normativa/autonómica mediante mecanismos oficiales verificables y con criterios territoriales explícitos.
- **Dependencias:** Fases 01–07 y verificación vigente de formatos y condiciones de cada fuente.
- **Entregables:** collectors independientes PCSP y DOGV, fixtures, políticas de fuente, criterios como coincidencia por organismo/municipio/texto y health.
- **Tests necesarios:** contract tests por fuente; clasificación territorial trazable; relaciones entre fuentes; protección ante cambios de formato; fallos aislados.
- **Criterio de aceptación:** la inclusión territorial explica su criterio y no se presenta como conclusión jurídica; no se inventan endpoints ni se usa PDF cuando exista un canal estructurado aplicable.
- **Fuera de alcance:** interpretación de norma aplicable, duplicación destructiva entre fuentes y scraping completo municipal.

## Fase 13 — Beta pública

- **Objetivo:** publicar una beta metodológicamente transparente después de PCSP y del intento documentado de integración de DOGV.
- **Dependencias:** Fases 03–12 y revisión jurídica aplicable.
- **Entregables:** beta pública, metodología, privacidad, fuentes, limitaciones, estado y mecanismo de corrección visibles.
- **Tests necesarios:** smoke end-to-end de build; revisión manual de muestras; controles de privacidad; verificación de enlaces y accesibilidad.
- **Criterio de aceptación:** una persona puede conocer origen, fecha, transformación y limitaciones de cada resultado; las incidencias de fuentes se muestran sin ocultación.
- **Fuera de alcance:** ampliación temática sin evaluación, mirroring generalizado, análisis político y promesas de certificación jurídica.

## Fase 14 — Ampliación

- **Objetivo:** añadir progresivamente fuentes, municipios y temas tras validar su valor, estabilidad, licencia y riesgo.
- **Dependencias:** Fase 13 y, para cada nueva fuente, su ficha de acceso/reutilización/privacidad y pruebas.
- **Entregables:** nuevos adaptadores, entidades configuradas, contratos, cobertura documentada y, cuando proceda, relaciones y estadísticas trazables.
- **Tests necesarios:** suite de cada nuevo collector; regresión de core; contract tests; anomalías; revisión de privacidad y tamaño de repositorio/build.
- **Criterio de aceptación:** cada ampliación conserva independencia de collector, coste recurrente cero y trazabilidad; un municipio se añade mediante entidades, no clonando el proyecto.
- **Fuera de alcance:** Catastro individualizado, OCR masivo, perfiles de personas, infraestructura de pago, API backend o tiempo real sin decisión posterior.
