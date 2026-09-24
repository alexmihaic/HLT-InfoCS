# BOP Castellón — auditoría de fuente

## Estado y alcance

- **Estado:** `partially_verified`.
- **Verificado:** 2026-09-24.
- **Fuente examinada:** portal oficial de la Diputación Provincial de Castellón,
  `https://bop.dipcas.es/PortalBOP/`.
- **Alcance:** contexto de publicación, portal de consulta, enlaces y descarga
  individual observada, reutilización, privacidad y límites de uso.
- **Fuera de alcance:** no se implementó collector, no se descargó ningún PDF,
  no se consultó un intervalo histórico y no se guardó contenido de anuncios.

`partially_verified` describe el estado global de la fuente: el contrato técnico
de consulta por fecha y el HTML mínimo del listado ya se han reproducido, pero
siguen pendientes semánticas no necesarias para iniciar el transporte, como
autoridad normalizada, errores de fechas vacías y reutilización específica.
El portal no documenta públicamente los endpoints observados como API.

## Clasificación de la evidencia

- **DOCUMENTED:** texto de la sección Información del propio BOP y aviso legal
  general oficial de Diputación.
- **OBSERVED:** respuesta HTTP y estructura HTML/API vistas directamente en el
  portal durante esta auditoría.
- **DERIVED:** conclusión prudencial de InfoCs; no atribuye capacidades ni
  permisos a la Diputación.

## Editor, cobertura y calendario

**DOCUMENTED:** la página Información identifica al *Boletín Oficial de la
Provincia de Castellón (BOP)* como periódico oficial que publica disposiciones
generales, ordenanzas y actos, edictos, acuerdos, notificaciones, anuncios y
otras resoluciones de Administraciones Públicas y de la Administración de
Justicia de ámbito territorial provincial cuando así lo prevé la normativa.

**DOCUMENTED:** la edición es electrónica, oficial y auténtica. La página indica
que cualquier usuario puede obtener copias oficiales y auténticas libre y
gratuitamente mediante el sistema de seguridad del portal.

**DOCUMENTED:** publicación ordinaria los martes, jueves y sábados durante todo
el año. El texto consultado no detalla el calendario de extraordinarios,
festivos ni excepciones.

**OBSERVED:** la interfaz presenta opciones «Castellano» y «Valencià». En el
enlace de descarga de anuncio observado aparece `idioma=es`; no se comprobó el
valor valenciano ni que cada anuncio esté disponible en ambos idiomas.

**OBSERVED:** la consulta reproducible de archivo relacionó la fecha
24-09-2026 con el boletín 115 y `idBoletin=26878`; la fecha 22-09-2026 se
relacionó con el boletín 114 y `idBoletin=26877`. La fila muestra además los
códigos `B260924` y `B260922`, respectivamente. La primera asociación confirma
que había edición publicada para el jueves 24-09-2026.

## Territorialidad para InfoCs

**Decisión de alcance InfoCs:**

```text
collection_scope = province
province_code = 12
```

La inclusión futura se basará en que el anuncio forma parte de una edición del
BOP de Castellón. No se reutilizará el matching textual de BOE y no será
necesario extraer municipio u organismo para incluir el anuncio. Esos datos,
cuando puedan acreditarse en una fase posterior, sólo enriquecerán geografía,
autoridad y navegación.

Esta regla expresa pertenencia al boletín provincial; **no afirma** que cada
anuncio se aplique jurídicamente a todos los municipios de la provincia.

## Portal, búsqueda y endpoints

En las páginas oficiales consultadas no se encontró documentación de API
pública, OpenAPI, esquema JSON/XML ni contrato REST de consulta. Las rutas
`/api/...` se clasifican como
`observed_undocumented`, no como API oficial documentada.

