# BOE Live Dry Run — 2026-09-23

## Objetivo y límites

Primera comprobación end-to-end con sumarios BOE reales, desde transporte
hasta Privacy Gate. Todas las publicaciones y Records se procesaron en memoria.
No se llamó a `RecordStore`; no se escribieron Records, Events, quarantine,
manifests, health ni respuestas crudas. Tampoco se solicitaron URL HTML, XML o
PDF de ningún ítem.

La consulta se ejecutó el 2026-09-23 a las 08:09 UTC (10:09 Europe/Madrid), con
timestamps internos explícitos iguales para las ejecuciones, un único proceso
por fecha y el User-Agent existente `InfoCs/0.1`.

## Endpoint y peticiones

Se utilizó exclusivamente el endpoint auditado:

```text
GET https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}
Accept: application/json
```

| Orden | Fecha | URL consultada | HTTP | Resultado del transporte |
| ---: | --- | --- | ---: | --- |
| 1 | 2026-09-18 | `/datosabiertos/api/boe/sumario/20260918` | 200 | `complete_success` |
| 2 | 2026-09-19 | `/datosabiertos/api/boe/sumario/20260919` | 200 | `complete_success` |
| 3 | 2026-09-22 | `/datosabiertos/api/boe/sumario/20260922` | 200 | `complete_success` |

Fueron tres peticiones GET en total. No hubo reintentos, redirects ni llamadas
a enlaces documentales u otros servicios.

## Métricas

| Fecha | HTTP / `transport_status` | seen | included | excluded | normalized | finalized | privacy allowed | quarantined | rejected | errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-09-18 | 200 / `complete_success` | 128 | 2 | 126 | 2 | 2 | 2 | 0 | 0 | 0 |
| 2026-09-19 | 200 / `complete_success` | 193 | 3 | 190 | 3 | 3 | 3 | 0 | 0 | 0 |
| 2026-09-22 | 200 / `complete_success` | 243 | 2 | 241 | 2 | 2 | 1 | 1 | 0 | 0 |

En las tres fechas se cumple `seen = included + excluded` e
`included = normalized = finalized`. No hubo ítems sin procesar ni errores de
pipeline.

## Inclusiones territoriales y revisión

La clasificación `expected_match` / `suspicious_match` que sigue es solo una
anotación de auditoría del dry-run; no modifica la política de producción ni
añade puntuaciones. En esta revisión, una coincidencia municipal literal es
`expected_match`; una señal de provincia sin atribución municipal es
`suspicious_match` para revisión humana, aunque sea una coincidencia válida
según la política v1.

Todas las coincidencias observadas usaron el método
`official_variant_casefolded_diacritic_insensitive_boundary`; no hubo alias
técnicos ni fuzzy matching.

| Fecha | `official_id` | Título o vista segura | Autoridad / categoría / publicación | Privacy | Coincidencia observada | Clasificación |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-18 | `BOE-A-2026-19433` | Título omitido: contiene un nombre personal; el gate v1 lo permitió según su regla de no bloquear nombres por sí solos. Pendiente de revisión antes de publicar ese contenido. | MINISTERIO FISCAL / `other` / 2026-09-18 | `allow` | `title`: “Castellón”; provincia `12`, “Castellón/Castelló”, `province_exact` | `suspicious_match` |
| 2026-09-18 | `BOE-A-2026-19457` | Resolución de 11 de septiembre de 2026, del Ayuntamiento de Segorbe (Castellón/Castelló), referente a la convocatoria para proveer una plaza. | ADMINISTRACIÓN LOCAL / `employment` / 2026-09-18 | `allow` | `title`: “Segorbe”, municipio `12104`, “Segorbe”, `municipality_exact`; también “Castellón”, provincia `12`, “Castellón/Castelló”, `province_exact` | Municipio: `expected_match`; provincia: `suspicious_match` |
| 2026-09-19 | `BOE-B-2026-30223` | `SEGORBE` | TRIBUNALES DE INSTANCIA. SECCIÓN CIVIL Y DE INSTRUCCIÓN / `other` / 2026-09-19 | `allow` | `title`: “SEGORBE”, municipio `12104`, “Segorbe”, `municipality_exact` | `expected_match` |
| 2026-09-19 | `BOE-B-2026-30232` | `VINAROS` | TRIBUNALES DE INSTANCIA. SECCIÓN CIVIL Y DE INSTRUCCIÓN / `other` / 2026-09-19 | `allow` | `title`: “VINAROS”, municipio `12138`, “Vinaròs”, `municipality_exact`; coincidencia sin acento | `expected_match` |
| 2026-09-19 | `BOE-B-2026-30240` | `CASTELLON DE LA PLANA` | TRIBUNALES DE INSTANCIA. SECCIÓN CIVIL / `other` / 2026-09-19 | `allow` | `title`: “CASTELLON DE LA PLANA”, municipio `12040`, “Castelló de la Plana/Castellón de la Plana”, `municipality_exact` | `expected_match` |
| 2026-09-22 | `BOE-B-2026-30520` | `CASTELLON DE LA PLANA` | TRIBUNALES DE INSTANCIA. SECCIÓN CIVIL / `other` / 2026-09-22 | `allow` | `title`: “CASTELLON DE LA PLANA”, municipio `12040`, “Castelló de la Plana/Castellón de la Plana”, `municipality_exact` | `expected_match` |
| 2026-09-22 | `BOE-B-2026-30592` | Vista mínima de privacidad; sin título, autoridad ni categoría. | No se publica | `quarantine` (`spanish_personal_identifier`, `title`) | No se publica detalle territorial para esta fila | No clasificado en el informe público |

