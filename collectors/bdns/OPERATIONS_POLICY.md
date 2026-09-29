# BDNS / SNPSAP — política de operación v1

**Revisión:** 2026-09-29
**Estado:** contrato operativo v1 aceptado; runner source-specific disponible; Action manual implementada en OPS-D, aún sin ejecución productiva ni schedule.

## Decisión ejecutiva

Separar tres clases de ejecución y declarar su cobertura:

| Clase | Propósito | Cuándo es completa | Ausencia |
| --- | --- | --- | --- |
| `discovery` | Explorar una consulta acotada o descubrir candidatos recientes. | Nunca por el mero hecho de terminar la muestra. Sólo si el scope declarado devuelve y procesa todas sus páginas. | No produce `missing_from_source`. |
| `incremental_update` | Volver a consultar una ventana temporal solapada para incorporar convocatorias recibidas recientemente. | Completa únicamente para esa ventana y todos sus detalles; no representa cobertura de llamadas antiguas ni de correcciones retrospectivas. | No produce `missing_from_source`. |
| `complete_scope` | Enumerar todas las páginas de un scope territorial y temporal explícito, por ejemplo una partición de fechas. | Todos los resultados y detalles del scope fueron procesados y las comprobaciones de paginación coinciden. No equivale a un snapshot atómico de la BDNS completa. | No produce ausencias canónicas en esta fase. |

Un límite de páginas, detalles o tiempo alcanzado antes de terminar el scope
significa `partial_success`, nunca `complete_success`. Un HTTP 200 vacío sólo
es `no_results` cuando los metadatos confirman `totalElements = 0`; es un
resultado correcto del scope, no fallo ni prueba de que BDNS no publicara nada.

## Evidencia de búsqueda y filtros

