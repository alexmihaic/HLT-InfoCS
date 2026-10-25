# PLACSP Source Contract v0.1 — Wave 1

Fecha: 2026-10-14. Estado: `DESIGN_READY / PUBLICATION_HOLD`.

Documento de diseño, no configuración ejecutable. No autoriza transporte, collector, escritura, publicación ni automatización. Se recomienda únicamente B/1044. El contrato canónico complementario está en [Source Data Schema Design](PLACSP_SOURCE_DATA_SCHEMA_DESIGN_v0.1.md).

## 1. Fuente y canal

Propuesta: `source.id = placsp`, publicador Dirección General del Patrimonio del Estado / Ministerio de Hacienda, canal `1044`, plataformas agregadas excluyendo contratos menores. Raíz acreditada en las investigaciones anteriores:

`https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom`

Fuera: A/643, menores/1143, otros canales, endpoints de detalle, búsquedas, ZIP históricos, HTML, documentos y portales de origen. La cobertura depende de las entidades participantes en agregación; no es toda la contratación española ni toda la contratación de Castellón. La red recibe metadata nacional; el filtrado territorial es local, no un filtro servidor acreditado.

En una futura definición conforme a `schemas/source.schema.json`: `access_type=feed`, `status=under_review`, `reuse.status=conditional`, `mirror_documents=false`, `fulltext_publication=false`, `default_document_policy=link_and_hash`. Esta última etiqueta del schema no obliga a incluir documentos: aquí se excluyen. `allowed_hosts` es una lista de hosts, no admite el objeto anidado del borrador histórico. Los guards de origen/puerto/ruta pertenecen a una política específica del collector, no a una ampliación implícita del schema de fuente. El contrato operativo separado declarará `incremental_feed`; ese campo no existe en el schema Source actual.

`docs/INFOCS_SPEC_v1.md` y `collectors/pcsp/` usan la denominación histórica `pcsp`. Se propone `placsp` como ID nuevo explícito, coherente con las investigaciones, no como alias intercambiable ni renombrado automático. Su aprobación deberá reflejarse en el registro de fuente futuro. No hay configuración productiva PLACSP localizada ni fixtures fuente: `collectors/pcsp/fixtures` contiene sólo `.gitkeep`.

## 2. Evidencia autoritativa

Base de esta revisión: `main`, HEAD `e144b5c6b3f7040aeb937502d59da02981f7b7bb`; referencia local `origin/main` igual al comenzar, sin fetch. No acredita el estado remoto actual. Siete archivos untracked de investigación preexistentes; 173 archivos bajo `data/`. No se han abierto las cohortes privadas.

| Referencia / clase de evidencia | Qué permite afirmar | Qué no permite afirmar |
| --- | --- | --- |
| `PLACSP_SOURCE_AUDIT_AND_SAMPLE_v0.1.md`, §§2–7, 14–17 — auditoría histórica, `OFFICIAL_DOC / OBSERVED_SAMPLE` | Universo B, campos/conceptos, señales territoriales distintas, reutilización condicionada | Vigencia comprobada hoy de todos los paths/listas o permiso de cada documento |
| `PLACSP_COLLECTOR_DESIGN_v0.1.md`, §§5–7, 14–18, 23–25 — diseño histórico | Unidad carpeta, mapeos propuestos y riesgos de paginación | Implementación actual ni resolución de todos sus pendientes |
| `PLACSP_IDENTITY_SNAPSHOT_GATE_v0.1.md` — contrato histórico | Prescripción oficial de reutilización de ID, updated y tombstone ref | Su conclusión inicial inconclusa no describe el resultado posterior |
| T1 v0.5, `hash_contract` íntegro — contrato local congelado | URIs, paths de evidencia, literalidad, multiplicidad y cuatro vectores | El fingerprint no es hash productivo ni identifica notices |
| `PLACSP_LONGITUDINAL_EVIDENCE_STRATEGY_v0.2.md`, §§9–12 | Regla estricta de STABLE_UPDATE, unidad Atom/carpeta, controles y privacidad | Automatización ni generalización universal |
| Revisión formal aceptada en el chat de esta tarea — resultado previamente verificado | C1=250; C2=132 encontrados; cuatro STABLE_UPDATE; cero contradicciones en la muestra; `PLACSP_IDENTITY_GATE_EVIDENCE_ACCEPTED` | No se ha vuelto a verificar C1/C2 en Wave 1; no se copian hashes ni artefactos privados |
| Acreditación de dos orígenes aceptada en el chat y política recogida en estrategia §8 | Excepción explícita sólo para paginación 1044 | Confianza global en enlaces del servidor |
| Modelos, schemas, identity/hash, Privacy, stores y runners actuales — `REPO_REFERENCE` | Contratos efectivamente implementados | Que PLACSP ya sea aceptable para los gates actuales |

