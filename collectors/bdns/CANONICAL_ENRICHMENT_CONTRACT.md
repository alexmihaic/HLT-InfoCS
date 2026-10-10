# BDNS canonical enrichment contract — 10B-B

Fecha: 2026-10-01. Capacidad de Core/schema implementada; fuente, gates,
migración y frontend pendientes. Se basa en HUMAN_READABILITY_FIELD_MAP.md.
No cambia el alcance territorial, reutilización, runner ni datos existentes.

## 1. Source-data architecture

RecordCandidate/Record añaden `source_data: SourceData | None`. Sólo se
serializa cuando existe. El contenedor cerrado admite únicamente `bdns`,
obligatorio si source_data aparece; no payload, attributes ni diccionario raw.
Todas las clases son dataclasses frozen/slots, con tuplas tipadas. Carga JSON
valida schema y después invariantes Python. No hay registros de plugins.

`source_data.bdns` sólo admite `source.id=bdns` y `category=grants.call`.
BDNS sin extensión sigue válido; BOE/BOP con extensión fallan. Es implicación,
no equivalencia: source=bdns no obliga a enriquecer inmediatamente.
Futuras fuentes requieren tipos/schema/proyección/gates explícitos, no campos
desconocidos aceptados por adelantado.

## 2. BDNS field model

| Campo canónico | Tipo | Path fuente / propósito |
| --- | --- | --- |
| extension_version | const string 1.0 | Versión de estructura, no dato administrativo |
| official_title_coofficial? | string | descripcionLeng literal |
| authority_hierarchy? | BDNSAuthorityHierarchy | organo.nivel1/nivel2/nivel3, sin inferir nivel Core |
| budget_total? | BDNSBudgetTotal | presupuestoTotal |
| call_type? | string | tipoConvocatoria literal, catálogo extensible |
| instruments | tuple[str] | instrumentos[].descripcion literal |
| eligible_beneficiary_types | tuple[BDNSOfficialClassification] | tiposBeneficiarios[].descripcion/codigo? |
| sectors | tuple[BDNSOfficialClassification] | sectores[].descripcion/codigo? |
| impact_regions | tuple[str] | regiones[].descripcion, sin INE inferido |
| received_date? | date | fechaRecepcion, nunca published_at |
| application? | BDNSApplicationPeriod | fechaInicio/FinSolicitud, textInicio/Fin, abierto |
| purpose? | string | descripcionFinalidad, no objeto inventado |
| regulatory_bases? | BDNSRegulatoryBases | descripcionBasesReguladoras/urlBasesReguladoras |
| electronic_office_url? | HTTPS string | Proyección segura de sedeElectronica, no ficha única inferida |
| extract_published_in_official_diary? | bool | sePublicaDiarioOficial |
| documents | tuple[BDNSDocumentReference] | Metadata de documentos, no binarios |
| extracts | tuple[BDNSExtractReference] | Metadata de anuncios; no fulltext |

BDNSOfficialClassification contiene label **oficial** requerido y code opcional.
No enum propio ni label UI. Un elemento sin label queda fuera del contrato
enriquecido inicial; 10B-C debe resolverlo fail-closed, no inventar nombre a
partir de código. No duplica código BDNS/título principal/GrantDetails/provincia.

Excluidos: id interno, long documental, numAnuncio como identidad global,
advertencia por Record, MRR/ayudaEstado/urlAyudaEstado/reglamento/fondos/objetivos/
sectoresProductos con semántica pendiente; fulltext, datos personales
nominativos, formatos, resumen, estado abierto/cerrado inferido y payload raw.

Opcionales escalares/bloques admiten null en JSON y se serializan por omisión;
no se conserva distinción administrativa inexistente entre ausencia y null.
Colecciones son listas JSON no-null, vacías por defecto y omitidas al serializar.
No afirmar que una colección ausente garantiza ausencia de elementos en fuente.
Extensión y bloques opcionales presentes requieren algún valor significativo;
una bandera false sí lo es. Strings vacíos no son placeholders válidos.

## 3. Money semantics

