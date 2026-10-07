# BDNS Human Readability — Frontend Surface Audit v0.1

Fecha: 2026-10-06. Fase: 10B-E1, auditoría local y diseño, sin implementación.
Snapshot: `20632e14a527059db09877fbc44d89ac816412b8`, branch `main`.
No se ha hecho fetch ni consulta externa. Los conteos describen este árbol,
no una consulta en tiempo real del portal o de BDNS.

## 1. Executive Finding

Los 42 Records BDNS locales son v2 y contienen `source_data.bdns`. Disponen
de presupuesto exacto, tipo, instrumentos, categorías elegibles, sectores,
finalidad, recepción, bases y metadata documental. **Ninguno de esos campos
enriquecidos llega al modelo de presentación actual.**

`records.ts` lee el JSON completo; `canonical.ts:adaptRecord()` selecciona
únicamente campos Core y descarta la extensión en su objeto de retorno.
`FrontendRecord` no declara `source_data` ni equivalente. El problema principal
es de contrato de proyección frontend, no de falta de datos ni de layout.
Los datos mínimos Core sí llegan y permiten mostrar título, organismo, provincia,
Código BDNS, fecha de detección, origen, historial y detalles técnicos.

Recomendación: extender el contrato frontend con un bloque BDNS tipado y
validado en build-time, y construir un ViewModel específico sobre esa
proyección. Mantener Core, BOE, Events y arquitectura visual actuales.
10B-D3 está cerrado (`BDNS_FIRST_SCHEDULED_V2_RUN_VALIDATED`); no es necesario
reabrir migración, gates o validación del collector para este diseño.

## 2. Current Frontend Data Flow

```text
data/records/bdns/*.json — canonical Record v2
  → site/src/lib/data/records.ts:loadRecords()/jsonFiles()
    → site/src/lib/data/canonical.ts:parseCanonicalJson()/adaptRecord()
      → site/src/lib/data/types.ts:FrontendRecord
        → site/src/lib/data/index.ts:loadPortalData()
          + events.ts:loadEvents() + sources.ts:buildSources()
        → site/src/lib/presentation/{recordView,labels,dates}.ts
        → site/src/pages/registro/[slug].astro
          y components/RecordCard.astro
        → site/package.json: astro build && pagefind --site dist
        → site/src/pages/buscar/index.astro + scripts/search.ts
```

Los paths `site/...` siguientes son relativos a la raíz del repositorio.
`loadRecords()` admite sólo directorios configurados como públicos en
`sources.ts` (BOE y BDNS), comprueba identidad duplicada y ordena por
`publishedAt ?? detectedAt`, descendente, con ID como desempate.
`loadPortalData()` une Events y metadata editorial de fuentes; no añade datos
BDNS. `encodeRecordId()` crea slugs UTF-8 en hexadecimal, no IDs fuente nuevos.

### Proyección Core actual

Loaded significa que el valor forma parte del JSON parseado, no que el
adaptador lo valide o retenga. La tabla distingue contrato de presencia real.

| Canonical field | Loaded | Adapted | Exposed in FrontendRecord | Lost before presentation |
| --- | --- | --- | --- | --- |
| id | sí | sí | id | no |
| source.id / official_id | sí | sí | sourceId / officialId | no |
| source restantes, si existen | sí | no | no | sí |
| title / category | sí | sí | title / category | no |
| authority.id/name/administration_level | sí | sí | authority | no |
| administration_level | sí | sí | administrationLevel | no |
| dates.published_at / event_at | sí | sí si presentes | publishedAt / eventAt | no; ausentes en los 42 BDNS |
| dates.detected_at / last_checked_at | sí | sí | detectedAt / lastCheckedAt | no |
| source_url | sí | sí | sourceUrl | no |
| geography.municipality/province | sí | sí | geography | no |
| grant.call_id/resolution_id | sí | sí | grant.callId/resolutionId | no |
| financial: seis importes Core | sí | sí si presentes | financial | no en adapter; actualmente no renderizados en ficha/card |
| documents Core: source_url/archive_status/has_local_copy/publication_allowed | sí | sí si presentes | documents | no en adapter; actualmente no renderizados |
| tags | sí | sí, default [] | tags | no en adapter; no superficie actual |
| technical.content_hash | sí | sí | contentHash | no |
| technical.content_hash_version y resto technical | sí | no | no | sí |
| provenance, incluido normalizer_version | sí | no | no | sí |
| schema_version / status | sí | no | no | sí |
| source_data.bdns completo | sí, 42/42 | **no** | **no** | **sí, en adaptRecord()** |

El adaptador valida la parte que proyecta: tipos, algunas fechas, hash y enums
de nivel administrativo. No valida schema completo, claves desconocidas ni
coherencia de extensión/hash v2. No confundir su lectura selectiva con una
validación canónica completa. En esta población no existen `financial`,
`documents` Core ni `tags`; los documentos útiles están en la extensión.

## 3. Current Record Surface

### Card y consumidores

`components/RecordCard.astro`: badges de fuente/categoría, indicador de
historial si existe algún Event, título enlazado, organismo, etiquetas
territoriales, fecha primaria y enlace «Fuente». Un create ya activa el
indicador; no significa que hubiera una modificación administrativa.

Consumidores directos encontrados: `pages/index.astro` (todos los Records)
y `pages/fuentes/[source].astro` (los de una fuente). Ambos calculan los mismos
helpers. Cambios utiliza `ChangeRecordEntry.astro`, no RecordCard. Búsqueda
construye su propio DOM en `scripts/search.ts`, aunque reutiliza la clase
CSS `record-card`: modificar RecordCard no modifica los resultados de búsqueda.

### Ficha: orden exacto

