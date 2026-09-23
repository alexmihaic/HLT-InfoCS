# Registro de decisiones arquitectónicas

## Formato

Cada decisión usa: ID, fecha, estado, contexto, decisión, alternativas consideradas y consecuencias. Los estados posibles son `aceptada`, `propuesta`, `pendiente`, `sustituida` y `rechazada`.

## ADR-001 — Datos canónicos textuales y versionables

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** InfoCs necesita trazabilidad pública, diffs revisables e histórico reproducible sin base de datos de producción.
- **Decisión:** JSON y JSONL son los formatos canónicos. Git conserva records, events, manifests y health. SQLite y DuckDB solo son artefactos derivados.
- **Alternativas consideradas:** SQLite o DuckDB como fuente principal; base de datos externa.
- **Consecuencias:** los datos deben normalizarse para producir diffs útiles; cualquier exportación binaria se regenera y no se trata como verdad.

## ADR-002 — Collectors federados e independientes

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** las fuentes administrativas tienen mecanismos, estabilidad y condiciones distintas.
- **Decisión:** cada fuente tendrá un collector independiente y seguirá la preferencia API oficial, estructurado, feed, descarga estructurada, HTML y PDF. El contrato separará descubrimiento, recuperación, interpretación, normalización y healthcheck.
- **Alternativas consideradas:** scraper monolítico; una lógica específica distribuida por el motor global; priorizar HTML/PDF por defecto.
- **Consecuencias:** una nueva fuente aporta su adaptador y fixtures sin modificar el núcleo salvo justificación arquitectónica. Un cambio a scraping queda documentado.

## ADR-003 — Metadatos y enlace por defecto; archivo selectivo

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** la accesibilidad pública no equivale a autorización de republicación; los documentos pueden contener datos personales y crecer rápidamente.
- **Decisión:** se publican por defecto metadatos normalizados, procedencia, URL oficial, fechas y hashes disponibles. Un documento, su texto completo o una captura solo se archiva públicamente si la política específica de la fuente lo permite explícitamente.
- **Alternativas consideradas:** espejo universal de PDFs; política única global de licencias; conservar solo enlaces sin trazabilidad.
- **Consecuencias:** cada fuente requiere ficha de reutilización; `archive/` permanece casi vacío durante el MVP; el sistema deberá impedir técnicamente el mirroring no autorizado.

## ADR-004 — Histórico aditivo y tolerante a fallos

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** una caída o regresión de un portal no prueba que un expediente haya sido retirado.
- **Decisión:** conservar el estado válido anterior ante fallo de un collector, registrar health/error y no inferir eliminaciones. Usar records actuales, events diarios y manifests encadenados.
- **Alternativas consideradas:** reemplazar siempre el estado por la última extracción; tratar una ausencia como eliminación; depender solo del diff de Git.
- **Consecuencias:** se necesitan eventos explícitos, hashes separados y tests de idempotencia, actualización, ausencia y fallo aislado.

## ADR-005 — Operación estática sin coste recurrente adicional

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** el proyecto busca sostenibilidad con 0 EUR/mes adicionales y una superficie operativa pequeña.
- **Decisión:** repositorio público, GitHub Actions estándar, build estático Astro y GitHub Pages; sin backend permanente, VPS, SaaS de pago, APIs de pago ni base de datos externa.
- **Alternativas consideradas:** API/backend propio; alojamiento de pago; monitorización SaaS; base de datos gestionada.
- **Consecuencias:** búsqueda, filtros y exports se precalculan; se vigila el tamaño de repositorio y build; no se almacenan binarios masivos.

## ADR-006 — Privacidad preventiva antes del commit

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** Git conserva historial y puede impedir una supresión efectiva de datos personales publicados indebidamente.
- **Decisión:** aplicar detección conservadora, minimización, exclusión o cuarentena en espacio temporal antes de publicar. Evitar OCR masivo en el MVP.
- **Alternativas consideradas:** limpiar datos después de commit; indexar todo documento oficialmente público; censura automática irreversible.
- **Consecuencias:** un posible dato sensible no llega a Git público; las coincidencias requieren revisión y no constituyen por sí mismas una afirmación jurídica.

