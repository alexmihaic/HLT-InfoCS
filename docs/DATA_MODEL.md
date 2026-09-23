# Modelo de datos InfoCs v1

## Alcance y contrato

Este documento define el contrato interno con el que un futuro collector entregará un record normalizado. No describe endpoints, formatos administrativos ni reglas de extracción de ninguna fuente real.

El contrato tiene dos representaciones compatibles:

- `src/infocs/models.py`: modelos Python inmutables, carga, serialización y validación de bordes.
- `schemas/record_candidate.schema.json`, `schemas/record.schema.json` y `schemas/source.schema.json`: contratos JSON Schema Draft 2020-12 portables.

La carga desde JSON valida primero el schema y después construye el modelo. Las pruebas usan los mismos fixtures contra el schema y contra los modelos. No se genera un contrato desde el otro: ambos se mantienen como especificación deliberadamente legible y se cubren con pruebas de compatibilidad funcional.

## Candidate y Record final

`RecordCandidate` es la observación normalizada y activa que llega del pipeline de ingestión. Incluye fuente, organismo, contenido, fechas, procedencia y bloques opcionales, con `status: active` como único valor permitido. No contiene `id`, `technical.content_hash` ni `technical.identity_strategy`. Puede incluir únicamente `technical.raw_sha256` o `technical.extraction_method` si ya los conoce el collector. Es válido contra `record_candidate.schema.json`, pero no se persiste.

`Record` es el resultado de `finalize_record(candidate)`. Conserva los campos del candidato y exige `id`, `technical.content_hash` y `technical.identity_strategy`. El schema persistible rechaza candidatos incompletos. Esta frontera evita identificadores provisionales y deja la identidad InfoCs exclusivamente en el core.

## Núcleo obligatorio de un record

Los únicos campos obligatorios para todo tipo de actividad son:

| Campo | Procedencia | Propósito |
| --- | --- | --- |
| `schema_version` | InfoCs | Versión fija del contrato, actualmente `1.0`. |
| `id` | InfoCs | Identidad estable generada por el motor de Fase 02. |
| `source.id` | InfoCs/configuración | Fuente configurada que originó el record. |
| `authority.id`, `authority.name`, `authority.administration_level` | Mixto | ID estable InfoCs, nombre oficial y nivel administrativo. |
| `administration_level` | Normalizado InfoCs | Nivel del hecho: `municipal`, `provincial`, `autonomous` o `state`. |
| `category` | Normalizado InfoCs | Categoría controlada inicial. |
| `title` | Oficial | Título comunicado por la fuente o su representación fiel. |
| `dates.detected_at` | InfoCs | Primera detección, timestamp ISO 8601 con zona horaria. |
| `dates.last_checked_at` | InfoCs | Última comprobación, timestamp ISO 8601 con zona horaria. |
| `source_url` | Oficial | URL de la publicación o recurso oficial. |
| `provenance` | InfoCs | Collector, versión, criterio territorial y transformación. |
| `status` | InfoCs | Estado actual explícito del record. |

`dates.published_at` y `dates.event_at` son fechas oficiales opcionales porque no todas las fuentes las exponen. Son fechas ISO (`YYYY-MM-DD`), mientras que los dos timestamps internos incluyen hora y zona horaria.

## Bloques opcionales

Los bloques solo aparecen cuando la fuente aporta información útil y su uso ha pasado las políticas aplicables:

- `source.official_id`: identificador oficial del ítem dentro de la fuente.
- `description`: descripción oficial o representación no editorial del contenido.
- `financial`: importes con semántica explícita.
- `procurement`: `expediente`, CPV y adjudicatario.
- `grant`: identificadores de convocatoria/resolución y beneficiario.
- `geography`: municipio y provincia normalizados por InfoCs.
- `documents`: enlaces y metadatos de documentos; nunca obliga a guardar una copia.
- `tags`, `relations`: clasificación y relaciones InfoCs, no conclusiones políticas o jurídicas.
- `technical`: hashes ya disponibles y método de extracción; el finalizador del core añade `identity_strategy` y `content_hash` semántico.