| Mecanismo observado | Evidencia | Método/formato | Conclusión y límites |
| --- | --- | --- | --- |
| `/PortalBOP/` | HTTP 200; HTML UTF-8, 82 794 bytes | GET, `text/html; charset=UTF-8` | HTML renderizado por servidor; en la respuesta se observaron enlaces de edición y anuncios. No es una respuesta JSON/XML estructurada. |
| `/PortalBOP/informacion/` | HTTP 200; HTML UTF-8, 25 743 bytes | GET, `text/html; charset=UTF-8` | Fuente de los datos editoriales y del calendario descritos arriba. |
| `/PortalBOP/buscador/` | HTTP 200; HTML UTF-8 | GET y formulario JSF | El botón «Buscador de boletines» (`buttons:j_idt72`) responde con una redirección parcial a `/PortalBOP/boletinesAntiguos/`. |
| `/PortalBOP/boletinesAntiguos/` | HTTP 200; HTML UTF-8 | GET; formulario JSF con búsqueda AJAX | Permite consultar por número o por intervalo de fechas. POST con intervalo 22–24/09/2026 devolvió dos filas de edición en respuesta XML parcial que contiene HTML actualizado. No es API documentada. |
| `/PortalBOP/api/descargarBoletin?idBoletin={id}&idioma={idioma}` | Enlace emitido por HTML de la portada | Enlace de descarga; no se solicitó el PDF | Ruta observada. El parámetro `idBoletin` parece identificador interno numérico; no hay documentación de formato, estabilidad o unicidad global. |
| `/PortalBOP/api/descargarAnuncio?idAnuncio={id}&idioma={idioma}` | Enlace emitido por HTML; un HEAD al enlace observado devolvió 200 | HEAD; `application/octet-stream; charset=UTF-8`; `Content-Disposition` con nombre terminado en `.pdf`; sin longitud indicada | Descarga individual PDF observada sin recuperar el cuerpo. `idAnuncio` es un identificador numérico de portal observado, no documentado como identificador oficial estable. |

## Technical retrieval contract

Este contrato es **OBSERVED** y específico del HTML servido el 2026-09-24. No
es una API pública documentada; JSF/PrimeFaces puede cambiar nombres de
componentes, `ViewState` y markup.

### Navegación al archivo

La ruta directa de archivo funcionó con GET. También se observó esta navegación
desde el buscador inicial:

1. `GET https://bop.dipcas.es/PortalBOP/buscador/` → HTTP 200,
   `text/html;charset=UTF-8`.
2. El formulario `id="buttons"`, `method="post"`, con hidden
   `buttons=buttons` y el `javax.faces.ViewState` de ese mismo formulario,
   envía el botón `buttons:j_idt72` («Buscador de boletines») como petición
   PrimeFaces AJAX. El POST devuelve HTTP 200, `text/xml;charset=UTF-8`, con una
   redirección JSF parcial a `/PortalBOP/boletinesAntiguos/`.
3. Seguir esa redirección mediante GET, manteniendo la cookie jar. En esta
   auditoría la misma vista se pudo abrir directamente por su URL.

El formulario de búsqueda global del primer GET (`id="j_idt42"`) sólo ofrece
`j_idt42:searchInput` y el botón `j_idt42:j_idt45`; no contiene controles de
fecha o número. No debe confundirse con la búsqueda de ediciones del archivo.

### Consulta de edición por fecha o número

En `GET /PortalBOP/boletinesAntiguos/` se observó:

```text
form id:     buscadorForm
method:      POST
action:      /PortalBOP/boletinesAntiguos/;jsessionid={sesion}
hidden:      buscadorForm=buscadorForm
hidden:      javax.faces.ViewState={token dinámico del propio formulario}
text input:  buscadorForm:numBoletinAntiguo
text input:  buscadorForm:fechaInicialAntiguo_input
text input:  buscadorForm:fechaFinalAntiguo_input
submit:      buscadorForm:j_idt152 (texto visible: «Buscar»)
dateFormat:  dd/mm/yy
```

La acción del botón invoca `PrimeFaces.ab` para actualizar
`formListBoletinAntiguos formListAnunciosBolAnt buscadorForm
buscadorReducidaForm`. La petición AJAX observada incluye
`javax.faces.partial.ajax=true`, `javax.faces.source`,
`javax.faces.partial.execute`, `javax.faces.partial.render`, el nombre del
botón como parámetro y todos los hidden requeridos del formulario. Se envía
`Faces-Request: partial/ajax` y `X-Requested-With: XMLHttpRequest`.

La consulta de prueba puso el mismo rango acotado de dos fechas ordinarias en
los dos inputs, usando `22/09/2026` y `24/09/2026`. El POST respondió HTTP 200,
`text/xml;charset=UTF-8`; la respuesta parcial actualizó
`formListBoletinAntiguos` y contenía HTML con las filas de las dos ediciones.
Por tanto, para una sola fecha, la consulta puede expresarse con fecha inicial
y final iguales. La búsqueda por número existe como control
`numBoletinAntiguo`, aunque no se envió una consulta adicional por número.

