# Política de normalización BOP Castellón v1

Esta capa convierte modelos source-specific ya parseados en `RecordCandidate` en memoria. No realiza HTTP, no interpreta documentos, no ejecuta Privacy Gate y no persiste Records. La recopilación técnica no autoriza la redistribución pública: los flags de publicación/reutilización del contrato BOP siguen bloqueados hasta revisión específica.

## Identidad y contenido

- `source.id` es `bop_castellon`.
- `source.official_id` es `idAnuncio`: identificador estable de portal observado, no identificador público/jurídico documentado. El ID InfoCs lo genera `finalize_record()` mediante la estrategia Core `official_id`.
- `idBoletin`, número y código identifican la edición, no el anuncio; se omiten del Candidate porque el Core no ofrece un campo de procedencia adecuado para esos datos técnicos.
- `title` conserva literalmente el título ya extraído del listado. No se crea descripción ni se reescribe contenido.

## Fechas, documentos y procedencia

`dates.published_at` procede de `BOPIssue.published_date`. `detected_at` y `last_checked_at` son argumentos explícitos con zona horaria; no se inventa hora ni `event_at`.

El enlace oficial individual se conserva como `source_url` y como único `Document.source_url`. No se consulta; MIME, hash, tamaño y copia local quedan ausentes. El documento queda no archivado y no autorizado para publicación por defecto.

La procedencia usa `bop_listing_html`. No se guardan HTML, cookies, ViewState ni datos de edición no contemplados por el Core.

## Geografía y autoridad

La publicación en BOP Castellón determina inclusión por alcance de fuente: todos los anuncios válidos reciben provincia `Castellón/Castelló` (código INE de provincia `12`) y una coincidencia `other_documented` cuya procedencia declara `collection_scope=province`. No es una coincidencia textual BOE.

El municipio sólo se añade cuando un heading estructural identifica exactamente un municipio del registry Castellón de 135 municipios, comparando variantes oficiales/alias con casefold, eliminación de diacríticos y límites de nombre. Se aceptan encabezados explícitos `Ayuntamiento/Ajuntament de …` y un heading cuyo texto completo coincide con una variante municipal. Nunca se busca municipio en el título del anuncio ni se aplica fuzzy matching.

- Ayuntamiento con match exacto: ID `bop-castellon:municipality:<INE>`, nivel `municipal`, nombre basado en el heading y geografía municipal canónica.
- Un heading explícito `Ayuntamiento/Ajuntament de …` sin match exacto se conserva como autoridad observada con ID InfoCs determinista y nivel `municipal`, pero sin municipio en la geografía; el nombre parecido nunca se fuerza al municipio más cercano.
- Diputación Provincial de Castellón explícita: ID `bop-castellon:diputacion:12`, nivel `provincial` y sólo geografía provincial.
- Otros organismos explícitos reconocidos por un prefijo de organismo conservan el heading como nombre. Su ID InfoCs determinista deriva del texto normalizado; es una etiqueta técnica de InfoCs, no un código administrativo. Sólo se establece nivel `autonomous` para Generalitat/conselleria y `state` para ministerios/delegaciones estatales inequívocos; otros niveles quedan `null`.
- Encabezado genérico o insuficiente: `authority` y `administration_level` son `null`; nunca se sustituye por la Diputación editora del boletín.

## Categoría

La categoría deriva exclusivamente de un conjunto pequeño y cerrado de frases en el título, normalizadas por mayúsculas/diacríticos y límites de palabra: empleo/oposiciones, contratación/licitación, subvenciones/ayudas, ordenanzas/reglamentos, presupuesto, urbanismo, subasta y convenio. Se usa únicamente el vocabulario Core existente; si no hay señal explícita, el resultado es `other`. Esta clasificación no influye en identidad ni en geografía.

## Límites

El Core excluye categoría, geografía, autoridad y procedencia de `content_hash`; reclasificaciones de esos metadatos no son cambios administrativos según la política actual. La política no valida privacidad, licitud de reutilización ni autoridad legal, no descarga PDFs y no produce `Record` persistibles por sí sola.
