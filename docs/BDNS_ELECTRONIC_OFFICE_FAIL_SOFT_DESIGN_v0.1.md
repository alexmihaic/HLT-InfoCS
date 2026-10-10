# BDNS electronic office fail-soft design v0.1

Fecha de diseño: 2026-10-09. Estado: **diseño implementado y validado localmente;
pendiente validar una colección productiva posterior a la publicación**.

Decisión: **OPTION A — PROJECTION ONLY**. Resultado de diseño: `BDNS_ELECTRONIC_OFFICE_FAIL_SOFT_DESIGN_READY`.

## 1. Incident

Run GitHub `37785887112`, BDNS collection #12, 2026-10-08; manifest `run-v1-fa8364bb-c551-4092-82b1-8140fc60be33`. Scope: `region=56;from=2026-09-22;to=2026-10-07;temporal_policy=fecha-recepcion-provisional-v1`. Manifest: seen=33, normalized=0, finalized=0, errors=2; primary `item_ingestion_failure`.

El diagnóstico read-only reprodujo la ventana 33/33 y el fallo en posición 1: `enrichment_invalid_url / electronic_office`. El valor está presente, `urlsplit()` termina sin error, pero no reconoce scheme ni host. Primera regla incumplida: `scheme_not_https`; clasificación bajo el contrato actual: `STRUCTURALLY_MALFORMED`. No se expone valor, identidad del item ni componentes de la sede.

La reproducción usó código local funcionalmente equivalente al SHA del run `8eece6943c51ab12e1f9d81d7bb97bad8ba602a8`. Esta fase no hace red ni reproduce de nuevo el item. Tampoco inspecciona los otros 32 detalles.

## 2. Root cause

`BDNSConvocatoriaDetail.electronic_office` es un valor fuente opcional `str | None`, parseado desde `sedeElectronica`. El mapper exige que cualquier string sea una URL HTTPS estricta. Un valor no navegable aborta datos administrativos independientes que sí podrían ser válidos.

El problema es el alcance del fallo de una proyección opcional. El diagnóstico no demuestra que la convocatoria, el destino remoto, la reutilización o el resto de sus metadatos sean inválidos.

## 3. Current behavior

```text
detail.electronic_office
  → build_bdns_source_data(): _url(value)
  → valid_bdns_supplied_url(): _valid_bdns_url(schemes=("https",))
  → False → BDNSEnrichmentError("enrichment_invalid_url")
  → normalize_bdns_enriched() falla
  → ingest_bdns(): errors += 1, SOURCE_FAILURE, razón/familia segura
  → runner merge de métricas
  → _RunFault("item_ingestion_failure", position, detail, field)
  → run failed / exit 1
```

Históricamente, el `except _RunFault` añadía otro error. `errors=2` no demuestra
dos items defectuosos. El **SMALL_FOLLOW_UP** se resuelve en release closure:
`error_already_counted` evita duplicar únicamente el error de item ya fusionado;
si ingest no contabilizó error, se añade uno. No se recortan errores múltiples,
no se altera la contabilidad de otras ramas ni los manifests históricos.

Referencias: `enrichment.py:build_bdns_source_data`, `ingest.py:ingest_bdns`, `runner.py:_merge_ingestion_metrics` y captura `_RunFault`, bajo `src/infocs/fetch/bdns/`.

## 4. Desired behavior

Para la entrada tipada `None | str`:

| Valor fuente | Proyección canónica | Aviso técnico | ¿Error por este campo? |
|---|---|---|---|
| None | None; key omitida | ninguno | No |
| String que pasa `valid_bdns_supplied_url` | mismo literal | ninguno | No |
| Otro string | None; key omitida | `electronic_office_dropped_invalid_url` | No |

El parser de entrada conserva sus reglas de shape/tipos. No se capturan errores generales de parsing, normalización, modelos, Privacy o Publication para convertirlos en omisiones.

