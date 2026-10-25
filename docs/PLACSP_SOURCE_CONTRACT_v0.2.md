# PLACSP Source Contract v0.2 — MVP canal 643

Fecha: 2026-10-25 (ajustes 02A incorporados). Estado: `PROPOSED / DESIGN_READY_FOR_REVIEW / PUBLICATION_HOLD`.

Base: `main` en `c8383985dea7013ad7bd5720c74c1c0af4d589dd` (DIPCAS-REF-01 integrado). Documento de diseño: no es configuración ejecutable ni autoriza transporte, collector, escritura, publicación ni automatización.

Este documento **sustituye parcialmente** a `docs/PLACSP_SOURCE_CONTRACT_v0.1.md` y a `docs/PLACSP_SOURCE_DATA_SCHEMA_DESIGN_v0.1.md` en lo que presuponen que el único canal es 1044. Lo no mencionado en la tabla de §2 sigue vigente tal como está en esos documentos. Los originales no se modifican ni se borran.

Etiquetas: `CONFIRMADO` (medido o leído en fuente oficial), `INFERIDO`, `NO VERIFICADO`, `BLOQUEADO`, `DECISIÓN` (adoptada por el responsable del proyecto), `PROPUESTA` (a aprobar).

## 1. Decisión y motivo

`DECISIÓN` (responsable del proyecto, tras PLACSP-SCOPE-01):

- Canal **643** (perfiles de contratante alojados en PLACSP, sin contratos menores) es el núcleo del primer MVP.
- Canal **1044** (agregación, sin menores) queda **reservado y no activado**. Entrar en él requiere una decisión posterior con evidencia propia.
- Sin contratos menores (1143), sin documentos completos, sin adjudicatarios ni contactos.
- Sin publicación de datos hasta completar las barreras existentes (§11 y §12).

Motivo (evidencia en el Anexo A):

- `CONFIRMADO`: en 798 entradas de 1044 (~38 h) hubo 0 con ejecución en Castellón (`ES522`) y 0 en la Comunitat Valenciana (`ES52x`); en 643 (410 entradas, ~29,5 h) hubo 4 con `ES522` y 40 con `ES52x`.
- `CONFIRMADO`: la especificación oficial (v1.10, 17/09/2024, §2.1) indica que los órganos de las comunidades autónomas y sus entes alojan su perfil en el sistema autonómico y solo remiten a la agregación un conjunto reducido de datos; las administraciones locales eligen de forma excluyente entre PLACSP y la plataforma autonómica.
- `CONFIRMADO`: el directorio oficial de perfiles alojados (generado el 01/10/2026) contiene DIR3 exacto para 128 de los 135 ayuntamientos de DIPCAS, para la Diputación y para varias mancomunidades.
- `INFERIDO`: con solo 1044, Wave 1 habría tenido cobertura nula o casi nula de Castellón.

## 2. Registro de decisiones anteriores superadas

No se borra ni se edita ningún documento previo. Los siete documentos PLACSP y `docs/INFOCS_PUBLIC_SOURCE_API_MAP_v0.1.md` están sin seguimiento en Git; `docs/evidence/` está ignorado. Este registro es la única anotación de sustitución.

| Documento y sección | Decisión anterior | Estado | Motivo y sustituto |
| --- | --- | --- | --- |
| SOURCE_CONTRACT_v0.1 §1 | Canal `1044`; «Fuera: A/643» | **SUPERADA** | Cobertura territorial (§1). Sustituto: §3 de este documento |
| SOURCE_CONTRACT_v0.1 §4 | Componentes de negocio con `feed_id`; prioridad `ID_PLATAFORMA`, `ID_OC_PLAT`, `DIR3` | **MANTENIDA**, con `feed_id=643` | En 643 `ID_PLATAFORMA` aparece en 410/410 entradas y `DIR3` en 323/410 |
| SOURCE_CONTRACT_v0.1 §5 | `official_id = "1044::" + entry.id` | **SUPERADA** | Sustituto: `"643::" + entry.id` (§5). La forma, el delimitador `::` y la literalidad se mantienen |
| SOURCE_CONTRACT_v0.1 §6 | Territorio en dos ejes; `INCLUDE`/`OUT_OF_SCOPE`/`UNRESOLVED` | **MANTENIDA y concretada** | §6. `OUT_OF_SCOPE` no se usa en el MVP |
| SOURCE_CONTRACT_v0.1 §7 | Paginación y orígenes solo para 1044 | **SUPERADA** | La acreditación de dos orígenes no cubre 643. Sustituto: §4 |
| SOURCE_CONTRACT_v0.1 §9 | Watermark sin solapamiento fijado | **EXTENDIDA** | §9 fija un solapamiento propuesto y reconciliación |
| SOURCE_CONTRACT_v0.1 §9, §13 (tombstones, hold, Events) | Tombstone sin efecto sobre el Record | **MANTENIDA** y matizada | El tipo `ANULADA`/`CERRADA` pasa a registrarse como observación técnica (§9.5) |
| SOURCE_CONTRACT_v0.1 §2 (evidencia C1/C2) | Evidencia de estabilidad de `entry.id` en 1044 | **NO TRANSFERIBLE a 643** | Se hizo solo en 1044. Para 643 la estabilidad de `entry.id` sigue `NO VERIFICADO` (§5.4) |
| SOURCE_CONTRACT_v0.1 cabecera «Se recomienda únicamente B/1044» y §15 «sólo 1044» | Canal único | **SUPERADA** | §1 |
| SCHEMA_DESIGN_v0.1 cabecera «Sólo B/1044»; §3; §4 (`feed_id` = 1044); §5 (`PLACSPCanonicalData.feed_id=1044`); §7 | Canal fijo 1044 | **SUPERADA** | `feed_id` pasa a literal `643`; la extensión admitirá `1044` solo si se activa más adelante (§7) |
| SCHEMA_DESIGN_v0.1 §4 (matriz de campos) | Allowlist de 1044 | **EXTENDIDA** | §8: allowlist del MVP, con `ID_PLATAFORMA` y las exclusiones observadas en 643 |
| SCHEMA_DESIGN_v0.1 §5–§17 | Modelo tipado, hash, fechas, importes, Privacy, tests | **MANTENIDAS** | Sin cambios de fondo; se aplican a `feed_id=643` |
| IDENTITY_SNAPSHOT_GATE_v0.1 §7, §9, §11 | Namespaces `643:` y `1044:` separados | **MANTENIDA** | Ya contemplaba 643. El delimitador `::` de Wave 1 prevalece sobre el `:` inicial. Su estado `PLACSP_NEEDS_IDENTITY_WORK` sigue vigente para 643 |
| LONGITUDINAL_EVIDENCE_STRATEGY_v0.2 | Cohorte prospectiva solo en 1044 | **NO SUPERADA, INCOMPLETA** | Sigue válida como evidencia de 1044. No cubre 643: hace falta una cohorte propia (§5.4, §14) |
| COLLECTOR_DESIGN_v0.1 §§5–7, 31 | Dos canales, A/643 y B/1044; waves P0–P11 | **MANTENIDA**, MVP acotado | El diseño ya separaba ambos canales. El MVP activa solo A/643 |
| SOURCE_AUDIT_AND_SAMPLE_v0.1 §4 | 398 entradas en 643, 29 en 1044 (2026-10-07) | **ACTUALIZADA** | Tamaños de página variables. Cifras actuales en el Anexo A |
| SOURCE_AUDIT_AND_SAMPLE_v0.1 §5–§6 | Ejemplos territoriales y alcance «C — ambos, distinguidos» | **MANTENIDA** | El Anexo A aporta medición en feeds, no solo fichas indexadas |
| Todos los anteriores | HEAD `e144b5c` como base | **OBSOLETA** | La base es `c838398` |

