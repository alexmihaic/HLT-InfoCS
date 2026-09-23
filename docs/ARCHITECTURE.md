# Arquitectura de InfoCs

## Propósito y límites

InfoCs es un índice público, reproducible y políticamente neutral de actividad pública de Castelló de la Plana y la provincia de Castellón. Organiza información procedente de fuentes oficiales, conserva su procedencia y permite detectar cambios. No es un espejo universal de la Administración, un sistema de análisis político, un archivo masivo de documentos ni un servicio con backend permanente.

Los hechos oficiales, las transformaciones de InfoCs y los cálculos de InfoCs deben mostrarse como capas diferenciadas. Toda clasificación territorial o temática producida por InfoCs debe conservar el criterio que la motivó.

## Flujo conceptual

```text
Fuentes oficiales
  -> Collectors independientes
  -> Control de entrada
  -> Normalización
  -> Identidad
  -> Finalización canónica (validación, identidad y hash)
  -> Deduplicación por fuente
  -> Detección de cambios
  -> Privacidad y reutilización
  -> Validación
  -> Records / Events / Manifests / Health
  -> Git
  -> Build estático
  -> GitHub Pages
```

### Fuentes oficiales y collectors

Cada fuente se incorpora mediante un collector independiente. Se elige el acceso más fiable disponible, en este orden: API oficial, datos JSON/XML/CSV, feed RSS/Atom, descarga estructurada, HTML y PDF. Una fuente estructurada no se degrada a scraping sin una decisión documentada.

El contrato conceptual de un collector separa descubrimiento, recuperación, interpretación, normalización y comprobación de salud. Añadir una fuente no debe cambiar el núcleo de identidad, deduplicación, histórico, exportación ni build.

### Control de entrada

Antes de interpretar una respuesta se comprueban dominio permitido, redirecciones, timeouts, tamaño, MIME, firmas binarias cuando proceda, límites de descompresión y hash. Las respuestas administrativas son contenido no confiable desde el punto de vista informático: no se ejecutan, no se importan y no se interpolan en comandos.

### Normalización

El núcleo común de un record recoge versión de esquema, identidad InfoCs, fuente, organismo, nivel administrativo, categoría, título, fechas, URL oficial, hash de contenido y estado. Los bloques opcionales cubren expedientes, importes decimales exactos, CPV, adjudicatarios, documentos, relaciones y criterios territoriales.

Los importes mantienen semántica explícita: una licitación, un presupuesto base, un valor estimado y una adjudicación no son intercambiables. El contrato v1 está definido en `docs/DATA_MODEL.md`, implementado en `src/infocs/models.py` y publicado de forma portable en JSON Schema. La identidad y el hash se definen en `docs/IDENTITY_AND_CHANGE_MODEL.md`; los Events persistibles, en `docs/EVENT_MODEL.md`. El collector entrega un `RecordCandidate` activo, sin ID interno ni hash; `finalize_record()` es el único punto común que lo convierte en un `Record` persistible. Los estados de ausencia, retirada o cuarentena se crean únicamente en procesos internos de InfoCs. No escribe datos.

### Identidad, deduplicación y cambios

La identidad prioriza identificador oficial estable, después combinación de expediente, fuente y organismo, URL canónica y, como último recurso, fingerprint compuesto. El `record_id` identifica el hecho; `content_hash` representa su estado normalizado; `document_sha256` y `raw_sha256` representan ficheros o respuestas concretas.

Un mismo hecho publicado por dos fuentes conserva ambos records; una relación futura como `same_event_as` no los fusionará ni cambiará su hash de contenido. `content_hash` representa solo el contenido administrativo observado, no el estado, la categoría, las etiquetas o los criterios territoriales calculados por InfoCs. La reconciliación mantiene transiciones internas de observación; el contrato público de Events v1 admite solo `create` y `update`. BOE es un feed incremental y nunca genera missing por ausencia entre sumarios diarios.

### Privacidad y reutilización

La zona temporal de cada ejecución precede al repositorio público. Antes de publicar se aplican detección preventiva, minimización, exclusión o cuarentena de posibles datos personales. Un resultado en cuarentena puede conservar metadatos y URL oficial, pero no texto completo público.

El `PrivacyGate` v1 es obligatorio entre `Record` y `RecordStore`: clasifica
cada record como `allow`, `quarantine` o `reject`. El store vuelve a comprobar
la decisión, de modo que un collector no puede publicar por olvidar una llamada
al gate. Un fallo del motor o de su configuración aborta el batch antes de
nuevas escrituras; una detección sensible sólo aísla el record afectado.

`allow` no es aprobación humana. Antes de la primera publicación BOE, una capa
separada de `Publication Review` resuelve `approved`, `hold` o `rejected` a
partir de una lista versionada de `official_id`. La ausencia de entrada es
`hold` (fail closed). El orden de publicación es
`finalize -> Privacy Gate -> Publication Review -> preflight de lote ->
RecordStore`; una aprobación nunca omite privacidad. Esta decisión no modifica
`Record.status`, procedencia ni `content_hash`. El primer lote controlado no
persiste eventos y no tiene rollback multiarchivo ante un fallo de I/O, aunque
cada archivo individual es atómico.

La política es individual por fuente: metadatos y enlaces por defecto; documentos, texto completo o capturas solo si su política de reutilización lo permite expresamente. `archive/` existe para copias permitidas y debe permanecer prácticamente vacío mientras no haya políticas aprobadas.