## ADR-007 — Neutralidad trazable por diseño

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** las comparaciones administrativas pueden confundirse con juicios políticos o jurídicos.
- **Decisión:** mostrar cronología, fuentes, criterios de inclusión, fórmulas y datos de entrada. Separar dato oficial, normalización InfoCs y cálculo InfoCs. No producir acusaciones, rankings editoriales ni inferencias de intención.
- **Alternativas consideradas:** puntuaciones de relevancia; análisis de sentimiento; resúmenes políticos automáticos; etiquetas jurídicas concluyentes.
- **Consecuencias:** las clasificaciones territoriales y estadísticas requieren explicación metodológica y trazabilidad a records concretos.

## Cuestión abierta — Orden de PCSP y DOGV respecto de la beta

- **ID:** OPEN-001
- **Fecha:** 2026-09-21
- **Estado:** resuelta
- **Contexto:** la especificación incluye PCSP en el MVP y DOGV como recomendable para el MVP público. El orden de fases solicitado para este bootstrap sitúa ambos en la Fase 12, después de la beta pública (Fase 11).
- **Decisión:** PCSP se incorpora antes de la beta pública y DOGV se intentará incorporar también antes de ella. La beta se desplaza después de ambas fases de integración.
- **Alternativas consideradas:** adelantar PCSP/DOGV al MVP; mantenerlos como ampliación posterior a beta.
- **Consecuencias:** `IMPLEMENTATION_PLAN.md` sitúa la beta pública después de PCSP/DOGV. La ausencia justificada de DOGV deberá quedar visible como limitación, no como sustitución silenciosa de fuente.

## ADR-008 — JSON Schema portable y modelos Python sin framework

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** InfoCs necesita validar JSON fuera de Python y evitar dos contratos incompatibles, sin incorporar un framework completo solo para esta fase.
- **Decisión:** JSON Schema Draft 2020-12 es el contrato portable. Los modelos Python inmutables usan `dataclasses` de la biblioteca estándar y validan las cargas contra esos schemas mediante `jsonschema==4.26.0` antes de construir objetos.
- **Alternativas consideradas:** Pydantic como fuente de schema; validadores manuales sin JSON Schema; mantener schema y modelos sin pruebas cruzadas.
- **Consecuencias:** se añade una única dependencia de validación, fijada a versión exacta. Los fixtures se validan mediante JSON Schema y se cargan con los modelos; cualquier ampliación debe actualizar ambos y sus tests.

## ADR-009 — `content_hash` modelado antes de su cálculo

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** la especificación sitúa `content_hash` en el núcleo recomendado, pero la Fase 02 contiene la definición de identidad, deduplicación y detección de cambios que determina su cálculo reproducible.
- **Decisión:** `technical.content_hash` existe en el contrato v1 como SHA-256 opcional y no se calcula en Fase 01. La Fase 02 decidirá los campos incluidos y endurecerá su requisito cuando el motor exista.
- **Alternativas consideradas:** inventar un hash provisional; exigir un hash ficticio; omitirlo del contrato hasta Fase 02.
- **Consecuencias:** los records sintéticos mínimos son válidos sin `content_hash`; ningún código de esta fase afirma detectar cambios o generar identidad.

## ADR-010 — Identidad y hash semántico separados

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** un mismo hecho puede cambiar sin dejar de ser el mismo record.
- **Decisión:** identidad con prioridad official_id, expediente, URL canónica y fingerprint; hash SHA-256 semántico que excluye timestamps internos y metadatos técnicos.
- **Alternativas consideradas:** hash como ID; título como ID; JSON recibido sin canonicalización.
- **Consecuencias:** solo cambios significativos generan `update`; un fallo de fuente no infiere eliminaciones.