| Orden | Bloque | Campos/helpers actuales | Condiciones y gap BDNS |
| --- | --- | --- | --- |
| 0 | Metadata Pagefind invisible | fuente/categoría, authority, primaryDate, slug | no contenido enriquecido |
| 1 | Breadcrumbs | rutas constantes | genérico |
| 2 | Header: badges, h1, organismo | sourceLabel, categoryLabel, title, authority.name | sin título cooficial, tipo ni presupuesto |
| 3 | Datos oficiales | authority; dates.publishedAt/eventAt formateadas; grant.callId | Código BDNS sólo si sourceId=bdns; sin extensión |
| 4 | Procesado por InfoCs | categoría, administrationLevelLabel, geographyLabels | mantiene separado lo normalizado |
| 5 | Fuente oficial / atribución | sourceUrl; source.attribution | «Abrir publicación oficial» apunta al endpoint técnico en los 42 BDNS |
| 6 | Trazabilidad / procesamiento | nota editorial fija de metodología | no resumen específico |
| 7 | Historial | timelineItems(events), eventDescription, fechas de observación | no historial inventado por enriquecimiento |
| 8 | Detalles técnicos | id, officialId, contentHash, detectedAt, lastCheckedAt | details; excluido de Pagefind |

El article entero tiene `data-pagefind-body`. No hay tabla o condición
source-specific para presupuesto, finalidad, plazos, bases ni documentos.
Los 42 Records carecen de published_at/event_at: la card muestra
«Detectado por InfoCs», correctamente distinto de recepción en BDNS.

### Transformaciones existentes

| Helper/capa | Clase | Qué hace / límite |
| --- | --- | --- |
| dates.ts:formatPortalDate | formatting | es-ES, fecha calendario ISO, UTC; no cambia de día ni infiere significado |
| recordView.ts:primaryDate | deterministic derivation + formatting | publicado si existe, si no detectado; no debe sustituirse por received_date bajo label Publicado |
| geographyLabels | label mapping | municipio/provincia normalizados, no inferencia desde organismo |
| labels.ts:categoryLabel/sourceLabel/administrationLevelLabel | label mapping | mapas explícitos, fallback genérico; no labels de catálogos BDNS |
| eventDescription/timelineItems | deterministic derivation | texto InfoCs sobre create/update y changed_fields; unknown → «información de la ficha» |
| changes.ts:changeItems | deterministic derivation | orden y unión Event/Record, enlaces a ficha; no nuevos Events |
| sourceDetails.ts / data/sources.ts | editorial text + derivation | alcance/reutilización fijos por fuente y conteos/actividad locales |
| TechnicalDetails | technical metadata | valores técnicos literales y timestamps; no texto administrativo |

Existe una arquitectura ViewModel reutilizable (`PrimaryDateView`,
`TimelineItem`, `ChangeItemView`, `SourceDetailView`). No existe BDNSRecordView.
No confundir notas editoriales estáticas de metodología con resumen de una ayuda.

## 4. BDNS v2 Canonical Field Inventory

Contrato: `schemas/record.schema.json:$defs.bdns_data` y subtipos;
`src/infocs/models.py:BDNSCanonicalData` y tipos frozen;
`collectors/bdns/CANONICAL_ENRICHMENT_CONTRACT.md` y
`ENRICHMENT_GATE_CONTRACT.md`. El anterior FIELD_MAP es evidencia histórica
de diseño, no reemplaza los nombres cerrados actuales.

**17 campos de primer nivel en el contrato; 16 observados. 44 paths de campo
incluyendo contenedores/subcampos/miembros []; 35 observados y 9 no observados.**
No hay `application.text`: existen start_text y end_text. Título principal y
Código BDNS siguen en Core. Null/ausencia son equivalentes en serialización;
arrays vacíos se omiten. No deducir ausencia oficial desde una omisión canónica.

| Campo bajo source_data.bdns | Tipo cerrado y contenido |
| --- | --- |
| extension_version | const string 1.0, contrato técnico |
| official_title_coofficial | texto oficial opcional, no traducción InfoCs |
| authority_hierarchy | objeto opcional: nivel1?, nivel2?, nivel3? (strings) |
| budget_total | objeto opcional: value string decimal exacto no negativo; currency? string ISO de tres letras |
| call_type | texto oficial opcional, no enum editorial |
| instruments | lista de strings oficiales |
| eligible_beneficiary_types | lista: label obligatorio, code? string |
| sectors | lista: label obligatorio, code? string |
| impact_regions | lista de strings oficiales |
| received_date | fecha ISO opcional |
| application | start_date?, end_date? ISO; start_text?, end_text? strings; abierto? boolean |
| purpose | texto oficial opcional |
| regulatory_bases | description? string; source_locator? string literal |
| electronic_office_url | URL HTTPS opcional, política estricta |
| extract_published_in_official_diary | boolean opcional, literal fuente |
| documents | lista: source_document_id entero no negativo; description?, filename?, published_date? ISO, modified_value? texto |
| extracts | lista: cve?, diary?, source_url? HTTPS, publication_date? ISO, title?, title_coofficial? |

Colecciones semánticamente unordered con orden canónico, no ranking.
Niveles de jerarquía e inicio/fin no son intercambiables.
No raw, concesiones, fulltext, moneda inferida, MIME, links documentales
persistidos ni estado abierto/cerrado generado.

## 5. Population Matrix

Denominador **42 Records**. P = Records con clave, NE = con algún valor
significativo, M = missing, N = sólo null. False es un valor significativo.
Para `[]` se cuenta Record con algún miembro que contiene ese subcampo,
no porcentaje de documentos. Todos los campos presentes tienen N=0 y P=NE.
Los nueve paths no observados tienen P=NE=N=0, M=42. No hubo arrays presentes vacíos.