BDNSBudgetTotal(value: Decimal, currency: str | None). Constructor rechaza float,
no-finitos y presupuesto negativo como restricción InfoCs. JSON usa value como
string decimal plano no negativo; nunca número JSON binario ni exponente.
`Decimal('3.27E+3') → {"value":"3270"}`. Se normalizan ceros decimales sin
Decimal.normalize/context rounding: también preserva importes mayores que la
precisión por defecto del contexto. Currency ausente/null se omite; si existe,
requiere código de tres letras y evidencia fuente que aportará 10B-C.

No default EUR. No financial.grant_amount. Concepto: presupuesto de convocatoria,
no importe concedido, pagado ni recibido. Formato UI fuera de esta fase.

## 4. Periods

BDNSApplicationPeriod: start_date?, end_date?, start_text?, end_text?, abierto?.
Date es date, no datetime ni texto interpretado. Pueden coexistir fechas y textos;
ambos son material observado. No deducir estado vigente ni ordenar/corregir
fechas oficiales silenciosamente. Abierto conserva el indicador literal fuente.
Recepción separada de publicación; plazos no alimentan event_at ni published_at.

## 5. Documents and bases

BDNSDocumentReference: source_document_id (entero no negativo, no bool),
description?, filename?, published_date?, modified_value?. DatMod conserva
valor literal sin garantizar formato universal ni zona horaria. IDs documentales
duplicados son error Python, incluso con metadata idéntica: no elegir una versión
silenciosamente. El schema portable no puede imponer unicidad por subcampo.

URL de documento **no se persiste duplicada**: se podrá derivar del ID y el
endpoint documentado `…/api/convocatorias/documentos?idDocumento=<id>` en 10B-H.
No URL inventada, MIME, sha256, OCR, fulltext, binarios ni local path.
No se crea una segunda lista Core Document para los mismos adjuntos.

BDNSRegulatoryBases: description?, **source_locator?**, independientes (10B-D2.8).
SOURCE LOCATOR es el valor literal `urlBasesReguladoras`: string no vacío,
máximo 2048 caracteres. Desde 10B-D3.4 permite U+0020 exclusivamente interno
(uno o varios), como texto fuente literal, no como URL certificada. Rechaza
U+0020 de borde, cualquier otro whitespace, controles C0/C1, DEL/backslash, escapes
percent inválidos, UTF-8 inválido ni credenciales detectables (también sin esquema
y en variante decodificada). No exige host, DNS, puerto válido, ausencia de IP/local
ni esquema. Si aparece un esquema explícito, sólo se admiten HTTP/HTTPS: no se
amplían esquemas no web no observados. La validación profunda canónica única es
`models.valid_bdns_regulatory_bases_source_locator`; schema expresa tipo/longitud
y shape cerrado, no finge `format: uri` ni replica toda la lógica Python.

CLICKABLE URL es propiedad derivada InfoCs: la única función
`enrichment.clickable_bdns_regulatory_bases_url` devuelve el literal exclusivamente
si además pasa la política estricta HTTPS pública de navegación; en otro caso None.
HTTP, schemeless y locators con U+0020 interno se conservan pero no se enlazan.
No se elimina, codifica ni sustituye el espacio. Ningún trim, scheme inference,
HTTP→HTTPS, normalización ni visita remota. No certifica autoridad/destino.
Sede/extractos conservan HTTPS estricto. Privacy inspecciona siempre el string
completo literal y decodificado, incluso no parseable, más componentes cuando
parseables. Persistencia no equivale a navegación ni autorización de publicación.

La sede es una proyección opcional: None se omite, HTTPS válido conserva su
literal y cualquier string fuera de la política estricta se proyecta a None.
No se conserva el raw rechazado. Sólo ese campo es fail-soft; no relaja
extractos/bases ni los demás gates. `electronic_office_url` es la proyección
literal HTTPS elegible, no todos los valores raw de `sedeElectronica`; la UI
actual puede seguir mostrándola como texto. El aviso técnico cerrado
`electronic_office_dropped_invalid_url` queda fuera del Record y su hash.

InfoCs does not repair source locators.
Invalid optional locator does not become a clickable URL.
Invalid optional locator does not invalidate unrelated canonical metadata.

`source_locator` es material en hash/diff; clickability no se persiste ni participa
en hash. Se corrige el nombre anterior `official_source_url` sin alias ni migración
ficticia: no existe baseline v2 público/CUTOVER. Se mantienen hash v2, extension 1.0
y normalizer 2.0.0. La decisión HTTP de D2.4 queda absorbida por este contrato.