## ADR-011 — Frontera entre contenido de fuente y estado derivado de InfoCs

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** el hash de Fase 02 incluía `status`, relaciones y otros campos de InfoCs. Una ausencia o reclasificación podía aparentar una modificación administrativa.
- **Decisión:** `content_hash` usa una proyección cerrada del contenido observado de la fuente. Excluye estado de observación/publicación, categorías, tags, relaciones, coincidencias territoriales, procedencia, metadatos técnicos y tiempos internos. El diff usa la misma proyección. La matriz exacta se mantiene en `IDENTITY_AND_CHANGE_MODEL.md`. Un eventual estado oficial será un campo diferente.
- **Alternativas consideradas:** hash del record completo; mantener `status` dentro del hash; hashes separados para fuente y metadatos derivados.
- **Consecuencias:** una transición a `missing_from_source` o `quarantine` no genera `update` de fuente. Una clasificación InfoCs puede cambiar sin evento de contenido; su auditoría futura deberá resolverse en un histórico distinto si se necesita. Al ampliar campos observados se revisará explícitamente la proyección.

## ADR-012 — Finalizador único y transiciones de observación idempotentes

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** el hash calculado no quedaba necesariamente insertado en el record persistible; repetir ausencias podía llenar eventos y una reaparición modificada necesitaba semántica única.
- **Decisión:** `finalize_record()` devuelve un nuevo record validado, normalizado, identificado y con `technical.content_hash` calculado. El token de identidad incorpora un sufijo digest para evitar colisiones por normalización de caracteres externos. `reconcile()` exige estado previo finalizado, fuente y hora de comprobación. La primera ausencia tras éxito completo emite `missing_from_source`; las posteriores no. La reaparición emite un único `reappeared`, con `changed_fields` si cambió el contenido, sin `update` adicional. No hay transición automática a `withdrawn`.
- **Alternativas consideradas:** asignar hash en cada collector; evento diario por ausencia; emitir `reappeared` más `update`; conversión temporal automática a `withdrawn`.
- **Consecuencias:** los futuros collectors usan el core común y no mutan records por su cuenta. La posterior ADR-013 separa formalmente el candidato del record persistible. El sufijo digest cambia los IDs sintéticos previos de Fase 02; no se han persistido datos administrativos que migrar. La política completa de privacidad y de retirada evidenciada sigue fuera de alcance; una reobservación no limpia por sí sola `quarantine` ni `withdrawn` previos. Duplicados simultáneos con estados internos contradictorios provocan error explícito.

## ADR-013 — Candidate sin identidad y Record persistible estricto

- **Fecha:** 2026-09-21
- **Estado:** aceptada
- **Contexto:** el finalizador generaba identidad y hash, pero el único schema/modelo disponible exigía que el collector aportase un `id` provisional. Eso confundía la frontera de responsabilidades y podía inducir implementaciones incompatibles.
- **Decisión:** se introducen `RecordCandidate` y `record_candidate.schema.json`. El candidato no admite `id`, `technical.content_hash` ni `technical.identity_strategy`, y su único estado permitido es `active`; puede incluir solo metadatos técnicos disponibles antes del core. `Record` y `record.schema.json` exigen `id`, `technical.content_hash` e `technical.identity_strategy`. `finalize_record()` solo acepta candidatos y siempre devuelve un record final validado.
- **Alternativas consideradas:** mantener un ID ficticio; hacer opcional el ID en el record persistible; duplicar íntegramente el schema; aceptar indistintamente candidatos y records en el finalizador.
- **Consecuencias:** los collectors no generan identidad InfoCs, hashes semánticos ni estados internos. El schema final reutiliza las definiciones y los campos comunes del schema final para evitar duplicación amplia. La reconciliación actualiza directamente records finalizados al cambiar estados internos excluidos del hash, sin exponer ese detalle al collector.

## ADR-014 — Semántica incremental y persistencia canónica por record