## 3. Fuente

- **Fuente:** `source.id = placsp` (nombre nuevo explícito frente al histórico `pcsp` de `docs/INFOCS_SPEC_v1.md` y `collectors/pcsp/`; su aprobación y registro siguen pendientes). Publicador: Dirección General del Patrimonio del Estado, Ministerio de Hacienda.
- **Canal:** 643, «Licitaciones publicadas en los perfiles del contratante ubicados en la Plataforma, excluyendo los contratos menores».
- **URL raíz** (inicio de la cadena; no se construyen páginas siguientes a mano):
  `https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom`
- **Especificación aplicable:** «Formato de sindicación y reutilización de datos sobre las publicaciones en la PLACSP», v1.10, 17/09/2024 (`https://contrataciondelsectorpublico.gob.es/datosabiertos/especificacion-sindicacion.pdf`), leída el 2026-10-25. `NO VERIFICADO`: que sea la versión más reciente a fecha de implementación; se revalida antes de cada wave de código.
- **Directorio de órganos:** `OrganosContratacion.xlsx` (Hacienda). Es un insumo de referencia, no un feed de publicaciones, y se trata fuera del canal de licitaciones (§10).
- **Fuera del MVP:** canal 1044, menores (1143), encargos a medios propios, consultas preliminares, ZIP históricos, fichas HTML, búsquedas, documentos, PDFs y portales de origen.
- **Esquema de fuente** (futuro, conforme a `schemas/source.schema.json`): `access_type=feed`, `status=under_review`, `reuse.status=conditional`, `mirror_documents=false`, `fulltext_publication=false`. Los guards de origen y paginación pertenecen a la política del collector, no al schema.

### 3.1 Hechos observados del canal 643 (2026-10-25, Anexo A)

- `CONFIRMADO`: la respuesta es `application/atom+xml`, HTTP 200, sin compresión efectiva (12.234.604 bytes), con cabecera `Last-Modified`.
- `CONFIRMADO`: la raíz se sirve desde `contrataciondelsectorpublico.gob.es`, pero los enlaces `self`, `first` y `next` del feed apuntan a `contrataciondelestado.es`. Los `entry.id` también usan `contrataciondelestado.es`.
- `CONFIRMADO`: la página raíz tenía 410 `entry` y 1 `deleted-entry`; `rel=next` apuntaba a un archivo con marca temporal en el nombre (`..._YYYYMMDD_HHMMSS.atom`).
- `NO VERIFICADO`: cadencia de regeneración del feed y de creación de archivos `next`; solo se observó una instantánea.

## 4. Paginación y política de red (futura)

La política de dos orígenes acreditada para 1044 **no se hereda**. Para 643 se propone una política propia, a validar con tests y revisión antes de usarla:

- Orígenes: `https://contrataciondelsectorpublico.gob.es:443` y `https://contrataciondelestado.es:443`, solo para el segmento `/sindicacion/sindicacion_643/`. Es una propuesta basada en lo observado; el segundo origen no está acreditado como excepción aprobada.
- HTTPS, nombre de host exacto, puerto 443, sin userinfo, IP, fragmento, controles, espacios, backslash ni escapes ambiguos; sin dot segments; ningún redirect automático (todo redirect se rechaza).
- Seguir solo `link@rel="next"`; resolver con `urljoin` y validar el destino completo; detectar ciclos y varios `next` incompatibles. Un archivo con menos entradas que otro no demuestra fin de cadena.
- Orden de las entradas: de más reciente a más antigua por `entry.updated` (§3.2 de la especificación). Esa regla es la base del corte temporal de §9.
- Transporte secuencial y cero reintentos en la primera versión; XML seguro (DTD y entidades bloqueadas, límites de profundidad, nodos y texto).
- Presupuesto por ejecución: `NEEDS_RECALIBRATION`. Referencia medida: ~12,2 MB y ~31 s por página de 410 entradas (~30 KB/entrada). No se fija un límite productivo en este documento. Alcanzar el límite antes de cubrir el intervalo da `incomplete`, sin avance de watermark y sin publicación del lote.

## 5. Identidad

### 5.1 Unidad

Un Record es el **último estado observado de una entrada Atom (carpeta/expediente) del canal 643**. Categoría `procurement`.

| Concepto | Contrato |
| --- | --- |
| Expediente (carpeta) | Unidad administrativa agrupada por `ContractFolderID` dentro de un órgano. No es único global |
| Entrada Atom | Representación vigente del expediente; contiene el estado más reciente y la lista de anuncios publicados (apartado 4.39 de la especificación). Es la unidad del Record |
| Publicación (anuncio) | Subestructura (`ValidNoticeInfo`). Sin identificador independiente acreditado; no genera Record ni Event propio |
| Lote | Subestructura (`ProcurementProjectLot`). Fuera del MVP (§6.5, §8) |
| Tombstone | Señal de sindicación sobre un `entry.id`; no es estado jurídico (§9.5) |

### 5.2 Identificador

- `source.official_id = "643::" + entry.id_literal`. El literal no se recorta, no se pasa a minúsculas ni se normaliza; se conserva como viene.
- Forma observada de `entry.id`: `https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/<número>`. **No es una URL de ficha pública** y no se usa como `source_url`.
- Identidad de negocio de comprobación: `[feed_id, authority_scheme, authority_structured_id, contract_folder_id]`. En 643 la señal preferente es `ID_PLATAFORMA`; `DIR3` queda como dato adicional. Nunca NIF, nombre de órgano ni título. Sin fallback: componente ausente, ambiguo o con espacios externos produce `identity_missing` o `structured_fields_inconsistent`, sin candidato publicable.
- **Representación para rutas y archivos.** El `entry.id` literal es el único identificador oficial y **nunca** se usa directamente como nombre de archivo o ruta (contiene `://` y `/`). Los nombres derivan de forma determinista del identificador interno de InfoCs, `infocs:placsp:<token>-<digest>` (Core `identify()`, digest SHA-256 del `official_id` exacto). Reglas: minúsculas ASCII `[a-z0-9-]`, longitud acotada, sin separadores de ruta, sin nombres reservados de Windows ni segmentos `.`/`..`. El literal viaja en `source.official_id` dentro del Record, no en el nombre. La función es pura: misma entrada, mismo nombre. Si dos `official_id` distintos dieran el mismo nombre, es colisión y se aborta el lote (el digest truncado no prueba ausencia de colisión). Nada de esto cambia schemas ni Events.
- `ContractFolderID` no se usa para deduplicar entre órganos ni canales. Evidencia: un mismo texto aparece en ambos canales para dos órganos distintos (Anexo A).

### 5.3 Entradas repetidas y correcciones sin cambio temporal