## Importe exacto y semántica económica

Los importes van en `financial`, no en un campo genérico `amount`. Los nombres permitidos son `base_budget`, `estimated_value`, `tender_amount`, `award_amount`, `modification_amount` y `grant_amount`.

Cada importe es un objeto con `value` como cadena decimal exacta y `currency` como código ISO 4217. Por ejemplo:

```json
"financial": {
  "tender_amount": {"value": "12000.00", "currency": "EUR"},
  "award_amount": {"value": "9876.54", "currency": "EUR"}
}
```

No se aceptan `float`, notación exponencial ni valores monetarios sin moneda. La diferencia entre importes será un cálculo posterior de InfoCs, no una inferencia del collector.

## Organismos y fuentes

`authority` contiene el ID InfoCs, nombre oficial, aliases futuros opcionales y nivel administrativo. Aún no existe catálogo de organismos reales.

Una definición de fuente independiente se valida con `source.schema.json`. Debe indicar ID, nombre, organismo responsable, URL oficial, tipo de acceso, estado de configuración, hosts permitidos y política de reutilización. La política incorpora si se permiten metadatos, datos transformados, mirroring documental, texto completo y la política por defecto `link_and_hash`. `terms.checked_at` registra la fecha de revisión de condiciones cuando exista.

El estado de una fuente (`active`, `disabled`, `under_review`) es configuración y no debe confundirse con salud operativa. `RunManifest` registra una ocurrencia de ejecución; `SourceHealth` es una proyección regenerable de manifests, no un estado de configuración ni un log. Sus contratos están en `docs/RUN_MANIFEST_MODEL.md` y `docs/SOURCE_HEALTH_MODEL.md`.

## Documentos y privacidad

Un documento tiene `source_url`, `archive_status`, `has_local_copy` y `publication_allowed`; MIME y SHA-256 son opcionales. El valor por defecto es:

```text
enlace oficial + metadatos + hash cuando exista
```

`not_archived` con `has_local_copy: false` es válido. En cambio, `archived` exige copia local y autorización de publicación. Este modelo no crea archivos locales ni consulta condiciones de ninguna fuente.

Antes de persistir un `Record`, el `PrivacyGate` común produce una decisión
`allow`, `quarantine` o `reject`. `quarantine` y `reject` no modifican el
record ni su `content_hash`: simplemente impiden escribir el payload público.
Las razones son técnicas (`rule` y `field`) y no contienen el valor detectado.
La persistencia de datos BOE reales continúa bloqueada; las pruebas usan
directorios temporales.

## Procedencia y territorialidad

`provenance` es obligatorio y contiene `collector`, `collector_version`, `transformed_by_infocs` y una lista, que puede estar vacía, de `territorial_matches`.

Cada coincidencia tiene una razón objetiva: `authority_match`, `municipality_match`, `explicit_text_match`, `official_code_match` u `other_documented`, más un detalle opcional. Nunca se usa un booleano opaco como `relevant_to_castellon`.

## Estados del record

`Record.status` es estado interno de publicación u observación de InfoCs; no es un estado aportado por el collector ni un estado administrativo oficial.

- `active`: la observación normalizada que entra por ingestión y el estado inicial de un Record final.
- `missing_from_source`: no se localizó tras una comprobación completa; no significa eliminación.
- `withdrawn`: hay evidencia suficiente de retirada o un estado oficial explícito.
- `quarantine`: no se publica el contenido sensible pendiente de revisión.

## Categorías iniciales

Los identificadores son minúsculos y usan puntos para subcategorías: por ejemplo, `procurement.award`. El vocabulario inicial es deliberadamente pequeño: `regulation`, `procurement`, `procurement.notice`, `procurement.award`, `grants`, `grants.call`, `grants.resolution`, `budget`, `employment`, `urbanism`, `governing_bodies`, `agreement`, `auction` y `other`.

