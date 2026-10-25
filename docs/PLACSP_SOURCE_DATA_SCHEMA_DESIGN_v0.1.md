# PLACSP Source Data Schema Design v0.1 — Wave 1

Fecha: 2026-10-14. `DESIGN_READY / IMPLEMENTATION_NOT_AUTHORIZED`.

Propuesta tipada, no JSON Schema ejecutable ni código Python. Sólo B/1044. Complementa [Source Contract](PLACSP_SOURCE_CONTRACT_v0.1.md); no modifica el diseño histórico, T1 ni cohortes. No contiene datos fuente reales ni hashes privados.

## 1. Auditoría del Core existente

Inspección local en `main`, HEAD `e144b5c6b3f7040aeb937502d59da02981f7b7bb`. Todos los documentos requeridos existen. Las observaciones históricas se distinguen del estado de código actual.

| Superficie actual | Hecho verificado / consecuencia |
| --- | --- |
| RecordCandidate / Record | Candidate activo, sin ID/hash/estrategia; finalize produce Record. Title y source_url son obligatorios; no se pueden omitir para salvar un mapping incompleto |
| SourceReference | id y official_id opcional; identify prioriza official_id exacto para digest |
| ProcurementDetails | Sólo expediente, cpv y awardee; no notices, estado fuente, deadline, procedimiento ni localizaciones con roles |
| FinancialAmounts / Money | Seis roles; value string decimal y currency de tres letras. Modelo/schema permiten negativos, no garantizan semántica económica ni pertenencia real a ISO 4217 |
| RecordDates | published_at/event_at date; detected_at/last_checked_at timestamp aware UTC. No timestamp administrativo en dates Core |
| Authority / Geography | Authority/nivel admiten conocimiento parcial; Geography singular y sin rol órgano/ejecución. No encaja automáticamente con localizaciones múltiples |
| Documents | Enlaces/metadata/copia; no obliga a descargarlos. Este proyecto inicial los dejará ausentes |
| Provenance | Collector/version/normalizer_version, matches con enums genéricos; clasificaciones derivadas fuera del hash |
| SourceData | `bdns: BDNSCanonicalData` obligatorio; modelos y candidate_core lo limitan a bdns/grants.call |
| finalize / semantic_payload | Ambos acceden expresamente a bdns. Hash v2 requiere extensión; sin extensión v1. Diff usa la misma proyección y rechaza transición v1/v2 sin migración |
| Privacy | Recorrido source_data BDNS-only; no cobertura automática completa de los strings PLACSP ni de todo Core |
| Stores / Events | RecordStore valida hash y Privacy; EventStore exige autorización. No cambios source-specific necesarios en persistencia si se mantiene contrato común |
| Runners | BOE prepara lote antes de escribir; BDNS puede escribir por item antes del control final search. PLACSP requiere preparación/control global propios |
| Fixtures PCSP | Sólo `collectors/pcsp/fixtures/.gitkeep`, no evidencia de paths ni cardinalidad |

Referencias: `docs/DATA_MODEL.md`, `IDENTITY_AND_CHANGE_MODEL.md`, `EVENT_MODEL.md`, `PRIVACY_MODEL.md`, `RUN_MANIFEST_MODEL.md`, `SOURCE_HEALTH_MODEL.md`, `ARCHITECTURE.md`; `src/infocs/models.py`, `finalize.py`, `identity/core.py`, `diff/core.py`, `privacy/gate.py`, `events.py`, `store.py`, `publication/*` y runners/ingestas BOE y BDNS; schemas Record/Candidate/Source. Algunas frases históricas como “todavía no existe persistencia” en DATA_MODEL no describen ya stores/runners; aquí prevalece la implementación inspeccionada.

## 2. Core-only frente a extensión tipada

| Criterio | A — Core-only | B — source_data.placsp |
| --- | --- | --- |
| Expresividad | Referencia/CPV/importes simples; pierde procedimiento, fuente del estado, avisos, precisión de fechas y roles de territorio | Conserva estructura cerrada, procedencia y roles administrativos |
| Semántica de cambios | Cambios sólo fuera de Core quedarían invisibles | Proyección material explícita y comprobable |
| Privacidad | Menos superficie, pero presión para mezclar datos en description | Más validadores/Privacy necesarios; minimización campo a campo |
| Compatibilidad | Menos cambios iniciales; no resuelve fidelidad source-specific | Cambios explícitos en unión/modelos/schema/finalize/hash/Privacy, sin migrar fuentes anteriores |
| Mantenibilidad | Mapping aparentemente sencillo pero pérdida semántica difícil de recuperar | Tipos por fuente, dispatch cerrado; evita diccionarios libres |
| Coste | Bajo, a costa de información acreditada | Moderado, con pruebas de compatibilidad obligatorias |

