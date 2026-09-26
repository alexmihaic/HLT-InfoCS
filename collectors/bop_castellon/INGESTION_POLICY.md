# Política de ingestión — BOP Castellón 05E

El flujo offline de barrera es:

`BOPFetchResult → BOPIssue/BOPAnnouncement → normalize → finalize_record() → Privacy Gate → Source Publication Eligibility`.

La normalización y finalización ocurren antes de Privacy Gate porque el gate
evalúa un `Record` finalizado. Privacy tiene precedencia: `quarantine` y
`reject` detienen el procesamiento y no se convierten en un hold de fuente.

Con `Privacy ALLOW`, la política source-wide vigente devuelve `HOLD` con
`reuse_policy_unresolved`. Es un resultado técnicamente correcto, no un fallo
del transporte, pero detiene cualquier publicación y persistencia antes de
RecordStore o EventStore. El repositorio es público: escribir aquí un Record o
Event BOP real supondría redistribuirlo públicamente.

El hold global no es una revisión manual por anuncio. No se llama a
`review_publication()`, no se consulta la allowlist BOE y no se crea una tarea
en Review Queue. El resultado de ingestión sólo expone métricas agregadas y
códigos seguros; no contiene títulos, IDs de anuncios, URLs ni payloads.

No se escriben Records, Events, Review Queue, Run Manifests ni Health BOP en
esta fase. El desbloqueo exige una base oficial de reutilización aplicable,
documentada y aprobada; la política source-specific podrá cambiar entonces,
con una decisión posterior sobre cualquier revisión individual.

El contrato RunManifest v1 puede representar el run como `success` y reflejar
el resultado agregado con el contador `publication_hold`, sin incluir
contenido BOP. Ese schema no conserva el motivo del hold en un run exitoso;
`reuse_policy_unresolved` queda en el resumen seguro de ingestión en memoria.
Como `SourceHealth` deriva `healthy` de un run `success`, el hold jurídico no
degrada la salud operacional del collector. Esta fase sólo verifica esos
contratos en tests: no materializa Manifest ni Health.
