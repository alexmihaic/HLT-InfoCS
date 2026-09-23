# Events canónicos v1

## Alcance

Un Event registra que InfoCs publicó por primera vez un Record (`create`) o
publicó una nueva versión semántica del mismo (`update`). `no_change` no crea
Event. La ausencia de un ítem en otro sumario BOE diario tampoco lo crea:
BOE es `incremental_feed`, no un snapshot. Las transiciones internas de
reconciliación (`missing_from_source` y `reappeared`) siguen siendo resultados
internos y no forman parte del contrato persistible de Events v1.

## Identidad y contenido

`event_id` es `evt-v1-` seguido de SHA-256 del JSON UTF-8 compacto
`[record_id, type, previous_content_hash, content_hash]`, con
`ensure_ascii=false`. En `create`, `previous_content_hash` ocupa explícitamente
el lugar de `null`; en `update` contiene el hash anterior. No incluye
`observed_at`, `official_id` ni campos derivados. Así, `A -> B` y `C -> B`
tienen IDs distintos, mientras que repetir `A -> B` produce el mismo ID.
Create de B y update A→B tampoco comparten ID.

El Event conserva `record_id`, `source_id`, `official_id` opcional,
`observed_at` normalizado a UTC y el `content_hash` actual. Un `update` añade
`previous_content_hash` y `changed_fields`, que son rutas ordenadas tomadas del
diff semántico existente. Nunca guarda valores anteriores/nuevos ni copia el
Record. `create` no enumera todos sus campos como cambios.

Los updates encadenan naturalmente el estado: el `content_hash` de un Event
es el `previous_content_hash` del siguiente update de esa secuencia. No se
añade criptografía de cadena, firma ni certificación externa.

## Privacidad y aprobación

El flujo exige Privacy Gate `allow` y Publication Review `approved` para
construir y escribir Event. `quarantine`, `reject` y `hold` no generan Events.
`changed_fields` contiene nombres de campos, no contenido. El primer Record
BOE preexistente no se retrorellena: su Event queda pendiente de decisión y
de un `observed_at` acreditado.

## EventStore

`EventStore` escribe un JSON individual bajo
`data/events/<source>/<record>/<event_id>.json`, con componentes codificados,
UTF-8 determinista y newline final. Valida modelo, schema e identidad. Prepara
un temporal validado y lo añade mediante creación atómica sin reemplazo; si el
ID ya existe con payload idéntico devuelve `created=false`, y si difiere falla
con conflicto contractual. Si solo difiere `observed_at`, la transición se
considera la misma, se conserva el timestamp del archivo existente y el retry
es idempotente. Cualquier otra diferencia bajo el mismo ID es conflicto.
`observed_at` representa la primera persistencia de la transición. `write()`
exige además el Record asociado y la configuración de Publication Review;
valida el Record y vuelve a ejecutar Privacy Gate y review antes de añadir el
archivo. `list_record()` ordena por `observed_at` y después `event_id`, sin
depender del orden del filesystem.

La ingesta hace preflight completo de Records y Events antes de escribir; a
continuación escribe Events y luego Records. No existe transacción real ni
rollback multiarchivo. Un fallo puede dejar temporalmente un Event sin Record;
se prefiere a perder irreversiblemente el Event. El retry reconstruye la misma
transición, conserva el `observed_at` ya persistido y vuelve a intentar el
Record. Create y update usan esta misma recuperación idempotente.

Una limitación consciente es que `A -> B`, `B -> A`, `A -> B` reutiliza el ID
de la primera transición `A -> B`. En v1 los Events identifican transiciones
administrativas únicas, no ocurrencias temporales repetidas. No se añaden run
IDs ni IDs de recurrencia todavía; queda como deuda futura.

## Relación con Record y límites

El Event apunta al estado actual por `record_id`; Record no conserva una lista
mutable de Events. No hay Event de backfill, delete, missing, reappearance,
withdrawn, manifests, health ni automatización en esta versión.
