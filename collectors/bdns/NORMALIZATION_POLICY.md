# BDNS / SNPSAP — política de normalización v1

**Revisión:** 2026-09-26

**Alcance:** reglas previas para convertir una convocatoria (no una concesión individual) en un futuro `RecordCandidate`. No implementa normalizador, privacidad ni publicación.

## Requisito de scope

Primero evaluar la política de `TERRITORIAL_POLICY.md`. Sólo los casos `INCLUDE` pueden continuar a normalización. Una región amplia o no resuelta no se convierte en Record local. Excluir una convocatoria fuera del scope no significa que la fuente haya fallado.

## Identidad y origen

- `source.id = bdns` (source contract).
- `source.official_id = codigoBDNS` del detalle, igual a `numeroConvocatoria` de búsqueda. El OpenAPI describe ambos como código BDNS de la convocatoria. Comprobar igualdad al unir las respuestas.
- El `id` numérico del detalle es interno a BDNS; no sustituye la identidad pública.
- `grant.call_id` puede conservar el mismo Código BDNS: es la referencia de dominio del bloque grant, mientras `source.official_id` es la identidad genérica. `resolution_id` y `beneficiary` se omiten; una convocatoria no es una concesión.
- `source_url`: endpoint oficial de detalle `https://www.infosubvenciones.es/bdnstrans/api/convocatorias?numConv=<codigoBDNS>`, con query encoding estándar. Es una URL reproducible documentada; no inventar una ficha frontend.

El detalle contiene `organo.nivel1`–`nivel3`, pero no su código. La búsqueda puede aportar `codigoInvente`, que el OpenAPI define como «Código INVENTE del órgano de la convocatoria». Si se usa, primero unir resumen y detalle comprobando `numeroConvocatoria == codigoBDNS`; namespacing sugerido para `authority.id`: `bdns:invente:<codigoInvente>`. Es código del órgano en INVENTE, no INE ni código territorial. Si no hay código y el órgano es identificable por sus niveles source-specific, un futuro ID InfoCs debe ser determinista y explícitamente derivado (por ejemplo, hash de la tupla jerárquica canónica); no presentarlo como identificador oficial. Sin nombre de órgano suficiente, `authority = null` es válido.

El OpenAPI describe `tipoAdministracion` (`C`, `A`, `L`, `O`) como filtro de búsqueda: Estado, Comunidad Autónoma, Entidad Local y otros órganos. No figura como campo devuelto por el modelo de convocatoria. No derivar `administration_level` de ese parámetro ni del texto `nivel1`–`nivel3`. En v1 dejar `authority.administration_level` y `administration_level` a `null`, salvo que una fuente/catálogo oficial asociado aporte una clasificación inequívoca a uno de los cuatro niveles Core. `L` no distingue municipal de provincial; `O` tampoco es un nivel Core.

## Campos Core