Todos los documentos locales solicitados existen. Los documentos históricos se preservan, incluso sus decisiones anteriores. Este diseño registra el alcance nuevo sin reescribirlos. Cero consultas oficiales en esta fase; las condiciones normativas se citan como previamente auditadas, no como verificación jurídica actual. Antes de implementación/transporte será necesaria la revisión oficial vigente exigida por `AGENTS.md`, en una fase autorizada.

## 3. Unidad de recopilación

Un Record representa el estado fuente más reciente observado de una unidad Atom/carpeta del canal 1044, no todo el expediente reconstruido ni una publicación individual. Categoría recomendada: `procurement`.

| Concepto | Contrato |
| --- | --- |
| Unidad Atom | Identidad de entrada mantenida entre representaciones según evidencia muestral |
| Carpeta / expediente | Unidad administrativa agrupada; su referencia de negocio no es globalmente única |
| Anuncio individual | Subestructura de carpeta; continuidad e IDs individuales no acreditados por v1 |
| Actualización | Nueva representación de la misma unidad; sólo cambios canónicos materiales producen update |
| Referencia documental | Recurso relacionado, no identidad de Record ni autorización de descarga |
| Tombstone | Señal de sindicación referida al Atom ID; no estado jurídico |

No usar `procurement.notice` ni `procurement.award` por contener avisos de esos tipos. Un update InfoCs dice que cambió metadata canónica; no afirma adjudicación, ejecución, modificación contractual o resolución por sí solo.

## 4. Identidad de negocio

Componentes de comprobación: `[feed_id, authority_scheme, authority_structured_id, contract_folder_id]`. Conservar la prioridad v1 para la señal de negocio: `ID_PLATAFORMA`, `ID_OC_PLAT`, `DIR3`; primer scheme presente, único valor distinto, sin fallback si es ambiguo/inválido. Nunca NIF, nombre de órgano o título. La prioridad de una futura resolución territorial de autoridad es un contrato distinto y no modifica esta clave.

`ContractFolderID` es referencia/agrupación acotada por autoridad y canal, no ID primario ni clave global. Componentes obligatorios ausentes, ambiguos o con whitespace externo inesperado: no reparar; `identity_missing` o `structured_fields_inconsistent`, sin candidato publicable.

Los hashes privados de C1/C2 no se usarán como IDs públicos ni como lookup productivo. El diseño utiliza los identificadores fuente aprobados, no la cohorte.

## 5. Atom ID e identidad InfoCs

Recomendación cerrada para aprobación: `source.id=placsp`, `source.official_id = "1044::" + entry.id_literal`. El delimitador `::` selecciona expresamente la propuesta del collector histórico frente al `:` del gate inicial; no cambia los hashes de evidencia ni migra datos existentes. El canal es literal controlado, seguido del Atom ID exacto; no trim, casefold, normalización Unicode, decodificación o reescritura de URL.