Después del mapping siguen finalización v2, Privacy, source eligibility, metadata publication, autorización y preflights Record/Event. No se garantiza publicación del item ni éxito del batch: cualquier otro blocker mantiene su comportamiento vigente. La restricción de extensión no vacía también permanece. Los Records incluidos requieren la señal territorial fuente, que aporta `impact_regions`; no fabricar datos para satisfacer esa restricción.

## 5. Options A/B/C

| Opción | Fidelidad y coste | Seguridad / compatibilidad | Decisión |
|---|---|---|---|
| A: sólo `electronic_office_url` | Pierde el valor no navegable; conserva exactamente el HTTPS aceptado. | Shape existente, minimización, ausencia ya soportada; sin migración de población válida. | **Seleccionada** |
| B: locator fuente + URL derivada | Conserva más fuente, pero añade campo, contrato de persistencia, Privacy y superficie/hash; exige evaluar versiones y posible transición. | No hay requisito demostrado que justifique esa ampliación para la sede. | No seleccionar ahora |
| C: sólo locator raw persistible | Mayor fidelidad literal, pero cambia el significado del campo y requiere policy de persistencia/Privacy y consumidores. | Incompatible con tratar `electronic_office_url` como URL estricta; tampoco resuelve por sí sola la navegación. | No seleccionar |

`BDNSRegulatoryBases.source_locator` demuestra la separación entre persistencia y navegación, pero su finalidad/fidelidad documental no obliga a reproducir ese modelo para la sede opcional. Bases reguladoras, extractos, documentos, `source_url` principal y otras fuentes quedan fuera de esta excepción.

## 6. Selected design

Añadir en `enrichment.py` una proyección pura y específica, por ejemplo `project_bdns_electronic_office_url(value)`, que entregue `(canonical_url, safe_warning_code)` siguiendo la tabla de §4. El mapper consume el primer componente. La observabilidad consume el segundo sin adjuntar la entrada.

Mantener `_url()` para extractos, el contrato de bases y `valid_bdns_supplied_url()` sin relajación. No añadir un catch general alrededor de `build_bdns_source_data()`. Si el mapper detecta otro fallo, se propaga como antes.

Reglas contractuales explícitas:

- **InfoCs does not repair source locators.**
- **Invalid optional locator does not become a clickable URL.**
- **Invalid optional locator does not invalidate unrelated canonical metadata.**

Sin trim, scheme inference, HTTP→HTTPS, percent encoding automático, host inferido, visitas, DNS, redirects ni reescritura. No conservar el raw omitido ni un hash suyo.

## 7. Canonical semantics

**`electronic_office_url` es la proyección literal del valor suministrado por BDNS que cumple la política estricta HTTPS de InfoCs y puede exponerse como enlace sólo tras superar los gates de publicación.**

No representa todos los valores raw de `sedeElectronica`; no certifica el organismo, el destino remoto, su disponibilidad o su seguridad TLS. La clickability elegible no obliga al frontend a crear enlace.

Los contratos actuales describen mapping all-or-nothing y sede recibida literal/material. La implementación debe documentar esta excepción específica en los contratos canónico y de enrichment; no tratarla como compatible sin explicación. Se conserva literalidad para el subconjunto aceptado. No hay requisito funcional demostrado de conservar el valor rechazado.

## 8. Hash compatibility

Auditoría local read-only del checkout `main` en `f1327ef6d6d735a500800fc675a1c8f70f45aeb0`; no se sincronizó ni consultó población remota en esta fase.

| Comprobación | Resultado |
|---|---:|
| Records BDNS inspeccionados | 44 |
| Hash version 2 / extensión 1.0 | 44 / 44 |
| Sede canónica presente / ausente | 5 / 39 |
| Sedes presentes válidas / inválidas bajo el validador estricto | 5 / 0 |
| Bytes originales iguales al roundtrip canónico con newline | 44 / 44 |
| Hash almacenado igual al hash recalculado | 44 / 44 |
| Payload fijo bajo la decisión A (válida→literal; ausencia→None) | 44 / 44 |
| Hash fijo bajo esa misma decisión | 44 / 44 |
| Privacy ALLOW / metadata publishable | 44 / 44 |
| Fallos de auditoría | 0 |

