# BOE — Política de ingesta incremental y persistencia v1 (Fase 03E)

## Frontera de privacidad

Esta fase valida el mecanismo únicamente con fixtures y datos sintéticos. No
se escriben records BOE reales en `data/records/`, ni eventos reales en
`data/events/`.

```text
LIVE REAL DATA PERSISTENCE BLOCKED until privacy gate exists
```

No se implementa todavía el privacy gate completo; la barrera se aplica por
el contrato de ejecución y por los tests que usan `TemporaryDirectory`.

## Semántica de colección

BOE declara `collection_semantics: incremental_feed`. El sumario diario es una
lista de publicaciones correspondientes a una fecha y no representa el estado
completo del BOE. Por tanto:

```text
día A: X
día B: Y
ausencia de X en B: no es missing_from_source
```

La ingesta nunca recorre los records anteriores buscando ausencias y nunca
produce `missing_from_source` o `reappeared`. Esos eventos siguen reservados a
la reconciliación de fuentes con semántica `snapshot`.

## Flujo y operaciones

```text
BOESummary / BOEFetchResult
  -> decisión territorial
  -> normalización
  -> finalize_record()
  -> comparación por record.id y content_hash
  -> RecordStore
```

Para cada `BOEItem`:

- `no_match` incrementa `excluded` y no crea ningún candidato.
- Un ID ausente del store produce `create` y un evento `create` en memoria.
- El mismo hash produce `no_change` y ningún evento ni escritura.
- Un hash distinto produce `update`, reemplaza el JSON del record y devuelve
  `changed_fields` usando `infocs.diff`; no se reimplementa el diff.

Los duplicados semánticamente iguales del mismo batch se colapsan. Dos
observaciones del mismo ID con contenido incompatible hacen fallar el batch de
forma explícita.

## Resultados de ejecución

`ingest_boe_summary()` devuelve un estado y métricas:

```text
seen, included, created, updated, unchanged, excluded
```

Los estados proceden del transporte BOE:

- `complete_success`: procesa la edición y puede escribir records válidos.
- `no_daily_publication`: éxito sin edición; cero operaciones, eventos ni
  escrituras. No equivale a snapshot vacío.
- `source_failure`: cero escrituras; conserva el store anterior.
- `invalid_request`: resultado explícito de error de cliente; cero escrituras.

Un error contractual de un ítem aborta el batch antes de escribir cualquier
record. La preparación completa y la comparación se realizan primero. Una
eventual I/O failure durante los reemplazos individuales se propaga como
error; cada archivo afectado sigue siendo atómico por separado.

## RecordStore canónico

`RecordStore` es una abstracción pequeña y reutilizable con:

```text
get(record_id[, source_id])
exists(record_id[, source_id])
write(record)
list_source(source_id)
```

Cada record vive en un JSON separado. El layout conceptual es:

```text
data/records/<source-id-safe>/r-<record-id-encoded>.json
```

El source ID y el record ID se convierten en segmentos seguros; se codifican
separadores, puntos y caracteres reservados, de modo que `../`, rutas
absolutas, separadores Windows/Unix y nombres reservados no pueden escapar del
root. El nombre no depende del `content_hash`, por lo que permanece estable
entre actualizaciones.

Antes de sustituir el archivo se valida el `Record`, se comprueba que su
`technical.content_hash` coincide con la proyección semántica y se escribe
UTF-8 determinista (`Record.canonical_json()`) con newline final. El temporal
se crea en el mismo directorio, se vacía y sincroniza, se vuelve a validar y se
aplica `os.replace`.

Los events se construyen en memoria con el modelo común y se validan contra su
schema en tests. No se persisten en 03E; manifests, health y automatización
diaria pertenecen a fases posteriores.