- `CONFIRMADO` (especificación §3.3.2 y observación): un feed puede contener varias `entry` con el mismo `id`. 643 tenía 407 `entry.id` distintos en 410 entradas.
- Prevalece la de mayor `updated` (comparado como instante con zona horaria); las anteriores se descartan sin escribir.
- **Mismo `id`, mismo `updated`, contenido conflictivo** (la proyección semántica del §8 difiere): es `duplicate_incompatible`. El lote entero se aborta y no se escribe nada. No se elige por orden XML ni por «la última en aparecer». Es una incidencia de la fuente a revisar a mano; no se resuelve automáticamente.
- **Mismo `id`, mismo `updated`, contenido idéntico:** duplicado benigno, se cuenta como uno.
- **Corrección sin cambio de `updated`** (admitida por la especificación §3.3.1): solo se detecta comparando la proyección con la del Record previo (§9.3). Si difiere y el `updated` es igual al del Record, es una corrección: Update solo si pasa todos los gates, con `correction_without_updated` en el diagnóstico técnico (no en el Record). Una entrada con `updated` **anterior** al del Record y contenido distinto nunca revierte el Record: se cuenta como `stale_version_ignored`.

### 5.4 Estabilidad de `entry.id` en 643

- `CONFIRMADO`: la especificación prescribe que una actualización conserva el `<id>`.
- `NO VERIFICADO`: ninguna observación longitudinal real en 643. La evidencia aceptada (C1/C2) fue solo de 1044.
- `BLOQUEADO` para producción: no se escriben Records de 643 hasta una comparación longitudinal propia (§14, tarea 2), con la misma regla estricta de `STABLE_UPDATE`. Wave 2 (fixtures sintéticos) no queda bloqueada.
- Otros riesgos de estabilidad: que un órgano cambie de plataforma o de DIR3; que la depuración de entradas antiguas elimine una versión (la especificación §3.3.2 lo admite en casos excepcionales).

### 5.5 Cambio real frente a actualización técnica

- `entry.updated`, `feed.updated`, página, posición, etiquetas derivadas y reordenaciones de conjuntos **no** son cambio. Solo cambia el Record si cambia la proyección semántica del §8 (hash de contenido).
- `entry.updated` avanza con cada nuevo anuncio, incluso si el nuevo anuncio solo cambia campos excluidos (documentos, resultados). Eso da `NO_CHANGE` y no genera Event.
- La especificación (§3.3.1) admite correcciones excepcionales sin cambio de `updated`; por eso el `updated` no basta para detectar cambios (§9).
- `content_hash`: se aplica el contrato de `PLACSP_SOURCE_DATA_SCHEMA_DESIGN_v0.1` §9, con la condición ya fijada allí de que BOE y BDNS conserven bytes y hashes idénticos.

### 5.6 Entre canales

643 y 1044 son namespaces distintos. Una posible coincidencia futura es una relación candidata (`RELATED_CANDIDATE`), nunca una fusión. En la muestra: 0 pares órgano + expediente en común entre canales.

## 6. Territorialidad

Dos ejes independientes: **órgano contratante** y **lugar de ejecución declarado**. La ubicación del adjudicatario nunca es señal.

### 6.1 Decisión por entrada

| Decisión | Condición |
| --- | --- |
| `INCLUDE` | Se cumple al menos un motivo de inclusión de §6.2, con su evidencia propia |
| `UNRESOLVED` | No se cumple ninguno. Se cuenta con su causa y no se publica |
| `OUT_OF_SCOPE` | **No se usa en el MVP.** Excluir con seguridad exigiría resolver el órgano en todo el país, y el crosswalk solo cubre Castellón. Un órgano de Castellón ausente del crosswalk no puede descartarse por una ejecución externa |

### 6.2 Motivos de inclusión (cada uno con evidencia independiente)

| Motivo | Condición exacta | Evidencia que se guarda |
| --- | --- | --- |
| `organ_dir3_crosswalk` | El `DIR3` del órgano contratante coincide **por igualdad exacta** con un DIR3 del crosswalk (§10), nivel 1 o 2 | DIR3 observado, versión del crosswalk, tipo de entidad |
| `execution_nuts3_es522` | `RealizedLocation/CountrySubentityCode` del expediente es exactamente `ES522` | Código observado y nivel |

- Si se cumplen los dos, se guardan los dos motivos, cada uno con su evidencia. No se fusionan ni se reducen a una etiqueta única.
- `ES522` acredita **provincia**, no municipio.
- `organ_dir3_crosswalk` acredita que el **órgano** está en Castellón, no que el contrato se ejecute allí.
- `ID_PLATAFORMA` por sí solo no es motivo de inclusión. Solo vale como puente cuando la entrada no trae `DIR3`: se busca su `ID_PLATAFORMA` exacto en el directorio oficial y se usa el DIR3 de esa fila, si está en el crosswalk. La evidencia guarda la versión del directorio. Si ni la entrada ni la fila del directorio aportan un DIR3 del crosswalk, la entrada queda en `UNRESOLVED`. Este puente es opcional en el MVP y depende de D6.

### 6.3 Señales que no acreditan nada (prohibidas como motivo)

Nombre del órgano o de su jerarquía, texto de título, descripción o resumen, código postal, `CityName` o `CountrySubentity` en texto, ruta jerárquica textual del directorio («Castellón>Ayuntamientos>…»), NIF, localización del proveedor, niveles amplios (`ES`, `ES5`, `ES52`, `ES523`…) y cualquier similitud de nombres. Incluidas las que parecen evidentes: el código postal `12xxx` de una entrada con ejecución fuera de la provincia no es una inclusión.

Ejemplo de la muestra: la Universitat Jaume I figura con código postal `12071` y ejecución `ES`. Su DIR3 no está en el crosswalk de nivel 1 ni 2, así que es `UNRESOLVED`.

### 6.4 Siete ayuntamientos con discrepancias

`CONFIRMADO` (cruce DIPCAS ↔ directorio oficial generado el 01/10/2026, comprobado el 2026-10-25). El DIR3 de DIPCAS no coincide con ninguna fila del directorio para estos siete. Ninguna identidad se resuelve por nombre. Evidencia común: INE y DIR3 del dataset `ayuntamientos` de DIPCAS (normalizado por DIPCAS-REF-01) y búsqueda en `OrganosContratacion.xlsx` por DIR3 exacto (0 filas).

| INE | Municipio (DIPCAS) | DIR3 DIPCAS | Tipo de incidencia | Evidencia concreta y límite |
| --- | --- | --- | --- | --- |
| 12022 | Bejís | L01120228 | `dir3_blank_in_directory` | Hay órganos con nombre compatible bajo la ruta del municipio y su campo DIR3 está vacío. Hallazgo por texto: no acredita identidad |
| 12041 | Castillo de Villamalefa | L01120419 | `dir3_blank_in_directory` | Igual |
| 12073 | Ludiente | L01120733 | `dir3_blank_in_directory` | Igual |
| 12074 | Llosa, la | L01120748 | `dir3_blank_in_directory` | Igual |
| 12087 | Palanques | L01120878 | `dir3_conflict` | La fila compatible por texto lleva otro DIR3 (`L01121418`). No se sabe cuál es el correcto; no se elige |
| 12089 | Peñíscola | L01120897 | `dir3_blank_in_directory` | Igual que Bejís |
| 12140 | Viver | L01121401 | `dir3_blank_in_directory` | Igual; además hay un órgano de otro municipio con nombre similar y DIR3 propio (`L01121331`), que muestra por qué el nombre no es prueba |

