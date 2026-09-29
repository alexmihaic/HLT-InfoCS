# BDNS / SNPSAP — contrato de transporte v1

**Revisión:** 2026-09-26

**Alcance:** búsqueda y detalle de convocatorias públicas. Sin normalización Core, persistencia ni solicitudes a documentos.

> Estado actual: las incertidumbres territoriales anotadas durante 04B se
> resolvieron después. Véanse [TERRITORIAL_POLICY.md](TERRITORIAL_POLICY.md),
> [NORMALIZATION_POLICY.md](NORMALIZATION_POLICY.md) y
> [LIVE_DRY_RUN.md](LIVE_DRY_RUN.md) para el contrato vigente y su evidencia.

## Operaciones

El cliente usa únicamente los endpoints públicos documentados de SNPSAP:

| Operación | Método y ruta | Parámetros v1 | Resultado |
| --- | --- | --- | --- |
| Búsqueda | `GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda` | `page` (base cero), `pageSize`, `order`, `direccion`; filtros opcionales `numeroConvocatoria`, `regiones` (IDs enteros del catálogo), `fechaDesde` y `fechaHasta` (`dd/MM/yyyy`) | Página JSON con `content`, totales y metadatos de paginación. |
| Detalle | `GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias` | `numConv=<numeroConvocatoria>` | Objeto JSON de la convocatoria. El parámetro opcional `vpd` no se usa. |

Cabeceras explícitas: `Accept: application/json` y User-Agent de InfoCs. No se envían autenticación ni cookies. Cada llamada crea una petición GET independiente; no se persiste estado de sesión. El cliente no sigue redirecciones automáticamente: una respuesta distinta de HTTP 200 se clasifica y no se sigue a otro destino.

Timeout de 15 segundos y máximo de respuesta de 2 MiB son límites defensivos elegidos por InfoCs; no son propiedades ni límites publicados por BDNS. La cuota numérica no está documentada. Política local: requests seriales, sin crawling, concurrencia ni reintentos automáticos.

## Estados y fallos

- `success`: HTTP 200, MIME JSON compatible y payload válido para la operación.
- `no_results`: búsqueda válida cuya lista `content` está vacía; no es fallo de fuente.
- `invalid_request`: consulta local inválida o HTTP 400.
- `source_failure`: red/timeout, redirección o HTTP inesperado, HTTP 429, MIME incompatible, respuesta sobre el límite, JSON inválido, forma contractual inválida o código de convocatoria distinto entre detalle y petición.

Los resultados y errores conservan sólo modelos tipados y códigos de error seguros; nunca el cuerpo raw. Los campos JSON desconocidos se ignoran y no se copian al modelo. Los bloques presentes que el contrato modela con una forma incompatible producen fallo cerrado.

## Modelos observados y paginación

La búsqueda modela `content[]`, `pageable.pageNumber`, `pageable.pageSize`, `pageable.offset`, `totalPages`, `totalElements`, `numberOfElements`, `first`, `last` y `empty`. Los campos de convocatoria preservados son `numeroConvocatoria`, `id` técnico opcional, `descripcion`, `descripcionLeng`, `fechaRecepcion`, `nivel1`–`nivel3`, `codigoInvente` y `mrr`. El filtro v1 de territorio usa el parámetro documentado `regiones` con IDs de catálogo BDNS; para Castellón el ID auditado es 56. La lista y el detalle son contratos distintos; no se presupone que tengan los mismos campos.

El detalle conserva, cuando están presentes, `codigoBDNS`, `id` técnico, título y variante lingüística, `organo.nivel1`–`nivel3`, `sedeElectronica`, `fechaRecepcion`, `presupuestoTotal`, tipo, instrumentos, tipos de beneficiario, sectores, regiones, finalidad, bases reguladoras, banderas y fechas del periodo de solicitud, metadata de documentos y metadata de `anuncios`/extractos. No conserva el payload completo ni campos desconocidos.