| Campo | P | NE | % Records NE | M | N | Shape observado |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| extension_version | 42 | 42 | 100 | 0 | 0 | string const |
| official_title_coofficial | 3 | 3 | 7,1 | 39 | 0 | string |
| authority_hierarchy | 42 | 42 | 100 | 0 | 0 | objeto nivel1,nivel2,nivel3 |
| authority_hierarchy.nivel1 | 42 | 42 | 100 | 0 | 0 | string |
| authority_hierarchy.nivel2 | 42 | 42 | 100 | 0 | 0 | string |
| authority_hierarchy.nivel3 | 42 | 42 | 100 | 0 | 0 | string |
| budget_total | 42 | 42 | 100 | 0 | 0 | objeto sólo value |
| budget_total.value | 42 | 42 | 100 | 0 | 0 | string decimal |
| budget_total.currency | 0 | 0 | 0 | 42 | 0 | no observado |
| call_type | 42 | 42 | 100 | 0 | 0 | string |
| instruments | 42 | 42 | 100 | 0 | 0 | array string |
| eligible_beneficiary_types | 42 | 42 | 100 | 0 | 0 | array objeto sólo label |
| eligible_beneficiary_types[].label | 42 | 42 | 100 | 0 | 0 | string |
| eligible_beneficiary_types[].code | 0 | 0 | 0 | 42 | 0 | no observado |
| sectors | 42 | 42 | 100 | 0 | 0 | array objeto code,label |
| sectors[].label | 42 | 42 | 100 | 0 | 0 | string |
| sectors[].code | 42 | 42 | 100 | 0 | 0 | string |
| impact_regions | 42 | 42 | 100 | 0 | 0 | array string |
| received_date | 42 | 42 | 100 | 0 | 0 | string ISO date |
| application | 42 | 42 | 100 | 0 | 0 | cinco shapes, abajo |
| application.start_date | 28 | 28 | 66,7 | 14 | 0 | string ISO date |
| application.end_date | 27 | 27 | 64,3 | 15 | 0 | string ISO date |
| application.start_text | 16 | 16 | 38,1 | 26 | 0 | string |
| application.end_text | 16 | 16 | 38,1 | 26 | 0 | string |
| application.abierto | 42 | 42 | 100 | 0 | 0 | boolean: false 39, true 3 |
| purpose | 42 | 42 | 100 | 0 | 0 | string |
| regulatory_bases | 42 | 42 | 100 | 0 | 0 | objeto description,source_locator |
| regulatory_bases.description | 42 | 42 | 100 | 0 | 0 | string |
| regulatory_bases.source_locator | 42 | 42 | 100 | 0 | 0 | string literal |
| electronic_office_url | 4 | 4 | 9,5 | 38 | 0 | string HTTPS |
| extract_published_in_official_diary | 42 | 42 | 100 | 0 | 0 | boolean: false 32, true 10 |
| documents | 42 | 42 | 100 | 0 | 0 | array objeto cinco claves |
| documents[].source_document_id | 42 | 42 | 100 | 0 | 0 | integer |
| documents[].description | 42 | 42 | 100 | 0 | 0 | string |
| documents[].filename | 42 | 42 | 100 | 0 | 0 | string |
| documents[].published_date | 42 | 42 | 100 | 0 | 0 | string ISO date |
| documents[].modified_value | 42 | 42 | 100 | 0 | 0 | string literal |
| extracts | 0 | 0 | 0 | 42 | 0 | omitido, no miembros |
| extracts[].cve | 0 | 0 | 0 | 42 | 0 | no observado |
| extracts[].diary | 0 | 0 | 0 | 42 | 0 | no observado |
| extracts[].source_url | 0 | 0 | 0 | 42 | 0 | no observado |
| extracts[].publication_date | 0 | 0 | 0 | 42 | 0 | no observado |
| extracts[].title | 0 | 0 | 0 | 42 | 0 | no observado |
| extracts[].title_coofficial | 0 | 0 | 0 | 42 | 0 | no observado |

Shapes application: `{abierto}`; `{abierto,start_date,end_date}`;
`{abierto,start_text,end_text}`; `{abierto,start_date,start_text,end_text}`;
`{abierto,start_date,end_date,start_text,end_text}`. Nunca inferir fin si falta.

| Array | Records NE | Min/max por Record (ausente=0) | Total miembros | Shapes miembros |
| --- | ---: | --- | ---: | --- |
| instruments | 42 | 1–1 | 42 | string |
| eligible_beneficiary_types | 42 | 1–2 | 44 | label |
| sectors | 42 | 1–3 | 46 | code,label |
| impact_regions | 42 | 1–1 | 42 | string |
| documents | 42 | 1–2 | 48 | source_document_id,description,filename,published_date,modified_value |
| extracts | 0 | 0–0 | 0 | ninguno |

Locators: **36 clickable, 6 no clickable**, evaluados sólo con el helper
productivo existente, sin navegación. Prefijos: 37 HTTPS (uno con espacio
ASCII interno), 2 HTTP y 3 sin esos prefijos. El dato fuente completo se
conserva en todos. No publicar valores ni ejemplos reales para explicar formas.

## 6. Semantic Safety Matrix

Esta semántica procede de los contratos locales aprobados, no de nuevas
investigaciones oficiales. Las labels son propuestas de presentación.