La comprobación de punto fijo reconstruyó objetos sólo en memoria; no implementó ni ejecutó el nuevo mapper y no escribió archivos de datos. Prueba compatibilidad para los valores ya almacenados, con todos los demás campos/timestamps iguales. El código futuro y la reproducción del item deben validarse después.

`_bdns_dict` omite None; `canonical_bdns_data` no incluye sede ausente. Un raw inválido nuevo no entra en payload/hash. Dos observaciones idénticas salvo un raw omitido distinto producen la misma proyección/hash. Una sede válida permanece material y literal: si cambia, debe seguir cambiando el hash.

**NO EXISTING RECORD MIGRATION; NO BDNS HASH CUTOVER; NO CONTENT_HASH_VERSION CHANGE.** Mantener hash v2, normalizer `2.0.0` y extensión `1.0`. No modificar el algoritmo hash ni materializar de nuevo la población. Si en una observación futura una sede antes válida pasa a ser inválida, el campo desaparece en la nueva proyección: esa diferencia debe seguir el procesamiento ordinario y sus gates, no una migración ni un Event artificial del fix.

## 9. Schema impact

`BDNSCanonicalData.electronic_office_url` ya es opcional. `_bdns_dict` lo omite al ser None; `_source_data_from_dict` carga ausencia con el default None. El schema Record permite ausencia y comparte `candidate_core` con el schema Candidate. Los demás campos mantienen la extensión significativa y sus bindings.

No modificar `src/infocs/models.py`, `schemas/record.schema.json` ni `schemas/record_candidate.schema.json`. No cambiar `extension_version`, `schema_version`, hash contract ni CUTOVER. No persistir warnings, raw locator, repaired URL, `clickable` ni flags de calidad dentro del Record.

## 10. Privacy/publication impact

Privacy inspecciona los campos canónicos retenidos. Al omitirse una sede no aceptada, no hay raw de ese campo publicado o almacenado que deba conservarse para inspección; los demás campos siguen con idéntica cobertura.

Una sede HTTPS que pasa sintaxis sigue siendo inspeccionada íntegramente, incluyendo path/query/fragment y variantes decoded. PII detectable o encoding UTF-8 inválido como `%FF` debe conservar su bloqueo Privacy. **No usar un fallo Privacy para descartar una URL sintácticamente válida y publicar el resto.**

Publication `_enriched_metadata_is_publishable` ya valida las URLs presentes y excluye None de esa iteración; no exige sede. Mantener sin cambios esa política, source eligibility, atribución, authorization exacta y Record/Event preflights. La inspección local confirma ALLOW/publicación en 39 Records que ya carecen del campo; no garantiza que una convocatoria nueva supere los otros gates.

## 11. Frontend impact

El adapter `site/src/lib/data/canonical.ts` proyecta opcionalmente `electronicOfficeUrl`; `bdnsRecordView.ts` crea el grupo sólo si existe. `BDNSHumanReadableDetail.astro` renderiza condicionalmente ese grupo como **texto**, con `data-pagefind-ignore`, no como enlace.

Ausencia: ningún grupo, enlace, placeholder ni aviso público. Sede válida: mismo literal y superficie vigente. No modificar frontend, Pagefind o decisiones de enlaces en esta implementación. La proyección es apta para una futura navegación aprobada, no autorización para introducirla aquí.

## 12. Diagnostics

Retener `electronic_office_dropped_invalid_url` en un canal operativo separado de errores:

1. Helper específico de enrichment entrega el código estático sin raw.
2. `diagnostics.py` declara una allowlist separada de warning codes. No añadirlo a `BDNS_ITEM_DETAIL_REASONS` ni usarlo como `safe_reason` de fallo.
3. `BDNSIngestionResult` añade `safe_warning_codes: tuple[str, ...] = ()`, fuera de métricas y del Record. Ingest obtiene el aviso del mismo helper específico; no duplica lógica URL.
4. `BDNSRunnerResult` agrega los códigos en contadores tipados source-specific
   `safe_diagnostics`, conforme a la decisión de implementación. Sólo expone
   counts positivos; puede haber diagnósticos en success con errors=0. Los
   failure details existentes siguen ausentes en success.
5. `workflow_safety.py` valida el objeto opcional cerrado, código conocido y
   count entero no negativo (no bool); Step Summary presenta sólo avisos seguros.
   El workflow ya invoca `validate-result --github-summary`, sin cambio YAML.

No URLs, host, paths, identificadores, hashes del raw ni mensajes de excepción. Ningún incremento de `metrics.errors`, cambio de exit code, checkpoint o salud por el aviso. No ampliar `RunMetrics`, schema de Manifest/Health ni persistir warnings en esos artefactos canónicos. El resultado operativo/Step Summary es observabilidad técnica, no dato administrativo.

Actualizar `enrichment_url_field_class` para que, ante un **error bloqueante** `enrichment_invalid_url`, enumere sólo las familias que todavía pueden causar ese fallo: bases y extractos. La sede inválida es un warning separado. Así una base inválida junto con sede omitida no se etiqueta erróneamente como `multiple_url_families`. Conservar las clases/códigos históricos en allowlists; no degradar los diagnósticos D3.2 existentes.

## 13. Test plan

Fixtures únicamente sintéticas; no copiar el locator real. Plan de regresiones
implementado y validado en los tests dirigidos de la corrección:

| Caso | Expectativa |
|---|---|
| None | omisión, sin warning ni error |
| HTTPS válido con case/path/query/fragment | literal exacto conservado |
| Sin scheme/host | omisión + warning; enrichment continúa |
| HTTP válido | omisión; sin upgrade |
| Whitespace, controles, backslash, percent escape inválido, userinfo, IP, puerto/DNS/local inválidos, exceso de longitud | omisión + warning; validador estricto sigue False |
| Sede inválida + otros datos oficiales válidos | resto de SourceData idéntico; finalize/preflight continúan |
| Sede inválida + PII en finalidad u otro campo retenido | Privacy sigue bloqueando |
| HTTPS sintácticamente válido con PII literal/decoded o `%FF` | Privacy sigue bloqueando; no descarte fail-soft por Privacy |
| Sede inválida + extracto/bases inválidas | error URL real conservado; familia bloqueante correcta |
| Sede inválida + decimal/documento/clasificación inválidos | mismo error específico; no catch general |
| Canonical sin sede vs producido desde un raw inválido, demás datos/timestamps iguales | mismo payload canónico/hash v2 |
| Cambio de raw inválido a otro raw inválido | mismo payload/hash; warnings no materiales |
| Fixture válida preexistente | mismos bytes/hash; cambiar una sede HTTPS válida sigue siendo material |
| Ingest y runner con sede inválida pero demás gates válidos | success, errors=0, aviso cerrado, persistencia/Event ordinarios en Stores temporales |
| Resultado success con warning | exit 0, sin failure details, Manifest principal intacto, staging habitual |
| Warning arbitrario/tipo incorrecto | rechazo por workflow; ningún valor fuente en resultado/summary |
| Warning + fallo real posterior | primary/detail/position reales intactos; warning no añade error |

El test actual `test_invalid_urls_all_three_fields_fail_closed` necesita separar sede de bases/extractos; no cambiar las expectativas estrictas de estos últimos. Las regresiones de familia deben distinguir warnings de blockers. No retirar tests Privacy ni constructores canónicos que rechazan HTTP en `electronic_office_url`.

## 14. Implementation surface

Archivos de la implementación con observabilidad operativa completa:

| Archivo | Cambio futuro |
|---|---|
| `src/infocs/fetch/bdns/enrichment.py` | proyección específica y uso en el mapper; `_url`/validador intactos |
| `src/infocs/fetch/bdns/diagnostics.py` | catálogo cerrado de warnings y familias de errores bloqueantes |
| `src/infocs/fetch/bdns/ingest.py` | warning opcional no-error en resultado operativo |
| `src/infocs/fetch/bdns/runner.py` | agregación/serialización segura; señal explícita del double-count en release closure |
| `src/infocs/fetch/bdns/workflow_safety.py` | allowlist/shape del warning y Step Summary seguro |
| `tests/unit/test_bdns_enrichment_gates.py` | mapping, otros gates y preflight |
| `tests/unit/test_bdns_canonical_enrichment.py` | payload/hash/roundtrip compatible |
| `tests/unit/test_bdns_ingest.py` | warning separado, no error, familias |
| `tests/unit/test_bdns_runner.py` | success/errores reales/staging/exit semantics |
| `tests/unit/test_bdns_workflow_safety.py` | aceptación cerrada, rechazo de arbitrarios y summary |
| `collectors/bdns/CANONICAL_ENRICHMENT_CONTRACT.md` | significado de proyección y materialidad |
| `collectors/bdns/ENRICHMENT_GATE_CONTRACT.md` | excepción fail-soft acotada; Privacy intacta |
| `collectors/bdns/RUNNER_CONTRACT.md` | warnings seguros fuera de Manifest/métricas |

Sin cambios previstos en models/schema/normalizer básico/hash/Privacy/Publication/Events/frontend/workflow YAML. Tampoco `PROJECT_STATE.md`, datos, baseline evidence, CUTOVER o health. El documento actual es el único cambio autorizado de esta fase.

## 15. Rollout plan

1. Autorizar implementación de §14, con tests dirigidos sintéticos y comprobación de hashes/bytes existentes. Las invariantes de privacidad y URL permanecen estrictas.
2. Revalidar el item 1 en memoria con guards de no escritura y presupuesto explícito. Su enrichment debería superar la sede, pero puede aparecer otro blocker: no ampliar scope automáticamente.
3. Autorizar por separado una validación read-only de toda la ventana (esperada 33; comprobar drift primero), con presupuesto y guards. No se conoce el estado de los otros 32 items.
4. Publicar sólo tras validación y permiso expreso. Ningún collector/workflow/migración está autorizado por este diseño; health se recuperará mediante el procesamiento normal, sin edición manual.
5. **SMALL_FOLLOW_UP resuelta en release closure:** señal interna explícita para
   no contar dos veces el error de item ya fusionado. Regresiones de errors=0/1/3,
   otros fault codes, Manifest/health/exit y diagnósticos; primary estable.

Validaciones completadas: implementación dirigida 97 tests + 224 subtests;
replay read-only estable 33/33, dos sedes descartadas, cero blockers; release
closure cinco regresiones específicas y una suite oficial de 481 tests PASS.
La auditoría reconciliada cubre 45 Records con bytes/hash v2 compatibles.
Esto no declara healthy a BDNS ni sustituye la siguiente ejecución productiva.

## 16. GO/HOLD

**GO — `BDNS_ELECTRONIC_OFFICE_FAIL_SOFT_DESIGN_READY`.**

La validación HTTPS permanece idéntica; la excepción propuesta reduce sólo el alcance del fallo de la sede opcional. No hay reparación ni raw persistido. La auditoría local demuestra punto fijo de bytes/hash en 44 Records, y el modelo/schema/gates/frontend ya soportan ausencia. No se necesita migración, hash cutover, bump de versiones ni nuevos campos canónicos.

La implementación local ha pasado tests y replay read-only; el cierre permite
publicar la corrección dentro de la allowlist aprobada. No se ha ejecutado una
colección productiva posterior al release ni se garantiza su resultado. Esa
validación pertenece a la fase autorizada posterior.
