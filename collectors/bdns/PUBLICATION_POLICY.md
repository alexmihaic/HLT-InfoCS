# BDNS — política de publicación de metadata v1

**Estado:** decisión source-specific implementada; la primera persistencia controlada queda limitada al alcance descrito en [INGESTION_POLICY.md](INGESTION_POLICY.md).

## Orden de decisiones

`Privacy Gate` → `Source Publication Eligibility` → `BDNS Metadata Publication Policy`.

El llamador ejecuta Privacy Gate sobre el `Record` finalizado y entrega esa decisión a `evaluate_bdns_publication()`. Una decisión `QUARANTINE` o `REJECT` se conserva y detiene el flujo; no produce decisión de elegibilidad ni de metadata. Con `ALLOW`, la política de fuente BDNS reutiliza `source_eligible()`. Esto sólo permite evaluar el Record concreto: no lo aprueba automáticamente.

La política BDNS produce `PUBLISHABLE_METADATA` o `HOLD`. `HOLD` usa únicamente `metadata_scope_not_publishable`; no es una decisión de privacidad ni genera una tarea de Review Queue. No se llama a `review_publication()` ni se carga `PublicationReviewConfig`: esa revisión manual sigue siendo el contrato BOE.

## Alcance publicable v1

Sólo metadata de una convocatoria BDNS normalizada por la versión aprobada y territorialmente incluida mediante la etiqueta oficial completa `ES522 - Castellón / Castelló` (catálogo BDNS id 56; no INE). Se permite el conjunto Core actual de:

- Código BDNS como `source.official_id` y `grant.call_id`;
- título oficial, sin inspección semántica en esta política;
- autoridad observada si está disponible, sin inventar nivel administrativo;
- provincia `Castellón/Castelló`, con su match territorial oficial;
- fecha oficial permitida por la política de normalización, timestamps de observación y `source_url` oficial de detalle;
- categoría `grants.call` y procedencia técnica/territorial de la normalización.

Para resultar `PUBLISHABLE_METADATA`, además se exige Privacy `ALLOW`, Source Eligibility `ELIGIBLE`, ausencia de concesión/beneficiario, `resolution_id`, descripción/fulltext, documentos/copias, datos financieros fuera de alcance, tags o relations no previstos, y una coincidencia territorial oficial canónica. Una forma distinta produce `HOLD / metadata_scope_not_publishable`, sin reescribir el Record.

Quedan fuera: concesiones individuales, beneficiarios, identificadores personales, PDFs y otros documentos, fulltext y cualquier copia local. La publicación real aún requerirá el flujo seguro de persistencia y el cumplimiento de las condiciones de reutilización.

## Atribución y reutilización

La atribución exigida no se almacena dentro de `Record`, `RecordCandidate`, identidad, `content_hash` ni diff. La superficie durable y visible junto al dataset es [`data/records/bdns/README.md`](../../data/records/bdns/README.md), que debe acompañar cualquier exportación del conjunto y contiene exactamente:

> Origen de los datos: Intervención General de la Administración del Estado

También debe preservar, cuando conste, la fecha de actualización; no desnaturalizar el sentido; indicar disociación y responsable cuando se realice; y no insinuar patrocinio o apoyo de IGAE. El Privacy Gate seguirá siendo obligatorio aunque la fuente sea pública y reutilizable bajo condiciones.

## Límites operativos

La evaluación de publicación es pura/en memoria: no llama al transporte, Privacy Gate, Publication Review, Stores, Review Queue, ManifestStore ni Health. La política no participa en identidad, `content_hash` ni diff administrativo. La escritura sólo puede hacerse a través del orquestador controlado y tras verificar nuevamente los gates y la superficie de atribución.