Tratamiento:

- Categoría C. Sus entradas son `UNRESOLVED`, salvo que cumplan `execution_nuts3_es522` (MVP-a no los necesita).
- Resolución: una fuente oficial que ligue DIR3 e INE de forma exacta (D1) o una corrección del directorio o de DIPCAS (D2). Sin esa fuente no se repara a mano.
- Corrección de un informe anterior: PLACSP-SCOPE-01 dijo que cuatro de estos siete tenían DIR3 en blanco. Son seis; Palanques es el conflicto.

### 6.5 Otras reglas

- Solo se evalúa `RealizedLocation` del expediente. El lugar de ejecución de cada lote (apartado 4.11.5) no se evalúa en el MVP (91/410 entradas tenían lotes). Es un falso negativo documentado y aceptado.
- `CountrySubentityCode` ausente o no válido: sin motivo de ejecución. No se completa desde el órgano.
- Varias ubicaciones: basta una con `ES522`; se conserva la pluralidad en la extensión. No se rellena `geography` singular de Core.
- Municipio de ejecución: no se atribuye. Ni siquiera por `CityName` (en la muestra, 1 de 135 coincidía literalmente con el nombre INE; «Burriana» no coincide con «Borriana»). Habilitarlo requiere una tabla oficial de códigos municipales validada (D11).
- Ballestar (`L04120001`) es una entidad **inframunicipal** y no cuenta como municipio. Puede ser motivo `organ_dir3_crosswalk` con tipo `sub_municipal`.
- Mancomunidades y Diputación: pueden dar `organ_dir3_crosswalk`; su alcance territorial real puede salir de la provincia y no implica ejecución en Castellón.

### 6.6 Clasificación para informes

| Categoría | Contenido |
| --- | --- |
| A. Órgano localizado en Castellón | `organ_dir3_crosswalk` |
| B. Ejecución declarada en Castellón | `execution_nuts3_es522` |
| C. Relación posible no acreditada | Huecos del §6.4, órganos con DIR3 en blanco, señales del §6.3 |
| D. Sin evidencia territorial suficiente | El resto |

Solo A y B se publican, y solo si pasan los gates.

## 7. Cambios de la extensión de datos respecto a v0.1

Cambios mínimos sobre `PLACSP_SOURCE_DATA_SCHEMA_DESIGN_v0.1`, sin implementar:

- `feed_id`: literal `643` en el MVP. El tipo admite `1044` solo si más adelante se activa ese canal.
- Binding `source.id=placsp`, `category=procurement`, `official_id = feed_id + "::" + atom_entry_id` concordante.
- `authority_identifier`: `{scheme, value}` con `scheme` en `ID_PLATAFORMA` o `DIR3`. `NIF` excluido.
- Nuevo campo opcional `territorial_inclusion`: lista de motivos (`organ_dir3_crosswalk`, `execution_nuts3_es522`) con versión del crosswalk. Va fuera del hash semántico de contenido (es clasificación de InfoCs, no dato oficial) y dentro de Provenance.
- Propuesto, pendiente de decisión (§9.5): `feed_withdrawal` opcional `{kind: ANULADA|CERRADA, when}` fuera del hash.
- Propuesto: indicador opcional `has_lots` (booleano) para que el lector sepa que el territorio de lotes no se evaluó.

## 8. Datos: lista blanca estricta del MVP

Estados: `PERMITIDO` (se extrae y se proyecta), `PERMITIDO CONDICIONADO` (necesita path o decisión pendiente), `EXCLUIDO` (no se lee, no se guarda, no se publica). Todo lo no listado está `EXCLUIDO`.

| Campo | Estado | Notas |
| --- | --- | --- |
| `entry.id` (identidad), `feed_id` | PERMITIDO | Identidad; fuera del hash |
| `ContractFolderID` | PERMITIDO | Agrupación; se inspecciona por PII (puede contener texto del órgano) |
| Identificador de órgano `ID_PLATAFORMA` y `DIR3` | PERMITIDO | Códigos institucionales |
| Nombre del órgano | PERMITIDO CONDICIONADO | Path exacto de nombre pendiente de validar; Privacy |
| Título y objeto (Atom `title`) | PERMITIDO CONDICIONADO | Texto libre: Privacy y revisión. Obligatorio por Core; sin título no hay candidato |
| `summary` Atom y descripción | EXCLUIDO inicialmente | Texto libre de alto riesgo |
| `source_url` (ficha pública) | PERMITIDO CONDICIONADO | `entry.id`, `next` y URL del feed **no** sirven. Requiere regla pública validada; si no, hold |
| Estado (`ContractFolderStatusCode`) | PERMITIDO | Código tal cual, sin traducir. Observados: `PUB`, `EV`, `RES`, `ADJ`, `PRE` |
| Tipo de contrato y tipo de procedimiento (códigos) | PERMITIDO | Códigos con lista y versión cuando se observan |
| CPV (`ItemClassificationCode`) | PERMITIDO | 0..n |
| Avisos: tipo (`NoticeTypeCode`) y fecha de emisión (`IssueDate`) | PERMITIDO | Asociados dentro de cada aviso. Tipos observados: `DOC_CD`, `DOC_CAN_ADJ`, `DOC_CN`, `DESISTIMIENTO`, `DOC_PIN`, `DOC_FORM`. Un tipo de adjudicación como `DOC_CAN_ADJ` es un código, no un dato de adjudicatario |
| Fin del plazo de presentación (`EndDate`) | PERMITIDO | Fecha o fecha-hora con la precisión original; `EndTime` no se infiere |
| Importe base sin impuestos (`TaxExclusiveAmount`) | PERMITIDO CONDICIONADO | Rol, moneda explícita y decimal exacto; bloqueado hasta cerrar la precisión decimal (D8) |
| Valor estimado sin impuestos (`EstimatedOverallContractAmount`) | PERMITIDO CONDICIONADO | Igual; no se iguala a presupuesto base |
| Importe total con impuestos (`TotalAmount`) | EXCLUIDO inicialmente | Semántica por versión sin acreditar |
| Lugar de ejecución: `CountrySubentityCode` | PERMITIDO | Solo el código y su nivel |
| Lugar de ejecución: `CountrySubentity`, `CityName`, dirección | EXCLUIDO | Texto libre; no es identificador territorial |
| Código postal, dirección y país del órgano | EXCLUIDO | No acreditan territorio (§6.3) |
| NIF del órgano (`schemeName=NIF`) | EXCLUIDO | Presente en 410/410 entradas |
| Contactos: nombre, teléfono, fax, correo | EXCLUIDO | Presentes en 410/410 entradas de 643 |
| Sitio web del órgano y URL del perfil | EXCLUIDO inicialmente | No necesarios |
| Adjudicatarios, ganadores, ofertas, `TenderResult`, `WinningParty`, importes de adjudicación | EXCLUIDO | 149 entradas con `TenderResult` en 643 |
| Lotes (`ProcurementProjectLot`) | EXCLUIDO | Salvo el indicador `has_lots` propuesto |
| Documentos, URIs, hashes de documento, nombres de fichero, pliegos | EXCLUIDO | Incluidos `LegalDocumentReference` y `AdditionalDocumentReference` |
| Criterios de adjudicación, requisitos, garantías, plazos de ejecución, financiación | EXCLUIDO | No necesarios |
| Referencias TED y otras publicaciones | EXCLUIDO inicialmente | Sin path ni cardinalidad aprobados |
| `entry.updated`, `feed.updated`, `rel=next`, tombstones | PERMITIDO como control técnico | Fuera del Record y del hash |

