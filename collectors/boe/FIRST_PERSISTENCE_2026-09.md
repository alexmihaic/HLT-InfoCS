# Primera persistencia BOE controlada — 2026-09-23

## Alcance

Se consultaron exclusivamente los sumarios diarios de 2026-09-18,
2026-09-19 y 2026-09-22 mediante el endpoint OpenData auditado. El lote es
incremental: no se dedujeron ausencias entre fechas. No se descargaron XML,
HTML ni PDF de ítems y no se persistieron Events, respuestas raw, quarantine,
manifests ni health.

La decisión humana de publicación es independiente de Privacy Gate. La
configuración versionada es `config/publication-review/boe-initial.json`;
ningún título ni payload BOE se duplica en este informe.

## Controlled preview y revisión

La preparación leyó 564 publicaciones; 7 tuvieron coincidencia territorial
y 557 quedaron excluidas por no coincidencia. Se validaron todas las
coincidencias incluidas antes de escribir:

| Fecha | official_id | Privacidad | Razón territorial | Revisión de publicación |
| --- | --- | --- | --- | --- |
| 2026-09-18 | `BOE-A-2026-19433` | allow | `province_exact` | hold — `personal_content_review` |
| 2026-09-18 | `BOE-A-2026-19457` | allow | `municipality_exact`, `province_exact` | approved — `reviewed_safe` |
| 2026-09-19 | `BOE-B-2026-30223` | allow | `municipality_exact` | hold — `personal_content_review` |
| 2026-09-19 | `BOE-B-2026-30232` | allow | `municipality_exact` | hold — `personal_content_review` |
| 2026-09-19 | `BOE-B-2026-30240` | allow | `municipality_exact` | hold — `personal_content_review` |
| 2026-09-22 | `BOE-B-2026-30520` | allow | `municipality_exact` | hold — `personal_content_review` |
| 2026-09-22 | `BOE-B-2026-30592` | quarantine (`spanish_personal_identifier`, `title`) | coincidencia no publicada | rejected — `privacy_quarantine` |

La aprobación única corresponde a una convocatoria de empleo local cuyo
sumario y coincidencia municipal se revisaron. Los cuatro anuncios de la
Sección B quedan en hold porque su contenido documental no se revisó; no se
descargaron para esta fase. El registro de coincidencia provincial con
contenido personal señalado en 03G permanece en hold. Una coincidencia
provincial, por sí sola, no obtuvo aprobación.

El preview y la configuración coincidieron exactamente: 1 approved, 5 hold y
1 rejected. Por tanto, se previó una escritura. La cuarentena no puede ser
revocada por una decisión humana.

## Persistencia y validación

Se creó un único Record canónico:

```text
data/records/boe/r-infocs%3Aboe%3Aboe-a-2026-19457-9ef9a385857862bd.json
```

El Record se volvió a cargar desde `RecordStore` y se comprobó: schema v1
válido, `source.id = boe`, `source.official_id` esperado, estrategia de
identidad `official_id`, hash presente, `status = active` y Privacy Gate
`allow`. La revisión de publicación queda únicamente en la configuración y no
se incorpora al Record ni a su `content_hash`.

Se reprocesaron las mismas tres fechas. El resultado del ID aprobado fue
`no_change`: mismo `record_id`, mismo `content_hash` y un solo archivo, sin
nuevas escrituras. La repetición no creó Events.

## Peticiones y límites

Se realizaron cuatro tandas de las tres consultas permitidas: preview inicial,
preflight inmediatamente anterior a la primera escritura y dos comprobaciones
de rerun. Total: 12 peticiones `GET`, cuatro por cada fecha; todas al patrón
`/datosabiertos/api/boe/sumario/{fecha}`. La comprobación adicional se hizo
para verificar la idempotencia; no produjo una segunda escritura. No hubo
reintentos automáticos ni peticiones a URLs documentales.

Los archivos del store son atómicos individualmente, pero no existe rollback
multiarchivo ante un error de I/O después de comenzar un lote. En esta
ejecución sólo hubo un Record aprobado. La revisión humana es puntual y no
autoriza nuevas publicaciones ni automatización. Privacy Gate v1 no garantiza
anonimización completa.

`data/events/` permanece vacío salvo `.gitkeep`. La persistencia no implica
commit ni push; los datos quedan pendientes de revisión humana del diff antes
de incorporarlos al repositorio público.
