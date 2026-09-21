# BOE — Auditoría de fuente

## Estado

- **Estado de auditoría:** `verified`.
- **Fecha de verificación:** 2026-09-21 (Europe/Madrid).
- **Alcance:** infraestructura pública oficial y condiciones de reutilización;
  no se ha escrito ni ejecutado un collector.
- **Resultado:** el mecanismo mínimo suficiente para una futura ingesta diaria
  es la API OpenData del **sumario diario**, no HTML ni PDF.

## Evidencia oficial consultada

- [Catálogo OpenData y especificación interactiva de API](https://www.boe.es/datosabiertos/api/api.php?lang=es).
- [Documentación técnica de la API de sumarios BOE](https://www.boe.es/datosabiertos/documentos/APIsumarioBOE.pdf).
- [FAQ oficial de datos abiertos del BOE](https://www.boe.es/datosabiertos/faq/boe.php).
- [Documentación técnica de legislación consolidada](https://www.boe.es/datosabiertos/documentos/APIconsolidada.pdf).
- [Condiciones generales de reutilización de la AEBOE](https://www.boe.es/informacion/aviso_legal/index.php?lang=es).

La información marcada como `official_documented` procede de esos documentos o
de sus descripciones de API. La marcada como `observed_undocumented` se limita
a una observación controlada y no se trata como una garantía de contrato.

## Servicios encontrados

| Servicio | Estado de evidencia | Finalidad | Decisión en 03A |
| --- | --- | --- | --- |
| API OpenData de sumario BOE | `official_documented` | Obtener el sumario de una fecha concreta | **Mecanismo recomendado** para la futura ingesta diaria. |
| URL XML/HTML/PDF por ítem del sumario | `official_documented` como URLs emitidas por el sumario | Consultar la publicación individual en los tres formatos | Documentos enlazados; no son el feed primario. |
| API OpenData de legislación consolidada | `official_documented` | Buscar y consultar normas consolidadas y sus metadatos | No sustituye al sumario diario; posible complemento futuro no incluido en 03A. |
| Datos auxiliares OpenData | `official_documented` | Materias, ámbitos y estados de consolidación | No necesarios para el contrato mínimo diario. |

No se han considerado blogs, clientes de terceros ni rutas inferidas.

## Mecanismo recomendado

```text
GET https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}
Accept: application/json
```

- `{fecha}` es obligatorio y usa `AAAAMMDD`; representa la fecha de
  publicación.
- La API está documentada como REST sobre HTTPS y `GET`; la documentación
  indica que otros métodos devuelven 403.
- No hay paginación documentada: una respuesta representa el sumario completo
  de ese día, pudiendo incluir más de un diario cuando hay edición
  extraordinaria.
- Formatos ofrecidos: JSON y XML. Se escoge JSON por ser estructurado y
  directamente interoperable; XML es una alternativa completa y documentada.
- La respuesta contiene `status` y `data`; una ejecución futura deberá validar
  ambos, no sólo el código HTTP.

No se recomienda construir el futuro collector con HTML o PDF: las URL de esos
formatos ya las expone el sumario estructurado para cada ítem.

## Endpoints auditados

| Candidato | Finalidad | Método / parámetros | Formato y `Content-Type` observado | Errores documentados | Estabilidad |
| --- | --- | --- | --- | --- | --- |
| `https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}` | Sumario diario | `GET`; `fecha` path, `AAAAMMDD` | JSON (`application/json`) o XML (`application/xml`) | 400, 404, 500 | `official_documented` |
| `https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{id}/metadatos` | Metadatos de una norma consolidada | `GET`; `id` path | XML en la prueba (`application/xml`); formatos según la API | 400, 404, 500 | `official_documented` |
| URL `url_xml` emitida por un ítem | Documento individual XML | `GET`; URL proporcionada por el sumario | `application/xml; charset=utf-8` en la prueba | No auditado como contrato independiente | `official_documented` como URL de salida; cuerpo `observed_undocumented` |
| URL `url_html` emitida por un ítem | Documento individual HTML | `HEAD` en la prueba; URL proporcionada por el sumario | `text/html; charset=UTF-8` | No auditado como contrato independiente | `official_documented` como URL de salida |
| URL `url_pdf` emitida por un ítem | Documento individual PDF | `HEAD` en la prueba; URL proporcionada por el sumario | `application/pdf` | No auditado como contrato independiente | `official_documented` como URL de salida |

La documentación del sumario muestra `url_pdf`, `url_html` y `url_xml` y los
metadatos de tamaño del PDF. No documenta un hash oficial de documento; no se
ha hallado uno en la respuesta del sumario auditada.

## Identidad y procedencia

El campo oficial recomendado para `source.official_id` es `identificador` del
ítem de sumario. La documentación lo define como identificador de la
disposición o anuncio. El ejemplo oficial y la muestra comprobada conservan
`BOE-A-2024-10761` en el sumario y en las URLs XML, HTML y PDF.

`control` figura como dato de uso interno y no se adopta como identidad. No se
ha impuesto una expresión regular universal: el futuro collector debe conservar
el valor oficial literal y dejar que el core derive el `Record.id` con su
estrategia `official_id`.

Si algún ítem careciera de `identificador`, no se inventará una equivalencia
BOE: el core aplicará su estrategia de reserva documentada y el caso requerirá
observación explícita.

## Fechas y mapeo

| Dato BOE | Disponibilidad comprobada | Mapeo InfoCs | Nota |
| --- | --- | --- | --- |
| `sumario.metadatos.fecha_publicacion` | Obligatorio en la API diaria; `AAAAMMDD` | `dates.published_at` | Equivalencia objetiva: la documentación lo define como fecha de publicación. |
| `fecha_disposicion` | Documentado como opcional en metadatos de legislación consolidada; observado en el XML individual de la muestra | `dates.event_at` sólo cuando proceda de una representación con semántica documentada | No se inventará para ítems que no lo proporcionen. |
| `fecha_actualizacion` | Documentado en legislación consolidada, UTC `AAAAMMDDTHHmmSSZ` | Ninguno de los timestamps internos | Es una fecha oficial de esa representación, no `detected_at` ni `last_checked_at`. |
| `detected_at`, `last_checked_at` | No proporcionados por BOE | Internos de InfoCs | Los asignará el pipeline, nunca la fuente. |

El sumario diario no aporta una fecha de disposición por ítem en su contrato
documentado. La API de legislación consolidada no es un listado diario: no debe
usarse para inferir que una norma se publicó o cambió hoy.

## Territorialidad

El ámbito del sumario es estatal. No se ha encontrado en su contrato un campo
directo de municipio, provincia o una marca de relevancia para Castellón.

Señales realmente disponibles:

- código y nombre de sección;
- código y nombre del departamento;
- epígrafe cuando exista;
- título;
- texto del documento XML o HTML enlazado;
- en legislación consolidada, `ambito` estatal o autonómico.

Estas señales permiten diseñar después reglas objetivas y explicables, pero no
prueban por sí solas aplicabilidad a Castellón. Una coincidencia literal de
texto deberá registrarse como coincidencia de texto, nunca como conclusión
jurídica o política. No hay todavía filtro territorial implementado.

## Tipos y posible mapeo inicial

El sumario publica disposiciones y anuncios, ordenados por secciones. La FAQ
oficial identifica, entre otras, disposiciones generales (I), autoridades y
personal (II), otras disposiciones (III), administración de justicia (IV) y
anuncios (V), incluidos contratación pública (V.A) y otros anuncios oficiales
(V.B).

Posibles mapeos posteriores, no automáticos fuera de los casos objetivos:

| Señal BOE | Categoría InfoCs inicial posible | Límite |
| --- | --- | --- |
| Sección I | `normativa` | Revisar el tipo concreto de cada ítem. |
| Sección II.B | `empleo` | Corresponde a oposiciones y concursos según la FAQ. |
| Sección V.A | `contratación` | Es anuncio de contratación, no implica adjudicación. |
| Sección V.B | `subvenciones` u `otros` | Sólo cuando el contenido identifique objetivamente una convocatoria/ayuda. |
| Secciones III, IV y restantes | `otros` | Pendiente de reglas específicas. |

## Documentos

Cada ítem del sumario ofrece URL oficial de PDF, XML y HTML. El PDF dispone de
`szBytes`, `szKBytes` y páginas en el propio sumario. La documentación de la
FAQ indica que el PDF firmado es la versión oficial y auténtica; InfoCs no debe
presentar su propia normalización como texto oficial.

La política prevista sigue siendo **enlace + metadatos + SHA-256 cuando se
obtenga legítimamente**. No hay copia local obligatoria y esta fase no ha
archivado ningún documento ni guardado ninguna respuesta BOE. El único PDF
probado se consultó con `HEAD`; no se descargó.

## Reutilización

Las condiciones generales de la AEBOE se aplican por regla general, con la
salvedad de que algunos documentos pueden tener condiciones especiales. La
reutilización comercial y no comercial está permitida bajo esas condiciones,
incluida copia, difusión, modificación, adaptación, extracción, reordenación y
combinación.

Obligaciones relevantes para InfoCs:

- no desnaturalizar el sentido de la información;
- citar la fuente y enlazar a la sede de la AEBOE: «Fuente de los datos:
  Agencia Estatal Boletín Oficial del Estado»; para transformaciones, «Basado
  en datos de la Agencia Estatal Boletín Oficial del Estado»;
- no sugerir carácter oficial ni patrocinio o apoyo de la AEBOE;
- conservar los metadatos de actualización y condiciones de reutilización que
  acompañen al documento;
- identificar de forma clara las modificaciones o adaptaciones;
- respetar la normativa de protección de datos cuando haya datos personales.

El contrato configura la publicación de metadatos y datos transformados como
posible bajo condiciones. `mirror_documents: false` y
`fulltext_publication: false` expresan la política preventiva de InfoCs y su
regla de no mirroring por defecto; no afirman que la licencia general prohíba
toda reproducción.

## Automatización responsable

No se ha encontrado un límite oficial documentado de tasa, una frecuencia
recomendada ni un requisito de `User-Agent` en la documentación oficial de la
API, FAQ o condiciones de reutilización revisadas el 2026-09-21.

Propuesta para una fase posterior: una consulta diaria del sumario, sin
crawling histórico ni reintentos agresivos; identificarse con un `User-Agent`
claro y aplicar espera exponencial ante fallos transitorios. Es una medida de
cortesía operativa de InfoCs, no un límite atribuido al BOE.

## Errores y salud de fuente

La documentación declara 200 para éxito, 400 para identificador o parámetros
incorrectos, 404 cuando no existe la información solicitada y 500 para error
de servidor. Las pruebas confirmaron 400 y 404 con cuerpo XML.

| Situación | Resultado esperado | Clasificación futura |
| --- | --- | --- |
| Respuesta 200 con `status.code = 200` y esquema válido | Sumario disponible | Éxito completo de esa consulta. |
| Fecha válida sin publicación (domingo probado) y 404 | No existe el sumario pedido | Fuente accesible, pero no es una observación completa que permita inferir ausencias de registros. |
| 400 | Petición inválida | Fallo de ejecución/configuración; no inferir ausencias. |
| 5xx, red, TLS o contenido no válido | Fuente no fiable en esa ejecución | Fallo de fuente; conservar datos previos. |

No se ha observado ni está documentada una respuesta 200 con lista de ítems
vacía para el endpoint diario. Esa semántica no debe inventarse.

## Peticiones controladas realizadas

Todas se hicieron el 2026-09-21 con `User-Agent: InfoCs-source-audit/0.1`, sin
seguir redirecciones, sin ejecutar contenido y sin persistir cuerpos de
respuesta. Los tamaños son aproximados en bytes leídos o declarados.

| # | Finalidad | Método y URL | Estado | MIME | Tamaño | Redirect |
| ---: | --- | --- | ---: | --- | ---: | --- |
| 1 | Confirmar sumario XML | `GET https://www.boe.es/datosabiertos/api/boe/sumario/20240529` (`Accept: application/xml`) | 200 | `application/xml` | 176126 leídos | Ninguno |
| 2 | Confirmar sumario JSON | `GET https://www.boe.es/datosabiertos/api/boe/sumario/20240529` (`Accept: application/json`) | 200 | `application/json` | 315546 leídos | Ninguno |
| 3 | Probar fecha válida sin publicación (domingo) | `GET https://www.boe.es/datosabiertos/api/boe/sumario/20240526` (`Accept: application/xml`) | 404 | `application/xml` | 170 leídos | Ninguno |
| 4 | Probar parámetro inválido | `GET https://www.boe.es/datosabiertos/api/boe/sumario/no-fecha` (`Accept: application/xml`) | 400 | `application/xml` | 175 leídos | Ninguno |
| 5 | Confirmar documento XML enlazado | `GET https://www.boe.es/diario_boe/xml.php?id=BOE-A-2024-10761` | 200 | `application/xml; charset=utf-8` | 42150 leídos | Ninguno |
| 6 | Confirmar cabecera HTML enlazado | `HEAD https://www.boe.es/diario_boe/txt.php?id=BOE-A-2024-10761` | 200 | `text/html; charset=UTF-8` | cuerpo no solicitado | Ninguno |
| 7 | Confirmar cabecera PDF enlazado | `HEAD https://www.boe.es/boe/dias/2024/05/29/pdfs/BOE-A-2024-10761.pdf` | 200 | `application/pdf` | 263064 declarados | Ninguno |
| 8 | Inspeccionar sólo nombres de elementos temporales del XML individual | `GET https://www.boe.es/diario_boe/xml.php?id=BOE-A-2024-10761` | 200 | `application/xml; charset=utf-8` | 42150 leídos | Ninguno |
| 9 | Confirmar metadatos de legislación consolidada | `GET https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-1992-26318/metadatos` (`Accept: application/xml`) | 200 | `application/xml` | 1336 leídos | Ninguno |

La petición 8 sólo extrajo los nombres `identificador`, `fecha_publicacion` y
`fecha_disposicion`; no se guardó el documento. La petición 9 confirmó los
nombres `identificador`, `fecha_publicacion`, `fecha_disposicion`,
`fecha_actualizacion` y `ambito` documentados para legislación consolidada.

## Fixtures y cambios de código

- **Fixtures BOE conservadas:** ninguna.
- **Datos administrativos reales persistidos:** ninguno.
- **Código de collector, parser, persistencia o integración con el core:**
  ninguno.
- **Tests de collector:** ninguno; no se añade un analizador YAML ni una nueva
  dependencia sólo para validar este documento contractual.

## Riesgos y cuestiones pendientes

1. El sumario diario es nacional y no ofrece una señal territorial directa de
   Castellón. La política de inclusión será un diseño posterior, trazable y no
   inferencial.
2. El contrato detallado del cuerpo de `url_xml` individual no se ha auditado
   como API independiente. Su uso futuro requerirá limitarse a campos
   documentados o una auditoría adicional.
3. Legislación consolidada expone fechas y estado de consolidación de normas,
   pero no es un feed de novedades diarias. Su posible uso necesita una
   decisión posterior separada.
4. No se ha encontrado una tasa oficial publicada; la automatización deberá ser
   deliberadamente conservadora y revisar la documentación antes de producción.
5. Las condiciones de reutilización admiten documentos con condiciones
   especiales; el futuro collector deberá respetar cualquier condición
   específica que acompañe a un documento.

No se han detectado bloqueos objetivos del core. Esta fase no modifica su
arquitectura ni inicia la Fase 03B.