Significado original conservado:

- Importes: cada importe lleva su rol original, moneda explícita y tratamiento fiscal; no se suman, no se convierten, no se infiere EUR ni IVA, no se redondea.
- Fechas: se conserva la precisión (fecha o fecha-hora con zona). La fecha de emisión de un aviso no se convierte en fecha de publicación; `dates.published_at` solo si una regla acredita un aviso inicial inequívoco (v0.1 §8), y por defecto se omite. `dates.event_at` ausente.
- Un campo opcional ausente no es error. Un campo material presente e inválido (importe, moneda, código, fecha) pone el elemento en hold; no se oculta como ausencia.

## 9. Estrategia incremental y seguridad

### 9.1 Modo

`incremental_feed`, no `complete_scope`. Una ausencia no implica retirada. El bootstrap inicial usa un horizonte de `entry.updated` aún por fijar; no se inventa una fecha de inicio ni un inventario completo.

### 9.2 Watermark con zona horaria

- Se guarda `entry.updated` como instante con offset (RFC 3339), comparado como instante absoluto. Observación: el offset del feed cambió a `+01:00` el 25-oct-2026 (cambio horario); un parser que ignore el offset da horas erróneas.
- El watermark avanza solo tras un lote íntegro: lectura completa de la ventana, controles, Privacy/Publication, preflight y escritura confirmada.
- Frontera inclusiva con desempate por `entry.id`. Un límite de seguridad nunca equivale a completitud.

### 9.3 Solapamiento y reconciliación: hipótesis de calibración

Los valores **72 h** (ventana diaria) y **14 días** (reconciliación semanal) **no son parámetros definitivos**. Son hipótesis de calibración: sirven para dimensionar el diseño y se confirman o sustituyen con evidencia antes de operar.

**Limitaciones de cobertura**

- Solo se observó una instantánea de 29,5 h (410 entradas); se desconoce la distribución del retraso entre la publicación en el órgano y la aparición en el feed.
- La especificación (§3.3.2) admite que se eliminen versiones antiguas de una entrada en casos excepcionales: el feed no es un historial completo.
- Las páginas `next` son archivos generados en un instante; si la generación se retrasa o es menos frecuente que la ejecución, la ventana puede tener huecos.
- Ninguna ventana finita detecta una corrección posterior a su horizonte.

**Correcciones sin cambio de `updated`**

- La especificación (§3.3.1) las admite. Un watermark basado solo en `updated` las pierde.
- Mitigación: toda entrada leída dentro de la ventana se normaliza y se compara por hash con el Record previo, aunque su `updated` sea anterior al watermark.
- Residual: una corrección en una entrada fuera de la ventana solo se detecta en la reconciliación; una que no vuelva a aparecer en las páginas leídas no se detecta. Es un límite documentado, no una garantía.

**Reconciliación acotada**

- Menos frecuente que la diaria, con presupuesto propio de páginas, bytes y tiempo, y el mismo preflight y fallo cerrado.
- Si el presupuesto se agota antes de cubrir el horizonte, el resultado es `incomplete`: no se afirma cobertura ni avanza ningún marcador de reconciliación.
- Cada ejecución declara el horizonte realmente cubierto (intervalo de `updated` leído), no el planificado.

**Retrasos y fallos**

- Si una ejecución falla o se omite, la siguiente parte del último watermark **confirmado** menos el solapamiento. Si el hueco supera el solapamiento, la cobertura de ese tramo no está demostrada: se marca `coverage_gap` (diagnóstico técnico) hasta cubrirlo con una reconciliación ampliada o una decisión manual.
- El watermark nunca supera la última entrada leída con la cadena `next` completa dentro del intervalo.
- Feed regenerado a mitad de lectura: aborto (`source_changed_during_run`).

**Cómo demostrar cobertura suficiente antes de operar** (criterios de aceptación; no se ejecutan ahora)

1. Observación autorizada de varios días consecutivos del feed 643, con evidencia minimizada, que mida: cadencia de regeneración y de páginas `next`; distribución del retraso entre `entry.updated` y la primera aparición; frecuencia de entradas que reaparecen con `updated` anterior; frecuencia de correcciones sin cambio de `updated`.
2. Comprobar que la ventana elegida cubre, con margen, un percentil alto acordado de ese retraso. Si no, ampliarla; no operar con cobertura no demostrada.
3. Dos ejecuciones solapadas: mismos Records y cero escrituras en la segunda (idempotencia).
4. Prueba de recuperación: simular un hueco de ejecución y demostrar que la reconciliación lo cubre o declara `coverage_gap`.
5. Hasta cumplirlo, los parámetros siguen siendo hipótesis y el collector no opera.

### 9.4 Idempotencia

- La misma entrada con la misma proyección da `NO_CHANGE`: cero escrituras y cero Events. Dos ejecuciones sobre las mismas entradas dejan el árbol de Git igual.
- Orden determinista de Records y Events; conjuntos ordenados canónicamente.
- Create si no hay Record previo; Update si cambia la proyección semántica bajo el mismo contrato; versión de proyección distinta requiere migración explícita, no un Update.
- Se conserva el `detected_at` previo. Una versión anterior no revierte un Record más reciente.

### 9.5 Anulaciones y tombstones

`at:deleted-entry` lleva `ref`, `when` y, desde julio de 2022, `comment type` (`ANULADA` o `CERRADA`).

- `CONFIRMADO`: la especificación define `ANULADA` como expediente anulado y no válido, y `CERRADA` como cerrado o archivado y ya no accesible.
- **Es una observación técnica.** La `ref` se interpreta en el namespace del feed (`643::` + `ref` literal) y se registra de forma minimizada (hash de la `ref`, tipo, `when`) fuera del hash del Record.
- Un tombstone **nunca** borra un Record, **nunca** crea un Event ni cambia por sí solo la categoría o el estado administrativo. Si la `ref` no corresponde a ningún Record, solo se cuenta.
- Si reaparece una `entry` con el mismo `id` y `updated` posterior al `when` del tombstone, se trata como actualización normal; el tombstone no es permanente.
- **Impedimento de presentación.** Un Record cuya `ref` tenga un tombstone posterior a su último `updated` **no puede presentarse como activo, abierto o vigente**, ni siquiera de forma implícita (por ejemplo, mostrando solo el último estado y los plazos). Queda retenido (hold) en publicación hasta que haya un estado acreditado: un estado de retirada aprobado y mostrado de forma neutra («retirada de la fuente: anulada/cerrada, fecha») o una `entry` posterior que lo reactive. Vale también para Records ya existentes: la publicación futura debe comprobar los tombstones antes de aprobar.
- No se crea ningún campo nuevo ni se cambian schemas o Events en esta tarea. `feed_withdrawal` (§7) sigue siendo propuesta; su aprobación es la decisión D4 y condición previa de publicar.
- Una ausencia en la ventana no es retirada; solo se procesa tras comprobaciones completas o con estado oficial explícito (`AGENTS.md`).

### 9.6 Recuperación tras fallos