| Campo Core | Política BDNS v1 |
| --- | --- |
| `category` | `grants.call`. No clasificar concesiones en esta fase. |
| `title` | `descripcion` exacta del detalle, sin reescritura ni combinación con órgano. Si falta, `descripcionLeng` puede usarse literalmente, sin traducir; si ambos faltan, no crear Candidate. |
| `description` | `None` por defecto; no copiar finalidad ni bloques largos de texto. |
| `dates.detected_at`, `dates.last_checked_at` | Timestamps explícitos del pipeline InfoCs, con zona horaria; no derivarlos del API. |
| `dates.published_at` | No usar `fechaRecepcion`. Sólo mapear `anuncios[].datPublicacion` cuando haya un extracto oficial identificable y su fecha tenga semántica inequívoca de publicación del propio anuncio que representa el Record. Si hay varios extractos sin tipo que distinga original de corrección/modificación, no elegir el primero por conveniencia: `published_at = null`. Si no hay evidencia suficiente, `null`. |
| `dates.event_at` | `null`; no hay semántica de evento administrativo confirmada para la convocatoria. |
| `financial` | Omitir `presupuestoTotal` en v1. La fuente lo define como presupuesto total de la convocatoria, no importe concedido a un beneficiario. El Core no tiene un concepto explícito de presupuesto global de convocatoria; no forzarlo a `grant_amount` ni a importe de concesión. Mantener el `Decimal` source-specific. No inferir EUR si el campo no declara moneda. |
| `grant` | `call_id = codigoBDNS`; `resolution_id` y `beneficiary` ausentes. Los tipos de beneficiarios elegibles no son adjudicatarios. |
| `geography` | Sólo la provincia normalizada si el evaluador territorial obtiene coincidencia oficial exacta; municipio únicamente con correspondencia oficial municipal. No extraerlo del título. |
| `documents` | Omitir de `RecordCandidate` v1. El payload del detalle conserva ID/metadata, no una URL directa. Aunque el OpenAPI documenta el endpoint binario oficial `GET /convocatorias/documentos?idDocumento=...`, v1 no genera ni publica ese enlace de descarga: la metadata sigue source-specific hasta que privacidad y la política de presentación del enlace estén resueltas. No descargar ni archivar. |
| `relations` | Ninguna en esta fase. |

Los extractos BOE sólo podrán sustentar una relación futura si hay evidencia cruzada determinista (por ejemplo, CVE y/o URL oficial BOE que coincida con la identidad canónica de un Record BOE). `numAnuncio`, diario y fecha describen el extracto, pero no bastan por sí solos para enlazar records. Nunca relacionar por título.

## Procedencia, hash y reutilización

- `provenance.collector = bdns`; versión según el paquete ejecutor.
- `normalizer_version` debe ser una versión explícita del futuro normalizador.
- `technical.extraction_method = bdns_rest_json`.
- Para una coincidencia territorial con el código de catálogo oficialmente resuelto: `OFFICIAL_CODE_MATCH`; para una autoridad localizada mediante catálogo oficial y cruce exacto: `AUTHORITY_MATCH`. No usar `EXPLICIT_TEXT_MATCH` para regiones estructuradas.
- La decisión territorial, atribución, licencia y condiciones de reutilización no entran en `content_hash`. La política Core ya excluye `geography`, `authority`, `administration_level`, `category` y `provenance`; `title`, `source_url`, `published_at`, importes Core y `grant.call_id` sí pueden participar conforme al contrato actual.
- Reutilización: `REUSE_CONFIRMED_WITH_CONDITIONS`, según el Aviso Legal SNPSAP auditado en `SOURCE_AUDIT.md`. La publicación/export futuro debe atribuir «Origen de los datos: Intervención General de la Administración del Estado», preservar la fecha de actualización cuando conste, indicar disociación de datos personales y responsable cuando se realice, y no insinuar patrocinio o apoyo de IGAE. No meter licencia/atribución en campos administrativos ni hash del Record.

## Privacidad y límites

Esta entidad es una convocatoria pública, no una concesión individual. Excluir concesiones nominativas, beneficiarios e identificadores personales de este normalizador. No trasladar los tipos de beneficiario elegible al beneficiario del Core. Cualquier futuro Candidate seguirá pasando por Privacy Gate antes de persistencia; la publicación oficial de origen no elimina esa obligación.

Las reglas no alteran `RecordCandidate`, identidad, finalizer ni `content_hash`. Los campos territoriales/administrativos no demostrados se omiten o quedan sin clasificar; nunca se inventa una fecha, moneda, autoridad, municipio ni URL.

**Referencias:** [política territorial BDNS](TERRITORIAL_POLICY.md), [auditoría de fuente](SOURCE_AUDIT.md), [contrato de transporte](TRANSPORT_CONTRACT.md), [modelo de datos Core](../../docs/DATA_MODEL.md), [modelo de identidad y cambios](../../docs/IDENTITY_AND_CHANGE_MODEL.md), [OpenAPI SNPSAP](https://www.infosubvenciones.es/bdnstrans/estaticos/doc/snpsap-api.json).