| Campo | Significado soportado / label candidato | Interpretación permitida | Prohibida |
| --- | --- | --- | --- |
| extension_version | versión del contrato | sólo técnica | calidad, frescura o estado de convocatoria |
| official_title_coofficial | Título oficial en otra lengua | literal adicional al h1 | traducción generada; inferir lengua sin evidencia |
| authority_hierarchy.nivel1/2/3 | Jerarquía del organismo (niveles fuente) | mostrar secuencia y roles nivel1/2/3 | inferir municipio, competencia o nivel Core desde el texto |
| budget_total.value/currency | Presupuesto de la convocatoria | decimal exacto; moneda sólo si está declarada | importe concedido, pagado/recibido, € por defecto |
| call_type | Tipo de convocatoria | label oficial literal | convertir convocatoria en concesión individual |
| instruments | Instrumentos de ayuda | listado literal | condiciones financieras o jurídicas no declaradas |
| eligible_beneficiary_types.label/code | Tipos de destinatarios elegibles | categorías oficiales; code secundario si existe | personas perceptoras, lista de ganadores o elegibilidad de una persona concreta |
| sectors.label/code | Sectores según BDNS | clasificación oficial y código opcional | versión CNAE asumida, impacto económico, jerarquía de códigos inventada |
| impact_regions | Ámbito declarado en BDNS | labels fuente | dirección, municipio inferido o reducción de ámbitos amplios |
| received_date | Fecha de recepción en BDNS | fecha por su rol | Fecha de publicación |
| application.start_date/end_date | Inicio/fin de solicitud | fechas separadas y literales | estado abierta/cerrada calculado; corregir fechas contradictorias |
| application.start_text/end_text | Inicio/fin: texto oficial | conservar junto a fechas si coexisten | parsear «a la firma» como fecha; inventar fin |
| application.abierto | indicador literal fuente | conservar en contrato; ocultar en MVP | false=cerrada/finalizada/fuera de plazo; true=abierta hoy |
| purpose | Finalidad declarada | texto oficial completo | objeto inventado, valoración o intención política |
| regulatory_bases.description | Bases reguladoras | descripción/nombre recibido | ley, disposición o análisis jurídico sin respaldo |
| regulatory_bases.source_locator | Localizador de bases suministrado por BDNS | literal; enlace sólo si pasa helper estricto | trim, reparación, %20, esquema inferido, HTTP→HTTPS |
| electronic_office_url | Sede electrónica indicada por BDNS | enlace HTTPS validado | ficha única de la convocatoria, certificado institucional InfoCs |
| extract_published_in_official_diary | indicador de publicación de extracto | técnicamente literal; diferido en MVP | false=convocatoria no publicada; true=extracto disponible en InfoCs |
| documents[].source_document_id | referencia documental | identidad local/derivación futura bajo contrato | enlace inventado, identificador de convocatoria |
| documents[].description/filename | Documentos oficiales: metadata | texto escapado; nombre de archivo opcional | contenido leído, MIME comprobado, copia archivada |
| documents[].published_date | Publicación del documento | fecha sólo del documento | fecha de convocatoria |
| documents[].modified_value | Modificación documental: valor fuente | literal secundario, sin interpretar formato | timestamp universal, nueva versión PDF o cambio jurídico demostrado |
| extracts[].cve/diary | Extracto: referencia y diario | metadata oficial cuando exista | nuevo Record/relación Core automática |
| extracts[].title/title_coofficial | Título de extracto | títulos literales | fulltext, resumen de disposición |
| extracts[].publication_date | Publicación del extracto | fecha de ese extracto | cambiar published_at Core desde la UI |
| extracts[].source_url | Enlace de extracto | HTTPS estricto | nuevo endpoint o texto obtenido por descarga |

Moneda: 0/42. Mostrar número exacto y «moneda no indicada en los datos»,
sin usar FrontendMoney actual (currency obligatoria), sin Number/parseFloat,
redondeo o Intl.NumberFormat sobre un float. Presentar fechas, no vigencia.

## 7. Surface Allocation Matrix

CARD ESSENTIAL es propuesta futura, no implementación E1. OD=Official Data,
EP=En pocas palabras (composición futura), ID=InfoCs Derived, T=Technical,
S=Search, H=Hidden. Un contenedor agrupa subcampos, no añade un hecho nuevo.

| Campo/grupo (incluye los subcampos indicados) | CARD | EP | OD | ID | T | S | H |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Core title / authority.name / source / category | esencial actual | organismo | sí título/organismo; source procedencia | categoría normalizada | IDs | sí | no |
| Core geography / administration_level | territorio actual | sólo territorio confirmado | no duplicar como fuente literal | sí | no | sí | no |
| Core grant.call_id | no | no | Código BDNS | no | también officialId | sí | no |
| detectedAt / lastCheckedAt / hash / provenance | fecha detección actual | no | no | no | sí | excluir técnicos | versiones no proyectadas ahora |
| extension_version | no | no | no | no | opcional | no | sí en ficha principal |
| official_title_coofficial | no | no | adicional | no | no | sí si visible | omitir ausente |
| authority_hierarchy.nivel1/2/3 | organismo Core, no tres niveles | no duplicar | detalle contextual | no | no | sí | omitir repetición exacta visible |
| budget_total.value/currency | esencial si existe | pieza opcional | sí | formato, no otro hecho | no | texto; rango futuro | moneda ausente no inventada |
| call_type | esencial si breve, literal | opcional | sí | no | no | sí | no |
| instruments | DETAIL ONLY | no en MVP | sí | no | no | sí | no |
| eligible_beneficiary_types.label | DETAIL ONLY | categorías opcionales | sí | no | no | sí | no |
| eligible_beneficiary_types.code | no | no | secundario si presente | no | no | futuro si necesario | ausente actual |
| sectors.label/code | DETAIL ONLY | labels opcionales, no impacto | sí label; code secundario | no | no | sí labels | no |
| impact_regions | Core provincia basta | opcional | ámbito fuente literal | no | no | sí | no |
| received_date | posible fecha por rol, no sustituir sort | opcional | sí | formato | no | sí | no |
| application fechas/textos | DETAIL ONLY | periodo opcional | sí, roles separados | formato | no | sí | ausencias omitidas |
| application.abierto | no | no | no MVP | no | no | no | sí por semántica pendiente |
| purpose | DETAIL ONLY | prioridad alta | sí literal | no | no | sí | no |
| regulatory_bases.description | DETAIL ONLY | no | sí | no | no | sí | no |
| regulatory_bases.source_locator | no | no | literal y enlace condicional | decisión navegación derivada, no panel obligatorio | no | excluir string de búsqueda | no esconder si no clickable |
| electronic_office_url | DETAIL ONLY | no | procedencia/enlace | no | no | label, no URL bruta | omitir ausente |
| extract_published_in_official_diary | no | no | no MVP | no | opcional | no | sí MVP |
| documents[].description/filename/published_date | DETAIL ONLY | no | lista metadata | fecha formateada | no | descripción; filename fuera por defecto | filename secundario |
| documents[].source_document_id/modified_value | no | no | no principal | no | referencia secundaria si útil | no | sí MVP |
| extracts[].title/title_coofficial/diary/publication_date | DETAIL ONLY futuro | no | metadata condicional | formato | no | sólo si visible | vacío actual |
| extracts[].source_url/cve | no | no | enlace/ref condicional | no | referencia secundaria | URL no; CVE futuro | vacío actual |

