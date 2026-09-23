# BOE — Safe Review Queue v1

## Finalidad y límites

`data/review/boe/pending.json` es un índice operativo derivado de ítems que
han pasado Privacy Gate (`allow`) pero permanecen en Publication Review
(`hold`). No es un dataset canónico ni una aprobación de publicación. La
configuración versionada de Publication Review sigue siendo la única fuente
de decisión.

La cola sólo puede contener `source_id`, `official_id`, `source_url` oficial,
`published_at`, el `run_id` de la observación más reciente, códigos de razones
territoriales, códigos de entidad, `publication_decision: hold` y
`reason_code`. El schema es cerrado (`additionalProperties: false`): no admite
título, descripción, nombres, authority, documentos, fragmentos, contenido de
Record ni valores detectados por privacidad.

Los ítems en `quarantine` o `reject` de Privacy Gate nunca se añaden. Si un ID
ya estaba pendiente, una observación de privacidad bloqueada lo retira sin
copiar el motivo ni el contenido sensible. Los Records approved/rejected por
Publication Review también retiran su ID de la cola. La ausencia en otro
sumario diario no retira nada: BOE es `incremental_feed`.

## Idempotencia y escritura

La clave de deduplicación es `(source_id, official_id)`. En un run se rechazan
observaciones incompatibles para la misma clave; entre runs, una nueva
observación `hold` actualiza los metadatos permitidos, incluido el último
`run_id`. El orden de filas es lexicográfico por fuente e ID. El JSON se valida
contra `schemas/review-queue.schema.json`, se serializa de manera compacta y
determinista en UTF-8 con newline final y se reemplaza atómicamente. Un retry
idéntico no modifica el archivo.

Cuando una persona revisa un ID, el flujo es: actualizar Publication Review
versionado y volver a procesar la fecha correspondiente. Si el ID resulta
approved y pasa Privacy Gate, la cola lo elimina y la ingesta normal decide
create/update/no_change. No existe aprobación automática, UI, notificación ni
reconciliación de ausencias.
