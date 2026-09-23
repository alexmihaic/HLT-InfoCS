# BOE — Transporte, parser, territorialidad, normalización e ingesta (03B–03F)

## Finalidad y límite

Este módulo implementa exclusivamente la primera parte del adaptador BOE:

```text
API BOE -> transporte HTTP seguro -> validación -> BOESummary / BOEItem
                                                        -> decisión territorial explicable
                                                        -> normalizador -> RecordCandidate
                                                        -> finalize_record() -> Privacy Gate -> RecordStore
```

El normalizador sólo crea un `RecordCandidate` activo para una decisión
`include`. No escribe datos, eventos, manifests ni health global. El core es
el único responsable de convertir ese candidato en un `Record` final mediante
`finalize_record()`; la integración se prueba offline, pero no persiste su
resultado.

## Endpoint y configuración

El transporte usa sólo el endpoint auditado:

```text
GET https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}
Accept: application/json
```

`{fecha}` se valida localmente como `YYYYMMDD`; no puede convertirse en una URL
arbitraria. Se permiten únicamente los hosts `www.boe.es` y `boe.es`, por HTTPS
y sin credenciales ni puertos no estándar.

`source_contract.yaml` se mantiene como documentación machine-readable de la
auditoría, **no** como configuración runtime en esta fase. No se ha añadido un
parser YAML sólo para cargar dos hosts duplicados. El transporte usa sólo
`src/infocs/fetch/boe/config.py` como fuente efectiva de constantes. Una fase
posterior deberá decidir si valida el YAML en runtime o genera una configuración
derivada; hasta entonces no hay dos allowlists activas que puedan discrepar.

## Transporte

`BOETransport.fetch_daily_summary()` usa únicamente biblioteca estándar:
`urllib.request`, `json`, `ssl` y `socket`. No se añade `requests` ni `httpx`:
la stdlib cubre HTTPS, timeouts, cabeceras, errores HTTP y un opener sin
redirects, sin introducir una dependencia de producción adicional.

- `User-Agent`: `InfoCs/0.1`.
- Timeout: 15 segundos.
- Redirects: deshabilitados; cualquier 3xx es `source_failure`.
- Retries: ninguno en v1. No se reintenta automáticamente 400, 404, 5xx ni
  errores de red.
- Tamaño máximo: 2 MiB. Es un **límite de seguridad InfoCs**, no un límite
  oficial BOE; supera ampliamente la muestra JSON de unos 315 KB auditada.
- Las respuestas se leen como máximo hasta el límite más un byte, no se
  escriben a disco y nunca se ejecutan.

## Semántica de resultado

`BOEFetchResult.status` usa un enum, no strings dispersos:

| Resultado | Condición |
| --- | --- |
| `complete_success` | HTTP 200, MIME JSON, cuerpo dentro del límite, JSON válido, `status.code == "200"` y estructura mínima válida. |
| `no_daily_publication` | HTTP 404; fecha sin sumario, no un sumario vacío ni una ausencia de records. |
| `invalid_request` | HTTP 400; no se reintenta. |
| `source_failure` | 5xx, 3xx, red/TLS/timeout, MIME erróneo, JSON inválido, exceso de tamaño o contrato inesperado. |

La observación real del 2026-09-21 confirmó que `status.code` es la **cadena**
`"200"`, no el entero `200`. El parser lo exige como tal para detectar una
deriva del contrato de fuente.

## Modelos source-specific

- `BOESummary`: fecha de publicación y diarios.
- `BOEDiary`, `BOESection`, `BOEDepartment`, `BOEHeading`: jerarquía del
  sumario, preservando el orden de sus colecciones.
- `BOEItem`: identificador, título, sección, departamento, epígrafe opcional,
  fecha heredada y enlaces oficiales.
- `BOEDocumentLinks`: URLs XML/HTML/PDF y tamaño/páginas PDF cuando existan.

La ausencia de `control` o de metadatos de tamaño/páginas PDF se representa con
`None`; no se sustituyen por cadenas vacías ni valores inventados.

## Fixtures y tests

`fixtures/summary_20240529_minimal.json` es una respuesta BOE real recortada a
un ítem, con metadatos de origen en `fixtures/README.md`. Las restantes
situaciones se modelan sintéticamente y offline en
`tests/unit/test_boe_transport.py`: 400, 404, 500, 302, MIME incorrecto, JSON
inválido, cuerpo excesivo, timeout, `status.code` no exitoso, estructura
incompleta, campos opcionales y múltiples diarios/secciones.