Core `identify()` usa `official_id` y calcula su digest sobre el valor exacto. Su slug legible sí se normaliza y trunca, pero no sustituye ese digest. La forma interna es `infocs:placsp:<token>-<digest>`; no es el identificador oficial. El sufijo actual es SHA-256 truncado a 16 hex, no una prueba de imposibilidad de colisión: preflight deberá verificar concordancia de identidad al encontrar un Record previo y bloquear cualquier colisión.

No activar `case_number`, `canonical_url` ni `composite_fingerprint` como fallback PLACSP: podrían mezclar carpetas, normalizar locators o depender de textos mutables. Un ID ausente/contradictorio produce hold/error seguro, no una nueva clave aproximada.

Mismo Atom ID con negocio incompatible: revisión contractual antes de sustituir el Record, pues puede ser corrección o reutilización indebida. Mismo negocio con varios Atom IDs: ambigüedad, no merge ni contradicción automática. Cambio de autoridad/expediente no prueba un objeto nuevo; nunca reasignar identidad automáticamente. Mantener separado cualquier canal futuro.

## 6. Alcance territorial

Dos ejes independientes: órgano contratante y lugar de ejecución declarado. Ubicación del proveedor nunca es señal territorial del contrato. Los motivos específicos se representan usando los enums existentes de Provenance, con detalles técnicos versionados, sin nuevo enum global.

| Decisión | Evidencia suficiente / consecuencia |
| --- | --- |
| `INCLUDE` | Al menos una señal exacta: órgano resuelto a Castellón mediante directorio institucional versionado, o ejecución con código provincial ES522/NUTS validado, o código municipal inequívoco de catálogo oficial validado |
| `OUT_OF_SCOPE` | Ambos ejes relevantes resueltos de manera suficiente, sin señal local, y evidencia positiva de ámbito fuera de la provincia; no equivale a contrato inexistente |
| `UNRESOLVED` | Sin señal local y al menos un eje ausente/ambiguo/amplio/no resoluble; una ejecución externa no excluye por sí sola un órgano local desconocido |

`authority_match` identifica inclusión por órgano; `official_code_match` por código de ejecución; `municipality_match` sólo por resolución municipal acreditada. Nunca `explicit_text_match` automático para título. ES522 permite provincia, no municipio. ES52, España o ámbito autonómico/estatal amplio no bastan para incluir.

Municipios múltiples: incluir si existe al menos uno inequívoco local, conservar la pluralidad en la extensión y no rellenar el `geography.municipality` singular. Contrato provincial local: provincia, no todos sus municipios. Autonómico/estatal: puede incluirse por ejecución local exacta; no por nivel administrativo solamente. Órgano local con ejecución externa: incluir por órgano, con ejecución expresada aparte. Ámbito parcialmente conocido: mantener la incertidumbre sin repartir importes ni imputar ejecución local completa.

Para evitar mezclar ejes, se recomienda dejar `geography` Core ausente inicialmente; la extensión expresa ejecución y Provenance la razón de inclusión. `authority.administration_level` y el nivel Core coinciden o son ambos null; nivel se deriva de catálogo, no del nombre. Directorio de autoridad, crosswalk municipal y catálogo territorial pinned son dependencias pendientes. Sin ellos sólo podrán usarse señales exactas ya verificadas; nunca completar por similitud. Ampliar a alcance supraprovincial requiere aprobación.

## 7. Paginación

Orígenes de transporte autorizables, exclusivamente canal 1044:

- `https://contrataciondelsectorpublico.gob.es:443`
- `https://contrataciondelestado.es:443`

Scope de segmentos: `/sindicacion/sindicacion_1044/`. Resolver referencias con `urljoin` contra base autorizada; comprobar la referencia antes de resolver para impedir que traversal desaparezca durante resolución y validar después el destino completo. No confiar en un `xml:base` que amplíe autorización; rechazar bases ambiguas/no aprobadas.

