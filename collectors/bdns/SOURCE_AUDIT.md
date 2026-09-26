# BDNS / SNPSAP — auditoría de fuente oficial

**Revisado:** 2026-09-26
**Alcance:** contrato documental de consulta automatizada de convocatorias públicas. Sin llamadas al API de datos, descargas de documentos ni persistencia.

## Responsable y sistema

La Base de Datos Nacional de Subvenciones (BDNS) es administrada y custodiada por la Intervención General de la Administración del Estado (IGAE). La información la suministran distintas administraciones y órganos, que conservan la responsabilidad sobre el contenido que aportan; por ello, IGAE es responsable del sistema, no necesariamente autora de cada convocatoria. El portal público de publicidad se denomina Sistema Nacional de Publicidad de Subvenciones y Ayudas Públicas (SNPSAP). Su cobertura comprende convocatorias y concesiones de la Administración General del Estado, comunidades autónomas, entidades locales y sector público institucional; no equivale a un registro de ayudas directas concedidas por la UE.

Fuentes: [Real Decreto 130/2019, arts. 3 y 9](https://www.boe.es/buscar/act.php?id=BOE-A-2019-4671), [FAQ oficial SNPSAP, preguntas 100–103](https://www.infosubvenciones.es/bdnstrans/A13/es/faqs).

## Mecanismo recomendado

**Recomendación técnica: la API REST documentada del SNPSAP**, no el HTML del portal ni una API interna inferida. La especificación OpenAPI publicada por el propio portal declara que expone información pública registrada en BDNS, versión 1.1.0 al revisarla, y enumera operaciones, parámetros, esquemas y respuestas.

Consulta inicial recomendada para una futura fase de transporte:

- `GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda`
- detalle de una convocatoria: `GET https://www.infosubvenciones.es/bdnstrans/api/convocatorias?numConv=<Código BDNS>`; `vpd` es opcional según la especificación.
- respuesta de ambas operaciones: `application/json`.

La búsqueda documentada admite páginas, tamaño de página, orden/dirección y filtros por código BDNS, texto del título, periodo (`fechaDesde`/`fechaHasta`, formato `dd/MM/yyyy`), tipo de Administración, órganos, región de impacto, tipo de beneficiario, instrumentos, finalidad y referencia de ayuda de Estado. No se documenta un máximo de `pageSize`. La respuesta incluye `content`, información de paginación, `totalPages`, `totalElements`, `numberOfElements` y `empty`.

La especificación incluye también `/convocatorias/ultimas`, operación de consulta de convocatorias recientes. El portal permite exportar vistas en CSV, PDF, XLSX, JSON y XML; esas exportaciones de la interfaz son una alternativa oficial, pero la API REST es la vía automatizada preferida. No se encontró un feed RSS/Atom contractual en los documentos revisados. Los servicios de gestión/intercambio administrativo de BDNS descritos en documentación PAP no se deben confundir con el API público del SNPSAP.

La API describe acceso público, sin autenticación para las operaciones públicas de consulta. La especificación reserva bearer/JWT para ciertas operaciones de suscripción autenticada; no se debe trasladar ese requisito a `convocatorias/busqueda`. No se documentan cookies ni cabeceras de sesión obligatorias.

Fuentes: [documentación/OpenAPI oficial](https://www.infosubvenciones.es/bdnstrans/GE/es/doc), [OpenAPI JSON SNPSAP](https://www.infosubvenciones.es/bdnstrans/estaticos/doc/snpsap-api.json), [ayuda oficial, sección de API REST](https://www.infosubvenciones.es/bdnstrans/estaticos/ayuda/AYUDA%20-%20Sistema%20Nacional%20de%20Publicidad%20de%20Subvenciones%20y%20Ayudas%20P%C3%BAblicas%20v2023.pdf).

## Identidad y entidades que no deben confundirse

| Entidad | Campos observados/documentados | Interpretación prudente |
| --- | --- | --- |
| Convocatoria | `numeroConvocatoria` en la búsqueda; `codigoBDNS` en detalle | Código BDNS público, requerido por el esquema de lista y descrito como código de convocatoria. Es la identidad externa primaria candidata de una convocatoria. |
| Convocatoria | `id` numérico en detalle y algunos ejemplos | La especificación lo llama identificador de convocatoria, pero no lo define como identificador público estable equivalente al Código BDNS. Conservar como identificador técnico, no sustituir el Código BDNS sin más evidencia. |
| Concesión individual | `id`/`idConcesion`, `idConvocatoria`, `numeroConvocatoria`, beneficiario, importe y fechas | Entidad distinta: una concesión enlaza con la convocatoria. No tratar el ID de concesión como ID de convocatoria. |
| Extracto/anuncio de convocatoria | elemento de `anuncios`: `numAnuncio`, títulos, `url`, `cve`, diario oficial y `datPublicacion` | Es una publicación/extracto asociado a la convocatoria. La especificación no aclara que `numAnuncio` sea global ni estable; no usarlo como identidad independiente todavía. |

El extracto puede enlazar directamente a una publicación BOE (`url`) y exponer diario oficial, fecha y `cve`; una relación BOE–BDNS puede ser determinista cuando existe una URL/identificador BOE explícito. No está demostrado que todos los extractos tengan dicho enlace ni que `cve` sea equivalente al identificador BOE canónico de InfoCs. No se implementan relaciones en esta fase.

Fuentes: [OpenAPI SNPSAP](https://www.infosubvenciones.es/bdnstrans/estaticos/doc/snpsap-api.json), [ejemplo oficial de detalle y extractos BOE](https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias/869664), [Real Decreto 130/2019](https://www.boe.es/buscar/act.php?id=BOE-A-2019-4671).

## Campos útiles para InfoCs

La búsqueda resumida declara: `numeroConvocatoria`, `descripcion` (título), `descripcionLeng`, `fechaRecepcion`, `nivel1`–`nivel3` del órgano y `codigoInvente`, además de `mrr`. En el detalle se documentan, entre otros:

- órgano convocante con niveles 1–3; sede electrónica;
- `fechaRecepcion` (fecha de recepción/registro en BDNS; no asumir que sea publicación);
- presupuesto total; tipo e instrumentos de convocatoria;
- tipos de beneficiario elegibles, sectores, región/regiones de impacto, finalidad y fondos;
- indicador de publicación del extracto en diario oficial;
- fecha de inicio y fin de solicitud, texto de esos periodos y booleano `abierto`;
- documentos anexos, con ID, nombre, descripción, longitud y fechas de modificación/publicación;
- extractos con número, títulos, URL, `cve`, diario oficial y fecha de publicación.

Los campos descriptivos (título, órgano, finalidad, documentos y extractos) son texto. `tipoAdministracion` es un filtro enumerado (`C`, `A`, `L`, `O`); los órganos pueden filtrarse por IDs, pero el mapeo de esos IDs a municipio/provincia requiere el catálogo/consulta correspondiente. `regiones` acepta IDs enteros; el API tiene una operación de catálogo que devuelve regiones en árbol, con etiquetas de estilo NUTS en los ejemplos. No se ha verificado que dicho árbol permita por sí solo resolver todos los municipios de Castellón.

La convocatoria no declara un campo provincial/municipal específico equivalente a INE. El órgano jerárquico y la región de impacto son señales estructuradas; su significado territorial exacto y cobertura deben validarse antes de diseñar el filtro Castellón. La fecha del extracto (`datPublicacion`) no debe intercambiarse con `fechaRecepcion`.

La especificación de detalle declara `anuncios[].texto` con tipo entero mientras `textoLeng` figura como texto; esa representación no es suficiente para inferir aquí cómo recuperar texto íntegro. No se recomienda usar esos campos hasta comprobar una respuesta real mínima y resolver la discrepancia.

No se encontró un campo único general de estado de convocatoria. Los campos `abierto`, fechas de solicitud y `sePublicaDiarioOficial` describen aspectos concretos, no un estado administrativo completo. Tampoco se asume que una palabra como «anulada» en el título sea un estado estructurado.

Fuentes: [OpenAPI SNPSAP](https://www.infosubvenciones.es/bdnstrans/estaticos/doc/snpsap-api.json), [detalle de convocatoria en portal oficial](https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias/869664).

## Transporte, paginación y operación

- Método: `GET` para la búsqueda, detalle, regiones y descarga individual documentados.
- Protocolo/formato: HTTPS y JSON para consultas; el documento binario individual se describe como `application/octet-stream`.
- Consulta: página indexada con `page` (ejemplo 0), `pageSize` (ejemplo 50), `order`, `direccion`, y filtros descritos arriba; no cursor. Respuesta con totales y posición/página.
- Fechas de búsqueda: `fechaDesde` y `fechaHasta`, formato documentado `dd/MM/yyyy`. La API llama `fechaRecepcion` a la fecha de recepción/registro del listado y el portal muestra un filtro «Fecha de registro», pero la especificación no vincula expresamente los parámetros del periodo a ese campo; tratar esa equivalencia como pendiente de confirmación en una consulta de muestra.
- Autenticación: no requerida/documentada para consultas públicas; bearer JWT sí aparece en ciertas operaciones de suscripción.
- Cabeceras, cookies, redirecciones, límite máximo de página, tamaño de respuesta y timeout: no fijados en la documentación revisada. No inventarlos como contrato; una futura implementación debe escoger límites conservadores, limitar concurrencia y respetar errores del servidor.
- Uso: la documentación advierte que los datos son dinámicos y pueden corregirse, insertarse, modificarse o eliminarse tras la extracción. IGAE puede restringir el acceso al API ante abuso manifiesto, riesgo de seguridad o uso fraudulento. No se publica un número concreto de solicitudes por minuto.

No se hizo consulta de datos al endpoint. La documentación es suficiente para elegir el mecanismo, no para certificar latencias, tamaños reales ni el comportamiento operativo de una respuesta actual.

## Documentos y relación con BOE

El detalle enumera documentos anexos. `GET /convocatorias/documentos?idDocumento=<id>` entrega un binario; `GET /convocatorias/zip?id=<Código BDNS>&vpd=<portal>` agrupa los documentos de la convocatoria. El API también incluye extractos con enlaces al diario oficial. No se descargaron documentos.

Política técnica inicial de InfoCs: conservar el enlace oficial de la convocatoria/extracto y no descargar ni espejar documentos; `mirror_documents: false` y `fulltext_publication: false`. Que el endpoint permita obtener un documento no obliga a hacerlo ni convierte cada adjunto en fuente de publicación autónoma.

## Reutilización y privacidad

**Clasificación: `REUSE_CONFIRMED_WITH_CONDITIONS`.** El Aviso Legal específico del SNPSAP permite expresamente reutilización comercial y no comercial de documentos del portal, incluyendo copia, difusión, modificación, adaptación, extracción, reordenación y combinación. También otorga una cesión gratuita y no exclusiva de derechos de propiedad intelectual que correspondan a esos documentos, dentro de las actividades necesarias para la reutilización autorizada. No se ha interpretado el acceso público como licencia: la base de reutilización es el Aviso Legal específico.

Condiciones expresas:

1. no desnaturalizar el sentido;
2. atribuir «Origen de los datos: Intervención General de la Administración del Estado»;
3. indicar la última fecha de actualización cuando conste en el original;
4. si se disocian datos personales, indicar que se hizo y quién lo hizo;
5. no insinuar participación, patrocinio o apoyo de IGAE;
6. conservar los metadatos de actualización y las condiciones de reutilización aplicables cuando se incluyan.

La autorización no elimina la protección de datos. El Aviso Legal y el art. 7.7 del RD 130/2019 limitan la reutilización de información personal a control/transparencia de la actividad pública y mejora de su gestión, archivo de interés público, investigación científica o histórica o estadística; el RD exige anonimización previa por el reutilizador. La publicación inicial de una convocatoria no implica que InfoCs deba republicar datos de beneficiarios, NIF/NIE u otros datos personales. Privacy Gate sigue siendo obligatorio. Para la primera versión se excluyen concesiones nominativas y texto íntegro; los títulos y demás metadata se someten a Privacy Gate antes de publicar.

El Aviso Legal aplica expresamente al uso de la información y documentos del SNPSAP/API, no por extensión inferida del aviso general de Hacienda. El API retorna además una advertencia legal en la respuesta. No se encontró requisito de autorización individual previa para la reutilización comprendida en estas condiciones; el uso implica aceptación de las condiciones. Esto no sustituye el cumplimiento de límites de finalidad/anonimización ni la revisión de cada campo.

El RD 130/2019 establece que cada Administración u órgano suministrador mantiene la propiedad y responsabilidad del contenido aportado, mientras IGAE administra y custodia la BDNS. Por prudencia, InfoCs limitará v1 a metadata factual y enlaces, no a reproducir documentos completos; si se pretende republicar adjuntos o extractos íntegros, habrá que analizar su contenido y derechos específicos.

Fuentes: [Aviso Legal del SNPSAP](https://www.infosubvenciones.es/bdnstrans/GE/es/avisolegal), [ayuda oficial de reutilización/API](https://www.infosubvenciones.es/bdnstrans/estaticos/ayuda/AYUDA%20-%20Sistema%20Nacional%20de%20Publicidad%20de%20Subvenciones%20y%20Ayudas%20P%C3%BAblicas%20v2023.pdf), [RD 130/2019, arts. 7 y 9](https://www.boe.es/buscar/act.php?id=BOE-A-2019-4671), [Ley 37/2007](https://www.boe.es/buscar/act.php?id=BOE-A-2007-19814).

## Alcance publicable provisional

Sujeto a Privacy Gate y atribución:

- Código BDNS de convocatoria, fecha de registro/recepción, fecha de publicación del extracto cuando exista;
- título, órgano, niveles administrativos y datos de presupuesto/solicitud no personales;
- categoría derivada por InfoCs, claramente diferenciada de los campos fuente;
- URLs del portal SNPSAP y del diario oficial.

Excluir por defecto de la primera versión: registros individuales de concesión/beneficiario, identificadores personales, texto íntegro y copia local de documentos. La API documenta fields de región de impacto, pero todavía no existe contrato suficiente para afirmar cobertura municipal/provincial exacta de Castellón.

## Incertidumbres y recomendación

- No se hizo llamada de datos al API; falta un smoke de lectura acotado en la fase de transporte para confirmar servidor, MIME real, esquema real, nombres de filtros regionales, advertencia devuelta y enlaces.
- No se verificó una estrategia definitiva para municipios de Castellón, organismos estatales con impacto local ni cambios retrospectivos. No diseñar aún el filtro territorial final.
- El límite de tasa, el tamaño máximo de página, timeout recomendado y continuidad del servicio no están publicados como valores numéricos.
- Hay más de un dominio de producción citado en el OpenAPI; el contrato v1 propone `www.infosubvenciones.es` como base primaria y no probará aliases sin necesidad.
- Los campos del extracto/texto necesitan inspección de muestra antes de incorporarlos como contenido.

**Recomendación:** `READY_FOR_BDNS_TRANSPORT`. Existe API pública documentada y una base oficial explícita para reutilización bajo condiciones. El transporte puede implementarse sin resolver todavía el filtro territorial final ni publicar contenido de concesiones/documentos.

## Fuentes oficiales examinadas

- [Portal y documentación API SNPSAP](https://www.infosubvenciones.es/bdnstrans/GE/es/doc)
- [Especificación OpenAPI SNPSAP, JSON](https://www.infosubvenciones.es/bdnstrans/estaticos/doc/snpsap-api.json)
- [Ayuda SNPSAP (incluye reutilización y API REST)](https://www.infosubvenciones.es/bdnstrans/estaticos/ayuda/AYUDA%20-%20Sistema%20Nacional%20de%20Publicidad%20de%20Subvenciones%20y%20Ayudas%20P%C3%BAblicas%20v2023.pdf)
- [Aviso Legal SNPSAP](https://www.infosubvenciones.es/bdnstrans/GE/es/avisolegal)
- [FAQ SNPSAP](https://www.infosubvenciones.es/bdnstrans/A13/es/faqs)
- [RD 130/2019 (BOE)](https://www.boe.es/buscar/act.php?id=BOE-A-2019-4671)
- [Ley 37/2007 (BOE)](https://www.boe.es/buscar/act.php?id=BOE-A-2007-19814)