Las formas completas `Castelló de la Plana` y `Castellón de la Plana` quedan
asociadas al municipio `12040`, también en una entrada sin acentos y en
mayúsculas. La mención aislada “Castellón” produjo únicamente la entidad de
provincia `12`, no el municipio `12040`. La referencia provincial no se
interpreta como aplicabilidad jurídica.

Las dos coincidencias provinciales del 18 se conservan como hechos literales;
el rótulo `suspicious_match` recomienda revisión contextual, no declara un
falso positivo demostrado. El aviso de cese en Fiscalía Provincial llegó como
`other` por el mapping actual; se registra como `classification_observation`
para una fase futura y no se cambia la taxonomía en 03G.

## Categorías y organismos

Entre las inclusiones permitidas se observaron `employment` y `other`. No se
observaron `regulation` ni `procurement` entre las filas permitidas. La fila en
cuarentena no muestra categoría en este informe para respetar la vista mínima
de privacidad.

Los nombres de autoridad observados fueron `MINISTERIO FISCAL`,
`ADMINISTRACIÓN LOCAL` y órganos judiciales de instancia. En todos los Records
finalizados, el normalizador genera `authority.id` con la forma
`boe-department:<department_code>` y asigna `state` tanto a la autoridad como al
Record. El finalizador acepta todos los Records y valida la igualdad de nivel;
no hubo conversión a nivel municipal por una mención a un Ayuntamiento. El
código de departamento no se replica aquí porque el resumen de auditoría no lo
necesita.

El mapping observado se mantiene sin cambios: sección `1` → `regulation`,
`2B` → `employment`, `5A` → `procurement` y resto → `other`.

## Privacidad, identidad y hashes

- Todas las inclusiones tenían `official_id`; cada Record utilizó
  `identity_strategy: official_id`.
- Conteos de identidad oficial: 2, 3 y 2 por fecha; cero fallbacks y cero
  colisiones de `Record.id`.
- La finalización repetida del mismo candidato produjo el mismo
  `content_hash` en cada fecha. Los valores de hash no se publican.
- Privacy Gate: 6 `allow`, 1 `quarantine`, 0 `reject` en total.
- La cuarentena del 22 se informa solo como `BOE-B-2026-30592`, regla
  `spanish_personal_identifier`, campo `title`, decisión `quarantine`. No se
  conserva ni divulga el valor que activó la regla.
- El título del `BOE-A-2026-19433` no se reproduce por incluir un nombre
  personal. El gate lo permitió según la política v1, que no bloquea nombres
  por sí solos; su publicación debe revisarse antes de cualquier persistencia.

## Anomalías, límites y conclusión

No se detectaron fallos de transporte/parser, fallback de identidad,
colisiones, hashes inestables ni errores de finalización. Las coincidencias
provinciales amplias siguen siendo una limitación conocida del matcher y se
señalan para revisión, sin inferir relevancia jurídica. Una detección de
privacidad puso un ítem en cuarentena y no filtró el texto. La regla v1 no
detecta nombres personales por sí solos; el título señalado se omite de este
informe y queda pendiente de revisión específica antes de publicación.

| Clasificación | Observación |
| --- | --- |
| `KNOWN_LIMITATION` | `province_exact` incluye referencias explícitas provinciales pero no prueba relevancia material; se marcó como `suspicious_match` solo para auditoría humana. No se demostró un falso positivo territorial. |
| `KNOWN_LIMITATION` | Un nombre personal en un título oficial no activa Privacy Gate v1 por diseño. El título afectado no se reproduce y requiere revisión antes de publicación. |
| `CATEGORY_LIMITATION` | Un anuncio de cese de una fiscalía provincial quedó en `other`; se registra como `classification_observation`, sin remapeo en 03G. |
| `KNOWN_LIMITATION` | Un ítem activó cuarentena por `spanish_personal_identifier` en `title`; el valor y título no se retienen en el informe público, así que no se califica como falso positivo ni se revisa aquí. |
| Sin hallazgo | No se observaron `TRANSPORT_BUG`, `PARSER_BUG`, `NORMALIZATION_BUG`, `IDENTITY_BUG` ni errores de transporte o privacidad. |

El dry-run no modificó el store: no se instanció ni invocó `RecordStore`, no se
crearon Events, manifests, health ni payloads de quarantine, y no se guardó
ninguna respuesta BOE. Este resultado valida las fechas muestreadas y no
autoriza por sí solo una ejecución automatizada ni la publicación de ítems en
cuarentena o pendientes de revisión.

**Recomendación del dry-run:** `READY_FOR_FIRST_PERSISTENCE`, limitada a
Records permitidos por el gate y tras revisión humana del contenido que el
informe identifica como pendiente. No se realizó persistencia en 03G.