No existe necesidad de una superficie SEARCH ONLY de texto administrativo
oculto en el MVP: indexar lo que el usuario puede leer. Los códigos técnicos
no deben entrar sólo para mejorar recall. Las labels/formatos derivados no
se persisten; un dato oficial no se vuelve «Procesado por InfoCs» por pasar
por el parser. Permanece en OD aunque su fecha/importe se formatee.

### En pocas palabras: decisión conceptual

Es viable una composición determinista de campos, **no un resumen**.
Prioridad: finalidad literal → organismo Core → tipo literal → presupuesto
con concepto/moneda explícitos → categorías elegibles → periodo por rol →
territorio confirmado. No se fija todavía una plantilla definitiva.
Omitir piezas ausentes, no usar flags ambiguos, no sustituir descripción
oficial larga por paráfrasis. Si sólo repetiría título y organismo, omitir
el bloque. Fecha y texto coexistentes deben conservarse sin elegir uno.
Si una futura pieza resume una lista, no inventar categoría paraguas.
La composición es InfoCs-derived y debe declararse como tal; los valores
incluidos siguen siendo oficiales. Build-time, no persistida ni en hash.
Nunca generar «impulsa/mejora/beneficia», «ayuda concedida», «abierta ahora»,
«recibirás», «para todos los residentes» ni afirmaciones de finalidad/impacto
que no estén literalmente respaldadas. MVP puede empezar con hechos separados
y posponer este bloque sin perder legibilidad.

## 8. Existing Components Reuse Map

Todos están en `site/src/components/`; son genéricos, no componentes BDNS.

| Componente | Props actuales / propósito | Reutilización / límite |
| --- | --- | --- |
| RecordCard | record,href,source,category,date,geography,hasHistory | conservar estructura; futura extensión opcional de VM compacto sólo BDNS |
| RecordMeta | source,category; SourceBadge/CategoryBadge | reutilizar; no llamar call_type categoría Core |
| OfficialData | title?,slot; panel de datos oficiales | reutilizar slot para grupos BDNS; heading semántico a evaluar sin rediseño |
| InfoCsDerived | title?,slot | conservar; no introducir aquí presupuesto/finalidad oficiales |
| TechnicalDetails | recordId,officialId,hash,detectedAt,lastCheckedAt | conservar plegado y fuera de índice; no necesita cambiar para MVP |
| SourceLink | href,label?; nueva pestaña, rel seguro y aviso accesible | reutilizar sólo con href aprobado; no valida URL ni sirve para locator no clickable |
| DateValue | label,value,display; time | reutilizar sólo fechas estructuradas; textos de plazo no son time |
| ChangeTimeline | TimelineItem[]; lista/EmptyState | no tocar semántica ni fabricar cambios; labels v2 de changed_fields pueden mejorar después |

`OfficialData`/`InfoCsDerived` usan aria-label y kicker `p`, no h2: al añadir
subsecciones extensas se necesita jerarquía h2/h3 explícita, sin hacer pasar
los kickers visuales por headings. SourceLink no debe recibir locators brutos.

## 9. Presentation Helpers Gap

| Necesidad | Clasificación | Decisión |
| --- | --- | --- |
| fecha ISO por rol | EXISTING REUSABLE | formatPortalDate + DateValue, sin inferir publicación |
| primaryDate/historial/geografía | EXISTING REUSABLE | conservar para superficies genéricas |
| rango + texto de solicitud | NEW DETERMINISTIC HELPER | roles separados, omisiones, no fechas inventadas ni vigencia |
| decimal sin moneda | NEW DETERMINISTIC HELPER | agrupación decimal sobre string exacto; no conversión binaria ni € |
| listas oficiales | PRESENTATION ONLY | listas semánticas, no traducción/catálogo propio |
| jerarquía de autoridad | NEW DETERMINISTIC HELPER | ordenar nivel1→2→3 sin interpretar competencia; no duplicar Core innecesariamente |
| labels BDNS por rol | PRESENTATION ONLY | mapa explícito de conceptos, valores oficiales sin enums frágiles |
| clickability de bases | EXISTING REUSABLE (Python; frontera pendiente) | una única política productiva, ver sección 11 |
| metadata documental | NEW DETERMINISTIC HELPER | descripción/filename/fecha y referencias, no PDF |
| tri-state abierto | DO NOT CREATE (MVP) | false/true/ausente no tienen label de vigencia aprobado |
| traducción/resumen LLM, parseo legal, municipio desde autoridad | DO NOT CREATE | fuera del contrato |
| ficha humana/document download URL | DO NOT CREATE (MVP) | no derivar rutas nuevas sin gate contractual específico |

