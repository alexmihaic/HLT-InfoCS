# Run Manifest v1

## Qué representa

Un `RunManifest` describe una ocurrencia concreta de intento de colección de
una fuente: alcance solicitado, tiempos, resultado, contadores agregados,
versiones relevantes y, si procede, un resumen seguro de error. No representa
un Record, un Event ni el estado de salud de la fuente. No incluye Records,
Events, payloads, respuestas raw, trazas, datos de máquina ni secretos.

`run_id` es `run-v1-<UUIDv4>` y se genera explícitamente al comenzar cada run
con `new_run_id()`. Dos ejecuciones de la misma fuente y el mismo scope reciben
IDs distintos. Este ID identifica una ocurrencia técnica; nunca identidad
administrativa ni reemplaza el `record_id`.

`started_at` y `finished_at` son timezone-aware, se normalizan a UTC y deben
cumplir `finished_at >= started_at`. El reloj/los valores se inyectan; el
modelo no usa `datetime.now()`. `requested_scope` expresa un tipo y valor
estructurados, por ejemplo `{ "type": "date", "value": "2026-09-23" }`.

## Estados y métricas

Estados v1: `success`, `partial`, `failed` y `no_publication`. `failed` lleva
`error_summary`; `success` y `no_publication` no. `partial` queda disponible
para una política futura y también requiere un resumen seguro. La ingesta BOE
actual es fail-closed y no inventa resultados parciales.

`RunMetrics` tiene un conjunto cerrado de contadores enteros no negativos; los
valores no aplicables son cero, no `null`: `seen`, `included`, `excluded`,
`normalized`, `finalized`, decisiones de privacy/publication, operaciones
`created`/`updated`/`unchanged`, `events_created`/`events_updated` y `errors`.
En el adaptador BOE, los dos contadores de Events describen Events producidos
en memoria para la transición; no certifican que se hayan escrito en disco.
Como `BOEIngestionResult` no ofrece contadores separados de normalize/finalize,
en `success` se derivan de `included`: el pipeline completo solo devuelve
éxito si esos pasos se completaron para todos los incluidos.

Para `success` se validan estos invariantes:

- `seen = included + excluded`;
- `included = normalized = finalized`;
- las tres decisiones de privacy suman `finalized`;
- las decisiones de publicación suman `privacy_allowed`;
- operaciones suman `publication_approved`;
- Events en memoria corresponden a operaciones create/update;
- `errors = 0`.

`no_publication` requiere todos los contadores en cero y no equivale a un
snapshot vacío. Un fallo temprano puede tener cero contadores de procesamiento
y un `errors = 1`. `partial` y `failed` pueden conservar métricas disponibles
sin afirmar invariantes de lote completo.

`error_summary` solo acepta `stage`, `error_code` y una `safe_message` de una
lista cerrada de plantillas públicas v1. No se propagan mensajes de excepción,
stack traces, payloads o razones del transporte. El adaptador BOE usa una
plantilla fija y omite el texto de error recibido; una nueva plantilla requiere
actualizar a la vez modelo, schema y tests.

`software_metadata` registra versión del collector, versión del contrato de
fuente si se conoce y un Git SHA opcional suministrado explícitamente. No
invoca Git ni inspecciona usuario, host, ruta local o entorno.

## Almacenamiento

`ManifestStore` guarda un JSON UTF-8 canónico con newline en
`<root>/<source>/<YYYY>/<MM>/<run_id>.json`, usando el mes UTC de `started_at`.
Valida schema, modelo, invariantes, ruta y serialización antes de escribir;
usa temporal validado y creación atómica sin reemplazo.

- mismo `run_id` y mismo contenido canónico: idempotente (`False`, no creado);
- mismo `run_id` con cualquier contenido distinto: conflicto contractual;
- IDs externos no se interpolan directamente en paths.

No existe chain/hash encadenado de manifests en v1. El contrato inicial no
define orden/serialización concurrente por fuente; Git y los propios archivos
aportan historial, sin presentarse como sello de tiempo certificado. Añadir
una cadena exige decisión posterior sobre concurrencia y ejecuciones tardías.

## Relación con Records y Events

El manifest es el artefacto final de una ejecución, separado de los artefactos
administrativos. La propuesta para una futura ejecución persistente es:

```text
iniciar run → procesar → preflight → Records/Events → manifest final
```

Un fallo antes de Records puede producir un manifest `failed`. Si Records y
Events completan pero falla I/O del manifest, los datos pueden existir sin
manifest; no hay transacción multiarchivo global ni rollback en v1. El diseño
no cambia RecordStore/EventStore.

El primer Record BOE y su primera persistencia no reciben manifest
retroactivamente: no se fabrica una identidad de run ni timestamps.

La integración offline 03K construía manifests en memoria desde
`BOEIngestionResult`. Desde 03L.1, el runner manual BOE finaliza y escribe el
Manifest real al acabar cada dispatch; después deriva y materializa Health.
El primer Record de 03H sigue sin Manifest retroactivo.
