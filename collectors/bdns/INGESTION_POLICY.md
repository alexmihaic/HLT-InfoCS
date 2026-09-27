# BDNS — política de ingestión y persistencia

El flujo v1 es:

`search` → `detail` → normalización territorial exacta → finalización →
Privacy Gate → Source Publication Eligibility → BDNS Metadata Publication
Policy → preflight de atribución, Record y path → RecordStore.

Sólo tras `Privacy ALLOW`, Source Eligibility `ELIGIBLE` y
`PUBLISHABLE_METADATA` se permite que RecordStore reciba el Record. Un
`QUARANTINE`, `REJECT`, metadata `HOLD`, error de contrato o fallo de
atribución bloquea la escritura. El filtro de búsqueda usa la región BDNS 56;
un detalle devuelto sin el match provincial canónico se trata como deriva de
contrato y detiene el run.

El repositorio es público: escribir bajo `data/records/bdns/` publica y
redistribuye esa metadata. La atribución y las condiciones aplicables están
visibles junto al dataset en [README.md](../../data/records/bdns/README.md).
El preflight comprueba que esa superficie existe y contiene la atribución y
las condiciones necesarias antes de escribir.

Tras 04F, EventStore no ejecuta Publication Review ni políticas de fuente.
Cada ruta pasa sus gates source-specific y entrega una
`PublicationAuthorization` ligada al Record/hash. Con EventStore configurado,
una operación `create`/`update` autorizada preflighta y escribe Event antes de
Record; `no_change` no necesita Event.

El orquestador aún permite una ruta de compatibilidad sin EventStore, que
puede informar `BDNS_CREATE_EVENT_DEFERRED` o
`BDNS_UPDATE_EVENT_DEFERRED`. No es el modo productivo futuro: antes de
automatizar BDNS, EventStore debe ser obligatorio para cualquier `create` o
`update`, de modo que no se publique un Record sin su transición autorizada.

La primera persistencia controlada ya ocurrió: existe un Record BDNS público y
su Event `create` se materializó posteriormente bajo la autorización
multi-source. La atribución IGAE sigue visible junto al dataset y el alcance
publicable no cambia. No se ejecutan concesiones, descargas ni mirroring. BDNS
aún no tiene automatización, Manifest productivo ni Health propio. Un fallo de
escritura no elimina ni invalida Records anteriores.