- Fallo de una página, XML, framing, MIME o seguridad: el lote es `failed` o `incomplete`. No avanza el watermark, no se escribe ningún Record ni Event, y se conservan los datos anteriores.
- Un fallo de la fuente no elimina ni invalida datos válidos anteriores (`AGENTS.md`).
- Reintento: la ejecución siguiente vuelve a leer la misma ventana (+ solapamiento); la idempotencia evita duplicados.
- Feed regenerado durante la ejecución (cambia `feed.updated` o la cadena `next` a mitad de lectura): `source_changed_during_run`, el lote se aborta.
- Catálogo de errores: el de v0.1 §14, con `feed_id=643`; los mensajes son códigos cerrados y nunca incluyen XML, ids, nombres, URLs ni excepciones crudas.

### 9.7 Integridad: escritura, preflight y publicación

**Escritura atómica por archivo no es publicación atómica por lote.** Reemplazar un archivo de forma atómica evita archivos truncados, pero un lote escribe muchos archivos (Records, Events, Manifest, Health) y no existe transacción multiarchivo ni rollback global. Un fallo a mitad dejaría un estado mixto que sería visible si llegase a un commit. Por eso la unidad de publicación es el **commit**, y el diseño impide que llegue a un commit nada que no sea un lote completo y validado.

Principios pedidos para BOE-INTEGRITY-01B, contrastados con el comportamiento actual de `boe-manual.yml` (`NO VERIFICADO`: no se localizó en el repositorio un documento con ese nombre, así que no se contrastaron contra él):

1. **Preflight completo.** El lote entero se normaliza, pasa Privacy y Publication y se prepara en memoria con preflight de Records y Events **antes de escribir** nada. Un error de preparación aborta con cero escrituras.
2. **Fallo cerrado.** Cualquier duda de integridad, seguridad, identidad o configuración detiene el lote. Ante un fallo solo pueden quedar preparados el Manifest y el Health `failed` validados; **nunca** Records, Events ni cola de revisión parciales, aunque cada JSON sea válido por separado (como hace BOE).
3. **Ninguna publicación parcial.** Se hace `git add` solo de lo que un validador de seguridad propio de PLACSP acepta como lote completo; si la ejecución no es un éxito, no se incluye ningún dato.
4. **Validación de integridad antes de desplegar.** Tras escribir y antes del commit: validación de datos canónicos, `git diff --check`, comprobación de que lo preparado coincide con el lote del preflight y de que no hay archivos ajenos. Pages solo se despacha tras un commit publicado con éxito.
5. **Coordinación segura con BOE y BDNS** (§9.8).

Manifest v1 y Health v1 existentes, sin ampliar contadores ni plantillas. Estado `no_publication` mientras haya hold; Health `healthy`. El checkpoint (watermark, tombstones, estado por objeto) no cabe en Manifest ni en Records y hoy no existe almacén: D5.

### 9.8 Coordinación con los workflows existentes

No se modifica ningún workflow en esta tarea. Observado en el repositorio:

- BOE: concurrencia `boe-collection-main`, cron `17 12` UTC. Antes de publicar hace `git fetch` y se niega (`exit 1`) si `origin/main` avanzó desde que empezó.
- BDNS: concurrencia `bdns-collection-main`, cron `17 8` UTC. Si `origin/main` avanzó, valida los cambios ajenos, hace `rebase`, revalida el commit y se niega si `origin/main` avanza otra vez.
- Los grupos de concurrencia son distintos, así que BOE y BDNS pueden ejecutarse a la vez; la protección real es la comprobación previa al `push`.

Diseño para PLACSP:

- Grupo propio `placsp-collection-main`, sin cancelación en curso, y franja distinta de las dos existentes y posterior a la regeneración del feed, una vez conocida su cadencia (D10). Cron va en UTC y el feed en hora peninsular.
- Antes del `push`: `fetch` de `origin/main`; si avanzó, no se publica sobre una base distinta sin revalidar. Opción por defecto: el patrón estricto de BOE (rechazar y dejar que la siguiente ejecución, idempotente, reintente). El rebase de BDNS solo si el validador de PLACSP comprueba que los commits ajenos no tocan rutas de PLACSP ni comparten Manifest o Health.
- Validador de seguridad propio de PLACSP (rutas permitidas, solo archivos de esta fuente); no se reutilizan ni se modifican los de BOE y BDNS.
- Una ejecución de PLACSP no toca las rutas, Manifest ni Health de BOE o BDNS.
- Pages: solo se despacha si hay commit con datos. Con el hold no hay commit de Records y no se despacha.
- Python 3.12 en CI. Volumen: diaria 1–3 páginas (≈12–37 MB); reconciliación hasta ~14 días de ventana (hipótesis). `NO VERIFICADO` el tiempo total con parsing y gates.

## 10. Dependencia DIPCAS y crosswalk

### 10.1 Tres cosas distintas

| Elemento | Qué es | Estado |
| --- | --- | --- |
| Módulo de normalización DIPCAS | Código en `src/infocs/reference/`: valida INE, DIR3, tipo (municipio o `E.L. Menor`) y enlaces. Sin red ni datos | En `main`. No necesita cambios |
| Snapshot real DIPCAS | Datos reales del dataset `ayuntamientos` | `blocked_pending_reuse_review`. **No se usa como entrada productiva ni se publica** |
| Directorio oficial PLACSP | `OrganosContratacion.xlsx` de Hacienda: perfiles alojados, activos e inactivos | Fuente oficial distinta, con sus propias condiciones de reutilización |

### 10.2 Crosswalk: contenido y origen

El crosswalk es un artefacto de referencia **solo de identificadores**, sin nombres, webs ni datos personales. Cada fila lleva `entity_kind`, `ine` (si es municipio), `dir3`, nivel, origen y fecha de comprobación.

| Nivel | Contenido | Origen propuesto |
| --- | --- | --- |
| 1 | Municipios: pares INE ↔ DIR3 | Una fuente que ligue ambos códigos de forma exacta. Los 128 casos con DIR3 coincidente en el directorio se comprueban contra ese par; los 7 huecos quedan fuera |
| 2 | Diputación, mancomunidades y Ballestar | Lista revisada a mano, con confirmación externa de cada DIR3. No se deduce de la ruta jerárquica del directorio |
| 3 | Sin resolver | Los 7 huecos, órganos sin DIR3, sub-órganos |

Origen del par INE ↔ DIR3 del nivel 1 (**decisión D1 abierta**). Opciones, sin elegir aquí:

- **(a)** Inventario oficial de DIR3, si publica el código INE de forma exacta y reutilizable. `NO VERIFICADO`: no se ha consultado.
- **(b)** El dataset DIPCAS, después de resolver la revisión de reutilización (DIPCAS-REF-02 o equivalente). El repositorio es público, así que versionar el crosswalk equivale a publicarlo.
- **(c)** Generarlo en cada ejecución a partir de la API de DIPCAS sin guardarlo en Git. Introduce una segunda dependencia de red y de disponibilidad; contradice la independencia entre collectors.

Hasta decidirlo, **el collector no puede evaluar el motivo `organ_dir3_crosswalk` en producción**. El motivo `execution_nuts3_es522` no depende de ningún crosswalk. Por eso el MVP admite dos etapas:

- **MVP-a**: solo `execution_nuts3_es522`.
- **MVP-b**: añade `organ_dir3_crosswalk`, cuando D1 esté resuelta.