Ampliar categorías exige actualizar modelo, schema, tests y documentación en la misma revisión.

## Serialización canónica

`Record.canonical_json()` genera JSON con UTF-8, claves ordenadas, separadores estables y sin valores no finitos. El motor de hash usa además una vista semántica que excluye campos volátiles; véase `IDENTITY_AND_CHANGE_MODEL.md`.

Un futuro collector debe producir un `RecordCandidate` normalizado y entregarlo a `finalize_record(candidate)`. Este valida el candidato, normaliza, calcula identidad/hash y devuelve un `Record` nuevo con `id`, `technical.identity_strategy` y `technical.content_hash`; el collector no debe escribir ninguno de esos campos. Todavía no existe persistencia. `source.official_id` y `procurement.expediente` se conservan originales aunque sus tokens internos se normalicen para identidad.

El `status` final (`active`, `missing_from_source`, `withdrawn`, `quarantine`) es estado de observación/publicación de InfoCs, no un estado administrativo oficial. Por ello no entra en `content_hash`, igual que `category`, `tags`, `relations` y `provenance.territorial_matches`. Solo `active` es válido en un `RecordCandidate`; los otros estados los establece y conserva el core. Los campos administrativos observados incluidos en el hash y la matriz completa están en `IDENTITY_AND_CHANGE_MODEL.md`. Una futura representación de estado oficial necesitará un campo separado y una decisión versionada.

## Ejemplo ficticio

```json
{
  "schema_version": "1.0",
  "id": "infocs:fixture:example-001",
  "source": {"id": "fixture_source", "official_id": "FICT-001"},
  "authority": {"id": "fixture_city", "name": "Ayuntamiento Ficticio", "administration_level": "municipal"},
  "administration_level": "municipal",
  "category": "procurement.award",
  "title": "Contrato ficticio de ejemplo",
  "dates": {"published_at": "2026-09-20", "detected_at": "2026-09-21T09:00:00Z", "last_checked_at": "2026-09-21T09:00:00Z"},
  "source_url": "https://source.example.test/contracts/FICT-001",
  "financial": {"award_amount": {"value": "9876.54", "currency": "EUR"}},
  "provenance": {"collector": "fixture_collector", "collector_version": "0.0.0", "territorial_matches": [{"reason": "authority_match", "detail": "fixture_city"}], "transformed_by_infocs": true},
  "status": "active"
}
```

Los fixtures completos están en `tests/fixtures/` y son íntegramente ficticios.

## Events

El contrato persistible de Event v1 está en `schemas/event.schema.json` y su
modelo/store en `src/infocs/events.py`. Sólo se admiten `create` y `update`.
El Event conserva identidad del record/fuente, `official_id` opcional,
`observed_at`, hash actual y, en updates, hash previo y rutas `changed_fields`.
No incorpora el payload del Record ni valores anteriores/nuevos. Las
transiciones de observación de `reconcile()` (`missing_from_source`,
`reappeared`) son eventos internos y no son persistibles mediante EventStore.
Véase `docs/EVENT_MODEL.md` para identidad, append-only y orden de persistencia.

## Ejecuciones y salud de fuentes

`RunManifest` es el historial append-only de cada ejecución: ID de ocurrencia
UUIDv4, fuente, modo de colección, alcance, tiempos UTC, status, métricas y
versiones. `ManifestStore` valida y añade JSON canónico, sin modificar Records
ni Events. `SourceHealth` se calcula a partir de manifests y puede regenerarse;
no se guarda en v1 como estado independiente. BOE declara `incremental_feed`;
la ausencia de un día no es una ausencia de Records. Véanse
`docs/RUN_MANIFEST_MODEL.md` y `docs/SOURCE_HEALTH_MODEL.md`.