Sin nuevos helpers de cálculo financiero, ranking ni filtros en E1.

## 10. Proposed BDNS ViewModel

Diseño en papel: futuro `site/src/lib/presentation/bdnsRecordView.ts`;
no se crea ese archivo en E1. Forma aproximada, no implementación completa:

```ts
interface BDNSRecordView {
  readonly kind: 'bdns';
  readonly card: {
    readonly callType?: string;        // oficial, sin reinterpretar
    readonly budget?: DisplayBudget;   // número exacto + concepto + moneda opcional
  };
  readonly officialFacts: readonly OfficialFactView[];
  readonly eligibility: {
    readonly beneficiaryTypes: readonly ClassificationView[];
    readonly sectors: readonly ClassificationView[];
    readonly impactRegions: readonly string[];
  };
  readonly application?: ApplicationView; // fechas y textos separados; no status
  readonly regulatoryBases?: {
    readonly description?: string;
    readonly sourceLocator?: string;   // literal
    readonly clickableHref?: string;  // derivado, sólo literal HTTPS aprobado
  };
  readonly documents: readonly DocumentMetadataView[];
  readonly extracts: readonly ExtractMetadataView[];
  readonly provenance: { readonly technicalApiHref: string; readonly attribution: string };
  // en pocas palabras: piezas trazables opcionales, no summary editorial persistido
}
```

`OfficialFactView` conserva origen/path canónico y rol además del display;
no se convierte en un dictionary Any. DisplayBudget contiene value exacto,
formattedValue y label; nada vuelve a data/. ApplicationView omite grupo vacío
(p. ej. application con sólo abierto no produce «Plazo no indicado» como hecho).
Strings se renderizan con escape Astro, nunca set:html. VM se construye una vez
desde proyección validada; Astro consume grupos, no interpreta dato fuente.
La trazabilidad genérica y Events permanecen en el ViewModel actual.

## 11. Frontend Contract Recommendation

**Elegida A: ampliar FrontendRecord con bloque source-specific tipado**,
conceptualmente `bdns?: FrontendBDNSData`. No copiar todo el modelo de negocio,
ni crear dataset paralelo; es proyección build-time readonly del contrato fuente.
Preservar decimal string, fechas ISO, labels/codes y locator literal.

E2 debe validar explícitamente en la frontera canonical.ts: source=bdns,
category=grants.call, hash contract v2, extension_version=1.0, shape cerrado,
arrays tipados, optionalidad, fechas reales, decimal exacto, IDs documentales
únicos y reglas del locator/URLs. Campos desconocidos en la extensión deben
fallar cerrado, no publicarse automáticamente. No registrar valor fuente en
errores. Record BDNS productivo v2 sin extensión es error de contrato; BOE con
extensión BDNS también. Mantener compatibilidad documentada para fixtures/v1,
sin inventar extensión para ellos ni volver a activar v1 productivo.

Las interfaces frontend declaran sólo la superficie necesaria, con referencia
al schema como autoridad. No calculan hashes, identidad, eligibility, Privacy
ni publication authorization; esos gates siguen en Python. Un type guard
explícito encamina BDNS al VM específico. BOE sigue su camino genérico sin
obligar a extender financial/document Core ni remodelar todas las fuentes.

| Alternativa | Evaluación |
| --- | --- |
| A: bloque BDNS tipado en FrontendRecord | mínima respecto a loadPortalData/cards/events existentes; elegida |
| B: unión discriminada de todo FrontendRecord | posible refinamiento futuro; ahora fuerza cambios transversales mayores |
| C: proyección paralela fuera de FrontendRecord | duplica carga/unión por ID y facilita divergencia de páginas/listados |
| D: raw source_data/Any o lectura directa Astro | pierde fail-closed/tipado y dispersa lógica; rechazada |

### Frontera Python/TypeScript de clickability: gate explícito E2

**Decisión E2 aprobada (2026-10-06):** `source_locator projection = literal
text only`; `cross-language clickability = deferred`. E2 no incorpora Python
al build, no implementa un segundo algoritmo TS y no genera href/flags.
La recomendación de fachada Python siguiente queda diferida, no adoptada.
El frontend comprueba shape/tipos, no repite Privacy, Publication, validación
de hash, normalización ni seguridad de URLs. Los valores canónicos son literales.

Implementación E2: `types.ts` añade `FrontendRecord.bdns?` y siete subtipos
readonly más `FrontendBDNSData`; `canonical.ts` proyecta todos los campos
aprobados con claves cerradas, versión 1.0, strings exactos y fechas reales.
Null opcional equivale a ausencia; arrays omitidos son [], pero arrays null
son error. `source_data` sólo permite bdns conforme al schema actual.
Una extensión exige source BDNS, category grants.call y hash version 2;
`records.ts` exige extensión para toda carga pública BDNS, dejando las
llamadas históricas directas al adapter compatibles sin extensión.
IDs documentales deben ser enteros no negativos seguros en JS: se rechazan
valores fuera de precisión, nunca se redondean intencionalmente. No son importes.
No hay output nuevo de UI ni cambios del modelo canónico; las funciones son
proyección, no ViewModel. Testing automatizado permanente queda para E6;
E2 usa check/build y comprobaciones efímeras sin dependencias nuevas.

El helper único actual `enrichment.clickable_bdns_regulatory_bases_url` es
Python; **no puede importarse directamente desde Astro/TS**. deploy-pages.yml
sólo configura Node, npm y Astro, no un runtime Python del proyecto.
No afirmar que la reutilización ya está resuelta ni reemplazarlo por
`new URL()` (normaliza/acepta formas distintas).