`INFERIDO` con base en una muestra de 29 horas, no extrapolable: en 643, las dos entradas con órgano acreditado por DIR3 de DIPCAS también tenían `ES522`. Con esa muestra, el eje de órgano no añadió entradas nuevas; su valor está en contratos de órganos de Castellón con un lugar de ejecución amplio o ajeno.

### 10.3 Reglas del crosswalk

- Versionado, con fecha, origen y revisor. Cada cambio se justifica con evidencia; nunca por similitud de nombres.
- Un DIR3 asociado a dos INE, o un INE a dos DIR3, bloquea esa fila (misma regla que `build_catalog`).
- Ninguna pieza de DIPCAS se modifica para PLACSP. DIPCAS-REF-01 se usa tal cual; si el crosswalk lo consume, lo hace como lector.

## 11. Privacy Gate

Obligatorio y con fallo cerrado.

- Los datos excluidos del §8 no se leen del XML. Esto reduce la superficie, pero no sustituye al gate.
- El Privacy actual solo recorre `source_data` de BDNS. La rama PLACSP debe inspeccionar **todos** los textos retenidos: título, nombre del órgano, `ContractFolderID`, identificadores, `source_url` completa (incluidas variantes decodificadas) y cualquier texto de la extensión. Debe cubrir nombres de personas y datos fiscales encubiertos en identificadores.
- Un error del motor de Privacy o de configuración aborta el lote. «Allow» no es dictamen jurídico.
- Sin XML crudo almacenado como alternativa; sin cohortes privadas ni hashes individuales en fixtures o Records públicos.
- Con 643 el riesgo es mayor que en 1044: contactos presentes en todas las entradas; NIF en todas; adjudicatarios con NIF en una parte (Anexo A). Excluirlos antes de cualquier proyección.

## 12. Publication Gate y reutilización

### 12.1 Publication Gate

- Reutilizar los tipos existentes (`SourcePublicationEligibility` `eligible`/`hold` y la decisión por Record `approved`/`hold`/`rejected`), con un adaptador PLACSP propio y un `policy_id` propio. No se reutilizan la configuración manual de BOE ni los predicados de BDNS.
- **Estado inicial: `hold` con `reuse_policy_unresolved`.** Mientras dure, la ejecución sería de tipo `no_publication`: sin Records en `data/`.
- Para aprobar un Record hacen falta todos estos requisitos: identidad coherente, metadata permitida, URL pública validada, territorio `INCLUDE`, Privacy `allow`, aplicación específica de las condiciones de reutilización cerrada (§12.2), ningún tombstone posterior sin resolver (§9.5) y decisión D4.

### 12.2 Reutilización (D6)

Fuente: página de datos abiertos del Ministerio de Hacienda, `https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos/paginas/Datosabiertos.aspx`. La información de la fila de condiciones generales la aporta el responsable del proyecto como contrastada para esta revisión; **no se ha vuelto a consultar en la tarea 02A** (sin HTTP adicional). En PLACSP-SCOPE-01 solo se leyó la página específica de licitaciones, no el aviso legal.

| Bloque | Contenido | Estado |
| --- | --- | --- |
| Condiciones generales | El Ministerio permite con carácter general la reutilización comercial y no comercial de sus conjuntos de datos, bajo condiciones de **atribución, integridad y actualización** | `CONFIRMADO` (por el responsable). Falta registrar el texto exacto y la fecha real de consulta en la revisión de fuente |
| Condiciones particulares del dataset 643 | Si el conjunto de licitaciones por perfiles alojados (643) o el directorio de órganos añaden condiciones o excepciones propias; alcance sobre metadata de terceros incluida en las entradas; tratamiento de los campos de texto libre | `NO VERIFICADO` |
| Requisitos de privacidad | Aplicación de la normativa de protección de datos a los datos personales de los avisos (contactos, representantes, personas físicas licitadoras o adjudicatarias); si la reutilización general ampara su republicación | `NO VERIFICADO`. El diseño los trata excluyendo esos datos (§8) y con el Privacy Gate (§11) |

Consecuencias:

- La cita prevista («Origen de los datos: Ministerio de Hacienda») cubre la atribución. Integridad y actualización se cumplen no alterando el significado de los datos (importes y fechas con su rol original, §8) y mostrando la fecha de actualización de la fuente en cada Record publicado. Son requisitos de diseño a verificar en Wave 2.
- La licencia EUPL de OpenPLACSP no es la licencia de los datos.
- El directorio de órganos se rige por las mismas condiciones generales y requiere el mismo control particular.
- **El bloqueo de publicación se mantiene** hasta cerrar la aplicación específica: texto exacto de las condiciones vigentes registrado con fecha, condiciones particulares del dataset 643 comprobadas y requisitos de privacidad cerrados. Confirmar las condiciones generales **no** desbloquea la publicación.
- Documentos de terceros, espejo, PDF y texto completo siguen excluidos.

## 13. Dependencias pendientes

| Id | Dependencia | Bloquea |
| --- | --- | --- |
| D1 | Origen del par INE ↔ DIR3 para el crosswalk (§10.2) | MVP-b (eje de órgano) y publicación del crosswalk |
| D2 | Resolución de los 7 ayuntamientos con discrepancias (§6.4), uno a uno | Cobertura completa del eje de órgano |
| D3 | Observación longitudinal de `entry.id` en 643 (§5.4) | Cualquier Record de 643 |
| D4 | Tratamiento público de `ANULADA`/`CERRADA` (§9.5) | Publicación |
| D5 | Almacén de estado para watermark, tombstones y versión por objeto | Idempotencia y recuperación |
| D6 | Condiciones generales confirmadas (§12.2). Pendientes: condiciones particulares del dataset 643 y del directorio, requisitos de privacidad y su aplicación específica; registro de `placsp` frente a `pcsp` | Publicación y activación de fuente |
| D7 | Ficha pública: regla de `source_url`; paths de título y nombre | Candidate completo y publicación |
| D8 | Precisión decimal de importes (v0.1 §11) | Importes |
| D9 | Superficie de Privacy para PLACSP; extensión `source_data.placsp` en Core (v0.1 §14) | Código del collector |
| D10 | Cadencia real del feed 643; valores de solapamiento, presupuesto y horizonte | Workflow y parámetros |
| D11 | Tabla oficial de códigos municipales para el municipio de ejecución | Cualquier atribución municipal |
| D12 | Lugar de ejecución de lotes | Cobertura de contratos con lotes |

## 14. Siguiente trabajo propuesto (sin autorización automática)

1. Revisión independiente de este contrato y decisión sobre D1 y D4.
2. Observación longitudinal de `entry.id` en 643, con cohorte propia y la regla `STABLE_UPDATE` (red, evidencia minimizada, sin XML guardado).
3. Wave 2: mapping de Candidate y fixtures sintéticos offline para 643, incluida la prueba de que BOE y BDNS conservan bytes y hashes.

## 15. Compatibilidad con el pipeline y alcance de los cambios

