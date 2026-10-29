# INFOCS · DISCOVERY-01 — entrega para revisión

Fecha: 29 de octubre de 2026. Revisión final autorizada para commit y PR; pendiente de revisión humana antes de merge.

## Auditoría y decisiones

- Base: `origin/main` / `main` en `6d28b1e` (UTILITY-03B-2). Fetch y avance fast-forward de main; rama nueva `feat/discovery-01-organism-filters`. Los archivos históricos sin seguimiento se conservaron.
- Se amplían RecordFilters, RecordList y el predicado de filtros existente; no se crea otra lista ni otro buscador.
- El directorio agrupa por el literal BDNS `authorityHierarchy.nivel2`. Se extrae `authorityName` para compartir exactamente ese criterio. Nombres idénticos se agrupan; variantes, acentos y diferencias literales no se fusionan. No es resolución de identidad jurídica. `nivel3` continúa disponible en las fichas, sin un nuevo filtro.
- `primaryDate` ya establece publicación > recepción BDNS > detección InfoCs. El intervalo usa esa misma fecha, inclusiva, sin inferir plazos de solicitud.
- Pagefind busca texto en fichas y mantiene su controlador e índice. Los filtros se aplican a `/registros/`; no se combinan con una consulta textual Pagefind.

## Funcionalidades

- Administración convocante BDNS con nombres oficiales y opción de ausencia solo si hay registros que carecen del dato. BOE no entra en esa opción.
- Fuente explícita cuando el listado contiene más de una fuente: permite distinguir procedencia con independencia del tipo de registro.
- Fechas desde/hasta, con significado visible y aviso para intervalos invertidos.
- Intersección de todos los filtros. Los recuentos de cada opción mantienen los demás filtros y sustituyen solo el suyo; las opciones con cero siguen disponibles para explicar estados compartidos incompatibles.
- URL: `tipo`, `convocatoria`, `municipio`, `organismo`, `fuente`, `desde`, `hasta`. Organismos usan `nombre:` seguido del literal; `sin-organismo` es un marcador separado. Los valores se validan contra opciones reales, las fechas contra el calendario y los parámetros duplicados se descartan. No se inserta contenido URL como HTML.
- Cambios añaden historial; atrás/adelante y recarga restauran controles, resultados y recuentos. Quitar filtros devuelve el foco al primer control.
- Estado vacío con recuperación y explicación de incompatibilidad entre municipio BOE y organismo BDNS. Sin JavaScript, el listado completo y los directorios siguen accesibles.

## Archivos de implementación y pruebas

Modificados:
- `site/src/components/RecordFilters.astro`
- `site/src/components/RecordList.astro`
- `site/src/lib/presentation/recordFilters.ts`
- `site/src/lib/presentation/authorities.ts`
- `site/src/pages/registros/index.astro`
- `site/src/styles/global.css`
- `site/scripts/utility.test.mjs` (actualiza el aviso antiguo de ausencia del filtro).

Nuevos:
- `site/src/scripts/recordFilters.ts`
- `site/scripts/discovery.test.mjs`
- `site/scripts/discovery-browser.cjs`
- Este informe.

No se modifican datos, collectors, schemas, políticas, workflows, dependencias ni fichas individuales.

## Ejemplos reales del build local

| Consulta local | Resultado |
| --- | --- |
| `/registros/?organismo=nombre%3AALMASSORA&fuente=bdns` | 6 registros |
| `/registros/?fuente=boe&desde=2026-10-01&hasta=2026-10-28` | 2 registros |
| `/registros/?organismo=nombre%3AALMASSORA&fuente=boe` | 0 registros y recuperación visible |
| `/buscar/?q=Almassora` | 6 resultados Pagefind |
| `/registros/?desde=2026-10-29&hasta=2026-10-01` | 0 registros y aviso de intervalo invertido |

Los recuentos corresponden a los 86 registros de esta revisión, no a la totalidad de las fuentes oficiales.

## Validación realizada