Recomendación conservadora para E2: una fachada build-time, por lote local,
que reutilice el helper Python existente con runtime/dependencias declarados
y contrato de salida mínimo validado; resultados efímeros, nunca flags
persistidos en Records. No subprocess por card ni consultas de red.
Esta decisión requerirá aprobación explícita del alcance build/deployment
antes de implementar; E1 no autoriza modificar workflow/dependencias.
Hasta cerrar esa frontera, el fallback seguro es mostrar bases y locator
como texto escapado, sin enlace, incluso para HTTPS; no bloquea el MVP de
hechos. No mantener dos algoritmos independientes de navegabilidad.

## 12. Pagefind Impact

Hechos de código: package.json construye Astro y ejecuta Pagefind 1.5.2 sobre
dist. El único `data-pagefind-body` encontrado está en el article de ficha.
Metadata explícita: kind, source, category, authority, primary_date_iso,
primary_date_label, primary_date_value, public_url. `title` no se declara
manualmente allí; search.ts espera meta.title del índice generado.
No se reconstruyó ni examinó el índice con un build en E1.

El cuerpo indexable actual incluye breadcrumbs, título, organismo,
OfficialData, InfoCsDerived, notas de procedencia/metodología e historial.
TechnicalDetails y su wrapper llevan data-pagefind-ignore; el contenedor
invisible de metadata también evita que sus textos dupliquen el cuerpo.
No existe indexación directa del JSON `source_data`.

Inferencia respaldada por markup/config: nuevos textos visibles dentro del
article, sin ignore, ampliarán términos en el próximo build normal sin un
indexer BDNS adicional. No implica filtros ni cambios automáticos de cards
de resultados. search.ts sólo usa metadata actual y plain_excerpt, con
textContent (no HTML de snippets); no consume RecordCard o FrontendRecord.

Decisión propuesta: indexar finalidad, tipo, instrumentos, labels elegibles,
sectores y descripciones de bases/documentos visibles. Excluir locator bruto,
filenames por defecto, ID documental, datMod, hash y versiones técnicas.
Preservar códigos BDNS públicos actuales. Si después se añaden budget/call_type
a resultados o filtros por sectores/destinatarios/fecha por rol, harán falta
metadata/filtros explícitos y cambios acotados en search.ts; no basta el texto
del cuerpo. No mezclar received_date con primary_date_iso bajo «Publicado».
No implementar filtros/benchmark/fulltext ni hidden keywords en E1.

## 13. Accessibility Plan

Conservar breadcrumbs con aria-current, h1, skip-link, foco visible, `<time>`,
listas de historial, aviso de nueva pestaña y Live Region de búsqueda.
Hechos en dl/dt/dd; grupos largos como sections con h2/h3 y aria-labelledby;
beneficiarios/sectores/documentos en listas. Periodos textuales en texto,
fechas estructuradas con datetime ISO. Locator no clickable como texto
seleccionable, no botón deshabilitado ni enlace reparado.
No depender sólo de color/badge para distinguir oficial/derivado.
Details sólo para información técnica/secundaria, no para esconder presupuesto
o plazos esenciales. No usar innerHTML para contenido oficial. No inferir
lang de título cooficial, filename o autoridad.

### Existing UI primitives reusable for 10B-E

styles/global.css + tokens.css + themes.css: detail-shell/content-shell,
detail-header, detail-authority, page-section, section-heading, surface-panel,
official-panel/derived-panel, detail-grid, source-panel, attribution,
record-card/list/meta, geography-list, muted, mono-value, source-link,
technical-details. Detail-grid es una columna base y dos desde 480px;
detail-columns usa dos bloques de seis columnas sobre grid de doce desde
768px. Listados usan ese mismo patrón; strings largos tienen overflow-wrap.
Shell cambia gutters a 768/1024px; controles/cards adaptan debajo de 480px.
Themes dark/light comparten variables semánticas; BaseLayout carga CSS y
selecciona tema, sin necesidad de nuevos colores/tipografía/navegación.
No se verificó visualmente responsive/contraste: eso es validación futura,
no un PASS visual por lectura de CSS.

## 14. BOE/BOP Regression Boundary

BOE tiene un Record local y debe conservar su proyección, primaryDate,
OfficialData, SourceLink, timeline, listados y metadata Pagefind. Ninguna
propiedad BDNS será requisito global. No sustituir financial.grantAmount
con presupuesto BDNS ni documents Core con metadata de extensión.

BOP tiene cero Records públicos; continúa
`TECHNICALLY_READY_PUBLICATION_BLOCKED — reuse_policy_unresolved`.
PUBLIC_SOURCE_IDS lo excluye. No crear fichas BOP ni usarlo para diseñar
prematuramente un catálogo universal. Los conteos/source pages siguen
derivados del mismo conjunto autorizado. Attribution IGAE y metodología
se conservan; no cambiar filtros de fuente o Events.

Regresiones futuras a comprobar (no ejecutadas E1): igualdad de vistas BOE,
cards home/fuente, búsqueda (DOM separado), ausencia BOP, títulos/slugs,
historial v1/v2 y exclusión técnica del índice. Labels unknown changed_fields
v2 usan hoy fallback; refinarlas no es requisito del MVP.

## 15. Human Readability MVP Surface

MVP justificable para implementación posterior:

1. Contrato tipado de BDNS y VM específico, sin alterar Records/Hashes.
2. Detail: título/organismo/Código BDNS existentes; presupuesto exacto sin
   moneda inferida, tipo/instrumentos, finalidad literal, destinatarios
   elegibles/sectores, recepción y solicitud fecha/texto por rol.
3. Bases: descripción y locator literal, enlace únicamente tras cerrar
   reutilización de clickability; no-clickable queda texto, no omisión.