- BOE, BDNS, BOP y DIPCAS: ningún cambio de comportamiento ni de código propio. El futuro collector PLACSP es independiente, como exige `AGENTS.md`.
- Sí exigirá cambios en piezas **compartidas** del Core (unión `SourceData`, `finalize`, hash/diff, Privacy, schemas de Record y Candidate), ya enumerados en `PLACSP_SOURCE_DATA_SCHEMA_DESIGN_v0.1` §14. Su condición es que la salida de BOE y BDNS sea idéntica byte a byte.
- Workflows, Astro y schemas: sin cambios en esta tarea.
- Coherencia entre identidad, territorio y publicación: la identidad no depende del territorio; el territorio solo decide `INCLUDE`/`UNRESOLVED`; la publicación exige además Privacy y reutilización. Ningún paso rellena un hueco de otro (sin fallback de identidad por título, sin territorio por nombre o código postal, sin publicación por haber sido incluido).

## 16. Estado de este documento

`GO` de diseño para revisión independiente. `HOLD` de implementación, de publicación y de activación de 1044. No se hicieron consultas HTTP para escribir este documento; la evidencia es la recogida por PLACSP-SCOPE-01 el 2026-10-25 (Anexo A).

## 17. Referencias y versionado de documentos

Este contrato no contiene enlaces relativos a otros documentos: los citados van como nombres de archivo en código, de modo que ninguno se rompe si solo este documento entra en Git. Los documentos históricos están sin seguimiento y **no se versionan automáticamente**; incorporarlos requiere una decisión aparte.

| Documento | Papel respecto a este contrato | Recomendación de versionado |
| --- | --- | --- |
| `PLACSP_SOURCE_CONTRACT_v0.2.md` | Este documento | Versionar |
| `PLACSP_SOURCE_DATA_SCHEMA_DESIGN_v0.1.md` | Referencia imprescindible: v0.2 remite a sus §4–§17 (modelo tipado, hash, fechas, importes, Privacy, tests) y a su §14 (cambios futuros del Core) | Imprescindible; versionar con este contrato o integrar esas secciones en una v0.2 del esquema |
| `PLACSP_SOURCE_CONTRACT_v0.1.md` | Referencia imprescindible: v0.2 remite a su §8 (fechas), §11 (importes) y §14 (errores) y sustituye parcialmente el resto | Imprescindible mientras v0.2 remita a él; versionar con una nota de «parcialmente superado» |
| `PLACSP_IDENTITY_SNAPSHOT_GATE_v0.1.md` | Referencia útil: estado `PLACSP_NEEDS_IDENTITY_WORK` para 643 | Recomendable; corto (7 KB) |
| `PLACSP_COLLECTOR_DESIGN_v0.1.md` | Diseño histórico de dos canales y waves P0–P11 | Evidencia histórica local; no imprescindible |
| `PLACSP_SOURCE_AUDIT_AND_SAMPLE_v0.1.md` | Auditoría de fuente y muestra del 2026-10-07 | Evidencia histórica local; v0.2 ya recoge lo vigente en su Anexo A |
| `PLACSP_LONGITUDINAL_EVIDENCE_STRATEGY_v0.2.md` | Estrategia de la cohorte de 1044 | Evidencia histórica local; solo relevante si se activa 1044 |
| `INFOCS_PUBLIC_SOURCE_API_MAP_v0.1.md` | Mapa general de fuentes; no es PLACSP | Decisión aparte |

Si se versiona solo este contrato, las referencias a v0.1 quedan como texto que apunta a archivos no versionados: el documento sigue siendo legible, pero la trazabilidad completa exige versionar al menos los dos «imprescindibles».

---

## Anexo A. Evidencia de PLACSP-SCOPE-01 (2026-10-25)

Se incluye aquí porque la evidencia de esa tarea vivía solo en una conversación. No contiene datos fuente reales, NIF, contactos ni nombres de adjudicatarios. Los feeds descargados y el directorio se borraron al terminar el análisis.

**Método.** 8 peticiones HTTP de lectura, sin reintentos: página de datos abiertos de Hacienda; HEAD y GET del directorio de órganos; 2 páginas del dataset DIPCAS `ayuntamientos` (solo `id`, `ine`, `dir3`, `nombre_poblacion`); primera página de 643; dos páginas de 1044; la especificación en PDF. Análisis en memoria.

**Fuentes oficiales.**

- `https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos/Paginas/licitaciones_plataforma_contratacion.aspx`
- `https://contrataciondelsectorpublico.gob.es/datosabiertos/OrganosContratacion.xlsx` (1.469.534 bytes; generado el 01/10/2026)
- `https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom`
- `https://contrataciondelestado.es/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom`
- `https://contrataciondelsectorpublico.gob.es/datosabiertos/especificacion-sindicacion.pdf` (v1.10, 17/09/2024)

**Muestra de feeds.**

| Medida | 643 (1 página) | 1044 (2 páginas) |
| --- | --- | --- |
| Entradas | 410 | 798 (298 + 500) |
| `entry.id` distintos | 407 | 798 |
| Tombstones | 1 (`ANULADA`) | 35 (`CERRADA`) |
| Intervalo de `updated` | 23-oct 14:25 a 24-oct 19:53 (+02:00); 29,5 h | 23-oct 13:11 a 25-oct 02:00; 37,8 h |
| Con `DIR3` | 323 | 324 (36 en la primera página, 288 en la segunda) |
| Con identificador alternativo | `ID_PLATAFORMA` en 410; NIF en 410 | `ID_OC_PLAT` en todas |
| Con `NUTS` | 410 | 798 |
| Con `ES522` | 4 | 0 |
| Con `ES52x` | 40 | 0 |
| Con lotes | 91 | 138 |
| Con `TenderResult` / `WinningParty` | 149 / 142 | 438 / 431 |
| Con campos de contacto | 410 | 0 |
| Con `ContractFolderID` | 410 | 797 |
| Transferencia | 12.234.604 bytes | 3.162.421 y 4.391.757 bytes |

Ventana común (23-oct 15:13 a 24-oct 19:53, +02:00): 643 con 200 entradas y 3 con `ES522`; 1044 con 294 entradas y 0.

Prefijos NUTS de 1044: `ES51`, `ES21`, `ES61`, `ES30`, `ES22`, `ES11` y otros; ninguno `ES52`.

**Entradas relacionadas con Castellón en 643 (5 de 410).** 2 con órgano acreditado por DIR3 de DIPCAS (Castellnovo y Borriana); 4 con `ES522` (esas dos, el Consorcio Hospitalario Provincial y la Dirección provincial del INSS); 1 con código postal `12071` y ejecución `ES`, no atribuida. En 1044: 0. Los 5 no sustentan un porcentaje.

**Cruce con el directorio (23.486 órganos).** 128 de 135 municipios de DIPCAS con DIR3 exacto, todos activos; 116 tienen varios órganos con el mismo DIR3 (alcaldía, pleno, junta de gobierno). Ballestar (`L04120001`): 2 órganos activos. Filas con ruta `Castellón>…`: 353 (319 en ayuntamientos, 6 de la Diputación con DIR3 `L02000012` y 28 de mancomunidades). Siete municipios sin coincidencia (§6.4).

**Cruce entre canales.** 0 pares (órgano, `ContractFolderID`) en común; 1 texto de `ContractFolderID` repetido entre canales, con órganos distintos.

**Límites.** Una sola instantánea de 30–38 h. No se leyó una segunda página de 643. No se mapearon los identificadores de plataforma agregada de 1044 (661, 62, 63, 121, 721, 561, 161). No se consultó el aviso legal ni incidencias oficiales. No se extrapolan porcentajes a toda la contratación de Castellón.
