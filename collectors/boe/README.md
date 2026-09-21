# BOE — Transporte y parser (Fase 03B)

## Finalidad y límite

Este módulo implementa exclusivamente la primera parte del adaptador BOE:

```text
API BOE -> transporte HTTP seguro -> validación -> BOESummary / BOEItem
```

No clasifica relevancia territorial, no consulta XML/HTML/PDF individuales, no
crea `RecordCandidate`, no llama a `finalize_record()` y no escribe datos,
eventos, manifests ni health global. Por tanto, un `BOEItem` no es todavía un
record InfoCs publicable.

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

## Lo que corresponde a 03C

Fase 03C decidirá, con reglas documentadas, cómo transformar el resultado
source-specific en `RecordCandidate`, qué datos oficiales conservar, y cómo
tratar categorías o inclusión territorial. Nada de ello está implementado aquí.
