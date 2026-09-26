# Política de elegibilidad de publicación — BOP Castellón v1

## Barreras separadas

El flujo previsto para cada anuncio es:

`normalize → finalize_record() → Privacy Gate → Source Publication Eligibility`

- **Privacy Gate** evalúa el contenido del `Record` finalizado. Sus decisiones `allow`, `quarantine` y `reject` conservan su semántica actual y tienen precedencia.
- **Source Publication Eligibility** pregunta si existe una barrera global aplicable a toda la fuente. `eligible` sólo permite continuar a políticas posteriores; no aprueba la publicación del Record. `hold` detiene el flujo antes de revisión manual.
- **Manual Publication Review** es una decisión individual por Record, implementada por la allowlist existente. En esta fase no se aplica a BOP y no se llama mientras haya source-wide HOLD.

## Estado de BOP

- source eligibility: `hold`
- reason: `reuse_policy_unresolved`
- scope: todos los Records derivados del BOP, después de `Privacy ALLOW`, sin depender de ID, título, categoría, autoridad, geografía, municipio o edición.
- si Privacy devuelve `quarantine` o `reject`, el flujo se detiene en Privacy; no se sustituye esa causa por el source hold.
- el source hold no es cuarentena ni rechazo, no es revisión manual pendiente y no genera entradas en una review queue.
- no se crea `data/review/bop_castellon/pending.json` ni se persiste ningún Record BOP.

La barrera podrá cambiar en el futuro a `eligible` cuando exista una base oficial de reutilización aplicable y documentada. Ese cambio pertenece a la política source-specific; no requiere alterar parser, normalizador, identidad, Privacy Gate ni la revisión manual BOE. `eligible` tampoco decidirá por sí solo si BOP necesitará revisión manual posterior.

La recopilación y normalización técnica no equivalen a permiso de redistribución. El informe de auditoría y sus incertidumbres están en [REUSE_POLICY_AUDIT.md](REUSE_POLICY_AUDIT.md).