HTTPS, hostname exacto, puerto efectivo 443, sin userinfo, IP, fragmento, controles, whitespace, backslash ni escapes inválidos. Rechazar dot segments, canal parecido, separadores codificados y dobles codificaciones ambiguas en path. Query legítima se conserva sin publicarla. Cero redirects automáticos; política inicial futura: rechazar todo redirect. Permitir alguno requerirá diseño/test explícito por salto y presupuesto, nunca confianza transitiva. Detectar ciclos y múltiples next incompatibles. Usar Atom `link@rel="next"`, no `@ref`: la mención histórica a `@ref` en audit §17 no define la extracción.

La política no se comparte globalmente con BOE/BDNS/BOP, ni habilita rutas públicas de ficha/documentos. Un último archivo con menos de 500 entries no demuestra fin; únicamente next ausente o una frontera temporal comprobada puede terminar el intervalo solicitado.

## 8. Semántica temporal

`feed.updated` y `entry.updated`: timestamps técnicos de fuente con offset; transporte/control/orden, fuera del payload administrativo y del hash semántico. `detected_at` y `last_checked_at`: tiempos InfoCs aware, normalizados por Core a UTC; preservar `detected_at` previo. Ninguno sustituye fecha de anuncio.

`NoticeIssueDate`: emisión de aviso asociado a tipo, no asumir automáticamente publicación efectiva ni aviso inicial. `dates.published_at` sólo si una regla acreditada identifica un aviso inicial DOC_CN inequívoco, con semántica de publicación aplicable y fecha de día; si no, omitir. No elegir la fecha mínima de múltiples DOC_CN sin demostrar cuál es inicial. El diseño histórico lo consideró resuelto a nivel de campo; aquí se delimita la selección aún no probada en B/1044.

`dates.event_at` ausente en el alcance inicial: no hay un acontecimiento contractual único de carpeta acreditado. Deadline queda separado. Si una fecha administrativa es timestamp, conservar valor/offset/precisión en extensión tipada; no truncarla a date Core. Un timestamp sin zona no se repara.

## 9. Incrementalidad y ausencia

Modo recomendado: `incremental_feed`, no `complete_scope` ni snapshot universal. Bootstrap con horizonte explícito de entry.updated todavía pendiente de aprobación/calibración; no inventar fecha de inicio ni inventario completo de expedientes vigentes. `rel=next` es navegación, no checkpoint estable ni autorización de backfill.

Watermark futuro por canal, frontera inclusiva y empates de IDs, avance sólo tras lote íntegro, controles y persistencia autorizada. Observaciones tardías/desordenadas son riesgo pendiente; no fijar solapamiento arbitrario. Una frontera temporal requiere confirmar orden y manejar empates; límite de seguridad nunca equivale a completitud.

Versiones del mismo Atom: misma identidad y timestamp con payload material divergente aborta; versiones posteriores coherentes pueden elegir último estado fuente sin recrear toda la historia. Versión anterior encontrada no debe revertir un Record más reciente. Será necesario diseñar dónde retener el watermark por objeto fuera del hash; no hay tal estado PLACSP hoy. Dos Atom distintos para el mismo negocio se aíslan como ambiguos. No copiar la regla histórica de abortar toda variación entre versiones como si toda actualización legítima fuera un duplicado incompatible.

Ausencia de páginas/muestra: no `missing_from_source`, `withdrawn` ni deleted. Tombstone no borra Record ni genera Event, no cambia categoría/status; referencia y when sólo en observación técnica minimizada. No se interpreta cancelación jurídica.

## 10. Seguridad y secuencia futura

Transporte streaming con lector EOF público validado: headers/read/close, sin response.fp, sin buffers integrales. Validar framing, status, MIME, encoding y raíz Atom por expanded QName. DTD/ENTITY/XXE bloqueados entre chunks; namespaces auxiliares tolerados, paths contractuales sólo por URI exacta. Límites de profundidad, nodos y texto deberán fijarse y probarse antes de transporte productivo. XML completo para páginas que se declaren completas; captura acotada de control sólo acredita la cabeza examinada.