No hay smoke test de red en la suite: las pruebas ordinarias no acceden a
Internet. La petición de humo se decidirá separadamente cuando exista una fase
autorizada para ello.

## Política territorial 03C

`territorial.py` aplica una política literal y auditable sobre metadatos ya
presentes en `BOEItem`. Sólo examina, en este orden, epígrafe, departamento y
título. Devuelve `BOETerritorialDecision` con `include` o `no_match` y motivos
como `municipality_exact`, `province_exact` o `authority_exact`.

La política no afirma que una disposición sea aplicable o importante para
Castellón: registra exclusivamente dónde se observó una coincidencia exacta.
No consulta `url_xml`, `url_html` ni `url_pdf`, no inspecciona la sección, no
usa fuzzy matching, IA o puntuaciones, y no clasifica el ítem. El registro
versionado de entidades está en `config/entities/castellon.json`; su contrato y
limitaciones se describen en `TERRITORIAL_POLICY.md`.

## Normalización 03D

`normalize_boe_item(item, decision, detected_at=..., last_checked_at=...)`
recibe un `BOEItem` ya parseado, una decisión territorial ya tomada y los
timestamps explícitos de observación. No accede a red ni abre XML, HTML o PDF.
Devuelve un `RecordCandidate` sólo si la decisión es `include`; para
`no_match` devuelve `None` sin tratar el ítem como un record irrelevante.

El mapping detallado, la regla de `source_url`, autoridad, categorías,
documentos, procedencia y límites están en
[`NORMALIZATION_POLICY.md`](NORMALIZATION_POLICY.md). 03D no implementa
persistencia, reconciliación BOE, eventos BOE, manifests ni inspección de
documentos individuales.

## Ingesta incremental 03E y Privacy Gate 03F

El sumario diario BOE está declarado como `collection_semantics:
incremental_feed` en `source_contract.yaml`: cada edición contiene
publicaciones de una fecha, no un snapshot completo. La ausencia de un ítem en
el siguiente día no genera `missing_from_source` ni cambia su estado activo.

`ingest_boe_summary()` evalúa, normaliza y finaliza los ítems incluidos, y
devuelve operaciones `create`, `update` o `no_change`. Un `source_failure`, un
`invalid_request` o un `no_daily_publication` no escribe nada; este último es
un resultado correcto sin edición diaria. Los eventos `create` y `update` se
devuelven en memoria para validar el contrato, pero no se guardan todavía en
`data/events/`.

`RecordStore` escribe un JSON por record en un directorio proporcionado por el
caller (en producción futura sería `data/records/<fuente>/`). La ruta del ID
se codifica de forma determinista, la representación es UTF-8 con newline
final y cada reemplazo usa un temporal del mismo directorio y `os.replace`.
Antes de `RecordStore.write()` el `PrivacyGate` v1 detecta patrones de alto
riesgo en textos seleccionados. `allow` permite escribir, mientras que
`quarantine` y `reject` no escriben payload ni evento público. El store vuelve a
evaluar el record, por lo que el gate no depende de un recuerdo del collector.
Los tests utilizan exclusivamente directorios temporales. La persistencia de
datos BOE reales sigue bloqueada en esta fase aunque la barrera técnica ya esté
implementada:

```text
LIVE REAL DATA PERSISTENCE BLOCKED pending explicit publication approval
```

## Live dry run 03G

`dry_run_boe_date()` está separado de la ingesta persistente: recibe fecha y
timestamps explícitos, transport, registry y Privacy Gate, pero no acepta ni
importa `RecordStore`. Devuelve métricas y una vista minimizada por ítem; títulos
y detalles territoriales no se incluyen para decisiones de privacidad que no
sean `allow`. La ejecución auditada de 2026-09-23 está documentada en
[`LIVE_DRY_RUN_2026-09.md`](LIVE_DRY_RUN_2026-09.md). Las pruebas siguen siendo
offline; no existe automatización ni escritura de resultados del dry-run.

## Primera persistencia controlada 03H

`config/publication-review/boe-initial.json` registra decisiones explícitas
por `official_id`. La revisión de publicación es distinta del Privacy Gate:
un record sólo puede escribirse si ambos permiten la operación. Los IDs no
listados quedan en `hold`; una cuarentena de privacidad no puede ser
sobrescrita por una aprobación. El preflight prepara y valida el lote completo
antes de invocar `RecordStore`; sólo los aprobados llegan al store, que vuelve
a evaluar privacidad. No se persisten events y no existe automatización.

La ejecución, el lote mínimo y sus límites se documentan en
[`FIRST_PERSISTENCE_2026-09.md`](FIRST_PERSISTENCE_2026-09.md).