La búsqueda oficial documentada acepta `regiones`, `fechaDesde`, `fechaHasta`,
`page`, `pageSize`, `order` y `direccion`. El catálogo auditado identifica
`regiones=56` como la región provincial BDNS de Castellón (`ES522`), no como
código INE. No se documenta un filtro separado por fecha de publicación de
extracto. La fecha de publicación disponible en detalle pertenece a
`anuncios[].datPublicacion`, no es un filtro de búsqueda según el contrato
auditado. Véanse [SOURCE_AUDIT.md](SOURCE_AUDIT.md),
[TERRITORIAL_POLICY.md](TERRITORIAL_POLICY.md) y la
[OpenAPI oficial SNPSAP](https://www.infosubvenciones.es/bdnstrans/estaticos/doc/snpsap-api.json).

Los parámetros temporales están documentados como `dd/MM/yyyy`. El contrato
local aún no confirma expresamente que delimiten `fechaRecepcion`. En una
consulta live acotada de `regiones=56`, `fechaDesde=01/09/2026` y
`fechaHasta=29/09/2026`, las cuatro filas devueltas entre las dos primeras
páginas tenían `fechaRecepcion` dentro del intervalo. Esto apoya esa lectura,
pero no demuestra semántica exhaustiva ni reemplaza la definición oficial del
campo. Hasta confirmar ese vínculo documental, cualquier incremental basado
en fechas es **provisional** y no puede garantizar que no omita convocatorias.

### Muestra live, 2026-09-29

Se realizaron exactamente cuatro GET a la búsqueda oficial; no se pidieron
detalles ni documentos y no se guardaron payloads:

- `regiones=56`, `pageSize=2`, `order=fechaRecepcion`, `direccion=desc`:
  las páginas 0 y 1 indicaron `totalElements=10.410`, `totalPages=5.205`,
  `pageable.pageSize=2`, offsets 0 y 2; no hubo código repetido entre esas
  dos páginas. Las cuatro fechas visibles fueron 28/09/2026.
- Mismos parámetros más la ventana 01/09/2026–29/09/2026: ambas páginas
  indicaron `totalElements=62`, `totalPages=31`, offsets 0 y 2; las cuatro
  fechas visibles estuvieron en la ventana.

Son tamaños dinámicos de la respuesta en esa fecha, no constantes ni pruebas
de estabilidad. El tamaño 2 fue sólo un sondeo pequeño; no prueba tamaños
mayores ni máximo del servidor. `pageSize=50` es un ejemplo documentado, no un
límite oficial. No hay cuota numérica publicada.

## Paginación e integridad de un scope

La API usa paginación indexada base cero, no cursor. Devuelve `content`,
`pageable.pageNumber`, `pageable.pageSize`, `pageable.offset`, `numberOfElements`,
`totalPages`, `totalElements`, `first`, `last` y `empty`.

Un futuro runner sólo podrá marcar un scope completo si:

1. fija el filtro territorial y, cuando proceda, un intervalo temporal antes
   de empezar;
2. itera `page=0..totalPages-1` con los mismos filtros y orden;
3. verifica por página el número solicitado, tamaño, offset, flags y cantidad
   de `content` contra los metadatos recibidos;
4. confirma que `totalPages` y `totalElements` no cambian durante el recorrido,
   que el número acumulado de sumarios coincide con el total y que los
   `numeroConvocatoria` son únicos;
5. obtiene y procesa el detalle de cada sumario, sin dejar errores de transporte,
   contrato o territorialidad sin resolver;
6. compara al final el total observado con una nueva lectura de control del
   inicio del scope; cualquier discrepancia invalida la completitud y exige
   repetir ese scope completo.

La API advierte que los datos pueden insertarse, corregirse, modificarse o
eliminarse tras la extracción. No publica token/snapshot de lectura ni garantiza
aislamiento entre páginas. Un total estable, orden descendente por
`fechaRecepcion` y cero duplicados detectados reducen riesgo, pero no prueban
que no se haya desplazado una fila concurrentemente. Además, los empates de
`fechaRecepcion` observados no tienen segundo criterio documentado. `order`
acepta `numeroConvocatoria`, pero su estabilidad como clave única de ordenación
no ha sido validada; debe probarse antes de usarla para completar particiones.
Si hay deriva, duplicados, cambios de total o error en cualquier detalle, el
resultado es parcial/fallido y no permite reconciliar ausencias.

## Backfill inicial

El sondeo actual sugiere un universo provincial de orden 10.410 convocatorias.
Con el ejemplo `pageSize=50` serían aproximadamente 209 páginas de búsqueda,
además de hasta 10.410 llamadas de detalle; no se ha medido el rendimiento ni
la cuota. No debe resolverse con un único run sin límites.

Propuesta de backfill controlado:

- acordar explícitamente la fecha inicial de cobertura; no afirmar backfill
  histórico total si sólo se eligió una fecha reciente;
- confirmar primero la semántica oficial de los filtros temporales;
- dividir el intervalo total en ventanas cerradas contiguas (preferiblemente
  meses; subdividir una ventana si rebasa presupuesto);
- completar una ventana entera en un run acotado antes de marcarla terminada;
- registrar el intervalo exacto en `requested_scope` del Manifest. Cada ventana
  completada es idempotentemente reejecutable mediante los Stores canónicos;
- ante interrupción, repetir desde la página cero de esa misma ventana: no
  continuar confiando en un offset guardado, porque el conjunto puede cambiar;
- avanzar a la siguiente ventana sólo tras un Manifest exitoso y la validación
  de todos sus Records/Events.

Mientras la semántica temporal siga sin confirmación oficial, las ventanas se
ejecutan bajo `fecha-recepcion-provisional-v1` y su `requested_scope` describe
exactamente los parámetros usados. Un scope completo sólo acredita la
enumeración estable del conjunto que devolvió esa consulta; no acredita por sí
solo que la fecha limite represente oficialmente fecha de recepción ni que se
hayan cubierto todas las correcciones retrospectivas.

## Incremental diario y cambios retrospectivos

Bajo la política source-specific versionada vigente, consultar una ventana que
empiece en el último límite **completado** menos un solape operativo y termine
en un corte fijo del run. Repetir el solape hace idempotentes las convocatorias
tardías dentro de él; el tamaño del solape es una política InfoCs que debe
ajustarse a la demora observada, no una garantía de BDNS.

No hay cursor ni filtro documentado por fecha de última modificación del
registro. Por tanto, una convocatoria antigua corregida fuera del solape puede
no aparecer en el incremental. Para detectar actualizaciones históricas se
requiere revalidar detalles ya conocidos en barridos periódicos completos o
disponer de una señal oficial de modificación futura. No existe garantía de
“cero pérdida de cambios” con sólo un watermark temporal finito; esa limitación
debe permanecer explícita en cobertura y Health.

Un marcador de fecha sólo avanza tras completar íntegramente el scope y
persistir sus Records/Events autorizados. `partial`, fallo, deriva territorial
o cualquier detalle no recuperado dejan el límite anterior intacto. Las
convocatorias nuevas/revisadas encontradas antes de un fallo pueden conservarse
si superaron todas las barreras y sus Events; el Manifest registra el run como
parcial/fallido y no habilita reconciliación de ausencias.

## Semántica de estado y ausencia

Resultados recomendados para el runner source-specific:

- `complete_success`: se agotaron y validaron todas las páginas y detalles del
  scope declarado. Si el scope tenía cero resultados y `totalElements=0`, el
  diagnóstico puede ser `no_results`, con Manifest v1 `success` y métricas
  cero; no usar `no_publication`, cuyo significado actual es más específico.
- `partial_success`: el presupuesto operativo se agotó o una parte del scope
  quedó pendiente. Manifest v1 `partial`, resumen seguro y ningún avance del
  watermark; el límite alcanzado no se transforma en `complete_success`.
- `source_failure`: error HTTP, timeout, MIME/JSON/contrato inválido o fallo
  antes de disponer de resultado utilizable; Manifest `failed`.
- `territorial_contract_drift`: filtro regional devuelve detalles que la
  política vigente no puede resolver; no relajar el matcher ni declarar
  completitud.

Un `metadata HOLD`, Privacy quarantine/reject o `no_results` no significa que
la fuente esté caída. En particular, no generar `missing_from_source`,
withdrawal ni reaparición desde una ventana incremental o un run parcial. Esta
fase no habilita procesamiento de ausencias aunque una partición se haya
enumerado completa.

## Record, Event y límites por run

Para cualquier `create` o `update`, `EventStore` es obligatorio en el runner
productivo. La ausencia de EventStore es un fallo de preflight antes de
`RecordStore`; no hay modo productivo `event_store=None` ni `DEFERRED`.
`no_change` no genera Event. Mantener privacidad, Source Eligibility, Metadata
Publication, atribución IGAE y preflight de Record/Event antes de escribir.

Propuesta de arranque conservadora, revisable con métricas operativas:

- una sola petición HTTP cada vez, sin retry automático ni documentos;
- solicitar inicialmente `pageSize=50`, que es el ejemplo oficial, sin afirmar
  que sea máximo; revisar coherencia del tamaño devuelto;
- máximo inicial de 250 detalles y 5 páginas de datos por run (con `pageSize=50`);
  la lectura de control final es una request adicional, no una sexta página de
  datos; presupuesto de 600 segundos;
- adaptar las ventanas para que normalmente quepan dentro del presupuesto;
  cualquier límite alcanzado antes de completar una ventana termina en
  `partial_success` y deja el checkpoint intacto;
- ajustar esos valores sólo después de observar latencia, cuotas/respuestas y
  volumen real en operación; no confundirlos con límites SNPSAP.

Los 250 detalles/600 segundos son una salvaguarda inicial de InfoCs, no un número
publicado por la API. El presupuesto se comprueba entre requests y tras la
lectura final; una request síncrona ya iniciada no se interrumpe y puede
terminar después del plazo, pero el run se marca parcial. La muestra de
septiembre (62 filas en 29 días) cabe bajo
ese presupuesto en términos de sumarios, aunque el tiempo de sus 62 detalles
no se ha medido.

## RunManifest v1 y SourceHealth

El esquema existente puede representar `source_id=bdns`, UTC, versión software,
scope, métricas agregadas y `success`/`partial`/`failed`; no hace falta cambiarlo
para v1:

- usar `collection_mode=snapshot` para una ventana/scope finito completamente
  enumerado; no llamar snapshot atómico de toda la BDNS;
- codificar región y límites temporales en `requested_scope.value` sin IDs de
  convocatoria ni contenido;
- `seen` = sumarios; `included` = convocatorias territorialmente resueltas e
  incluidas; `excluded` = exclusiones terminales resueltas; `normalized` y
  `finalized` cubren las incluidas procesadas;
- mapear Privacy a los tres contadores existentes. Sólo tras Privacy ALLOW,
  `PUBLISHABLE_METADATA` puede contarse como `publication_approved` en el
  sentido agregado de “pasó la política de publicación de esa fuente”; no
  representa manual review BDNS. HOLD y reject ocupan sus contadores
  homónimos. `created`/`updated`/`unchanged` deben sumar las aprobadas. La
  atribución no forma parte del Record ni del hash.
- para `partial`, v1 exige `error_summary` seguro y `errors >= 1`; usar un
  código acotado como `run_budget_exhausted` para interrupción de cobertura,
  sin clasificarlo como caída del servidor. `errors` contará esta terminación
  incompleta a efectos del contrato, no sólo errores HTTP.
- `no_results` de un scope completo se registra como `success` con métricas
  cero; no confundirlo con `no_publication` ni con un `snapshot` vacío de toda
  la fuente.

Los contadores v1 no guardan páginas esperadas/recorridas, totales observados,
solape, watermark ni motivo detallado de `publication_hold`. No es blocker
para un v1 seguro si cada Manifest representa un scope finito y el estado
específico del run se conserva en el resultado operacional seguro; sí limita
la auditoría posterior de cobertura y la automatización. No añadir campos ni
schema en esta fase.

El runner deriva `SourceHealth` después de escribir el Manifest, reutilizando
la regla Core: éxito (incluido `no_results` como
`success`) → `healthy`; `partial` → `degraded`; uno/dos `failed` consecutivos
→ `degraded`; tres o más → `failing`; sin historial → `unknown`. Es salud del
proceso de colección/cobertura, no disponibilidad de BDNS ni indicador de que
hayan llegado registros nuevos. Un run `success`/`no_results` rompe la racha de
fallos; `partial` se marca `degraded`, pero no se cuenta como fallo
consecutivo. `partial` por presupuesto indica cobertura pendiente, no que
SNPSAP esté técnicamente caído. El resultado se escribe en
`data/health/bdns.json` y reutiliza el schema Core existente.

## Workflow y carrera con `main`

La Action manual `workflow_dispatch` está implementada por OPS-D; no hay
schedule. Cualquier automatización periódica queda diferida. El contrato de
inputs, allowlist de publicación y pasos de carrera se mantiene en
[AUTOMATION_CONTRACT.md](AUTOMATION_CONTRACT.md). Las reglas operativas son:

1. una ventana explícita mediante `workflow_dispatch`; cualquier schedule
   futuro requerirá aprobación y serialización;
2. checkout, Python fijado según el repo e instalación reproducible;
3. ejecutar runner con RecordStore, EventStore, ManifestStore y Health;
4. validar Records, Events, Manifest, Health, atribución y paths antes del
   staging; nunca persistir contenido raw ni documentos;
5. stagear exclusivamente artefactos canónicos BDNS y derivados permitidos;
6. escribir Manifest/Health tras procesar, incluso ante fallo observable, y
   propagar estado no-cero al final después de la publicación segura;
7. permitir `create/update` sólo con Event preflight y EventStore;
8. un run parcial puede publicar Records/Events válidos ya observados, pero no
   confirma cobertura ni avanza el checkpoint.

Registrar SHA base antes de llamar la API. Antes del commit, hacer fetch de
`origin/main` y revisar el diff remoto exacto. Si sólo avanzó con commits
compatibles `data(boe)`, comprobar que no hay paths BDNS ni conflictos,
reaplicar/rebasar el cambio y revalidar los artefactos combinados; repetir el
push normal. Cualquier cambio de código/config/schema/workflow, cambio BDNS
concurrente o conflicto detiene la publicación para intervención. Nunca merge
opaco ni force push; limitar a un intento de rebase y fallar cerrado si la
carrera se repite.

La Action manual captura exit code y JSON estructurado del runner, valida
y publicará los artefactos canónicos válidos —también ante un run parcial— antes
de propagar al final el resultado no-completo. No decidirá el estado leyendo o
parseando texto humano de consola. El allowlist exacto de staging vive en
[RUNNER_CONTRACT.md](RUNNER_CONTRACT.md).

## Interfaz del runner

El módulo ejecutable es `python -m infocs.fetch.bdns.runner`. Requiere modo y
fecha final explícitos. `discovery` y `complete_scope` requieren también
`--from-date`; `incremental_update` usa `--initial-from-date` sólo si aún no
existe un Manifest incremental exitoso, y en ejecuciones posteriores obtiene
el último límite completado y aplica el solape indicado. El scope y la versión
provisional del filtro temporal quedan en `requested_scope` del Manifest.

Los topes se pueden reducir por argumentos, nunca elevar por encima de cinco
páginas, 250 detalles y diez minutos. La página de control final se añade a
esas cinco páginas máximas. El EventStore se configura siempre y el runner
escribe Manifest y Health derivados. La salida CLI es JSON estructurado y los
códigos de salida distinguen resultado completo, parcial y fallo; esta interfaz
no habilita workflow ni schedule por sí sola.

## Validaciones y límites que debe respetar el runner

1. Mantener explícito y versionado que `fechaDesde`/`fechaHasta` se usan como
   proxy provisional de `fechaRecepcion`; la muestra live no basta para
   elevarlo a garantía documental.
2. Validar el orden por una clave única o aceptar que no hay garantía de
   desempate/snapshot durante la paginación.
3. Fijar la fecha inicial del backfill y política de barridos de detalles
   históricos para detectar modificaciones retrospectivas.
4. Medir latencia/carga y revisar límites operativos iniciales antes de un
   schedule.

La semántica de `fechaDesde`/`fechaHasta` y la ausencia de snapshot/desempate
siguen siendo incertidumbres explícitas. El runner deberá tratar la semántica
temporal como una política source-specific versionada y no elevar la evidencia
live a garantía documental. Para declarar completo un scope, aplicará las
comprobaciones de totales estables, unicidad, acumulado esperado y lectura de
control final definidas arriba; cualquier deriva será parcial o fallo.

## Decisión operativa v1 aceptada

InfoCs BDNS v1 no promete detección inmediata ni exhaustiva de todas las
modificaciones retrospectivas. La cobertura operativa combina ventanas
incrementales solapadas, backfills por scopes cerrados y revalidaciones
periódicas de registros conocidos.

Esto no es un workaround temporal: es el contrato operativo v1 mientras
SNPSAP no exponga una señal de última modificación o cursor equivalente. Esta
limitación no impide automatizar un runner que declare con precisión el scope,
la cobertura y los resultados parciales, y que mantenga intacto el checkpoint
ante partial/failure.