Los presupuestos de evidencia (5 GET, 32 MiB, 2.500 entries, 300 s, cero retries, control reservado) no son límites productivos aprobados. La suposición histórica de página completa siempre <=8 MiB está invalidada; límite productivo `NEEDS_RECALIBRATION`, sin elegir ahora 16/32/64 MiB. Llegar a cualquier límite antes de cubrir el intervalo: incomplete, sin checkpoint ni publicación del lote. Proponer transporte secuencial y cero retries iniciales; cualquier política posterior requiere aprobación.

Orden conceptual recomendado: Fetch → XML Validation → Structured Extraction → contrato de fuente → Territorial Gate → Candidate → finalize → lectura de prior/conservación detected_at → Privacy → elegibilidad de fuente y publicación de metadata → autorización → preflight Record/Event de todo el lote → control raíz → Events luego Records → Manifest → Health → checkpoint sólo después de éxito completo según contrato futuro.

Auditoría actual: BOE prepara/preflighta operaciones de lote en `ingest_boe_summary`, después escribe Events/Records; runner añade Manifest/Health. BDNS finaliza, conserva detected_at, pasa Privacy/publicación/autorización y preflight por item; su runner procesa items y hace control search al final, después de posibles escrituras. No copiar ese orden de escrituras a PLACSP: exige preparación global antes del control final y la materialización. RecordStore reevalúa Privacy; EventStore valida binding de autorización, no reutilización. No existe transacción multiarchivo ni rollback global; preflight reduce riesgos, no los elimina.

## 11. Reutilización

`OFFICIAL_DOC` previamente auditada: metadata con condiciones de origen, integridad, actualización y no patrocinio; no licencia EUPL de datos por ser licencia de OpenPLACSP. Cita prevista: “Origen de los datos: Ministerio de Hacienda”. Conservar referencia/versiones de condiciones y fecha de revisión real, no poner la fecha de Wave 1 como `terms.checked_at` de una consulta inexistente.

Normativa/documentación no reconsultadas hoy. Revalidación vigente y política campo a campo necesarias antes de activar fuente. Derechos de documentos de terceros, mirror, PDF y fulltext siguen no resueltos y excluidos. No se promete publicación automática.

## 12. Privacidad

Excluir desde extracción adjudicatarios, NIF/CIF, personas licitadoras, contactos, domicilios particulares, representantes, firmas y documentación. Metadata institucional y códigos no son inmunes a PII: inspeccionar identificadores, nombres, título, descripción aprobada y URLs completas, incluidas variantes decodificadas sin reescribir lo persistido.

Privacy actual no reconoce todos los nombres y su enumeración de source_data sólo conoce BDNS; tampoco inspecciona automáticamente toda autoridad/source_url Core. La futura rama PLACSP deberá cubrir todos los strings retenidos y pruebas de PII encubierta en IDs/URLs. Un fallo de inspección/configuración aborta; allow no es dictamen jurídico. No usar XML raw como almacenamiento alternativo. Cohortes privadas nunca entran en fixtures o Records públicos; sus hashes son correlacionables.

## 13. Publicación y Events

Reutilizar SourcePublicationEligibility `eligible/hold` y, para la decisión por Record, el catálogo existente `approved/hold/rejected` de PublicationDecisionType, con adaptador PLACSP separado, no la configuración manual BOE ni los predicados BDNS. Si se reutiliza ese tipo fuera de BOE deberán separarse sus validadores source-specific; no crear un enum sólo por renombrar estados.

Ahora: `hold/reuse_policy_unresolved` mientras no exista revisión vigente operativa, registro de fuente aprobado y superficie PLACSP cubierta por Privacy. Futuro approved requiere canal/origen legítimos, identidad coherente, metadata permitida, URL pública específica validada, territorio INCLUDE y Privacy allow. Hold por incertidumbre/campo indispensable pendiente; rejected por contenido fuera del alcance o familia explícitamente prohibida. Nunca sobreescribir quarantine/reject.

