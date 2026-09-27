# BDNS live dry-run

Fecha de ejecución: 2026-09-27 (UTC).

Ejecución acotada en memoria contra la API oficial SNPSAP. Se aplicó el
filtro documentado de región BDNS `56` y la respuesta del detalle coincidió
con el match territorial canónico aprobado para Castellón (`ES522`). No se
guardaron respuestas ni datos de convocatoria.

## Resultado

- Resultado técnico: `success`.
- Requests HTTP: 2 de un máximo permitido de 4 (búsqueda + un detalle).
- Estados HTTP: 200, 200.
- Búsqueda: 3 resultados observados; se consultó el detalle del primero.
- Territorialidad: 1 `in_scope`, código `exact_castellon_province_region`.
- Finalizados: 1.
- Privacy Gate: 1 `allow`, 0 `quarantine`, 0 `reject`.
- Source Publication Eligibility: 1 `eligible`.
- Política BDNS de metadata: 1 `publishable_metadata`, 0 `hold`.
- Errores: 0.
- Escrituras: 0.

El informe omite títulos, códigos BDNS, órganos, URLs y cuerpos de respuesta.
No se llamaron RecordStore, EventStore, Review Queue, Publication Review,
ManifestStore ni Health. Tampoco se solicitaron documentos ni concesiones.

La atribución IGAE exigida por las condiciones de reutilización corresponde a
la futura capa de publicación/exportación; no se incorpora al Record ni a su
hash.
