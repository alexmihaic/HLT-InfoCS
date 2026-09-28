# UI gaps — sistema aprobado vs datos vs Astro

| Superficie aprobada | Dato/implementación disponible | Decisión | Clasificación |
| --- | --- | --- | --- |
| Shell dark, tema claro, tipografía, badges, ficha, fuentes | Astro 09A/09B con Records BOE/BDNS | Integrar en esta fase | `IMPLEMENT_NOW` |
| Ejemplos de contratación PCSP en boards | No existe fuente/Record PCSP actual | No reproducir ni inventar ejemplos | `DEFER_DATA_GAP` |
| BOP en portada/fuentes | Source metadata editorial; 0 Records por reuse hold | Mostrar sólo publicación pendiente | `IMPLEMENT_NOW` |
| Valor anterior y actual en evento update | Event v1 no conserva snapshots before/after | No mostrar comparativa | `DEFER_DATA_GAP` |
| No localizado / reaparecido | No son tipos Event v1 actuales | No crear estados ni timeline | `DEFER_DATA_GAP` |
| Estado operativo por fuente | Sólo existe Health BOE; BDNS Health pendiente | No presentar panel agregado ni inferir estado | `DEFER_OPERATIONS` |
| Búsqueda real y filtros | No implementados; fase posterior de búsqueda | Sin control ficticio | `DEFER_PHASE_10` |
| Datasets/export/RSS | No existen contratos de salida actuales | No prometer formatos | `DEFER_PHASE_10` |
| `/cambios/`, `/fuentes/[source]/`, `/metodologia/` y 404 | Canónicos, editoriales y reglas disponibles | Implementados con Records/Events reales y fuentes conocidas | `RESOLVED` |
| `/buscar/` | Búsqueda real no implementada | Phase 10; no mostrar control ficticio | `DEFER_PHASE_10` |
| `/estado-fuentes/` | Observabilidad coherente multi-source incompleta | No inferir salud editorial ni técnica | `DEFER_OPERATIONS` |
| `/datos/` | No existen contratos de datasets/exports | No anunciar formatos aún | `DEFER_PHASE_10` |
| Ruta `/record/[slug]` de la slice 09A/09B | Sin deployment público ni enlaces externos | Alinear a `/registro/[slug]/`, sin ruta duplicada | `IMPLEMENT_NOW` |
| Contenido técnico de onboarding/bootstrap en Home | Ya no describe la experiencia de producto | Sustituir por portada pública | `OBSOLETE` |

No se altera el backend para cubrir estos gaps. No se introducen datos ficticios
en loaders, `data/` ni HTML generado.