4. Documentos: descripciones y fecha de publicación documental; filename
   secundario si aporta identificación. **Metadata-only en MVP**, sin links
   de descarga nuevos, PDFs ni afirmaciones sobre contenido.
5. Procedencia: API técnica con label honesto («Datos oficiales BDNS / API»),
   atribución IGAE, trazabilidad e historial actuales.
6. Card futura compacta: tipo literal y presupuesto con label; mantener
   título, organismo, territorio y fecha claramente atribuida. Sin listas
   elegibles, bases/documentos ni párrafos de finalidad en card.

La jerarquía/ámbito fuente y título cooficial pueden añadirse cuando presentes,
sin inflar cards. En pocas palabras no es requisito para declarar legibilidad
del MVP: opcional tras revisión de composición determinista. E2 sólo crea la
proyección; no implementa esta UI completa ni amplía política de publicación.

## 16. Deferred Fields

Abierto y flag de diario: semántica insuficiente para badges/estado general.
Currency: ninguna presente; no completar EUR. Extractos: cero observados,
mantener tipo futuro sin bloques vacíos ni inferirlos desde flag true.
Beneficiary code: ausente; no crear códigos ni traducir labels.
Document modified_value: formato universal no confirmado, no parsear
timestamp; ID documental es referencia secundaria, no comprensión principal.
Links de documento/ficha humana: no persistidos; anteriores contratos citan
endpoints/patrón, pero su habilitación y estabilidad necesitan gate específico
de enlaces, sin requests implícitas en E1. API actual permanece fallback.
No convertir sede electrónica en ficha oficial de convocatoria.

MRR/ayudaEstado/reglamento/fondos/objetivos no pertenecen al canonical aprobado:
no recuperarlos desde API ni exponerlos. No fulltext, OCR, archivos, personas
beneficiarias o concesiones nominativas. Filtros/facetas/rangos financieros,
estado abierto/cerrado, mapas y explicación legal quedan fuera.

Dirección futura **InfoCs — PUBLIC DATA EXPLORATION LAYER**:
Explore Castellón, What Changed, Territorial History, Explain This Data.
Human Readability es infraestructura previa; E1 no diseña ni implementa esas
funciones ni adopta aquí la dirección inspirada en Objetivo 176.

## 17. Risks

- Fidelidad: hacer Number de Decimal, inferir EUR o trim del locator modifica
  significado/precisión. La presentación no reescribe datos canónicos.
- Semántica: recepción/documento/extracto/detección no son fechas equivalentes;
  false no significa cierre; categorías no son personas beneficiadas.
- Navegación: SourceLink no valida; URL parser JS no equivale a helper Python.
  La frontera cross-language es un gate concreto, no trabajo ya disponible.
- Contrato: TypeScript types no validan JSON runtime. La proyección debe fallar
  cerrado en versión/shape desconocidos sin imprimir payloads en errores.
- Privacidad: metadata y filenames no son inocuos por definición. Gates ya
  autorizaron canonical; no enriquecer con texto/API/PDF fuera de ellos.
- UX: longitud de títulos/finalidad/labels y jerarquía duplicada; evitar cards
  gigantes, paráfrasis/truncación que se haga pasar por dato íntegro y bloque
  de plazo vacío basado sólo en abierto.
- Búsqueda: notas repetidas y filenames/locators pueden dominar excerpts.
  Excluir ruido técnico sin ocultar datos esenciales sólo para rankear mejor.
- Histórico: contratos antiguos conservan frases pending de su fase; para
  estado productivo usar PROJECT_STATE actualizado, no reabrir cutover.
- Muestra: snapshot de 42 no garantiza formas futuras; tipos opcionales y
  fail-closed deben cubrir contrato, no sólo shapes hoy observados.

## 18. Recommended Implementation Sequence

| Fase | Alcance / gate de salida |
| --- | --- |
| 10B-E2 — BDNS FRONTEND CONTRACT & TYPED PROJECTION | bloque frontend BDNS, runtime parse cerrado, exact decimals/dates/locators, binding; BOE igual. Aprobar cómo consumir helper único de clickability o empezar text-only. Sin nueva fuente ni UI completa. |
| 10B-E3 — BDNS PRESENTATION VIEWMODEL | grupos semánticos, formatting exacto, omisiones, periodos, listas/documentos; composición opcional trazable; no flags persistidos/estado inferido. |
| 10B-E4 — BDNS HUMAN-READABLE DETAIL | OfficialData ampliada sólo BDNS, bases/documentos metadata, API label/attribution, accesibilidad; sin rediseño ni PDF. |
| 10B-E5 — BDNS CARD & SEARCH SURFACE | card compacta home/fuente; adaptar resultados DOM sólo si aprobado; indexar texto visible y excluir ruido, no filtros aún. |
| 10B-E6 — VALIDATION & PUBLISH | tests proporcionales, build, QA responsive/light-dark/accesibilidad y Pagefind, BOE/BOP no regresión; publicación sólo con autorización. |

E1 responde los diez gates: la pérdida está en adaptRecord; los 44 paths de
contrato/35 observados están inventariados; presencia por campo y shapes
contados; significado/prohibiciones explícitos; asignación de superficies,
deferred fields, componentes reutilizables, bloque tipado+VM, frontera BOE y
MVP definidos. La clickability cross-language necesita decisión en E2, no
bloquea este diseño ni autoriza un segundo validador divergente.

Operaciones E1: source network requests 0; collectors/migraciones/workflows 0;
tests/builds 0; data writes 0. Único archivo creado: este documento.
No cambios de PROJECT_STATE, código, schema, frontend o configuración.

**Resultado: BDNS_HUMAN_READABILITY_FRONTEND_SURFACE_AUDIT_COMPLETE.**
