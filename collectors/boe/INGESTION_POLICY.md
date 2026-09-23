# BOE — Política de ingesta incremental y persistencia v1 (Fase 03E)

## Frontera de privacidad

Esta fase valida el mecanismo únicamente con fixtures y datos sintéticos. No
se escriben records BOE reales en `data/records/`, ni eventos reales en
`data/events/`.

```text
LIVE REAL DATA PERSISTENCE BLOCKED pending explicit publication approval
```

El Privacy Gate v1 es una barrera técnica obligatoria en el flujo: clasifica
cada `Record` antes de `RecordStore.write()`, y el store vuelve a comprobarlo.
La persistencia de datos administrativos BOE reales sigue bloqueada en esta
fase; los tests usan `TemporaryDirectory` y datos sintéticos.

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
  -> Privacy Gate
  -> comparación por record.id y content_hash
  -> RecordStore
```

Para cada `BOEItem`:

- `no_match` incrementa `excluded` y no crea ningún candidato.
- Un ID ausente del store produce `create` y un evento `create` en memoria.
- El mismo hash produce `no_change` y ningún evento ni escritura.
- Un hash distinto produce `update`, reemplaza el JSON del record y devuelve
  `changed_fields` usando `infocs.diff`; no se reimplementa el diff.
- Un record `quarantine` o `reject` no produce operación ni evento público.
  Los records seguros de la misma edición sí pueden continuar.

Los duplicados semánticamente iguales del mismo batch se colapsan. Dos
observaciones del mismo ID con contenido incompatible hacen fallar el batch de
forma explícita.

## Resultados de ejecución

`ingest_boe_summary()` devuelve un estado y métricas:

```text
seen, included, created, updated, unchanged, excluded,
privacy_allowed, privacy_quarantined, privacy_rejected
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

Desde 03I los Events canónicos admiten sólo `create` y `update`, y se pueden
persistir en `EventStore` únicamente después de Privacy Gate `allow` y
Publication Review `approved`. El caller debe proporcionar la configuración
de revisión; un ID no listado queda en `hold`. La ingesta preflighta todos los
Records/Events antes de escribir, y después escribe Event seguido de Record.
No hay transacción filesystem multiarchivo: un error de I/O puede dejar un
Event temporalmente sin Record, que es recuperable con un retry de la
transición. Un Record actualizado sin Event no es recuperable de forma fiable,
por lo que se prefiere Event-first. La ausencia entre días sigue sin generar
evento. El primer Record real histórico no se retrorellena y `data/events/`
permanece vacío salvo `.gitkeep`.
