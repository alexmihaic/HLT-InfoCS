# Source Health v1

## Health es una proyección, no un log

`SourceHealth` se deriva exclusivamente de los `RunManifest` validados de una
fuente. Los manifests son el historial; Health es un resumen regenerable. El
runner BOE materializa `data/health/boe.json` después de cada run manual o
programado; el archivo se regenera desde los manifests y no es una fuente de
verdad aparte.

La función ordena los manifests por `finished_at`, `started_at` y `run_id`.
Por ello el resultado no depende del orden de entrada ni del filesystem. Si
hay dos runs con la misma hora, `run_id` deshace el empate de forma estable.

Campos v1: `source_id`, `status`, `consecutive_failures` y, cuando existe
historial, `last_run_id`, `last_attempt_at`, `last_success_at`,
`last_error_code` y `updated_at`. `last_attempt_at` es el `started_at` del
último manifest finalizado; `updated_at` es el `finished_at` de ese manifest,
no el momento de materializar la proyección. `last_success_at` es el final del
último `success` o `no_publication`. Se omite `last_publication_at`: el scope
solicitado no prueba una publicación y no hay un contador global fiable que
justifique dicho campo.

## Estados v1

- Sin manifests: `unknown`, sin timestamps afirmados.
- Último run `success` o `no_publication`: `healthy`; ambos cuentan como éxito
  operacional y reinician la racha de fallos.
- Último run `partial`: `degraded`.
- Uno o dos `failed` consecutivos: `degraded`.
- Tres o más `failed` consecutivos: `failing`.

El umbral v1 es **3 fallos consecutivos**, fijo y cubierto por tests. Una racha
solo cuenta manifests adyacentes cuyo status sea `failed`; una ejecución
`partial`, `success` o `no_publication` la interrumpe. Una ejecución correcta
posterior vuelve a `healthy` y deja `consecutive_failures = 0`.

`last_error_code` conserva el código del error más reciente disponible en el
historial, aunque después haya habido éxito; no conserva el mensaje ni el
payload. Health no declara que la fuente no haya publicado nada salvo cuando
el manifest de esa ejecución indique `no_publication`.

## Regeneración y límites

`derive_source_health(manifests, source_id=...)` valida que los manifests
pertenecen a una única fuente y devuelve el mismo resultado para el mismo
conjunto de entrada. `write_source_health()` valida el modelo/schema y
materializa JSON UTF-8 determinista con newline final mediante reemplazo
atómico. El writer no obtiene el reloj ni altera los timestamps derivados.

No existen notificaciones, SLA, checks de disponibilidad entre runs,
monitorización externa ni reglas de anomalía en v1. El schedule BOE diario se
ejecuta a las 12:17 `Europe/Madrid`; `no_publication` es un resultado válido y
mantiene Health `healthy`.