Recomendación: **B**, unión cerrada BDNS o PLACSP. Se descarta Core-only porque los cambios en estado/plazos/avisos no pueden expresarse fielmente sin sobrecargar textos o perderlos. No se necesita nuevo enum de categoría ni redefinir Record como anuncio.

## 3. Decisión recomendada

`source_data` ausente para fuentes sin extensión; con extensión, exactamente una de `bdns` o `placsp`. Ni objeto vacío, ambas, keys desconocidas, extensiones ajenas o payload XML. PLACSP requiere source.id=placsp, category=procurement, feed_id=1044, official_id concordante; BDNS conserva sus bindings y su posibilidad actual de Records legacy sin extensión. BOE/BOP no aceptan estas extensiones.

La recomendación no significa que los modelos actuales acepten esta forma. Los cambios futuros se enumeran en §14. Metadata observacional de Atom/feed, budgets y checkpoints vive fuera de SourceData administrativo; no ampliar TechnicalMetadata/Manifest subrepticiamente.

## 4. Matriz de campos

Etiquetas: `C=CONFIRMED_SOURCE_FIELD` (path fijado en contrato de evidencia o documentación previamente auditada; no presencia universal); `E=EXISTING_CORE_FIELD`; `P=PROPOSED_FIELD`; `U=UNVERIFIED_SOURCE_FIELD` (mapping/path/cardinalidad B pendiente); `X=EXCLUDED_FIELD`. Un nombre canónico P no se convierte en campo fuente C. Ausencia y opcionalidad son diferentes de dato presente inválido.

Evidencia abreviada: `H`=T1 v0.5 hash_contract, `A`=audit v0.1, `D`=collector design v0.1, `R`=código/schema actual. Paths completos con abreviaturas: `F=atom:feed`, `E0=F/atom:entry`, `S=E0/ext:ContractFolderStatus`, `L=S/ext:LocatedContractingParty/cac:Party`, `P0=S/cac:ProcurementProject`, `T=S/cac:TenderingProcess`, `N=S/ext:ValidNoticeInfo`. No confundir E de etiqueta con E0 de path.

Namespaces exactos de H: atom=`http://www.w3.org/2005/Atom`; tomb=`http://purl.org/atompub/tombstones/1.0`; cbc=`urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2`; cac=`urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2`; ext=`urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2`; bext=`urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2`. H admite además las URIs UBL `urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2` y `...:CommonAggregateComponents-2` en grupos cbc/cac. Prefijos indiferentes; grupo reconocido sólo por URI. No mezclar componentes de dos layouts incompatibles por compartir nombre local: validar una estructura contractual completa.

En tabla, cardinalidad es contrato recomendado de mapping, no censo del XSD. `0..n` conserva pluralidad cuando existe; campos singulares con varios valores distintos son inconsistencia. Publicación “cond.” requiere todos los gates, no allow automático. Riesgo bajo no equivale a ausencia de PII.

