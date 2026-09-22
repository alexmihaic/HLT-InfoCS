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

Los importes mantienen semántica explícita: una licitación, un presupuesto base, un valor estimado y una adjudicación no son intercambiables. El contrato v1 está definido en `docs/DATA_MODEL.md`, implementado en `src/infocs/models.py` y publicado de forma portable en JSON Schema. La identidad, el hash y los eventos se definen en `docs/IDENTITY_AND_CHANGE_MODEL.md`. El collector entrega un `RecordCandidate` activo, sin ID interno ni hash; `finalize_record()` es el único punto común que lo convierte en un `Record` persistible. Los estados de ausencia, retirada o cuarentena se crean únicamente en procesos internos de InfoCs. No escribe datos.

### Identidad, deduplicación y cambios

La identidad prioriza identificador oficial estable, después combinación de expediente, fuente y organismo, URL canónica y, como último recurso, fingerprint compuesto. El `record_id` identifica el hecho; `content_hash` representa su estado normalizado; `document_sha256` y `raw_sha256` representan ficheros o respuestas concretas.

Un mismo hecho publicado por dos fuentes conserva ambos records; una relación futura como `same_event_as` no los fusionará ni cambiará su hash de contenido. `content_hash` representa solo el contenido administrativo observado, no el estado, la categoría, las etiquetas o los criterios territoriales calculados por InfoCs. Un hash distinto para el mismo `record_id` genera `update`, salvo si reaparece desde `missing_from_source`: entonces se genera un solo `reappeared` con campos modificados. Una ausencia solo se registra una vez tras una ejecución completa y nunca se convierte automáticamente en retirada.

### Privacidad y reutilización

La zona temporal de cada ejecución precede al repositorio público. Antes de publicar se aplican detección preventiva, minimización, exclusión o cuarentena de posibles datos personales. Un resultado en cuarentena puede conservar metadatos y URL oficial, pero no texto completo público.

La política es individual por fuente: metadatos y enlaces por defecto; documentos, texto completo o capturas solo si su política de reutilización lo permite expresamente. `archive/` existe para copias permitidas y debe permanecer prácticamente vacío mientras no haya políticas aprobadas.

### Validación

La entrada normalizada debe pasar el schema de `RecordCandidate` y reglas semánticas antes de llegar a datos canónicos. El finalizador asigna identidad y `technical.content_hash` y valida el resultado contra el schema más estricto de `Record`; la reconciliación requiere records anteriores con hash coherente. Los controles completos de privacidad y políticas de fuente siguen pendientes. Los errores graves del conjunto impedirán publicar ese conjunto; los errores aislados no destruirán datos válidos de otras fuentes.

## Datos versionados e histórico

Los formatos canónicos serán JSON/JSONL textuales y versionables. La estructura prevista contiene:

- `records/`: estado actual por fuente.
- `events/`: altas, actualizaciones, reapariciones, ausencias y correcciones detectadas por fecha.
- `manifests/`: resultados de ejecución y hashes, encadenados con el manifiesto anterior.
- `health/`: último intento, último éxito, último cambio, errores consecutivos, estado y métricas por fuente.
- `exports/`: artefactos generados para consumo abierto.

Git aporta historial público y reproducibilidad, pero no una certificación jurídica inmutable. Los manifiestos encadenados y hashes aumentan la detectabilidad de cambios retrospectivos; no sustituyen a un sellado de tiempo independiente.

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
Esta abstracción no crea bases de datos ni persiste eventos, manifests o health.
En BOE 03E se utiliza sólo con temporales de test: la persistencia de datos
administrativos reales permanece bloqueada hasta el privacy gate.

## Automatización y publicación

La automatización futura ejecutará collectors de forma aislada, agregará sus resultados aunque una fuente falle, validará y solo después actualizará los datos válidos. Cada fuente publicará salud diferenciando `last_success` de `last_change_detected`. No se añaden workflows en esta fase.

El portal futuro será una construcción Astro estática, con búsqueda e índices precalculados, sin cuentas, cookies de analítica, base de datos remota ni servidor de búsqueda. GitHub Pages será el destino de publicación previsto. La configuración de dominio y despliegue queda fuera de este bootstrap.

## Restricciones operativas

- Coste recurrente adicional objetivo: 0 EUR/mes mediante repositorio público, runners estándar y Pages.
- No usar PDFs ni artefactos de Actions como almacén masivo.
- No afirmar conclusiones jurídicas o políticas a partir de clasificaciones automáticas.
- Toda desviación de esta arquitectura requiere una decisión registrada en `docs/DECISIONS.md`.
