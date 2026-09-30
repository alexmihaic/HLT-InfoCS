# BDNS manual GitHub Action — OPS-D

La automatización v1 es exclusivamente manual mediante
`.github/workflows/bdns-manual.yml` (`workflow_dispatch`); no hay schedule ni
cron. Requiere `main`, solicita modo y fechas ISO explícitas, fija la región
provincial BDNS `56` y valida el intervalo localmente antes de iniciar el
runner. En `incremental_update`, `fecha_desde` es la fecha inicial sólo cuando
falta un checkpoint incremental compatible; después se aplica el checkpoint
y solape definidos por la política operativa.

El runner conserva sus límites versionados (50 resultados por página, 250
detalles, 5 páginas y 600 segundos); no se exponen como inputs. La Action
captura exit code y JSON estructurado, valida su correspondencia y no interpreta
texto humano. Antes de publicar, `workflow_safety` permite sólo altas/cambios
JSON en `data/records/bdns/`, `data/events/bdns/`, `data/manifests/bdns/` y
`data/health/bdns.json`. No permite borrados, payloads, documentos, paths de
otras fuentes ni checkpoint independiente. Comprueba modelos, schemas, paths
canónicos, hash de Record, vínculo Event–Record, atribución y coherencia
Manifest–Health.

Sin artefactos modificados no se crea commit vacío. Si los hay, se validan y se
publican antes de propagar el resultado original: `0` es éxito completo,
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
de Pages. La automatización BDNS sigue siendo manual, sin schedule ni cron.

La primera ejecución manual `complete_scope` del 2026-09-28 terminó con éxito.
Detectó que el push de datos no inicia Pages cuando usa `GITHUB_TOKEN`. OPS-E.1
añade el dispatch explícito; su funcionamiento quedará live-validado cuando un
próximo collector publique un commit de datos. BDNS sigue sin schedule.