| Campo canónico / etiquetas | Path / namespace acreditado o pendiente | Tipo; cardinalidad; requisito | Semántica administrativa y ausencia | Destino / content_hash | Privacidad / publicación | Evidencia |
| --- | --- | --- | --- | --- | --- | --- |
| feed_id P | Configuración fija, no atributo XML inventado | literal 1044; 1 requerido | Canal, sin ausencia válida | Extensión / no, identidad | Bajo / cond. | H,D |
| atom_entry_id C/P | E0/atom:id | string exacto; 1 requerido | Unidad Atom; falta bloquea | Extensión + official_id / no identidad | Correlacionable / scan, cond. | H |
| contract_folder_id C/P/E | S/cbc:ContractFolderID | string exacto; 1 requerido | Referencia carpeta, no global; falta bloquea | Extensión + procurement.expediente / sí | Puede contener PII / scan, cond. | H,A§7 |
| authority_identifier C/P | L/cac:PartyIdentification/cbc:ID, @schemeName | par scheme/value; señal seleccionada única requerida | Órgano/perfil, no licitación; ausencia impide negocio comparable | Extensión; Authority.id derivado aparte / sí datos fuente | Fiscal excluido / scan, cond. | H.business_identity |
| contracting_authority.name U/P/E | Nombre de órgano acreditado conceptualmente; path completo B no fijado por H | string; 0..1 opcional | Nombre institucional, no fallback de identidad; ausente Authority puede ser null | Extensión/Authority / sí nombre fuente, no Core Authority | Medio / scan, cond. | A§7,D§13; path pendiente |
| authority_hierarchy U | Path exacto/schemes de niveles no acreditados aquí | Diferido | Jerarquía no inferida del nombre | Ninguno inicial / no | Posibles personas / no inicial | D propuesta |
| title U/E | Candidato Atom title / nombre ProcurementProject; extracción y equivalencia B pendientes | string; 1 requerido por Core | Título fiel del objeto; no placeholder si falta | Core / sí | Alto por texto libre / scan + revisión | A§22,D§9,R; no path C |
| description U/E | Path/semántica B pendientes | string; 0..1, omisión permitida | Descripción fuente; no síntesis editorial | Core futura / sí si aprobada | Alto / diferir inicialmente | A§22,R |
| source_status C/P | S/bext:ContractFolderStatusCode; atributos de lista por verificar | CodeReference; 0..1 opcional | Estado declarado, sin traducción; ausencia desconocido | Extensión / sí | Bajo / codelist y scan, cond. | H.status_codes,D§14 |
| procedure_code C/P | T/cbc:ProcedureCode; atributos por verificar | CodeReference; 0..1 opcional | Modalidad de procedimiento, no categoría; ausencia desconocido | Extensión / sí | Bajo / cond. | H.procedure_codes |
| contract_type_code C/P | P0/cbc:TypeCode | CodeReference; 0..1 opcional | Tipo de contrato, no categoría de Record | Extensión / sí | Bajo / catálogo, cond. | D§14 documentado; presencia B pendiente |
| cpv C/P/E | P0/cac:CommodityClassification/cbc:ItemClassificationCode | códigos; 0..n opcional | Clasificación objeto; falta no afirma sin CPV | Extensión + procurement.cpv / sí | Bajo / validar lista, cond. | H.cpv_codes,R |
| notice.type C/P | N/bext:NoticeTypeCode | CodeReference; 0..1 por observación; array 0..n | Tipo de aviso contenido; no ID independiente | Extensión notice_observations / sí | Bajo / sin label inferida, cond. | H.notice_refs,D§14 |
| notice.issue_date C/P | N/bext:NoticeIssueDate | OfficialTemporalValue; 0..1 por observación | Emisión del aviso, no automáticamente publicación inicial | Extensión / sí | Bajo / cond. | H.structured_dates,D§15 |
| notice_id U | No extraído por v1; path/scheme B pendientes | No habilitado | No declarar identidad independiente de anuncio | Diferido / no | Correlacionable / no inicial | H.notice_id_projection |
| dates.published_at E/P | Derivación condicionada de aviso inicial; sin path independiente | date; 0..1 | Sólo publicación acreditada; ambigüedad omite | Core / sí | Bajo / política fecha, cond. | D§15 + limitación selección |
| dates.event_at E/X | Sin acontecimiento único acreditado | Ausente | No Atom update ni deadline | Core ausente / no | No inicial | R,D§15 |
| submission_deadline C/P | T/cac:TenderSubmissionDeadlinePeriod/cbc:EndDate | OfficialTemporalValue; 0..1 opcional | Fin de presentación; no estado abierto/cerrado | Extensión / sí | Bajo / cond. | H.structured_dates |
| deadline_time U | EndTime y combinación fecha/hora/zona no acreditadas por H | Diferido | No inventar hora para una fecha | Ninguno / no | No inicial | A,D; proyección H sólo EndDate |
| base_budget C/P/E | P0/cac:BudgetAmount/cbc:TaxExclusiveAmount/@currencyID | Decimal string + moneda; 0..1 opcional | Base sin impuestos, no adjudicado/pagado | Extensión + financial.base_budget / sí | Bajo / rol+moneda, cond. | D§16, A§13; no prueba poblacional B |
| estimated_value C/P/E | P0/cac:BudgetAmount/cbc:EstimatedOverallContractAmount/@currencyID | Igual; 0..1 opcional | Estimado sin impuestos, separado de base | Extensión + financial.estimated_value / sí | Bajo / cond. | D§16,A§13 |
| total_including_tax C/P | P0/cac:BudgetAmount/cbc:TotalAmount/@currencyID | Igual; 0..1; defer inicial | Total con impuestos, no financial.tender_amount por equivalencia supuesta | No activado inicial / no hasta aprobación | Bajo / hold campo | D§16; semántica por versión pendiente |
| financial.tender/award/modification/grant_amount E/X | Mapping PLACSP inicial no acreditado | Ausentes | No inferir resultado, modificación ni subvención | Ninguno / no | No inicial | R,A§13,D§16 |
| execution_locations.territory C/P | P0/cac:RealizedLocation/cbc:CountrySubentityCode | CodeReference; 0..n | Lugar declarado por nivel código; falta desconocido | Extensión / sí | Bajo / catálogo, cond. | H.territory_codes,A§6 |
| execution.city_name / postal_zone U | Path completo y código municipal B pendientes | Diferido | Nombre libre no ID territorial; sin municipio inventado | Ninguno inicial / no | Medio / fuera inicial | A§6,D§12 |
| geography E/P | Derivada de localización/catálogo, no path nuevo | Singular; recomendada ausente | Core no distingue roles/pluralidad | Core ausente; Provenance motivos / no | Bajo / sólo futura decisión | R,A§6 |
| source_url U/E | E0/atom:link@href candidato; @rel y destino público elegible pendientes | HTTPS; 1 requerido Core | Ficha pública, no feed/next/entry.id | Core / sí | URL puede contener PII / guard público+scan | D§22,A§16,R |
| publication_references / TED U | Múltiples referencias conceptuales; paths/schemes/cardinalidad pendientes | Diferidas | Publicaciones relacionadas, no identidad carpeta | Ninguno inicial / no | Correlacionable / no inicial | A§7,D§27 |
| awardee, tax_id, contacts X | No extracción inicial; no afirmar paths nuevos | Excluidos | Partes ganadoras/contactos, no unidad | Ninguno / no | Alto / rechazados | A§14,D§19 |
| lots / results / award_dates X | Referencias de estructuras en A§12,10; paths completos B no validados | Excluidos | Lote/resultado/acto, no expediente raíz | Ninguno / no | Alto / diferidos | A,D§19 |
| documents / document_urls X/E | Referencias documentales; paths B no habilitados | Array Core vacío/omitido | Recursos externos no descargados | Ninguno / no | Alto / excluidos incluso filenames | A§16,D§22 |
| entry_updated C | E0/atom:updated | aware timestamp; 1 transporte | Sincronización; inválido bloquea observación | Estado técnico separado / no | Bajo / no extensión | H,A§10 |
| feed_updated / next C | F/atom:updated; F/atom:link@rel=next/@href | 1 timestamp; 0..1 next inequívoco | Control/navegación, no estado contractual | Transporte / no | No logs de href / no enlace público | H/A; política acreditada |
| tombstone.ref / when C | F/tomb:deleted-entry/@ref,@when | ref 1, when opcional validado | Señal feed, no cancelación | Diagnóstico técnico / no | Correlacionable / no Record ni Event | H,A§11 |
| detected_at / last_checked_at E | Reloj InfoCs inyectado | 1 cada uno aware | Observación propia; conservar primera detección | Core / no | Técnico / metadatos | R |