Authorization ligada a record_id/source_id/content_hash/policy_id, sólo después de gates. Create si no hay prior; update si cambia la proyección semántica bajo igual contrato; no_change sin Event. Avance Atom, paginación, aparición de notice por sí sola o tombstone no generan Event autónomo. No Events administrativos derivados de estados jurídicos supuestos. Mantener limitación Core: transiciones A→B repetidas comparten event_id, no son ocurrencias independientes.

## 14. Errores y diagnósticos

Catálogo propuesto, aún no enums implementados. Counts/códigos cerrados, nunca XML, IDs, nombres, URLs, payload o exception raw. No ampliar RunMetrics/Manifest arbitrariamente; nuevos safe messages futuros necesitan contrato/schema/tests propios.

| Código propuesto | Alcance / política |
| --- | --- |
| `transport_failure`, `invalid_http_framing`, `invalid_content_type`, `invalid_xml`, `xml_security_rejection`, `invalid_atom_root` | Abortan lote; sin avance/checkpoint |
| `pagination_unsafe`, `pagination_loop`, `budget_exhausted`, `source_changed_during_run` | Abortan completitud del lote |
| `identity_missing`, `identity_contradiction`, `duplicate_incompatible`, `structured_fields_inconsistent` | Error contractual; impedir sustitución insegura; contradicción/duplicado incompatible aborta lote |
| `territory_unresolved` | Hold/exclusión segura contabilizada, no OUT_OF_SCOPE; no nueva publicación del item |
| `public_source_url_unverified`, `reuse_policy_unresolved` | Publication hold, sin autorización |
| `invalid_administrative_date`, `invalid_amount`, `unsupported_codelist` | Campo material presente inválido: hold del item, no ocultarlo como ausencia; si impide coherencia del lote, abortar |
| `optional_description_omitted`, `optional_publication_date_unresolved` | Diagnósticos non-error sólo para campos cuya omisión explícita está permitida; no increments errors por sí solos |
| `privacy_engine_failure`, `publication_policy_failure`, `record_preflight_failure`, `event_preflight_failure` | Abortan lote antes de escrituras |

Campo opcional ausente no es error. Fail-soft no repara fuente ni puede borrar un importe/código material inválido para simular éxito. URL principal/título/identidad son indispensables: no inventar placeholders ni fallback al feed. Un hold conserva cualquier Record previo; no degrada datos válidos. Política de checkpoint ante holds de items materiales queda conservadora: no avance hasta resolución, salvo futuro contrato aprobado de backlog separado.

## 15. Limitaciones, decisiones pendientes y GO/HOLD

Decisiones recomendadas para aprobación: unidad Atom/carpeta; official_id literal namespaced; procurement; sólo 1044; extensión tipada; territorio por ejes; incremental sin inferir ausencia; Privacy/publicación fail-closed; sin documentos/resultados/ganadores.

Pendientes bloqueantes de ejecución/publicación, no resueltos por este diseño: paths y cardinalidades B de título/nombre/URL de ficha; selección de aviso inicial; listas/versiones de códigos y moneda; directorios territoriales; superficie Privacy; política vigente de reutilización; tamaño productivo/horizonte/watermark y estado técnico por objeto; registro del nombre placsp frente a pcsp; tests de unión y hashes. Sin evidencia no se pueblan esos campos ni se activa producción.

`GO` de diseño: hay una integración consistente con Core y límites explícitos. `HOLD` de implementación/publicación: requiere aprobación de ambos documentos y fases posteriores; el gate empírico aceptado no elimina estos gates. Next propuesto: Wave 2 de mapping y fixtures offline, sin autorización automática ni consultas de fuente implícitas. Los puntos no acreditados deberán obtener evidencia en una investigación autorizada separada, no con fixtures inventadas.

Actividad Wave 1: dos documentos; source GET=0; acceso C1/C2=0; tests/builds=0; cambios de producto/datos=0; stage/commit/push=0.