Se mantuvo una cookie jar del mismo host en cada secuencia. El portal emitió
cookies llamadas `JSESSIONID`, `TS019819ec` y `TS01dc4fc6`; no se conservaron
valores. El `ViewState` es dinámico y debe obtenerse del GET inmediatamente
anterior: no versionarlo ni reutilizarlo entre sesiones. No se observó un
redirect HTTP 3xx en los POST, sino una instrucción de navegación dentro de XML
JSF. No se necesitó ni se utilizó navegador automatizado.

### Mapeo de edición comprobado

El HTML parcial del listado asoció estos valores en la misma fila/enlace:

| Fecha solicitada | Número mostrado | Código mostrado | `idBoletin` del enlace |
| --- | ---: | --- | ---: |
| 24-09-2026 | 115 | `B260924` | `26878` |
| 22-09-2026 | 114 | `B260922` | `26877` |

Los valores son **OBSERVED** en una misma fila de resultado. La lectura de que
`115`/`114` son el número correlativo del boletín y `B260924`/`B260922` el código
de edición es **DERIVED** de la posición y formato de la fila; el portal no
publica un esquema/contrato con nombres de campo. La fecha solicitada queda
relacionada inequívocamente con un `idBoletin` y una edición en estas dos
muestras.

`idBoletin=26878` coincide entre el enlace del boletín de la portada y la fila
de archivo fechada 24-09-2026. Es un identificador técnico del portal
provisionalmente utilizable como `source_edition_id`, no un número oficial
documentado. `idAnuncio=168123` se observó repetido en el listado y en el enlace
de descarga; un HEAD anterior validó el endpoint, sin descargar su PDF. No se
comprobó una vista valenciana ni el comportamiento del ID en años distintos.

### Estructura mínima del listado de anuncios

- El listado de anuncios está dentro del formulario
  `busquedaBoletinesForm` y se organiza en componentes PrimeFaces tipo
  `ui-accordion`.
- El título aparece en un `<span class="titulo4">`.
- El enlace de documento aparece como `<a href=".../api/descargarAnuncio?idAnuncio={id}&idioma=es">`
  dentro de un span con clase `linkDownloadFileCurrentAnuncioIcon`.
- La relación exacta de un item con un heading depende de la estructura anidada
  de IDs JSF (`busquedaBoletinesForm:j_idt93:...`). Es parseable en el HTML
  observado, pero los IDs posicionales no son un contrato estable.
- Los headings observados son agrupaciones/categorías y no prueban la identidad
  del organismo anunciante. No hay `authority_raw` por anuncio demostrado. No se
  encontró municipio estructurado.

La consulta de ediciones y la extracción de sus listados no requirió PDF. Los
PDF quedan como documentos enlazados; no se descargaron.

La secuencia exacta, los nombres de controles, cabeceras AJAX y cookies
observados se detallan en «Technical retrieval contract». El transporte futuro
deberá tratar este formulario como interfaz HTML observada, no como API pública
estable ni como un contrato documentado por Diputación.

### Identidad

- **Edición:** `idBoletin` (parámetro numérico observado). Para 24-09-2026,
  `26878` aparece tanto en el enlace de boletín de la portada como en la fila
  devuelta por la búsqueda de archivo; el enlace de descarga individual del
  boletín usa el mismo parámetro. Es un **identificador de portal observado**,
  no un identificador jurídico documentado. Persistencia entre idiomas y
  unicidad a largo plazo no verificadas.
- **Anuncio:** `idAnuncio` (parámetro numérico observado). El ID de muestra
  `168123` aparece en el listado y en su enlace oficial de descarga; una
  petición HEAD previa a ese enlace devolvió 200. La misma muestra se observó
  en respuestas repetidas del listado. Provisionalmente puede usarse como
  `source.official_id`, con la precisión: **stable portal identifier observed,
  not documented public identifier**. Vista valenciana no comprobada.
- **Fallback:** no inventar una equivalencia oficial. Si falta un identificador
  utilizable, una fase posterior debe aplicar la estrategia de identidad del
  Core con una URL oficial estable o un fingerprint y registrar la estrategia.

## Metadatos por anuncio, autoridad y geografía

**OBSERVED:** el listado de anuncios contiene acordeones por bloques, títulos en
`<span class="titulo4">` y enlaces PDF en
`<span class="linkDownloadFileCurrentAnuncioIcon"><a href=".../api/descargarAnuncio?idAnuncio=...&idioma=es">`.
El ID de anuncio y el título son extraíbles de HTML, sin PDF. El listado de
archivo de ediciones usa filas `<tr>` con enlace de descarga que incluye
`idBoletin`; los campos observados aparecen como número, fecha y código de
edición en la misma fila.

