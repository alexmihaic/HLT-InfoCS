# BDNS — primera persistencia controlada

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

El EventStore v1 exige revalidar Publication Review manual BOE para crear o
actualizar Events. BDNS no debe llamar esa revisión ni fabricar una aprobación
BOE; por tanto, en esta fase `create`/`update` Event se difiere y se informa
como `BDNS_CREATE_EVENT_DEFERRED` o `BDNS_UPDATE_EVENT_DEFERRED`. Un
`no_change` no necesita Event. No se altera el modelo Event ni el EventStore.

La fase procesa como máximo tres detalles y persiste como máximo un Record.
No ejecuta concesiones, Review Queue, manifests, health, descargas ni
automatización. Un fallo de escritura no elimina ni invalida Records
anteriores.
