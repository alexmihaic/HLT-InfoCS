# BOE — Política de normalización v1 (Fase 03D)

## Alcance

Esta capa conecta el resultado ya validado de 03B y 03C con el contrato
interno de InfoCs, sin escribir en disco:

```text
BOEItem + BOETerritorialDecision(include)
  -> normalize_boe_item(...)
  -> RecordCandidate(active)
  -> finalize_record() [integración del core, sin persistencia]
  -> Record
```

El normalizador no hace HTTP, no vuelve a evaluar la territorialidad y no abre
los enlaces XML, HTML o PDF. Una decisión `no_match` devuelve `None`, sin
error ni creación de un record marcado como irrelevante.

## Source e identidad

| InfoCs | Origen BOE | Regla |
| --- | --- | --- |
| `source.id` | Constante de fuente | `boe`. |
| `source.official_id` | `BOEItem.official_id` | Se conserva el literal oficial y es obligatorio. |
| `source_url` | `BOEItem.documents` | HTML si está presente; si no, XML; si no, PDF. No se construye ninguna URL. |

El core recibe el `official_id` sin un identificador InfoCs provisional. Por
ello `finalize_record()` aplica la estrategia `official_id` y genera el
namespace interno de fuente. Un título corregido no modifica esa identidad.

## Autoridad y nivel administrativo

El sumario proporciona departamento y sección, pero no permite afirmar una
persona jurídica más específica. Por eso la autoridad BOE v1 es conservadora:

```text
authority.id = boe-department:<department_code>
authority.name = department_name
authority.administration_level = state
administration_level = state
```

`boe-department:<code>` es un identificador derivado por InfoCs para el
departamento expresado en el sumario; no pretende ser un identificador
universal de la institución. Una mención territorial no rebaja el nivel de la
publicación BOE de estatal a municipal o provincial.

## Fechas y contenido

`BOEItem.published_on` se asigna a `dates.published_at`. El sumario v1 no
aporta una fecha de hecho con semántica suficiente, por lo que no se rellena
`dates.event_at`.

`detected_at` y `last_checked_at` son argumentos explícitos, con zona horaria;
la función no llama a `datetime.now()`. Los valida y el contrato InfoCs los
normaliza a UTC. El título BOE se conserva, salvo compactar whitespace técnico.
No se crea una descripción, resumen ni texto completo.

## Categorías iniciales

La clasificación es pequeña, explícita y basada sólo en `section_code`:

| Código de sección BOE | Categoría InfoCs |
| --- | --- |
| `1` | `regulation` |
| `2B` | `employment` |
| `5A` | `procurement` |
| Cualquier otro, incluido `5B` | `other` |

La sección `5A` no aporta por sí sola expediente, CPV, importe ni adjudicatario,
y `5B` no se clasifica automáticamente como subvención. Los bloques
`financial`, `procurement` y `grant` quedan ausentes hasta que una fuente
aporte esos datos de manera objetiva.

## Documentos

Las URLs HTML, XML y PDF ya aportadas por el sumario se convierten en enlaces
`documents`; no se descargan. Todos se marcan:

```text
archive_status = not_archived
has_local_copy = false
publication_allowed = false
```

No se inventan MIME, SHA-256, copia local ni full text. Tamaño y páginas del
PDF existen en el modelo BOE source-specific, pero el contrato común de
`Document` no tiene campos equivalentes; se omiten conscientemente en 03D.
El orden de enlaces no tiene significado: se deduplica y ordena de forma
determinista.

## Territorialidad y geografía

Cada `BOETerritorialMatch` se preserva en
`provenance.territorial_matches`. La razón se traduce al vocabulario común:

| Razón BOE | Razón InfoCs |
| --- | --- |
| `municipality_exact` | `municipality_match` |
| `province_exact` | `explicit_text_match` |
| `authority_exact` | `authority_match` |

El campo `detail` es JSON compacto, con claves ordenadas, y conserva
`boe_reason`, `entity_code`, `entity_name`, `field`, `matched_text` y
`method`. Es procedencia InfoCs, no contenido administrativo de la fuente; por
eso no participa en `content_hash`. Las coincidencias se deduplican y ordenan
para que su orden de entrada no cambie el candidato.

Sólo se rellena `geography.municipality` si hay **una única** coincidencia
`municipality_exact` cuyo código tiene el formato INE de municipio de la
provincia 12 (`12xxx`). Se conserva el nombre de entidad de la decisión y el
código queda en la procedencia. Ante varias coincidencias, una coincidencia
provincial o una de organismo, `geography` queda ausente: no se inventa un
municipio principal ni se afirma aplicabilidad territorial.

## Procedencia y metadatos técnicos

El candidato declara:

```text
provenance.collector = boe_summary
provenance.collector_version = 0.1.0
provenance.normalizer_version = 1.0.0
provenance.transformed_by_infocs = true
technical.extraction_method = boe_summary_json
```

No se rellena `technical.raw_sha256`: 03B no conserva una respuesta raw de
producción a la que pueda asociarse un hash real. El candidato siempre entra
con `status: active`; `missing_from_source`, `withdrawn` y `quarantine` son
estados internos del core y no pueden llegar desde BOE.

## Validaciones y límites

La normalización rechaza explícitamente un `include` sin coincidencias,
identificador BOE o departamento vacío, fecha de publicación que no sea fecha
sin hora, timestamps sin zona o en orden inválido, y URLs BOE no HTTPS o fuera
de la allowlist. No añade defaults para ocultar una deriva del contrato.

La fase sólo prueba la integración con `finalize_record()` en memoria. No hay
persistencia, reconciliación diaria, eventos, manifests, health global ni
lectura de documentos individuales.