Este catálogo cubre todas las familias solicitadas y documentadas, no todos los elementos posibles de CODICE. No se ofrece una XSD exhaustiva inventada. El respaldo documental de un path no demuestra su cardinalidad empírica B. Atributos `listURI/listVersionID` son propuestas por validar en cada path, no hechos inferidos por nombre; cuando no se acredita su origen, no generarlos.

## 5. Modelo tipado propuesto

Nombres conceptuales, aún no clases implementadas. Objetos cerrados, validadores Python incluso en construcción directa; nada de `dict[str, Any]` fuente.

| Tipo | Campos permitidos / reglas |
| --- | --- |
| PLACSPCanonicalData | extension_version propuesto 1.0; feed_id=1044; atom_entry_id; contract_folder_id; contracting_authority; procedure opcional; source_status opcional; cpv_codes[]; notice_observations[]; submission_deadline opcional; execution_locations[]; amounts[] |
| PLACSPContractingAuthority | identifier requerido único `{scheme,value}` seguro; name opcional tras acreditar path. No jerarquía, URL, dirección, contactos ni NIF iniciales |
| PLACSPProcedure | contract_type y procedure_type opcionales CodeReference; al menos uno si aparece el objeto |
| PLACSPCodeReference | value requerido exacto; list_uri y list_version opcionales sólo cuando observados y validados; registro source-contract externo puede fijar lista para código sin atributo. Desconocido no se traduce |
| PLACSPNoticeObservation | type opcional CodeReference; issue_date opcional OfficialTemporalValue; al menos uno. Sin notice_id inventado, URL, label ni contenido de adjudicación |
| OfficialTemporalValue | discriminante precision=`date` o `date_time`, value literal ISO validado; date_time aware, no zona inferida. Semántica de rol dada por el campo contenedor |
| PLACSPExecutionLocation | territory requerido CodeReference. Sin CityName, dirección postal, país inferido ni municipalidad ficticia en forma inicial |
| PLACSPAmount | role enum inicial base_budget_excluding_tax / estimated_value_excluding_tax; value decimal exacto; currency explícita validada; tax_treatment=excluding_tax; scope=contract_folder. No lots, no total/award iniciales |

Campos identidad obligatorios permiten comprobación de unidad; no todos los extras son obligatorios. Un array vacío significa ningún elemento aprovechable aportado dentro del contrato aprobado, no inexistencia administrativa. Un campo presente inválido no se convierte en vacío para ocultar un fallo.

