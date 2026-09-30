# BDNS GitHub Action — OPS-G

`.github/workflows/bdns-manual.yml` conserva el disparo manual y añade una
ejecución diaria programada. El horario es una política operativa de InfoCs:
08:17 `Europe/Madrid` (`17 8 * * *`), sin disparo `push` ni `pull_request`.
GitHub Actions schedule es best-effort: su configuración no prueba que cada
run se haya ejecutado puntualmente; RunManifest y SourceHealth son la evidencia
operativa.

`workflow_dispatch` mantiene sus inputs y comportamiento: modo y fechas ISO
explícitas, validación local, región provincial BDNS `56`; para un incremental
manual, `fecha_desde` sólo sirve como inicio si falta un checkpoint compatible.
El evento `schedule` fija `incremental_update` y calcula `through_date` como
ayer según el calendario `Europe/Madrid`. No suministra fecha inicial ni hace
bootstrap: antes de iniciar el runner exige un Manifest BDNS `success` de tipo
`bdns_incremental_update` con `fecha-recepcion-provisional-v1`. Si no existe,
falla cerrado antes de cualquier request y requiere intervención manual.
El runner vuelve a resolver el scope desde el Manifest; el workflow no crea un
watermark ni duplica el límite inicial. Se aplica el solape operativo vigente
de 14 días respecto al `to` del último incremental exitoso compatible.
Reduce omisiones recientes, pero no garantiza detectar todas las correcciones
retrospectivas; la revalidación histórica queda pendiente de OPS-H.

El runner conserva sus límites versionados (50 resultados por página, 250
detalles, 5 páginas y 600 segundos); no se exponen como inputs. La Action
captura exit code y JSON estructurado, valida su correspondencia y no interpreta
texto humano. Antes de publicar, `workflow_safety` permite sólo altas/cambios
JSON en `data/records/bdns/`, `data/events/bdns/`, `data/manifests/bdns/` y
`data/health/bdns.json`. No permite borrados, payloads, documentos, paths de
otras fuentes ni checkpoint independiente. Comprueba modelos, schemas, paths
canónicos, hash de Record, vínculo Event–Record, atribución y coherencia
Manifest–Health.

Sin artefactos modificados no se crea commit vacío ni se despacha Pages. Si los
hay, se validan y se publican antes de propagar el resultado original: `0` es éxito completo,
`2` deja publicados artefactos parciales y termina el workflow como no exitoso,
`1` propaga fallo terminal después de publicar únicamente observabilidad
válida, si la hay. Un fallo de validación/publicación termina por sí mismo con
error y no se fuerza ningún push.

La Action registra el SHA base y hace `fetch` antes de publicar. Sólo acepta
una carrera lineal formada íntegramente por commits automáticos
`data(boe): collect YYYY-MM-DD`, con paths de datos BOE canónicos y sin
borrados. En ese caso crea el commit BDNS, realiza un único rebase normal y
revalida los artefactos; cambios inesperados, conflictos o una segunda carrera
abortan. Push normal a `main`, nunca force-push. Cuando el push de un commit
`data(bdns): ...` termina correctamente, la Action despacha explícitamente
`deploy-pages.yml` en `main`, antes de propagar el exit code original del
runner; si no hubo commit no hay dispatch. El push de datos usa `GITHUB_TOKEN`,
cuyos eventos `push` no disparan otros workflows ni un build de Pages, por lo
que este `workflow_dispatch` explícito es necesario. Un fallo del dispatch
falla la Action BDNS. Los pushes normales/humanos conservan el trigger `push`
de Pages. Si un run programado crea un commit, su mensaje seguro es
`data(bdns): scheduled incremental through YYYY-MM-DD`; el modo manual conserva
su formato actual. La concurrencia `bdns-collection-main` serializa los runs
manuales y programados. Las protecciones de carrera con BOE permanecen iguales.

La ejecución productiva `complete_scope`, la cadena de publicación automática
a Pages y un `incremental_update` compatible e idempotente se validaron en
OPS-E/OPS-E.2/OPS-F. El schedule quedó implementado en OPS-G y está pendiente
de la primera ejecución programada; BDNS no debe considerarse
schedule-validado hasta entonces.