- **Fecha:** 2026-09-23
- **Estado:** aceptada
- **Contexto:** el sumario diario del BOE contiene publicaciones de una fecha y no un snapshot completo de todos los registros existentes. Además, los records canónicos deben actualizarse sin reescribir una fuente JSON monolítica ni publicar datos reales antes del control de privacidad.
- **Decisión:** las fuentes declaran explícitamente una semántica de colección (`incremental_feed` o `snapshot`); BOE es `incremental_feed`. La ingesta BOE sólo produce `create`, `update` y `no_change`: nunca infiere ausencias entre sumarios diarios. Los records se almacenan como JSON individuales por fuente e ID en un `RecordStore` con nombres seguros, serialización determinista y reemplazo atómico temporal. Events se pueden producir en memoria, pero no se persisten en esta fase. La persistencia de records BOE reales queda bloqueada hasta existir el privacy gate.
- **Alternativas consideradas:** tratar cada sumario como snapshot; generar `missing_from_source` por ausencia diaria; un único JSON grande por fuente; SQLite/DuckDB como store canónico; escribir records reales antes de completar privacidad.
- **Consecuencias:** la reconciliación de ausencias sólo podrá ejecutarse para una fuente declarada `snapshot`. Un update conserva la ruta del record y sustituye únicamente su JSON mediante operación atómica. Los tests necesitan directorios temporales y no pueden validar el flujo escribiendo en `data/records/`. Manifests, health, eventos persistidos y automatización quedan para fases posteriores.

## ADR-015 — Privacy Gate obligatorio antes del RecordStore

- **Fecha:** 2026-09-23
- **Estado:** aceptada
- **Contexto:** el repositorio es público y la persistencia de datos BOE reales estaba bloqueada hasta convertir las reglas de privacidad en una barrera técnica común.
- **Decisión:** todo `Record` debe recibir una decisión `allow`, `quarantine` o `reject` después de `finalize_record()` y antes de `RecordStore.write()`. La ingesta aplica la decisión por record; el store vuelve a comprobarla. `quarantine` y `reject` no escriben payload ni evento público. Un fallo de configuración o ejecución del gate aborta el batch antes de nuevas escrituras.
- **Alternativas consideradas:** confiar en que cada collector invoque el gate; redacción automática; persistir primero y revisar después; clasificar todos los nombres como personas.
- **Consecuencias:** la detección v1 es determinista y conservadora, configurable en JSON y limitada a DNI/NIE personales validados, IBAN, proveedores de email de consumo configurados, teléfonos con contexto particular explícito y domicilios etiquetados como personales. Los NIF empresariales sólo se distinguen por forma y checksum conocidos; formas plausibles pero ambiguas se aíslan sin atribuirlas a una persona. No se hace OCR, IA, mirroring ni redacción. `reject` queda disponible para reglas explícitas, pero ninguna regla predeterminada lo emite. `allow` no garantiza anonimización ni aprobación jurídica. El `content_hash` y `Record.status` no se modifican. La persistencia real BOE sigue bloqueada hasta aprobación posterior de publicación.

## ADR-016 — Aprobación humana separada de privacidad

- **Fecha:** 2026-09-23
- **Estado:** aceptada
- **Contexto:** el Privacy Gate sólo detecta reglas automáticas; `allow` no acredita revisión de contenido, territorialidad ni advertencias humanas. El primer lote real debe poder limitarse y repetirse sin convertir esa decisión en estado administrativo del Record.
- **Decisión:** toda persistencia pública controlada exige una decisión separada `approved`, `hold` o `rejected`, procedente de una configuración JSON versionada por `official_id`. Un ID ausente de la lista queda en `hold`. Sólo `approved` más Privacy Gate `allow` puede llegar al RecordStore. El lote completo se valida antes de iniciar escrituras; Events no se persisten.
- **Alternativas consideradas:** interpretar Privacy Gate `allow` como aprobación; flag `persist=False`; aceptar IDs nuevos automáticamente; añadir una decisión de publicación al modelo Record.
- **Consecuencias:** la revisión humana queda fuera de `Record.status`, procedencia y `content_hash`. Los anuncios de riesgo o con contenido enlazado no revisado permanecen en `hold`. Los reemplazos son atómicos por archivo, pero la primera versión no hace rollback multiarchivo ante una falla de I/O.