La respuesta de búsqueda usa paginación indexada, no cursor. El máximo de página no está documentado; el cliente valida enteros positivos pero no inventa un máximo de servidor. En el smoke se pidió `page=0`, `pageSize=1`, `order=fechaRecepcion`, `direccion=desc`; SNPSAP devolvió una página de un elemento y metadatos coherentes de página. El total observado fue 654694 y es sólo una observación dinámica del 2026-09-26, no una constante contractual.

El runner OPS-B usa los filtros temporales documentados como límites explícitos
de scope, con política local versionada `fecha-recepcion-provisional-v1`.
La muestra live compatible con `fechaRecepcion` no convierte esa semántica en
una garantía oficial. El runner serializa fechas a `dd/MM/yyyy`, fija `regiones=56`
y valida página/totales/identidad y una lectura de control al final del scope.

## Identidad y semántica de campos

`numeroConvocatoria` en búsqueda y `codigoBDNS` en detalle representan el código externo de convocatoria. El cliente comprueba que ambos coinciden al pedir detalle. `id` se conserva sólo como identificador interno numérico opcional, no como sustituto del código. Concesiones y extractos no forman parte de esta implementación ni se confunden con la convocatoria.

Las fechas se parsean como `YYYY-MM-DD` sólo en campos tipados. `fechaRecepcion` conserva su semántica de fecha de recepción/registro en BDNS y no se renombra como fecha de publicación. Las fechas de publicación sólo se conservan dentro de metadata de extractos/documentos cuando el campo documentado `datPublicacion` está presente. No se calcula `published_at` Core.

Los importes JSON se parsean a `Decimal` (nunca `float`); no se añade moneda si la fuente no la declara. Regiones, niveles de órgano, códigos y etiquetas se conservan como metadata source-specific; aquí no se hace matching territorial, clasificación administrativa Core ni inferencia desde texto.

## Documentos y extractos

El detalle incluye metadata de anexos (`id`, nombre, descripción, longitud y fechas) y puede incluir extractos con número, título, CVE, diario oficial, fecha y URL. No se solicita el endpoint de descarga ni URL de documento/extracto durante el transporte. No se infieren MIME, hash ni contenido. Política de esta fase: enlace/metadata únicamente; sin ZIP, PDF, fulltext ni copia local.

## Comprobación live acotada

El 2026-09-26 se realizaron exactamente dos requests HTTPS, ambas GET, a la API documentada:

1. Búsqueda con página cero y tamaño uno: HTTP 200, JSON válido, un resultado; la respuesta indicó el total de elementos y la paginación descritos arriba.
2. Detalle del código BDNS devuelto por esa búsqueda: HTTP 200, JSON válido; `codigoBDNS` coincidió con `numeroConvocatoria`. La muestra contenía órgano, `fechaRecepcion`, presupuesto, una región y metadata de un documento; no contenía extractos ni fechas de solicitud. La presencia/ausencia en esta única convocatoria no define opcionalidad universal.

No se imprimieron títulos, etiquetas de órgano, datos de personas ni URLs de documentos. No se solicitó ningún documento y no se guardó la respuesta live.

## Fuentes y límites pendientes

El contrato de parámetros y campos procede de `SOURCE_AUDIT.md` y del OpenAPI oficial SNPSAP enlazado allí. El smoke confirma el funcionamiento actual de búsqueda y detalle, la paginación observada y la igualdad del código de convocatoria entre operaciones; no demuestra cobertura completa de campos, tamaño máximo de página, cuota, estabilidad histórica, ni mapeo de regiones/órganos a Castellón.

Reutilización sigue sujeta a las condiciones oficiales auditadas y al Privacy Gate obligatorio. Esta fase no cambia esa decisión ni autoriza publicar registros: territorialidad de Castellón queda pendiente de una fase posterior. No se implementan Records, Events, concesiones, filtros territoriales, Privacy Gate, Publication Review ni persistencia.