- `npm run check`: 0 errores, 0 avisos, 0 hints.
- `npm run build`: 115 páginas; Pagefind indexa 86 fichas.
- `node --test scripts/*.test.mjs`: 83/83, sin omisiones.
- `python -m unittest discover -s tests`: 702/702.
- `node scripts/verify-build.mjs`: OK, 86 fichas y 86 registros publicados.
- Validador canónico: OK (86 records, 94 events, 73 manifests, 2 health, 1 review). El primer intento directo no encontraba el paquete local `infocs`; se ejecutó correctamente con `PYTHONPATH` apuntando a `src`, sin instalaciones ni cambios de configuración persistentes.
- `git diff --check`: OK. Git solo avisa de normalización futura CRLF/LF.
- Edge headless real sobre el build servido en localhost: filtros AND, recuentos por opción, recarga, atrás/adelante, foco tras reset, URLs inválidas/duplicadas, intervalo invertido, teclado, claro/oscuro, 390 px sin desbordamiento horizontal, home, directorio, página de Almassora, una ficha y búsqueda Pagefind. Cero errores de consola.
- Casos sintéticos Node: nombres repetidos y variantes, colisión evitada con el marcador, ausencia BDNS, BOE incluso con jerarquía sintética, fecha imposible/bisiesta, límites inclusivos, combinaciones sin coincidencias. El conjunto publicado actual no requiere una opción de ausencia; se valida con fixtures, sin alterar datos.

## Evidencias y reproducción

Capturas en `docs/evidence/discovery-01/`: `escritorio-claro.png`, `escritorio-oscuro.png`, `movil-light.png`, `movil-dark.png`, `intervalo-invalido.png`, `pagefind-movil.png`; resumen `browser-results.json`. Revisadas visualmente las capturas de móvil claro y escritorio oscuro. Esta carpeta está ignorada por una regla existente; las evidencias son locales, no se fuerza su inclusión en Git.

Logs locales sin seguimiento: `discovery-python.log` y `site/discovery-{check,build,node}.log`.

Para reproducir navegador: servir `site/dist` en `127.0.0.1:8031` y, desde `site`, ejecutar `node scripts/discovery-browser.cjs <ruta-al-modulo-playwright>`. La prueba utiliza Edge instalado y Playwright del runtime de Codex; no añade dependencias al proyecto.

## Límites y revisión pendiente

- Validación automatizada en Edge de escritorio con viewport móvil; no equivale a dispositivo físico, Safari/Firefox ni auditoría con lector de pantalla.
- Controles nativos con etiquetas y región de estado; no se ha realizado una auditoría WCAG integral.
- El filtro de administración conserva el nivel 2 del directorio. No desambigua entidades con el mismo literal ni deduce territorio, elegibilidad o estado de convocatoria.
- Recuentos calculados en cliente sobre el listado estático; coste proporcional a registros y opciones. Adecuado para el volumen actual, sin benchmark de grandes volúmenes.
- Pagefind y los filtros continúan siendo vías distintas. Ningún resultado se presenta como exhaustividad oficial.
- Archivos históricos sin seguimiento conservados. La entrega se prepara en una PR; no se fusiona ni se despliega manualmente.

## Revisión final y requisitos opcionales

- Corrección editorial mínima: el aviso especifica el nivel 2 de la jerarquía oficial BDNS y que no necesariamente identifica jurídicamente al organismo convocante exacto. Test sobre HTML generado. La agrupación no cambia.
- `origin/main` avanzó a `d77514e` con dos commits exclusivamente de datos. Revisadas las rutas: sin solapamiento con los archivos de esta entrega. Se conserva la base `6d28b1e`, sin rebase ni integración local de los datos.
- El script de navegador es opcional y no forma parte de CI ni de las dependencias del proyecto. Requiere Node, un módulo Playwright disponible externamente y un navegador instalado. Admite una ruta absoluta al módulo y una URL base como argumentos, con independencia del directorio de ejecución. Capturas relativas al repositorio.
- Por defecto usa Edge instalado (`msedge`). `DISCOVERY_BROWSER_CHANNEL=chrome` permite Chrome; `DISCOVERY_BROWSER_CHANNEL=chromium` usa Chromium previamente instalado para Playwright. No descarga ni instala navegadores. Es una comprobación del dataset actual: requiere Almassora y registros BOE de octubre de 2026; si cambia esa cobertura habrá que adaptar los ejemplos de prueba.
- Evidencias y logs siguen excluidos del commit. Las capturas se regeneran al ejecutar la prueba opcional.