La fecha, número y código de edición sí se relacionaron con `idBoletin` mediante
la consulta de archivo, aunque sus nombres de columna y la garantía de
estabilidad del HTML siguen siendo observacionales, no documentados.

El HTML muestra headings de acordeón categoriales, pero no un campo por anuncio
que identifique inequívocamente al organismo anunciante. No se demostró una
jerarquía machine-readable de Diputación, ayuntamientos, mancomunidades,
consorcios u órganos judiciales. Tampoco se encontró un municipio estructurado.
El heading puede conservarse como `section_raw` si 04B confirma el selector; no
debe convertirse en `authority_raw`. Autoridad y geografía por anuncio se
difieren a 04C.

## Documentos

- La portada emite enlaces a una descarga del boletín y a descargas individuales
  de anuncio.
- La descarga individual observada responde como binario genérico y anuncia un
  nombre de archivo PDF. No se descargó el PDF ni se inspeccionó su contenido.
- No se verificó una URL HTML individual, XML, firma, CSV/JSON, hash oficial,
  metadatos de páginas ni tamaño de archivo.
- Los enlaces no contienen un parámetro de sesión en el patrón observado, pero
  no se garantiza estabilidad a largo plazo.

**Política InfoCs propuesta:** `link + metadata`; `mirror_documents: false` y
`fulltext_publication: false`. No almacenar boletines completos ni PDFs.

## Privacidad

Los tipos de contenido descritos por el propio BOP incluyen notificaciones,
edictos y procedimientos; pueden contener datos personales. El contrato declara
`privacy_gate_required: true`. La fase de extracción posterior debe aplicar el
Privacy Gate antes de cualquier publicación; la posibilidad de consultar
libremente una copia oficial no elimina esta obligación.

No se guardó texto de anuncios como fixture.

## Reutilización y derechos

La sección de Información del BOP describe el acceso gratuito a copias oficiales
y auténticas; no es por sí sola una licencia de reutilización.

El aviso legal general de `dipcas.es` contiene condiciones generales de
reutilización de información pública (entre ellas no alterar ni desnaturalizar,
citar fuente, indicar fecha de actualización cuando conste, no sugerir respaldo
y conservar metadatos), pero también contiene restricciones sobre reproducción
de contenidos del portal y limita determinados usos a extractos privados/de
investigación. No se encontró una licencia específica del BOP que resuelva cómo
se aplican esas cláusulas a los anuncios oficiales.

**Política prudencial InfoCs:** estado de reutilización `unknown`; no republicar
títulos ni texto transformado hasta revisión específica. Usar por ahora enlaces
oficiales y metadatos técnicos mínimos, con atribución a Diputación/BOP y sin
sugerir carácter oficial o patrocinio. Esto no es una conclusión jurídica ni
una afirmación de que la reutilización esté prohibida o permitida.

## Errores, uso automatizado y salud

- La portada, información y buscador observados respondieron HTTP 200.
- `robots.txt` en el host BOP respondió 404 Not Found. Esto no se interpreta como
  permiso ni prohibición de automatización.
- El HEAD al enlace oficial de descarga individual observado respondió HTTP 200.
- **No se probaron** fecha sin edición, anuncio inexistente, parámetros
  inválidos, errores 4xx/5xx ni redirects. No se asigna semántica de
  `no_publication`, `invalid_request` o `source_failure` a esos casos todavía.
- No se encontró documentación oficial de rate limits, frecuencia recomendada,
  User-Agent ni política técnica de automatización.

**Uso conservador futuro propuesto (DERIVED):** una consulta de listado por
ejecución, sin paralelismo ni polling; solicitar sólo los recursos necesarios;
no repetir descargas de documentos; detenerse ante respuestas inesperadas. La
frecuencia y los límites deben revisarse si Diputación publica instrucciones.

## Peticiones reales realizadas

Sólo al host oficial `bop.dipcas.es` y al dominio oficial de Diputación:

1. `GET https://bop.dipcas.es/PortalBOP/` — 200, HTML UTF-8, 82 794 bytes;
   identificar la portada, edición/listado y enlaces oficiales.
