# InfoCs UI Data Contract v1

## Frontera de datos

JSON canónico en `data/` → loader build-time → adapters
`adaptRecord()` / `adaptEvent()` → tipos `FrontendRecord`/
`FrontendEvent` → presentation view model → componentes Astro. Los
componentes no consumen directamente JSON canónico ni implementan reglas del
Core.

## Opcionalidad

Autoridad y nivel administrativo pueden ser null; fecha publicada, fecha del
acto, geografía, importes, documentos y relaciones pueden faltar. El adapter
preserva esa ausencia; la UI omite el bloque correspondiente. Nunca infiere
municipio/autoridad desde el título.

## Fechas e historial

`publishedAt` se presenta como «Publicado». Si no existe, `detectedAt` se
presenta como «Detectado por InfoCs». `eventAt` sólo se presenta con esa
semántica. Un Event create significa incorporación/detección por InfoCs, no
fecha de publicación del organismo.

Events v1 aporta tipo, instante observado, hashes y `changedFields`; no
proporciona valores before/after ni eventos de desaparición/reaparición.
La vista puede describir campos cambiados, pero no reconstruir sus valores.

## Campos de presentación

La capa `presentation` centraliza nombres de fuente, categorías, nivel
administrativo, fecha primaria, geografía y descripción de eventos. IDs y
hashes se reservan a los detalles técnicos; no se muestran en listados.

## Fuentes visibles

BOE y BDNS se leen desde Records públicos canónicos. BOP puede aparecer en
metadata editorial como «Publicación pendiente», pero no se lee ni se muestra
como dataset. No se inventan cifras de actividad o salud.
