# Identidad y cambios v1

## Identidad y finalización

`record_id` identifica un registro conceptual dentro de una fuente; no es su hash de contenido. `identify()` prioriza `official_id`, `case_number` (expediente + fuente + organismo), `canonical_url` y `composite_fingerprint`. El ID interno tiene namespace de fuente (`infocs:<source>:<token>-<digest>`); el identificador oficial original no se modifica. El digest evita colisiones causadas por la normalización de caracteres. El fingerprint combina atributos relativamente estables y es un último recurso: un cambio de título puede cambiar la identidad si no hay identificador mejor. No hay fuzzy matching ni fusión entre fuentes.

La URL canónica normaliza esquema y host, elimina fragmentos y slash final, y elimina únicamente `utm_*`, `gclid` y `fbclid`. No sigue redirects, no reordena la query y no elimina otros parámetros.

Todo candidato normalizado debe pasar por `infocs.finalize.finalize_record()` antes de guardarse o reconciliarse. El collector entrega un `RecordCandidate`, válido contra su schema propio y sin `id`, `technical.content_hash` ni `technical.identity_strategy`. La función no muta la entrada: valida el candidato y sus reglas cruzadas, normaliza timestamps internos a UTC e importes con `Decimal`, deduplica/ordena las colecciones sin orden semántico, asigna `id` y `technical.identity_strategy`, calcula `technical.content_hash`, valida de nuevo el `Record` persistible y lo devuelve. La escritura a disco no forma parte de este contrato.

## Frontera de `content_hash`

`content_hash` es el SHA-256 del JSON UTF-8 de `semantic_payload(record)`, con claves ordenadas, separadores compactos y sin NaN. La selección es una lista cerrada de información administrativa observada, no una serialización del record entero. `diff()` compara exactamente la misma proyección; por eso un campo excluido no produce un `update` ni una ruta de cambio.

| Campo o grupo | `included_in_content_hash` | Motivo |
| --- | --- | --- |
| `title`, `description`, `source_url` | yes | Contenido y enlace oficial observado. |
| `dates.published_at`, `dates.event_at` | yes | Fechas oficiales, sin inventar horas. |
| `financial.*.value`, `financial.*.currency` | yes | Conceptos económicos observados; decimal numéricamente canónico. |
| `procurement.expediente`, `procurement.cpv`, `procurement.awardee` | yes | Contenido de contratación comunicado por la fuente. |
| `grant.call_id`, `grant.resolution_id`, `grant.beneficiary` | yes | Contenido de subvención comunicado por la fuente. |
| `documents[*].source_url`, `documents[*].sha256` | yes | Documento oficial enlazado y contenido exacto cuando hay hash. |
| `documents[*].mime`, `archive_status`, `has_local_copy`, `publication_allowed` | no | MIME y política/copia de archivo son metadatos técnicos o de publicación de InfoCs. |
| `status` | no | Ciclo de observación y publicación de InfoCs; no equivale a un estado oficial. |
| `category`, `tags`, `relations` | no | Clasificación o relación derivada por InfoCs. |
| `provenance`, incluidos `territorial_matches`, collector, versión y transformación | no | Procedencia y criterio de inclusión gestionados por InfoCs. |
| `geography`, `administration_level`, `authority`, `source.id`, `source.official_id`, `id`, `schema_version` | no | Identidad, fuente o clasificación normalizada; no una modificación del contenido observado. |
| `dates.detected_at`, `dates.last_checked_at`, `technical.*` | no | Observación y metadatos internos, incluidos los propios hashes. |

`title` y `description` se tratan como representaciones fieles del contenido de la fuente; una reescritura editorial de InfoCs debería modelarse en un campo derivado diferente. La exclusión de `authority.name` y `geography` refleja su clasificación como metadatos normalizados en el contrato actual, no que un cambio oficial de organismo carezca de interés. Si en el futuro una fuente aporta un estado administrativo oficial u otro campo observado, deberá modelarse por separado, añadirse deliberadamente a esta proyección, documentarse y probarse. `status=withdrawn` **no** es prueba por sí mismo de retirada oficial.

## Canonicalización y diferencias

En la vista semántica, `procurement.cpv` y `documents` son conjuntos: se deduplican y ordenan. En el record final, también se normalizan como conjuntos `tags`, `relations`, `provenance.territorial_matches` y `authority.aliases`, aunque estos no participen en el hash. Los objetos JSON se ordenan por clave. El valor de dinero se transforma con `Decimal`: `1000`, `1000.0` y `1000.00` producen `1000`; nunca se usa `float`. Las fechas internas requieren zona horaria y se serializan en UTC; las fechas oficiales conservan precisión de día.

`diff(previous, current)` produce rutas de la proyección semántica, por ejemplo `financial.award_amount.value`. El objeto de diferencia puede contener valores anterior/nuevo en memoria; los eventos persistibles guardan solo rutas y hashes por defecto para no multiplicar datos potencialmente sensibles. Una diferencia de orden en una colección-set o un cambio de metadatos InfoCs produce diff vacío.

La deduplicación intrafuente agrupa por `record_id`. Dos candidatos activos con contenido observado incompatible provocan error explícito; si coinciden semánticamente se elige de forma determinista la comprobación más reciente. Los estados no activos no entran por deduplicación: pertenecen a records finalizados y los gestiona la reconciliación o un flujo interno posterior.

## Transiciones de observación

`reconcile()` recibe el estado anterior finalizado, candidatos activos observados, resultado de la ejecución (`complete_success`, `partial_success` o `failed`), fuente y `checked_at` con zona horaria. Comprueba la coherencia de los hashes anteriores y finaliza los candidatos. Una ejecución fallida no acepta records observados. Los estados `missing_from_source`, `withdrawn` y `quarantine` no pueden llegar desde un collector.

| Antes | Observación | Después | Evento |
| --- | --- | --- | --- |
| Sin record | Encontrado | `active` (según candidato) | `create` |
| `active` | Encontrado, igual contenido semántico | `active` | Ninguno |
| `active` | Encontrado, distinto contenido | `active` | `update` con `changed_fields` |
| `active` | Ausente en `complete_success` | `missing_from_source` | Un `missing_from_source` |
| `missing_from_source` | Sigue ausente en `complete_success` | `missing_from_source` | Ninguno; se actualiza `last_checked_at` |
| `missing_from_source` | Reaparece sin cambios | `active` (según candidato) | Un `reappeared`, sin `changed_fields` |
| `missing_from_source` | Reaparece con cambios | `active` (según candidato) | Un `reappeared` con hashes anterior/nuevo y `changed_fields` |
| Cualquier record ausente | `partial_success` o `failed` | Sin cambio | Ninguno |

`missing_from_source` expresa solo ausencia tras una observación completa, no eliminación. Ningún número de ausencias convierte automáticamente el registro en `withdrawn`; se necesitará evidencia suficiente o estado oficial explícito, mecanismo aún fuera de alcance. `quarantine` es una decisión interna de privacidad y tampoco modifica el hash. Los records de fuentes distintas no se fusionan automáticamente ni se crean relaciones cross-source en este motor.

Una reobservación no borra por sí sola una cuarentena o retirada evidenciada anterior; levantar esos estados requiere un flujo explícito posterior. El motor actual no implementa ese flujo ni la política completa de privacidad.