BDNSExtractReference: cve?, diary?, source_url?, publication_date?, title?,
title_coofficial?. Al menos un dato; URL HTTPS cuando existe. No relations,
identidad de anuncio ni texto íntegro en esta fase.

## 6. Hash material fields

Hash v2 = proyección v1 sin cambiar + `source_data.bdns` material cerrado.
Participan todos los campos de la tabla salvo extension_version: presupuesto
exacto/moneda si existe, tipo, instrumentos, clasificaciones oficiales,
jerarquía literal, regiones, recepción, plazos fecha/texto/indicador, finalidad,
bases/enlace recibido, sede/enlace recibido, indicador de diario,
documentos (ID, textos, fechas) y metadata de extractos.

Bases/extractos y la sede aceptada son dato fuente; la sede descartada no es
material. Ausencia y raw inválido producen la misma proyección/hash si los demás
datos son iguales. No migración de Records existentes, bump de extensión 1.0
ni cambio de hash v2 por esta corrección. Document URL reconstruida
no es nuevo estado. DatMod es señal de modificación de metadata fuente, no
prueba de cuáles bytes/document text cambiaron. Ningún hash PDF inventado.

Mantener exclusiones v1 de autoridad/category/geography: no se corrigen de paso.
La jerarquía/regiones fuente **nuevas** sí entran en la extensión v2 conforme
al mapa aprobado; distinguirlas de conocimiento interno de normalización.

## 7. Hash exclusions

technical.content_hash_version y extension_version sólo identifican contratos;
no entran como valores administrativos en la proyección. Tampoco technical,
timestamps InfoCs, provenance, attribution, decisiones/tokens de publicación,
formatos, labels UI, resumen ni enlaces reconstruibles. El schema ni siquiera
admite guardar la mayoría de esos campos en la extensión.

source_url API preexistente sí está en v1: conservarlo; sustituirlo por una
ficha humana por UX produciría una modificación semántica evitable.

## 8. Collection ordering and canonical JSON

Instrumentos, tipos elegibles, sectores, regiones, documentos y extractos son
colecciones de pertenencia, **no ranking/secuencia administrativa**. Orden
canónico por JSON estable, deduplicación de valores iguales; reordering no altera
hash/diff. Finalizador también canonicaliza orden antes de serializar el Record.
Document IDs duplicados se rechazan antes, como se explica en sección 5.

La jerarquía no es una lista intercambiable: nivel1/2/3 tienen roles distintos.
Inicio/fin también; no swap ni sorting de fechas. Omitir null/colecciones vacías
evita cambios por representación vacía. Texto literal no se parafrasea.

## 9. Hash transition — selected OPTION A: explicit hash version

`technical.content_hash_version` permite 1 o 2. Ausencia equivale a **1** y el
serializador omite el default 1, manteniendo JSON/hashes antiguos intactos.
Record sin extensión sólo admite v1; con extensión exige v2 explícito en schema
y Python. Finalizador selecciona v2 exclusivamente cuando hay source_data.
Candidate no admite content_hash/version elegidos por caller.

`content_hash()` rechaza mismatches versión/extensión; no ignora source_data
para calcular un v1. `diff()` y `update_event()` rechazan v1↔v2 con
HashContractTransitionError **antes de fabricar un update**. No fallback de
compatibilidad, proyección común silenciosa ni dual hash temporal.

La futura migración establece baseline v2 sin Event administrativo. El versionado
es la estrategia, no una licencia para que ingest regenere datos automáticamente.
Una nueva incorporación que ya nace enriquecida tendrá v2 desde su primer
create autorizado, sin transición histórica.

## 10. Event semantics and authorization

Event create = incorporación de observación; update = cambio de estado
administrativo comparable, nunca cambio de implementación/representación.
Event schema e identity algorithm no se modifican. Diff v2→v2 conserva paths
materiales y la autorización sigue ligada al Record exacto y content_hash.
Una autorización anterior no sirve para el baseline nuevo.

