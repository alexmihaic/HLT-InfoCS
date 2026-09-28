# InfoCs Component Library v1

Biblioteca aprobada para la interfaz pública. 09C y 09D implementan las piezas
necesarias para Records/Events reales y las fuentes editoriales conocidas.

## Componentes de esta slice

| Componente | Uso | Datos admitidos |
| --- | --- | --- |
| `Wordmark` | Identidad textual InfoCs | Texto Info + Cs azul; sin isotipo nuevo |
| `Header` / `Footer` | Shell común y navegación disponible | Rutas existentes, explicación breve |
| `ThemeToggle` | Preferencia dark/light | Estado local de presentación |
| `SourceBadge` | Procedencia | Label editorial de fuente |
| `CategoryBadge` | Tipo de publicación | Label de presentation layer |
| `StatusBadge` | Estado editorial de fuente | Activa / Publicación pendiente |
| `RecordCard` / `RecordMeta` | Lista de publicaciones | Record view model real |
| `DateValue` | Fecha con semántica | «Publicado» o «Detectado por InfoCs» |
| `SourceLink` | Salida a la fuente | URL oficial canónica |
| `OfficialData` | Bloque de datos oficiales | Sólo campos canónicos presentes |
| `InfoCsDerived` | Normalización/procedencia | Geografía/categoría ya canónicas |
| `TechnicalDetails` | Detalle progresivo | ID/hash/timestamps técnicos disponibles |
| `ChangeTimeline` / `ChangeEvent` | Historial observado | Events existentes; sin valores before/after inventados |
| `ChangeRecordEntry` | `/cambios/` y actividad de fuente | Event resuelto a su Record; tipo, observación y enlace |
| `MethodologySection` | `/metodologia/` | Copy público derivado de políticas aprobadas |
| `EmptyState` | Ausencia explícita | Mensaje contextual, sin datos de relleno |

Las piezas de búsqueda, filtros, charts, paneles de salud y paginación se
mantienen fuera de esta slice hasta que existan datos y fases que los habiliten.

## Reglas de composición

- Los componentes reciben labels y semántica de `site/src/lib/presentation/`.
- Ausencia significa omitir o explicar que no hay historial; nunca sustituir
  por un nombre, importe, nivel o estado ficticio.
- Acciones de navegación y enlaces son HTML nativo; no requieren JavaScript.
- Badges combinan texto, forma y color; el color no comunica por sí solo.
- Los detalles técnicos usan `<details>` y son secundarios a la lectura.