NoticeObservation no es una tabla de anuncios independientes. Dedupe de filas completamente idénticas y orden estable por representación canónica para comparación de estado, sin asignar IDs de notice; cambios de fila no indican qué anuncio individual cambió. Preservar asociación tipo/fecha dentro de cada ValidNoticeInfo; nunca mezclar listas ordenadas por separado. Filas contradictorias no se resuelven por orden XML. Documentación histórica que proponía ordenar por ID oficial de anuncio no es implementable con v1: queda diferida explícitamente.

CPV/location/notice son colecciones sin orden administrativo probado: orden canónico por tupla/cadena, dedupe de elementos idénticos del modelo productivo; conservar elementos distintos y bloquear duplicados singulares incompatibles. Esto es una proyección productiva propuesta distinta de la multiplicidad del fingerprint privado: no modifica ni recalcula H/C1/C2. Si un futuro esquema demostrase multiplicidad semántica, versionar la proyección antes de usarla, no perderla silenciosamente.

## 6. Compatibilidad con RecordCandidate

Candidate futuro: source placsp+official_id, procurement, estado active, title y URL pública acreditados, fechas de observación, Provenance, extensión cerrada. No ID/hash/estrategia calculados por normalizador. `grant`, `awardee` y documents ausentes; authority puede ser null si no hay nombre/identidad Core resoluble, aunque la identidad estructurada mínima de autoridad de la extensión esté presente. Sin nivel acreditado, ambos niveles null.

La validación de contrato fuente debe impedir que un Candidate PLACSP sin extensión o sin official_id use fallbacks. El schema general puede seguir admitiendo Records legacy sin source_data; el adaptador/política PLACSP no los publica. Ninguna omisión de campos Core obligatorios se compensa con título genérico o URL de feed.

## 7. Identidad productiva

Recomendación `official_id`: literal `1044::` + Atom ID exacto. Core mantiene el valor oficial y genera ID interno de fuente placsp con digest del literal. La clave de negocio comprueba continuidad y scope, no produce por sí sola el record_id. No usar los hashes privados ni inferir aviso individual.

Riesgos/errores: ausencia → hold; mismo Atom/negocio incompatible → revisión; distinto Atom/mismo negocio → ambigüedad; colisión de ID interno con official_id distinto → error; no merge ni migración automática. `case_number` descartado por unicidad no global, canonical_url por locator/normalización no acreditados, composite por textos mutables. Literalidad y binding feed/official_id/atom_entry_id deben testearse en Python y schema donde sea expresable; concatenación cruzada requiere validador Python.

## 8. Proyección semántica

Propuesta de `canonical_placsp_data`: sólo contract_folder_id, contracting_authority (identificador y nombre observado aprobado), procedure, source_status, cpv_codes, notice_observations, submission_deadline, execution_locations y amounts permitidos. Excluir extension_version/feed_id/atom_entry_id (identidad/versión); nada de feed.updated/entry.updated, flags de captura, pagina, selección o hashes de evidencia.

Core sigue incluyendo title, description si habilitada, source_url, fechas administrativas aprobadas, expediente, CPV y importes con roles. Coincidencias duplicadas Core/extensión son intencionales para interoperabilidad y procedencia; reglas cruzadas deben garantizar igualdad. Cambiar nombre fuente/estado/lugar declarado en extensión es material aunque Authority/Geography normalizados sigan fuera de hash Core.

No publicar metadata de título/URL aún sin path/guard aprobado. Presentación, labels traducidas, crosswalk, categoría, status InfoCs, autoridad normalizada, Provenance, times internos y condiciones técnicas no entran en hash. No añadir mappings a grant, awardee o documents.

## 9. Hash y diff

`structural_fingerprint_sha256` de evidencia sólo cubre seis familias: no es `technical.content_hash`, fixture de negocio ni hash de Record. No reutilizarlo en producción. `entry.updated` posterior puede coexistir con NO_CHANGE; cambios en título/importe fuera del fingerprint pueden producir UPDATE productivo.

Recomendación condicional: mantener content_hash_version=2 para extensión PLACSP con dispatch explícito por tag; v1 de BOE/BOP y v2 BDNS intactos. No asignar todavía una nueva versión ejecutable. La decisión sólo se ratifica tras pruebas byte/hash de todos los Records existentes y golden fixtures: idéntico output BDNS de canonical_bdns_data, sin añadir keys ni cambiar orden, nulls, decimales, colecciones o extension_version.