Los Events viejos permanecen append-only con hashes v1. No se reescriben para
simular una cadena v2 previa. La continuidad entre el último Event v1 y baseline
v2 tendrá evidencia explícita de migración, no un update ficticio ni timestamp
de publicación inventado.

## 11. Migration requirements for 10B-D

Tooling y contrato concretados posteriormente en
[BASELINE_MIGRATION_CONTRACT.md](BASELINE_MIGRATION_CONTRACT.md) (D1, offline).
Los requisitos siguientes se mantienen; D2 ejecutará el cutover por separado.

10B-B no implementó writer/migration primitive. Requisitos concretos de la
ruta separada, antes de cualquier write futuro:

1. Preflight autorizado: cargar baseline v1 validado, conservar record_id y
   detected_at; nueva observación enriquecida válida con todos los gates de
   10B-C; EventStore nunca se utiliza para representar la migración.
2. Contrastar parte administrativa conocida v1 (proyección enriquecida sin
   source_data/version2) contra hash previo. Si cambia, **detener la migración
   silenciosa**: procesar/documentar el cambio genuino por una operación separada
   antes de establecer baseline. Datos nuevos no tenían valores históricos:
   no afirmar que se conoce su evolución pasada.
3. Preparar evidencia durable, segura y validada de transición que relacione
   record_id, hash/version anteriores y nuevos, software/motivo/fecha de migración;
   sin contenido personal ni raw. El artefacto/path/schema de esa evidencia se
   deberá aprobar en 10B-D. No reutilizar Event update ni fingir RunManifest
   completo como sustituto. **Sin esa evidencia, cero migración.**
4. Escritura explícita del baseline por la ruta de migración aprobada, manteniendo
   validaciones de modelo/hash/path/privacidad/atribución; no vía runner diario
   ni flag que desactive gates. No tocar Events antiguos.
5. Observaciones posteriores v2 se comparan con ese baseline v2. Idéntico →
   no_change; cambio material → update autorizado con previous_content_hash
   del baseline v2. Verificar vínculo documental con historia v1.

Dataclasses inmutables permiten construir objetos nuevos en memoria; no mutar
el anterior. RecordStore reemplaza JSON atómicamente, no ofrece transacción
multiarchivo: la futura migración necesita preflight/idempotencia/recuperación
documentados para baseline y evidencia. No relajar EventStore ni authorization.

## 12. Privacy/publication follow-up for 10B-C

**Schema support != publication authorization.** Los bloqueos preventivos de
10B-B en RecordStore y el issuer se sustituyen en 10B-C por inspección Privacy
explícita y metadata policy v2, documentadas en
[ENRICHMENT_GATE_CONTRACT.md](ENRICHMENT_GATE_CONTRACT.md). El Store conserva
schema/hash/Privacy; el adapter autoriza sólo tras los gates source-specific.
Sin nuevas reglas source-specific en EventStore ni bypass configurable.

Se inspeccionan textos/URLs/filenames de título cooficial, jerarquía,
clasificaciones, plazos, finalidad, bases, documentos y extractos. No cambia
reuse ni se permiten concesiones, fulltext/personas nominativas por enriquecer
metadata. La capacidad v2 NO se conecta al runner antes del baseline 10B-D.

## 13. Compatibility

Se mantiene schema_version **1.0**, conforme a su valor fijo actual: ampliación
opcional/cerrada del contrato, sin alterar campos obligatorios ni semántica
existente. Es backward-compatible para **datos**: el lector actualizado carga
Records v1 previos sin cambiar bytes/hashes. Lectores/schemas antiguos cerrados
no aceptan nuevos Records enriquecidos: no prometer forward compatibility.
Por eso se actualizan consumidores antes de migrar; extension_version y
content_hash_version separan shape fuente y baseline semántico.

Candidate comparte candidate_core del schema Record: hereda source_data y
binding source/category; sus metadatos siguen sin ID/hash/version final.
No nuevas dependencias, datasets paralelos ni cambios productivos BOE/BOP.

## 14. Next phase

10B-C implementa mapping y gates como capacidad offline separada, manteniendo
ingest/runner/schedule en v1 y bloqueando diff/update entre contratos.
No activar refetch/migración por el schedule. 10B-D aprueba e implementa la ruta
de baseline con evidencia. Frontend y enlaces/document UX siguen posteriores.
