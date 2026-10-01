# BDNS — Human Readability Field Map

Auditoría y propuesta de datos, Phase 10B-A. Fecha: 2026-10-01.
**No es un contrato implementado ni autoriza migración/publicación.**

## 1. Purpose

Hacer comprensibles las convocatorias sin confundirlas con concesiones,
reescribir su título, inventar importes concedidos ni convertir interpretación
en dato oficial. Separar dato oficial, procesado por InfoCs y presentación.
Mantener arquitectura estática, privacidad, atribución IGAE y procedencia.

### Evidencia y alcance

- Inspeccionados `models.py`, `parser.py`, `normalize.py`, `transport.py`,
  `ingest.py`, `runner.py` BDNS; modelos/schema Record, proyección hash/diff,
  Privacy Gate, publication policy; fixtures y tests BDNS pertinentes;
  adapter/types/presentation Astro, portada, RecordCard, SourceLink y ficha.
- Contratos locales: SOURCE_AUDIT, source_contract, TRANSPORT_CONTRACT,
  NORMALIZATION_POLICY, PUBLICATION_POLICY y documentación operativa.
- [OpenAPI oficial ya auditado](https://www.infosubvenciones.es/bdnstrans/estaticos/doc/snpsap-api.json)
  y [documentación oficial](https://www.infosubvenciones.es/bdnstrans/GE/es/doc):
  referencias del contrato existente; **no se volvieron a descargar**.
- Precheck limpio. Fetch: HEAD local
  `e65c17714019b610c5fe4b65983eb88599a85a9c`; origin/main
  `42278f1decc12ad85823b7ef414121a4f24f3d43`. Dos commits nuevos de datos
  (`data(bdns)` y `data(boe)`). Sin pull, ejecución de collectors ni escritura
  en data. Se leyeron los Records nuevos con `git show origin/main:…`.
- HEAD contiene 8 Records BDNS; origin/main contiene 32. PROJECT_STATE sigue
  describiendo el checkpoint anterior: no se actualiza en esta auditoría.
- **Dos GET de DETAIL**, sin search, redirects, retries ni descarga documental:
  `GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias?numConv=929452`
  y el mismo endpoint con `numConv=931805`. Ambos HTTP 200, application/json;
  cuerpos de 3.051 y 2.635 bytes. Lectura en memoria, límite 2 MiB y timeout
  15 s como política cliente. No respuestas raw guardadas ni fixtures reales.
  Motivo: los Records mínimos no conservan los campos descartados y la fixture
  es sintética; faltaba confirmar campos adicionales, plazos y documentos.
- `929452`: órgano municipal, presupuesto 3270, dos documentos, fechas de
  solicitud null y textos de plazo presentes. `931805`: órgano provincial
  diferente, presupuesto 20000, un documento y fechas de solicitud presentes
  (2026-01-23..2026-09-01), textos null. Ambas: tipo literal
  «Concesión directa - instrumental», región ES522 exacta y ningún anuncio.
  La segunda muestra aporta también una estructura de plazos diferente.
  No se reproducen títulos, nombres personales ni nombres de ficheros reales.
- Dos ejemplos **no certifican** todos los tipos/estados posibles, semántica
  de campos sólo null, estabilidad histórica ni seguridad de cada adjunto.

## 2. Current gap

El parser ya conserva presupuesto exacto, tipo, instrumentos, destinatarios
por tipo, sectores, finalidad, bases, plazos, documentos y extractos. El
normalizador publica solamente identidad, título, órgano compuesto, provincia,
URL API, call_id, fechas InfoCs y, condicionalmente, publicación de un extracto.
El resto desaparece antes del RecordStore; no existe raw/sidecar recuperable.

Astro dispone de financial/documents en su contrato, pero no de description ni
de estos detalles BDNS; la card/ficha tampoco presenta presupuesto o adjuntos.
«Fuente» / «Abrir publicación oficial» abre el API de detalle. El endpoint es
oficial y verificable, pero la etiqueta no explica que son datos técnicos.

Dos barreras adicionales: la metadata policy v1 rechaza description, financial,
documents y otros contenidos fuera del alcance mínimo; Privacy Gate no recorre
una extensión futura. Enriquecer sólo parser/schema/UI **no basta**.

## 3. Official field inventory

Ubicación: `D` = raíz de DETAIL; `S` = elemento de búsqueda. Cada path escrito
es exacto; `[]` indica colección. Ejemplos entre `<…>` o example.invalid son
ilustrativos, no contenido real añadido al dataset.

Null/cardinalidad: `?` = el parser admite ausencia/null (0..1); `!` = requiere
valor (1, dentro del elemento presente); `*` = lista 0..n, cuyo contenedor
ausente/null se transforma actualmente en vacío. Es **aceptación InfoCs**, no
garantía de obligatoriedad/nullability oficial. `O-null` = null observado en
ambas muestras, tipo no-null no confirmado aquí; `O-list` = sólo [] observado.
Las garantías oficiales de nullability no están cerradas para todos los campos.

Estado `P/N/R/UI`: parseado / normalizado / persistido / mostrado actualmente.
`S` sí; `—` no; `cond` condicional; `par` parcial; `tec` sólo técnico.
Normalización/persistencia describen el código, no presencia universal en cada
Record. Clase y hash propuestos se desarrollan en secciones 5–7.

| Path exacto | Tipo; null/card. | Ejemplo seguro | Significado respaldado / límite | P/N/R/UI | Clase; hash propuesto |
| --- | --- | --- | --- | --- | --- |
| S.numeroConvocatoria | string; ! | `900001` | Código público, enlazado a detalle | S/S/S/S | A; identidad, no nuevo hash |
| D.codigoBDNS | string; ! | `900001` | Código de convocatoria, no concesión | S/S/S/S | A; call_id ya en hash |
| D.id | integer; ? | `700001` | Identificador técnico distinto del código | S/—/—/— | D; no |
| S.id | integer; ? | `700001` | ID técnico de summary | S/—/—/— | D; no |
| D.organo | object; ? | `{nivel1: <nivel>}` | Jerarquía del convocante | S/par/par/par | B; ver niveles |
| D.organo.nivel1 | string; ? | `LOCAL` | Nivel literal, no enum Core inferido | S/par/par/par | B; sí si se conserva |
| D.organo.nivel2 | string; ? | `<organismo>` | Nivel literal | S/par/par/par | B; sí |
| D.organo.nivel3 | string; ? | `<unidad>` | Nivel literal | S/par/par/par | B; sí |
| S.nivel1 | string; ? | `<nivel>` | Jerarquía resumida; detalle preferido | S/—/—/— | E; no duplicar |
| S.nivel2 | string; ? | `<organismo>` | Igual | S/—/—/— | E; no duplicar |
| S.nivel3 | string; ? | `<unidad>` | Igual | S/—/—/— | E; no duplicar |
| S.codigoInvente | string; ? | `<código>` | ID órgano tras unión por código BDNS | S/cond/cond/tec | A/D; no nuevo hash de ID |
| D.sedeElectronica | string; ?; O-null | `https://sede.example.invalid/` | Sede, no ficha única de convocatoria | S/—/—/— | B; sí si enlace administrativo |
| D.descripcion | string; ? | `<título oficial>` | **Título**, no objeto independiente | S/S/S/S | A; sí, actual |
| D.descripcionLeng | string; ?; null observado | `<título cooficial>` | Alternativa literal; fallback de título | S/cond/cond/cond | B; sí si adicional |
| S.descripcion | string; ? | `<título listado>` | No sustituir el detalle válido | S/—/—/— | E; no duplicar |
| S.descripcionLeng | string; ? | `<título listado>` | Igual | S/—/—/— | E; no duplicar |
| D.presupuestoTotal | JSON number → Decimal; ? | `3.27E+3` → `3270` | Presupuesto total convocatoria | S/—/—/— | B; sí |
| D.tipoConvocatoria | string; ? | `Concesión directa - instrumental` | Tipo oficial literal, no grant.resolution | S/—/—/— | B; sí |
| D.instrumentos | array; * | `[{descripcion: <instrumento>}]` | Instrumentos oficiales | S/—/—/— | B; sí |
| D.instrumentos[].descripcion | string; ! | `<instrumento oficial>` | Label; código no observado en muestras | S/—/—/— | B; sí |
| D.tiposBeneficiarios | array; * | `[{descripcion: <tipo>}]` | Categorías elegibles, no adjudicatarios | S/—/—/— | B; sí |
| D.tiposBeneficiarios[].codigo | string; ?; ausente en muestras | `<código oficial>` | Parser admite código; fixture sintética | S/—/—/— | B; sí cuando exista |
| D.tiposBeneficiarios[].descripcion | string; ? | `PERSONAS JURÍDICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA` | Clasificación oficial | S/—/—/— | B; sí |
| D.sectores | array; * | `[{codigo: "S", descripcion: <label>}]` | Clasificación sectorial | S/—/—/— | B; sí |
| D.sectores[].codigo | string; ? | `S` / `88` | Código fuente; no asumir versión taxonómica | S/—/—/— | B; sí |
| D.sectores[].descripcion | string; ? | `<sector oficial>` | Label fuente, no análisis de impacto | S/—/—/— | B; sí |
| D.regiones | array; * | `[{descripcion: <región>}]` | Regiones de impacto | S/par/par/par | B; sí para conjunto observado |
| D.regiones[].descripcion | string; ! | `ES522 - Castellón / Castelló` | Match exacto permite provincia canónica | S/S/S/S | B/A; sí si extensión conserva conjunto |
| D.fechaRecepcion | string ISO date; ? | `2026-09-15` | Recepción/registro BDNS, no publicación | S/—/—/— | B; sí |
| S.fechaRecepcion | string ISO date; ? | `2026-09-15` | Fecha resumida, preferir detalle | S/—/—/— | E; no duplicar |
| D.fechaInicioSolicitud | string ISO date; ?; null observado | `2026-01-23` | Inicio solicitud según fuente | S/—/—/— | B; sí |
| D.fechaFinSolicitud | string ISO date; ?; null observado | `2026-09-01` | Fin solicitud según fuente | S/—/—/— | B; sí |
| D.textInicio | string; ?; null observado | `<condición oficial de inicio>` | Inicio textual, no fecha parseada | S/—/—/— | B; sí |
| D.textFin | string; ?; null observado | `<condición oficial de fin>` | Fin textual, no fecha inferida | S/—/—/— | B; sí |
| D.descripcionFinalidad | string; ? | `<finalidad oficial>` | Label/descripción fuente; no necesariamente objeto | S/—/—/— | B; sí |
| D.descripcionBasesReguladoras | string; ? | `<nombre de las bases>` | Descripción de bases, no fulltext | S/—/—/— | B; sí |
| D.urlBasesReguladoras | string; ? | `https://sede.example.invalid/bases` | Enlace recibido, validar URL | S/—/—/— | B; sí |
| D.sePublicaDiarioOficial | boolean; ? | `false` | Indicador diario; no estado abierto/cerrado | S/—/—/— | B; sí |
| D.abierto | boolean; ? | `false` | Parser lo nombra open_ended_application; no basta para estado vigente | S/—/—/— | B; sí, sin badge abierto/cerrado |
| D.documentos | array; * | `[{id: 800001, …}]` | Metadata, no contenido binario | S/—/—/— | B; sí para conjunto material |
| D.documentos[].id | integer; ! | `800001` | ID documento para endpoint documentado | S/—/—/— | B; sí, pertenencia |
| D.documentos[].descripcion | string; ? | `<descripción oficial>` | Texto potencialmente sensible | S/—/—/— | B; sí, sujeto a privacidad |
| D.documentos[].nombreFic | string; ? | `documento-ejemplo.pdf` | Filename, no prueba MIME/contenido | S/—/—/— | B; sí si publicado |
| D.documentos[].long | integer; ? | `1024` | Longitud fuente, no medición InfoCs | S/—/—/— | D; no, indicador no material por sí solo |
| D.documentos[].datPublicacion | string ISO date; ? | `2026-09-15` | Publicación documento, no convocatoria | S/—/—/— | B; sí |
| D.documentos[].datMod | string; ? | `2026-09-15` | Modificación documental; parser conserva texto | S/—/—/— | B; sí, señal fuente sin afirmar diff binario |
| D.anuncios | array; * | `[{numAnuncio: 1, …}]` | Extractos de diario, no otra convocatoria | S/par/par/par | B; sí para metadata material |
| D.anuncios[].numAnuncio | integer; ? | `1` | Número no demostrado globalmente estable | S/—/—/— | D; no como identidad global |
| D.anuncios[].titulo | string; ? | `<título extracto>` | Título fuente, no fulltext | S/—/—/— | B; sí, sujeto a privacidad |
| D.anuncios[].tituloLeng | string; ? | `<título cooficial>` | Igual | S/—/—/— | B; sí |
| D.anuncios[].cve | string; ? | `<CVE oficial>` | Identificador cuando exista | S/cond/—/— | B; sí |
| D.anuncios[].desDiarioOficial | string; ? | `BOLETÍN OFICIAL DEL ESTADO` | Diario explícito | S/cond/—/— | B; sí |
| D.anuncios[].url | string; ? | `https://www.boe.es/…` | URL oficial cuando verificable | S/cond/—/— | B; sí |
| D.anuncios[].datPublicacion | string ISO date; ? | `2026-09-26` | Fecha extracto; un único extracto identificable puede alimentar published_at | S/cond/cond/cond | B/A; sí |
| S.mrr | boolean; ? | `false` | Indicador resumido; no inferir fondo/importe | S/—/—/— | B diferido; no hasta semántica cerrada |
| D.mrr | boolean observado; no parser | `false` | Indicador no explicado por las muestras | —/—/—/— | B diferido; no ahora |
| D.ayudaEstado | O-null; 0..1 observado | `null` | Referencia de ayuda de Estado; estructura no-null pendiente | —/—/—/— | B diferido; no ahora |
| D.urlAyudaEstado | O-null; 0..1 observado | `null` | Posible enlace relacionado; destino no demostrado | —/—/—/— | B diferido; no ahora |
| D.reglamento | O-null; 0..1 observado | `null` | Tipo/semántica no-null pendiente | —/—/—/— | B diferido; no ahora |
| D.fondos | O-list; 0..n observado | `[]` | Colección oficial; elementos no observados | —/—/—/— | B diferido; no ahora |
| D.objetivos | O-list; 0..n observado | `[]` | Colección oficial; elementos no observados | —/—/—/— | B diferido; no ahora |
| D.sectoresProductos | O-list; 0..n observado | `[]` | No confundir con sectores; taxonomía pendiente | —/—/—/— | B diferido; no ahora |
| D.advertencia | string observado; escalar | `<aviso legal oficial>` | No contenido administrativo del Record | —/—/—/— | E por Record; condiciones a nivel fuente |
| D.anuncios[].texto | tipo ambiguo en OpenAPI previo | `<no usado>` | Fulltext/discrepancia contractual | —/—/—/— | E; no |
| D.anuncios[].textoLeng | string según auditoría previa | `<no usado>` | Fulltext fuera de alcance | —/—/—/— | E; no |

No aparecieron `objeto`, `textoInicio` ni `textoFin` en las dos respuestas.
Los nombres soportados son `textInicio`/`textFin`. No inventar aliases en el
contrato fuente. Tampoco se observó moneda, URL de ficha humana ni URL directa
de documento dentro del detalle. Las fechas/estructuras de anuncios restantes
se conocen por contrato/parser/fixture, no por estas dos muestras vacías.

## 4. Source semantics

- **presupuestoTotal:** presupuesto total de la convocatoria según el contrato
  auditado; etiqueta «Presupuesto de la convocatoria». No «importe concedido»,
  «dinero recibido», importe por persona ni pago ejecutado. Un registro de tipo
  «Concesión directa - instrumental» sigue siendo convocatoria, no concesión
  nominativa en InfoCs.
- Los presupuestos observados fueron enteros 3270 y 20000. El transporte usa
  `json.loads(..., parse_float=Decimal)` y el parser admite int/Decimal, no
  float/string/bool ni no-finitos. Inspección en memoria de `3.27E+3` produjo
  Decimal exacto y forma plana `3270`; **no fue el lexema live observado**.
  Serialización propuesta: string decimal plano, sin redondeo binario ni
  conversión a Number en el frontend. Money actual obliga currency: no forzar
  ese modelo sin evidencia de moneda. Ninguna de estas respuestas la declara;
  símbolo € **condicionado** a cerrar evidencia oficial explícita. Hasta
  entonces número exacto con «moneda no indicada», o sin bloque monetario.
- `descripcion` es el título oficial. No se demostró descripción/objeto
  independiente. `descripcionFinalidad` no autoriza una sinopsis de documentos.
- `fechaRecepcion`: «Registrado/recibido en BDNS», nunca «Publicado».
  `fechaInicioSolicitud`/`fechaFinSolicitud`: inicio/fin de solicitud;
  `textInicio`/`textFin`: texto fuente literal, no fechas deducidas.
  Si fechas y textos coexisten, mostrar ambos con sus roles; no elegir uno
  silenciosamente ni calcular un estado administrativo por una sola bandera.
- `abierto` se conserva como indicador fuente; se necesita semántica oficial
  adicional antes de mostrar «abierta/cerrada». Un fin de solicitud pasado
  puede mostrarse como fecha sin atribuir retirada/cierre de la convocatoria.
- `anuncios[].datPublicacion` es publicación del extracto;
  `documentos[].datPublicacion` es publicación del documento. No intercambiarlas
  con recepción o detected_at. DatMod observado es fecha, pero el parser no
  garantiza formato universal: preservar valor; no inventar hora/zona.
- Beneficiarios son **tipos elegibles**; no Awardee ni lista de perceptores.
  Sectores son códigos/labels de la fuente; no asumir versión CNAE exacta,
  jerarquía, equivalencias entre `S` y `88` ni evaluar impacto local.
- Órgano jerárquico e INVENTE no justifican municipio/administration_level
  inferidos. ES522 permite provincia; no deducir municipio de nombres/URLs.

## 5. Field classification

La tabla de inventario asigna todas las clases; prioridad de conservación:

- **A — CANONICAL PUBLIC DATA:** identidad, título, authority, categoría,
  provincia verificada, published_at cuando procede y enlace API existente.
  Reutilizar Core; no duplicar estas entidades dentro de la extensión.
- **B — SOURCE-SPECIFIC PUBLIC DATA:** presupuesto de convocatoria, tipo,
  instrumentos, tipos elegibles, sectores, jerarquía literal, regiones fuente,
  recepción, plazos fecha/texto, finalidad, bases y metadata documental/extractos.
  Conservar sólo campos comprendidos, tipados y admitidos por privacidad.
  MRR/ayudaEstado/reglamento/fondos/objetivos/sectoresProductos quedan **diferidos**:
  su existencia no equivale a semántica suficiente para publicar.
- **C — PRESENTATION-DERIVED:** labels, número formateado, lista de documentos
  disponibles, URL documental derivada del ID y ruta documentada, URL de ficha
  humana cuando habilitada, resumen por plantillas, fechas formateadas y badges
  explícitos. No persistirlos ni introducirlos en hash.
- **D — TECHNICAL / PROVENANCE:** id interno, document.long, número local de
  anuncio como referencia técnica, métodos/versiones de extracción, evidencia
  territorial y evidencia de transformación. No ficha principal ni identidad
  alternativa. Conservar sólo si sirve a una necesidad de auditoría; no raw.
- **E — DO NOT PERSIST / DO NOT PUBLISH:** duplicados de summary, avisos legales
  completos por Record, fulltext, campos desconocidos sin significado, datos
  personales/nominativos no autorizados, MIME/hash inventados y estado general
  inferido. Ausente/null no se convierte en texto inventado.

## 6. Canonical vs source-specific proposal

**Recomendación concreta: opción C, extensión canónica tipada
`source_data.bdns` dentro de RecordCandidate/Record, no sidecar ni JSON raw.**
Nombre/formato final sujetos a aprobación de 10B-B; versión de extensión
explícita y schema cerrado, ligada a source.id=bdns y grants.call.

| Opción | Evaluación |
| --- | --- |
| A: ampliar estructuras genéricas existentes | Reusar identidad/authority/geography/dates; financial.grant_amount no representa presupuestoTotal. Forzar todo aquí distorsiona conceptos. |
| B: gran grant genérico con todos los campos BDNS | Un presupuesto de convocatoria puede llegar a ser compartido; no hay evidencia para generalizar todos los flags/catálogos SNPSAP a BOE/PCSP/DOGV. |
| C: source_data.bdns cerrado y tipado | Separa semántica fuente y Core; permite privacidad/hash/diff/serialización explícitos y una presentación reutilizable. Elegida. |
| D: sidecar/attributes arbitrarios | Dataset doble, binding/historial/privacidad difíciles y campos desconocidos publicables por accidente. Rechazada para v1. |

Contenido conceptual, **no schema nuevo**:

```text
source_data.bdns (extension_version)
  official_title_coofficial?
  authority_hierarchy? (nivel1/nivel2/nivel3)
  budget_total? (value: exact decimal string; currency?: evidence-backed)
  call_type?
  instruments[] (official label)
  eligible_beneficiary_types[] (official code?, label?)
  sectors[] (official code?, label?)
  impact_regions[] (official label)
  received_date?
  application? (start_date?, end_date?, start_text?, end_text?, abierto?)
  purpose?
  regulatory_bases? (description?, official_source_url?)
  electronic_office_url?
  extract_published_in_official_diary?
  documents[] (id, description?, filename?, publication_date?, modified_value?)
  extracts[] (cve?, diary?, source_url?, publication_date?, titles?)
```

No redundancia de codigoBDNS, call_id, título principal, province ni source_url.
Jerarquía literal permite presentación sin parsear authority.name. Código
INVENTE sigue la unión validada, no un segundo órgano independiente.
No extender aún ayudaEstado/etc con tipos deducidos de null. Nada se copia
arbitrariamente: unknown additional fields siguen ignorados fail-safe.

BOE/PCSP/DOGV mantienen su shape sin extensión BDNS. Si futuras fuentes prueban
una semántica compartida, promover selectivamente campos a grant genérico,
con migración explícita, no desde una necesidad estética.

## 7. Content-hash participation

Participación **propuesta** por campo en el inventario; no se cambia hash aquí.
Reglas adicionales:

- Sí: presupuesto exacto, tipo, finalidad oficial, tipos elegibles, sectores,
  instrumentos, jerarquía literal, regiones observadas, fechas/plazos/textos,
  bases y sus enlaces recibidos, metadata material/document set y extractos.
  Son estado administrativo observado que puede cambiar.
- No: labels UI, formatos, resumen InfoCs, extension_version por sí sola,
  attribution, decisiones de publicación, evidencias internas, timestamps
  InfoCs, ID técnico alternativo y URL API/documento/humana **derivada**.
  URLs fuente de bases/extractos sí son estado recibido. DatMod es una señal
  documental observada; su cambio no prueba cuáles bytes cambiaron.
- Arrays sin orden administrativo: normalizar como conjuntos deterministas,
  deduplicados por identidad/valor confirmado; no reordenación = update.
  No tratar todas las listas como sets sin validar su semántica. Jerarquía y
  roles de fecha conservan orden/identidad. Null/ausencia no significan cero,
  nadie elegible ni ningún documento; definir su política antes de migrar.
- `semantic_payload()` es una whitelist cerrada; **añadir schema no añade
  hash**. Hoy incluye title/source_url, description, published_at/event_at,
  financial, procurement, grant.call_id/resolution_id/beneficiary y
  documents.source_url/sha256. No incluye authority/category/geography ni
  provenance. No atribuirles cobertura hash actual que no tienen.
- El source_url API actual **sí participa**; no cambiarlo por una URL humana
  sólo por UX: alteraría hash/diff. Añadir links de presentación separados.
- Añadir proyección explícita de los nuevos campos y versión de contrato
  semántico; diff usa esa misma proyección. Tests exactitud, cambios materiales,
  colecciones, ausencia, publicación-neutralidad y compatibilidad BOE/BDNS.
  No corregir de paso todas las exclusiones históricas del Core.
- Event v1 conserva hashes/changed_fields, no valores before/after. No generar
  un relato de cambios retrospectivos inexistentes a partir del enriquecimiento.

## 8. Privacy implications

Normalmente publicables tras controles: presupuesto, códigos/labels de tipos
elegibles y sectores, regiones, fechas, flags comprendidos. No equivalen a
una aprobación automática del Record.

Texto de título/finalidad/bases/plazos/órgano/cooficiales, nombres y descripciones
de documentos pueden contener personas físicas, NIF/NIE, emails, teléfonos,
domicilios o beneficiarios nominativos. URLs pueden contener esos datos en
path/query. Un filename también puede identificarlos. No sólo description.

Privacy Gate actual inspecciona title, description y nombres/identificadores
de Awardee en procurement/grant; **no** todos los niveles de órgano, URLs,
filenames o una nueva extensión. La futura implementación debe declarar y
testear un recorrido exhaustivo de los textos publicables de la extensión,
antes de Source Eligibility/Metadata Policy/Authorization/Stores. No sidecar
que lo eluda. Los detectores actuales no garantizan reconocer todos los nombres
personales; el enriquecimiento exige revisión de alcance y fallos cerrados.

Campos nominativos, identificadores personales, contactos/domicilios privados,
concesiones y fulltext: fuera de este alcance; no copiarlos ni filtrarlos
silenciosamente para obtener ALLOW. QUARANTINE/REJECT bloquean publicación
según los contratos existentes. Si una disociación se aprueba posteriormente,
conservar el hecho y responsable conforme al aviso legal.

Mantener [reutilización ya auditada](https://www.infosubvenciones.es/bdnstrans/GE/es/avisolegal):
atribución IGAE en superficie pública, no desnaturalizar, conservar actualización
fuente cuando conste, no insinuar patrocinio. Datos públicos no equivalen a
republicación indiscriminada ni licencia automática de adjuntos de terceros.

## 9. Document model

Metadata tipada dentro de la extensión: document_id, description?, filename?,
publication_date?, modified_value?. La longitud opcional sólo es técnica.
Nombre/description se muestran únicamente si superan controles; ID no como
título principal. Si faltan labels, «Documento oficial» es label UI, no nombre
atribuido a la fuente.

Ruta individual **documentada en el contrato existente**:
`https://www.infosubvenciones.es/bdnstrans/api/convocatorias/documentos?idDocumento=<id>`.
Derivar official_url con un entero validado en el adaptador de enlaces; no
guardarla duplicada ni usar id interno de convocatoria como document_id.
Link-only; no solicitud binaria aquí. MIME contractual application/octet-stream
no asegura PDF ni contenido; filename.pdf no certifica MIME. Sin OCR, fulltext,
mirror, copia, sha256 ni «verificado por InfoCs» sobre contenido no leído.

Core Document carece de ID, descripción, filename y fechas; no hacer dos listas
duplicadas. Recomendación v1: metadata/enlaces BDNS en extensión, no crear
Core Document paralelo. Cualquier promoción genérica posterior necesita un
único modelo y la misma barrera de privacidad/publicación.

## 10. Source-link strategy

Tres roles distintos, no un botón ambiguo:

1. **Ficha oficial humana:** SOURCE_AUDIT ya identifica el ejemplo oficial
   [ficha SNPSAP](https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias/869664).
   Evidencia de patrón público `…/GE/es/convocatorias/<Código BDNS>`, no endpoint
   REST ni contrato universal de estabilidad. Las respuestas consultadas no
   incluyen URL humana. Proponer ese template sólo tras verificar en la fase
   de enlaces que abre las fichas objetivo; **no se comprobó aquí** para 929452
   ni 931805 y no se declara enlace validado para cada registro. No inventar
   rutas nuevas ni sustituir source_url persistida.
2. **Datos técnicos:** source_url API de detalle existente. Label propuesto
   «Datos oficiales BDNS (API)» / «Ver API oficial». Si la ficha humana no puede
   validarse, éste sigue siendo el enlace disponible, claramente identificado.
3. **Documentos/bases/extractos:** enlaces individuales documentados o URLs
   recibidas, con roles diferenciados. Bases de las muestras apuntan a sedes
   electrónicas distintas; no son automáticamente la ficha BDNS.

Validación futura HTTPS y esquemas/hosts apropiados; rechazar javascript/data,
credenciales y valores sensibles. Enlaces fuente fuera de infosubvenciones
requieren procedencia verificable, no allowlist universal inventada. No inferir
MIME a partir de URL. Link labels/templates son presentación; URLs oficiales
recibidas materialmente diferentes pueden entrar en hash según sección 7.

## 11. Presentation model

Contrato conceptual `BDNSCallView`, calculado durante build desde el Record
enriquecido y SourceMeta, sin lectura live ni API runtime:

- source/category badges y título exacto; tipo literal si existe;
- budget {exactValue, currency?, display, label: Presupuesto de la convocatoria};
- authority {displayName, officialHierarchy?}, provincia canónica;
- officialPurpose?, factualSummary? y eligibleBeneficiaryTypes[];
- instruments[], sectors[] con códigos opcionales;
- application {startDate?, endDate?, startText?, endText?}, receivedDate?;
- bases {label?, url?}, documents[] y extractPublicationDates[];
- links {humanOfficial?, technicalApi, bases?, documents[]};
- realTimeline, attribution fuente y technicalDisclosure separado.

Tres capas visibles: **Dato oficial** (valor recibido); **Procesado por InfoCs**
(provincia normalizada, formatos, agrupaciones y resumen por reglas);
**Detalles técnicos** (API/IDs/procedencia/hash/fechas de observación).
No re-matching territorial, parser de títulos ni inferred authority en Astro.
No existe un «objeto» si la fuente no lo proporciona. Optionalidad y estados
vacíos reales, no bloques que aparenten completitud.

## 12. “En pocas palabras” rules

**No persistir texto editorial.** Plantillas deterministas en presentation/
ViewModel durante build, con trazabilidad por segmento a path oficial.
Ejemplo de plantilla: «Tipo: {tipoConvocatoria}. Destinatarios según BDNS:
{tiposBeneficiarios[].descripcion}. Finalidad indicada: {descripcionFinalidad}.»
Sólo segmentos presentes; mantener literales y no inferir vínculos causales.

No usar LLM, resumen de PDF ni extracción de nombres/intenciones desde título.
«Convenio entre X e Y» sólo si campos explícitos o un texto oficial publicable
lo afirman literalmente; no deducir partes del título ni tipos elegibles.
Si sólo hay un label de finalidad, presentar ese label, no ampliar a «impulsar
la cultura local». No evaluar bondad, impacto, eficacia o dinero recibido.
Si no hay contenido adicional útil, omitir resumen en vez de repetir título.
Texto escapado, sin HTML fuente ejecutable ni recortes que alteren significado.
El título exacto y acceso oficial permanecen disponibles.

## 13. Card model

Card breve: fuente + categoría, tipo oficial opcional, título exacto, órgano
cuando existe, provincia/municipio **sólo canónico**, presupuesto con etiqueta
correcta/moneda acreditada y fecha principal segura.

Mantener primaryDate: publishedAt → «Publicado»; si no → «Detectado por InfoCs».
Recepción o fin de solicitud, si se añaden, son líneas explícitas, no sustituyen
publishedAt. No documentos, clasificaciones largas ni IDs técnicos principales.
Nunca deducir municipio del órgano. Ausencia de presupuesto no equivale a cero.

## 14. Detail-page model

1. Fuente/categoría/tipo, título literal y órgano.
2. Presupuesto de convocatoria, sin apariencia de importe adjudicado.
3. Finalidad oficial o resumen estrictamente derivado, si útil.
4. Tipos de destinatarios, instrumentos y sectores oficiales.
5. Ámbito normalizado y regiones fuente, separados si ambos son útiles.
6. Solicitud: fechas y/o condiciones textuales. Recepción BDNS diferenciada;
   publicación de extractos/documentos con sujeto explícito. Observación InfoCs
   queda en procesado/técnico, no inventa publicación administrativa.
7. Bases y documentos link-only, sin preview de contenido no leído.
8. Procedencia: Código BDNS, IGAE attribution y enlaces por rol.
9. Historial real: create = InfoCs incorporó; update = detectó cambios.
   No before/after sin soporte Event v1, ni historial antiguo inventado.
10. Detalles técnicos progresivos, sin convertir la ficha en dump JSON.

No rediseño UI; este contrato de contenido debe integrarse con el sistema
aprobado y el pipeline canonical → adapter → presentation → ViewModel → component.

## 15. Frontend gap map

`YES` fuente significa observado o contrato local explícito; no disponibilidad
universal. `proposed` no es una promesa implementada.

| Field | Source available? | Parsed? | Canonical? | Presented? | Desired? | Blocking change? |
| --- | --- | --- | --- | --- | --- | --- |
| Código/título/órgano/provincia | YES | YES | YES | YES | conservar | No; no reinterpretar |
| Presupuesto total | YES live | YES Decimal | NO | NO | YES | extensión + hash + privacy/policy + adapter |
| Moneda | NO en muestras | NO | NO | NO | sólo acreditada | evidencia oficial, no asumir EUR |
| Tipo convocatoria | YES live | YES | NO | NO | YES literal | extensión + hash + policy |
| Objeto/description separado | NO demostrado | NO | NO BDNS | NO | sólo si existe | no inventar desde descripcion |
| Finalidad | YES live | YES | NO | NO | YES | extensión + Privacy + hash/policy |
| Instrumentos | YES live | YES labels | NO | NO | YES | extensión/hash/policy |
| Tipos elegibles | YES live | YES | NO | NO | YES | extensión/Privacy; nunca Awardee |
| Sectores/códigos | YES live | YES | NO | NO | YES | extensión/hash; catálogo no inferido |
| Jerarquía órgano literal | YES live | YES | sólo name compuesto | parcial | YES opcional | extensión; no split por slash |
| Regiones completas | YES live | YES labels | sólo province/match | province | YES cuando útiles | extensión/hash; no nuevo matching |
| Recepción BDNS | YES live | YES | NO | NO | YES con label | extensión/hash, no published_at |
| Inicio/fin fecha/texto | YES live | YES | NO | NO | YES | extensión/hash/Privacy; optionalidad |
| abierto/diario | YES live | YES | NO | NO | limitado | semántica de abierto antes de badge |
| Bases nombre/URL | YES live | YES | NO | NO | YES | extensión/Privacy/URLs/hash/policy |
| Documentos metadata | YES live | YES | NO | NO | YES link-only | extensión/Privacy/hash/policy; no binarios |
| Extractos/fechas/links | YES contrato; [] live | YES | fecha condicional | fecha condicional | YES si presentes | extensión y enlace validado |
| Sede electrónica | YES contrato; null live | YES | NO | NO | opcional | URL segura; no llamar ficha única |
| MRR/ayudaEstado/reglamento/fondos/objetivos/productos | parcial/null/vacío | sólo S.mrr | NO | NO | diferido | contrato/semántica no-null |
| Ficha humana | patrón oficial previo | NO | NO | NO | YES tras verificación | validación enlaces, no schema administrativo |
| API técnica | YES | construido | YES source_url | mal distinguido | YES label claro | presentation sin cambiar hash |
| Resumen/importe formateado | derivable | n/a | NO | NO | YES conservador | presentation + datos enriquecidos |

## 16. Filter/facet opportunities

Futuras facetas: source, category, autoridad canónica, tipo literal de
convocatoria, sector (code + label), tipo elegible, presupuesto decimal con
concepto/moneda homogéneos, fechas por rol. Municipio sólo cuando exista dato
canónico demostrado, no nombre de órgano o sede. Códigos sin versión/catálogo
no permiten jerarquías ni equivalencias automáticas.

No implementar filtros, index extra ni cambios Pagefind en esta fase.
Posteriormente decidir qué campos públicos enriquecidos se indexan; nunca raw,
identificadores personales o detalles técnicos completos para buscar mejor.

## 17. Migration implications

Schema v1 cerrado (`unevaluatedProperties: false`, schema_version=1.0); models,
Candidate/from_dict/to_dict, schemas, hash projection, Privacy/publication y
frontend deben acordar un contrato versionado antes de escribir extensión.
No añadir un objeto que sólo pase por JSON pero se pierda al round-trip.

Mantener Código BDNS → mismo record_id. Records existentes no permiten recuperar
presupuesto/plazos por transformación local: se necesita un futuro refetch
controlado, autorizado por separado. No inventar los campos faltantes.

La primera incorporación de campos produce hashes distintos aunque BDNS no
haya cambiado. **No usar sin más el runner diario como migrador** ni emitir
«cambio administrativo» por diferencia de representación. Gate previo de
migración: decidir y documentar baseline/versionado semántico y continuidad
de hash/Event; no reescribir Events viejos ni fabricar comparación histórica.
Current Event v1 no distingue migration de update: la solución se debe aprobar
antes del backfill, sin forzar ahora schema Event ni borrar historia.

Stores/authorization deben recibir el Record completo después de todos los
gates; Hash binding debe incluir extensión material. Publication policy v1
no permite el nuevo alcance: versionarlo explícitamente, mantener exclusión de
concesiones/personas/fulltext y tests de fail-closed. Workflow safety, parser
frontend y static index deberán validar el nuevo contrato, no publicar objetos
que otra capa ignore. No cambio incidental a BOE/BOP ni schedule/limits.

## 18. Open questions and decision gates

Respuestas de diseño a los diez gates:

1. Conservar campos útiles B comprendidos de la sección 6 más los A actuales;
   no raw, concesiones ni colecciones desconocidas por rellenar una ficha.
2. A existente genérico; ampliación tipada BDNS-specific. No convertir
   presupuestoTotal en grant_amount ni catálogos específicos en Core universal.
3. Nuevos estados administrativos materiales sí en hash, derivados/control no;
   whitelist explícita y versión/migración antes de publicar.
4. «Presupuesto de la convocatoria», Decimal/string exactos; EUR pendiente de
   evidencia explícita, no «dinero recibido».
5. Fechas por sujeto: recepción, solicitud, extracto, documento y observación;
   no inferencias ni fechaRecepcion → published_at.
6. Hay patrón de ficha humana respaldado por ejemplo oficial previo, no prueba
   per-record hecha ahora. Habilitar tras verificación; API permanece fallback
   honesto con label técnico.
7. Metadata tipada y links de endpoint individual documentado; sin descarga,
   MIME/hash inferidos ni fulltext.
8. Plantillas deterministas build-time, sin persistencia/editorialización;
   omitidas si no hay campos oficiales útiles.
9. Nuevos textos/URLs/filenames amplían riesgo personal. Gate debe cubrirlos;
   categorías de destinatarios no son beneficiarios nominativos.
10. Antes del frontend: aprobar extensión/hash/migración; actualizar parser/
    normalizer, Privacy y publication scope; fixtures/tests y enriquecimiento
    autorizado del dataset. No bastan cambios Astro.

Pendientes acotados (no bloquean diseñar el subconjunto seguro): moneda; semántica
de abierto; tipos no-null de ayudaEstado/reglamento y elementos fondos/objetivos/
sectoresProductos; versión de clasificación sectorial; formato universal datMod;
estabilidad y comprobación de fichas humanas; privacidad por campo y decisión
de transición hash/event de enriquecimiento. Estas cuestiones no autorizan más
requests en 10B-A ni publicación de los campos diferidos.

## 19. Recommended implementation sequence

| Fase propuesta | Alcance y gate de salida |
| --- | --- |
| 10B-B — Typed enrichment contract | Aprobar extensión Candidate/Record, versión, exact decimals/nullability, source binding y hash projection. Definir transición de baseline/migración/Event antes de datos reales. No frontend. |
| 10B-C — BDNS enrichment + publication/privacy | Parser/normalizer allowlist, Privacy recorrido de nuevos campos, metadata policy versionada y autorización. Tests sintéticos de precisión/exponente, optionalidad, dates, documentos, hash/diff, identidad y no bypass. Cerrar evidencia de moneda/links sólo si necesaria. |
| 10B-D — Controlled existing-record enrichment | Plan de migración aprobado, dry-run y refetch limitado autorizado separadamente; conservar IDs/historia y no llamar cambios administrativos a enriquecer representación. Ningún backfill implícito por schedule. |
| 10B-E — Frontend adapter/ViewModel | Cargar extensión validada, formatting exacto, labels/summary deterministas y campos opcionales; sin scraping ni inferencias de texto. |
| 10B-F — Human-readable detail | Integrar el contenido real y las tres capas con UI aprobada, fechas por rol, privacidad y attribution. |
| 10B-G — Concise cards | Presupuesto/tipo cuando existen sin tarjetas gigantes, primary date segura, accesibilidad/responsive. |
| 10B-H — Source/API/documents UX | Verificar ficha humana; links separados, fallback API, metadata documental link-only y mensajes honestos. Puede adelantarse su validación contractual a 10B-C sin implementar UI. |

Filtros/facetas y reindexación detallada posteriores según scope aprobado;
no son parte de esta auditoría. No tests/suite/compileall ejecutados aquí;
sólo lectura de pruebas existentes e inspección decimal en memoria.

**Recomendación: READY_FOR_BDNS_HUMAN_READABILITY_IMPLEMENTATION**, limitada al
subconjunto seguro y a la secuencia con gates anterior. No implica contrato
nuevo aprobado, migración autorizada ni campos diferidos resueltos.