| Situación futura | Resultado |
| --- | --- |
| Sin prior, gates aprobados | CREATE, evento create autorizado |
| Prior misma identidad/versión y hash igual | NO_CHANGE, sin Event, comprobación técnica puede avanzar |
| Prior misma identidad/versión y proyección material distinta, evolución coherente | UPDATE con changed_fields del diff y Event autorizado |
| Sólo Atom/feed.updated/página/reordenación de sets/labels derivadas | NO_CHANGE |
| Versión de hash o proyección material incompatible | Revisión/migración explícita; no update administrativo por software |
| Negocio/Atom incompatibles, mismo timestamp con payloads distintos | Error/hold contractual, sin sustitución arbitraria |
| Representación anterior a estado aceptado | No revertir; mantener estado técnico fuera del hash y revisar desorden si procede |

El contrato v2 Core sólo compara el entero de versión; no basta para detectar cambios dentro de una proyección PLACSP. Antes de primer Record fijar versión/digest de proyección y política de evolución que impida comparar contratos incompatibles; registrar versión de software/source contract en observabilidad. Cualquier cambio material futuro necesita baseline explícita, no basta alterar extension_version (excluida del hash).

## 10. Fechas

Atom/feed: transporte/orden/control, no fechas administrativas ni Event. Core date sólo recibe una fecha realmente de precisión día y semántica acreditada. Timestamp administrativo conserva precisión/offset en OfficialTemporalValue; no convertirlo a día ni completar zona. Times InfoCs UTC y detected_at previo conservado.

published_at se omite hasta regla inequívoca de aviso inicial aplicable; no tomar mínimo entre DOC_CN ambiguos. event_at ausente. NoticeIssueDate se etiqueta emisión, deadline presentación; no adjudicación ni formalización implícitas. Un valor administrativo inválido presente exige hold de esa observación/material, no elegir otra fecha conveniente.

## 11. Importes

Base sin impuestos y estimado separado, rol y currency explícitos. No inferir EUR, sumar lotes, redondear, recalcular IVA, igualar estimado/base ni afirmar ejecución/pago. Campo documentado no garantiza presencia o validez B.

Para la proyección productiva se propone decimal exacto numéricamente canónico (ceros fraccionarios finales no materiales), usando Decimal sin float y sin redondeo por contexto; no “reparar” strings inválidos. Mantener fiscalidad y scope. El Core actual usa `Decimal.normalize()` en canonical_decimal, susceptible de contexto para precisión grande; exige tests de límites y fidelidad antes de habilitar importes PLACSP. Si no puede garantizar exactitud sin alterar BDNS, retener el mapping económico en HOLD hasta diseño específico, no cambiar el normalizador global en esta wave.

Core Money permite negativos y patrón de moneda de tres letras: el validador PLACSP debe añadir semántica no negativa de estos roles y catálogo monetario reconocido, sin cambiar Money BDNS/BOE. Ausente: omitir rol; moneda ausente/desconocida o importe inválido presente: hold, no Money inventado. No se conservan cantidades ambiguas en un dict raw. Total con impuestos/adjudicado quedan fuera hasta nueva aprobación.

## 12. Documentos y URLs

URL feed, pagina, Atom ID y ficha pública son categorías distintas. Guard de transporte no es política de navegación pública. Atom ID puede tener forma URI sin ser clickable. source_url debe proceder de referencia de ficha observada, validada por una allowlist de publicación independiente (rutas, esquemas y host aprobados), no por concat, HTTPS upgrade o redirects probados.

Actualmente no hay ese contrato público de B resuelto: publication hold, no fallback a feed ni locator raw. No PDFs, filenames, firmas, fulltext, descarga, referencias documentales o notice IDs extraídos de documentos. `documents` Core omitido. Referencias TED/otras publicaciones no se incluyen en forma inicial hasta tener path/scheme/cardinalidad y finalidad aprobados.

## 13. Null y omisión

En Python, opcionales None; JSON canónico PLACSP omite opcionales ausentes. Arrays de extensión requeridos siempre presentes como []; proyección semántica propuesta omite arrays vacíos, sin confundir null/[] en modelo. Identidad obligatoria no admite None/vacío; objeto opcional presente requiere al menos un campo útil. No strings “unknown”, ceros monetarios sintéticos ni false por ausencia.

Authority/niveles conservan los null explícitos actuales; fechas oficiales omitidas como Core. No cambiar serialización BDNS: admite su contrato actual de null/omisión y sus sets. Probar from_dict/to_dict/canonical_json/modelo directo/schema y estados de ausencia en cada rama. Toda discordancia impide release.

## 14. Compatibilidad JSON Schema / Python

Cambios FUTUROS, no realizados:

1. SourceData: variantes tipadas BDNS/PLACSP o wrapper con exactamente una variante; conservar API/construcción BDNS o adaptarla sin cambiar output. No map abierto.
2. models.py: nuevas dataclasses y loader por tag, validación directa y cruzada source/category/feed/official_id. Rechazar ambas/ninguna/unknown; no try/except que elimine extensión incompatible.
3. record.schema.json: source_data oneOf de objetos cerrados, nuevos defs cerrados y bindings por fuente; preservar defs BDNS. Candidate hereda candidate_core, sin permitir technical final; testar unevaluatedProperties en ambos.
4. finalize.py: dispatch explícito para colecciones canónicas; asignar hash sólo después de validar rama. diff/core.py: proyección PLACSP separada, output BDNS anterior idéntico.
5. privacy/gate.py: proyección explícita de todos los strings PLACSP y superficies URL; no sólo detectar DNI en title. Conservar reglas/resultado BDNS/BOE.
6. Publication: adaptador PLACSP/policy_id nuevos, sin usar autorización BDNS/BOE; source registration propio con revisión de condiciones. Source schema puede mantenerse con definición compatible y política operativa aparte, no insertar keys no soportadas.

No requieren cambio previsto: ProcurementDetails, FinancialAmounts, categorías, Events schema/identity ni stores genéricos. Record/Candidate schemas sí requerirán ampliación explícita autorizada; hoy están intactos. Frontend deberá evitar presentar carpeta como notice/award y ocultar campos ausentes en fase aparte, no reciclar render BDNS; workflows siguen intactos.

## 15. Estrategia de versionado

| Contrato | Propuesta / condición |
| --- | --- |
| Fuente | Documento v0.1 de diseño; versión operativa futura explícita y aprobada, no activación automática |
| Proyección administrativa | Nombre propuesto placsp-canonical-projection-v1; congelar bytes/orden/campos y golden fixtures antes de asignación operativa |
| Normalizador | collector_version y provenance.normalizer_version separados de estado administrativo |
| Extensión | Literal propuesto 1.0 si shape cerrado inicial queda aprobado; no bump BDNS 1.0 |
| Hash productivo | v2 recomendado condicionalmente; no v3, no migración; sólo después de pruebas de preservación |
| Evidencia | placsp-identity-evidence-v1 y cohort-v1 sin cambios; no se convierten en proyección canónica |

La versión de la proyección no se oculta en una label técnica mientras se altera el hash: cambios de significado requieren revisión/migración formal. No hay Records PLACSP que migrar en esta fase; no se garantiza compatibilidad ejecutada sólo por diseñarla.

## 16. Impacto y no regresión

| Componente | Impacto futuro / protección |
| --- | --- |
| BOE | Sin extensión, hash v1 y review manual idénticos; fixtures golden y autorización cruzada rechazada |
| BDNS | Unión ampliada pero su rama, v2, extensión 1.0, fail-soft y JSON idénticos; cero migraciones/backfill/events de software |
| BOP | Sigue HOLD por reutilización; ninguna autorización implícita PLACSP desbloquea BOP |
| Candidate/Record | Definiciones compartidas ampliadas sólo por nueva variante; activos/fechas/identidad obligatorios preservados |
| Source schema/config | Usar forma existente; detalles de canal/guards en contrato operativo específico, no allowlist global |
| Identity | official_id existente; no cambio general del slug/digest/fallback; PLACSP prohíbe fallback en adaptador |
| Hash/diff | Nuevo dispatch controlado; golden payload/hash anterior por fuente, versiones incompatibles bloqueadas |
| Events/stores | Sin nuevo tipo; autorización y preflight genéricos, idempotencia actual; sin eventos por timestamp/tombstone |
| Privacy/Publication | Nueva superficie PLACSP explícita, no exención por fuente oficial ni weakening BDNS |
| Frontend/workflows | Cero cambios ahora; representación futura source-specific y publicación requerirán aprobación aparte |

Compatibilidad documentalmente factible, no demostración de código aún no escrito. Inventario actual: 173 archivos data; no se reserializan ni validan ejecutando pipeline en esta wave. Futuras pruebas deben contar Records reales entonces, no fijar la cifra histórica de 44; comparar bytes/hashes de todos, incluyendo fuentes sin extensión. Preservación byte-for-byte durante esta fase se comprueba al cierre.

## 17. Fixtures y plan de tests

Sólo fixtures sintéticas nuevas y autorización separada de Wave 2; no cohortes privadas, hashes individuales ni payloads reales. No tests ejecutados en Wave 1.