2. `GET https://bop.dipcas.es/PortalBOP/informacion/` — 200, HTML UTF-8,
   25 743 bytes; comprobar editor, cobertura, calendario, carácter oficial y
   gratuidad.
3. `GET https://bop.dipcas.es/robots.txt` — 404; comprobar política publicada
   de robots.
4. `GET https://bop.dipcas.es/PortalBOP/buscador/` — 200, HTML UTF-8,
   82 844 bytes; examinar estructura de formularios y si existe contrato de
   búsqueda estructurada.
5. `HEAD https://bop.dipcas.es/PortalBOP/api/descargarAnuncio?idAnuncio={observado}&idioma=es`
   — 200, `application/octet-stream; charset=UTF-8`, sin `Content-Length`,
   `Content-Disposition` con nombre `.pdf`; validar únicamente cabeceras del
   enlace individual, sin descargarlo.
6. `GET http://www.dipcas.es/es/aviso-legal.html` — 200,
   HTML UTF-8, 66 799 bytes; revisar las condiciones generales oficiales de
   reutilización y propiedad intelectual.

### Peticiones de 04A.1

En esta fase se hicieron **7 peticiones HTTP directas** (5 GET y 2 POST); el
primer POST sólo navegó al archivo y el segundo realizó una consulta acotada.
No hubo POST por separado para cada fecha:

1. `GET https://bop.dipcas.es/PortalBOP/buscador/` — 200, HTML UTF-8,
   82 839 bytes; leer formularios/campos visibles. No se envió POST en esta
   secuencia porque el proceso de inspección terminó.
2. `GET https://bop.dipcas.es/PortalBOP/buscador/` — 200, HTML UTF-8,
   82 844 bytes; inspeccionar acciones PrimeFaces, fields y estructura del
   listado, sin imprimir `ViewState`.
3. `GET https://bop.dipcas.es/PortalBOP/buscador/` — 200, HTML UTF-8,
   82 844 bytes; obtener sesión para la secuencia de navegación.
4. `POST https://bop.dipcas.es/PortalBOP/buscador/;jsessionid={sesion}` — 200,
   XML parcial de 144 bytes; botón `buttons:j_idt72`, respuesta ordenó navegar
   a `/PortalBOP/boletinesAntiguos/`.
5. `GET https://bop.dipcas.es/PortalBOP/boletinesAntiguos/` — 200, HTML UTF-8,
   57 866 bytes; identificar los inputs exactos del archivo. No se envió POST
   en esta inspección.
6. `GET https://bop.dipcas.es/PortalBOP/boletinesAntiguos/` — 200, HTML UTF-8,
   57 859 bytes; obtener un ViewState fresco para consultar el intervalo.
7. `POST https://bop.dipcas.es/PortalBOP/boletinesAntiguos/;jsessionid={sesion}`
   — 200, XML parcial de 35 898 bytes; intervalo inclusivo 22/09/2026 a
   24/09/2026. Devolvió sólo las dos filas de edición correspondientes a esas
   fechas.

Los valores de `JSESSIONID`, `ViewState` y otras cookies se omitieron. Los GET
repetidos se debieron a que cada inspección aislada descartó la sesión antes de
construir un POST reproducible; no se repitió el POST de consulta ni se volvió a
consultar ninguna URL de documento.

No se solicitaron PDFs, XML/HTML de anuncios individuales ni copias completas
de boletines. Las búsquedas web auxiliares se limitaron al dominio oficial
`dipcas.es` y no se usaron como sustituto de las observaciones del portal.

## Cuestiones diferidas

1. Confirmar si `idAnuncio`/`idBoletin` se conservan al cambiar a la vista
   valenciana y si siguen estables entre años; no hace falta para implementar
   04B con IDs de portal.
2. Verificar semántica de fecha sin edición, ID inexistente y parámetro
   inválido. 04B puede cubrir respuestas sintéticas sin atribuirles aún
   semántica oficial.
3. Precisar headers de columnas y confirmar nombres contractuales de fecha,
   número y código de edición; los valores observados sí se relacionan en cada
   fila.
4. Resolver si hay un `authority_raw` por anuncio y si puede extraerse
   municipio; se difiere a 04C.
5. Verificar disponibilidad de versiones de documento HTML/XML, firma, páginas
   y hash sin descargar cuerpos.
6. Resolver condiciones específicas de reutilización antes de publicar
   metadatos descriptivos o datos transformados. Esto no bloquea transporte y
   parser offline ni recolección técnica para desarrollo.
