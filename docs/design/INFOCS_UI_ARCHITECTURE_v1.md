# InfoCs UI Architecture v1

## Navegación aprobada

La arquitectura de producto contempla estas rutas:

- `/` — actividad/publicaciones recientes.
- `/buscar/` — búsqueda y resultados.
- `/registro/[slug]/` — ficha de registro.
- `/cambios/` — cambios observados.
- `/fuentes/` y `/fuentes/[source]/` — índice y detalle de fuente.
- `/estado-fuentes/` — estado operativo de fuentes.
- `/datos/` — acceso a datasets.
- `/metodologia/` — método y alcance.

La implementación pública actual expone `/`, `/registro/[slug]/`, `/fuentes/`,
`/fuentes/[source]/`, `/cambios/`, `/metodologia/` y `404.html`. El encabezado
enlaza a Inicio, Cambios, Fuentes y Metodología. `/buscar/` queda para Phase 10;
`/estado-fuentes/` y `/datos/` siguen pendientes de contratos de operaciones
y exports, respectivamente.

## Superficies

**Inicio:** propósito en una frase, registros cronológicos reales y resumen
de BOE/BDNS/BOP. Sin búsqueda de apariencia funcional, métricas decorativas
ni bloques ficticios.

**Ficha:** regreso, fuente/categoría, título, organismo y fechas disponibles;
separación entre dato oficial y procesado; historial sólo si hay Events;
enlace original y detalles técnicos progresivos.

**Fuentes:** responsable, tipo de acceso, estado editorial, disponibilidad,
enlace oficial y atribución aplicable. BOP figura como publicación pendiente,
no como fuente degradada.

## Adaptación por viewport

Escritorio usa una cuadrícula fluida compatible con 12 columnas. Tablet reduce
columnas y espacios. Móvil apila registros y grupos de datos; no comprime una
tabla de escritorio. Objetivos táctiles ≥44 px y contenido legible desde
320 px.

## Estado operativo vs producto

Los estados de las tarjetas de fuente son editoriales y explícitos. No se
derivan de `SourceHealth`; ese modelo no cubre todas las fuentes.

## Implementación slice

Esta arquitectura aprobada es más amplia que las rutas actuales. Las rutas
descritas arriba se irán integrando en fases posteriores; no se considera
que la slice actual reemplace el sistema completo de producto/UI.