### Validación

La entrada normalizada debe pasar el schema de `RecordCandidate` y reglas semánticas antes de llegar a datos canónicos. El finalizador asigna identidad y `technical.content_hash` y valida el resultado contra el schema más estricto de `Record`; el Privacy Gate decide antes de cualquier escritura; la reconciliación requiere records anteriores con hash coherente. Los errores graves del conjunto impedirán publicar ese conjunto; los errores aislados no destruirán datos válidos de otras fuentes.

## Datos versionados e histórico

Los formatos canónicos serán JSON/JSONL textuales y versionables. La estructura prevista contiene:

- `records/`: estado actual por fuente.
- `events/`: Events canónicos `create` y `update`, vinculados al Record mediante `record_id`.
- `manifests/`: historial append-only de ejecuciones concretas, un JSON por run.
- `health/`: proyección regenerable derivada de los manifests; no es otra historia.
- `review/`: cola BOE minimizada y derivada de IDs con privacidad permitida y revisión humana pendiente; no es dataset canónico.
- `exports/`: artefactos generados para consumo abierto.

Git aporta historial público y reproducibilidad, pero no una certificación jurídica inmutable. Run Manifest v1 no implementa hash chain: orden y encadenamiento requieren una decisión explícita sobre ejecuciones concurrentes o tardías, y no sustituyen a un sellado de tiempo independiente.

`RunManifest` identifica una ocurrencia con UUIDv4 y registra alcance, UTC,
estado, métricas cerradas, versiones y un resumen de error seguro. Su store es
append-only e idempotente por `run_id`; no contiene Records/Events. `SourceHealth`
se deriva de estos manifests, con `unknown`, `healthy`, `degraded` o `failing`;
`no_publication` cuenta como éxito operacional. Los contratos e invariantes
están en `docs/RUN_MANIFEST_MODEL.md` y `docs/SOURCE_HEALTH_MODEL.md`.

SQLite o DuckDB podrán generarse localmente para análisis, validación o descargas, pero nunca serán la verdad canónica sin una decisión documentada posterior.

### Semántica de colección y persistencia canónica

Cada fuente debe declarar si una ejecución es un `incremental_feed` o un
`snapshot`. Un feed incremental comunica publicaciones nuevas o revisadas de
un intervalo, no la ausencia de todo lo que no aparece en esa ejecución. BOE
declara `incremental_feed`, por lo que sus sumarios diarios no generan
`missing_from_source` por comparación entre fechas. La reconciliación de
ausencias queda reservada a fuentes con semántica `snapshot` y observación
completa.

El `RecordStore` común mantiene un JSON por record bajo el directorio de la
fuente. El ID externo se codifica como segmento seguro y no se usa el hash de
contenido como nombre de archivo. La escritura valida el `Record`, comprueba
el hash semántico, serializa con `Record.canonical_json()` y newline final,
escribe un temporal en el mismo directorio y ejecuta un reemplazo atómico.
`EventStore` mantiene un JSON por Event, exige el Record asociado y la
configuración de revisión, revalida privacidad/aprobación, schema e identidad,
y lo añade atómicamente sin reemplazar historia. La ingesta preflighta ambos
artefactos y escribe Event seguido de Record para que un fallo del Record sea
reintentable. No existe transacción real multiarchivo: puede quedar un Event
temporalmente sin Record, pero no perderse la transición. No hay backfill del
Record BOE ya persistido. Los estados internos
`missing_from_source` y `reappeared` de reconciliación no son Events públicos
v1.
En 03E/03F los stores se ejercitaron con temporales; 03H autorizó y persistió
un único Record real revisado. 03I no modifica ese dataset ni retrorellena su
Event.

## Automatización y publicación

El workflow BOE admite un dispatch manual de fecha explícita y una ejecución diaria a las 12:17 `Europe/Madrid`. El runner Python resuelve `--today` con `zoneinfo`; el workflow no calcula fechas ni reconstruye el pipeline. Mantiene Privacy Gate → Publication Review → Event → Record, actualiza la cola minimizada `data/review/boe/pending.json` sólo para IDs con `allow + hold`, escribe Run Manifest y deriva después `data/health/boe.json`. Una cuarentena nunca entra en la cola. Un fallo de fuente puede publicar un manifest `failed` y Health actualizado antes de propagar un exit code fallido a Actions. La acción sólo permite JSON bajo `data/records/`, `data/events/`, `data/manifests/`, `data/health/` y `data/review/`; si `origin/main` avanzó desde el inicio, no publica. Manual y schedule comparten grupo de concurrencia y no se cancelan entre sí.

El portal futuro será una construcción Astro estática, con búsqueda e índices precalculados, sin cuentas, cookies de analítica, base de datos remota ni servidor de búsqueda. GitHub Pages será el destino de publicación previsto. La configuración de dominio y despliegue queda fuera de este bootstrap.

## Restricciones operativas

- Coste recurrente adicional objetivo: 0 EUR/mes mediante repositorio público, runners estándar y Pages.
- No usar PDFs ni artefactos de Actions como almacén masivo.
- No afirmar conclusiones jurídicas o políticas a partir de clasificaciones automáticas.
- Toda desviación de esta arquitectura requiere una decisión registrada en `docs/DECISIONS.md`.