- Identidad: updates mismo ID; casing/Unicode/whitespace literal no reescrito; namespace fuente/canal; falta/colisión; mismo negocio con múltiples Atom; mismo ID negocio divergente; sin título/fuzzy fallback.
- XML: URIs exactas/prefijos equivalentes, layout incompatible, auxiliares ignorados, wrong namespace no reinterpretado, split DTD/ENTITY, XXE, truncamiento, depth/nodes/text, EOF y framing público; test de política de dos orígenes/rutas/redirects independiente de enlaces públicos.
- Mapping: title/ficha obligatorios sólo con path acreditado; CPV y códigos; tipos/fechas asociados por aviso; duplicados idénticos/repetición válida/mismo timestamp divergente; arrays/null; unknown fields y codelists no aceptados por silencio.
- Temporalidad: timestamp-only no cambia content_hash; notice/deadline cambia si material; no elegir aviso inicial por orden XML; fecha vs timestamp, zonas/precisión; detected_at previo; no reversión por versión antigua; sin missing por ausencia/tombstone.
- Territorialidad: órgano vs ejecución, ES522 vs ES52, proveedor excluido, municipio ambiguo, crosswalk versionado, multiubicación, INCLUDE/OUT_OF_SCOPE/UNRESOLVED, no fuzzy.
- Economía: roles/fiscalidad/moneda explícitos, cero vs ausente, negativos/no exponencial/float inválidos, precisión larga/contexto, cifras equivalentes sin cambio, sin IVA/suma/moneda inferidos.
- Privacy: PII en title, IDs, nombre institucional aparente, URLs codificadas, contacto/domicilio; rama PLACSP completa; allow no sobreescribe hold; configuración inválida aborta.
- Schema/Python: objetos cerrados, BDNS|PLACSP exclusiva, source/category/feed bindings, BOE+PLACSP/BDNS+PLACSP/PLACSP+BDNS rechazados, candidato sin technical final; construcción directa, roundtrip y omisión.
- Hash/diff: fingerprint != hash productivo, materialidad por cada familia, sets ordenados, labels/times excluidos, contract-version mismatch, golden BOE/BDNS actuales sin cambios y cero migraciones.
- Events: create/update autorizados por policy correcta; no_change sin Event; bindings cruzados rechazados; preflight/idempotencia/conflictos; fallos sin escritura, Event→Record recuperación; control del lote antes de cualquier materialización.

Un fixture puede demostrar el comportamiento previsto del normalizador; no acredita que un path U exista en la fuente. Resolver ese punto mediante revisión documental/muestra autorizada independiente antes de habilitar el mapping.

## 18. Riesgos, decisiones y bloqueos

| Decisión obligatoria | Recomendación y fundamento | Riesgo / alternativa descartada / dependencia |
| --- | --- | --- |
| A unidad | Atom/carpeta, evidencia aceptada de cuatro updates | No notices/expediente completo; muestra no universal |
| B identidad | official_id 1044::literal, digest Core exacto | Colisión truncada/reutilización requiere guards; no expediente/título fallback; aprobar nombre placsp |
| C categoría | procurement, raíz estable | Notice/award mezclarían subobjeto con unidad |
| D extensión | source_data.placsp tipada, por pérdida Core-only | Ampliación de loaders/gates/schema requiere tests y aprobación |
| E hash | Proyección material propia + Core, no fingerprint privado | No cobertura de todos los campos; v2 sólo si golden compatibility |
| F fechas | Atom separado, fechas administrativas por rol/precisión | Aviso inicial/publicación efectiva aún condicionados; no min/update fallback |
| G territorio | Dos ejes, señales exactas; UNRESOLVED si insuficiente | Directorios/codelists pendientes; no título/proveedor ni scope amplio automático |
| H incremental | Watermark/frontera futura, no ausencia/deleted | Snapshot no transaccional, latencia/desorden; horizonte/calibración pendientes |
| I privacidad/publicación | Minimización + Privacy completa + source/metadata gates | Revisión vigente, URL pública y PII por nombre no plenamente detectables; no derechos de documentos inferidos |
| J compatibilidad | BDNS/BOE byte/hash protegidos, BOP HOLD | No prueba ejecutable aún; sin migraciones/version bump implícito |

No hay contradicción fundamental que obligue a rediseñar la unidad o el Core para redactar estos documentos. Sí hay bloqueos explícitos para implementar/publicar mappings no acreditados y para operar la fuente: título/ficha/nombre B, selección de publicación, listas/territorio, precisión monetaria, estado por objeto, tamaños/horizonte, Privacy y reutilización vigente. Permanecen pendientes; no se marca production-ready ni se fabrica evidencia.

Resultado de diseño: `PLACSP_WAVE1_DESIGN_READY`. Siguiente fase propuesta: `PLACSP COLLECTOR WAVE 2 — RECORDCANDIDATE MAPPING & OFFLINE CONTRACT FIXTURES v0.1`, sólo después de revisión/aprobación de ambos documentos. No queda autorizada; deberá distinguir tests sintéticos de pendientes de fuente y no modificar contratos de identidad para superar tests.
