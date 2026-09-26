# Auditoría de reutilización y publicación — BOP Castellón

**Revisada:** 2026-09-26

**Alcance:** determinar qué base oficial puede demostrarse para que InfoCs redistribuya información obtenida del BOP. Es una auditoría documental técnica, no un dictamen jurídico. No se consultaron copias de terceros.

## Decisión

**`REUSE_REQUIRES_SOURCE_CONFIRMATION`**

La documentación consultada acredita que el portal ofrece consulta y copias oficiales gratuitas, y que la Diputación publica condiciones generales de reutilización. No permite determinar con suficiente certeza que esas condiciones autoricen a InfoCs a republicar metadata o títulos del BOP: el aviso legal también prohíbe la reproducción total o parcial de contenidos de su Portal, prevé modalidades de licencia o solicitud previa y no aclara expresamente su aplicación al subdominio BOP ni a sus anuncios. Tampoco se pudo verificar el articulado de la ordenanza local ni del reglamento específico del BOP en los formatos servidos. No concluimos que la reutilización esté prohibida; la autorización aplicable a este conjunto concreto queda sin resolver.

Hasta obtener confirmación oficial o una base normativa/documental inequívoca, la decisión técnica es **no publicar metadata ni datos transformados del BOP**. Una futura fase 04D.1 debe fallar cerrada: `publication = hold`, `reason = reuse_policy_unresolved`. Se mantiene permitida únicamente la colección técnica necesaria para desarrollo y pruebas no publicadas, bajo las restricciones vigentes.

## Fuentes oficiales consultadas

- [Presentación e información del BOP Castellón](https://bop.dipcas.es/PortalBOP/informacion/) — describe la función del boletín, calendario, autenticidad de la edición electrónica, obtención de copias y correo de contacto.
- [Normativa del BOP Castellón](https://bop.dipcas.es/PortalBOP/normativa/) — enumera la Ley 5/2002, la ordenanza fiscal y el Reglamento Regulador del BOP.
- [Reglamento Regulador del BOP, enlazado desde Transparencia](https://transparencia.dipcas.es/es/transparencia_indicadores/public/descarga?id=c3baQraqv0Z5DdH5YcaTxg%3D%3D) — PDF oficial de siete páginas localizado; el lector de fuentes disponible no extrajo su texto, por lo que no se atribuye aquí ningún contenido a sus artículos.
- [Ordenanzas y Reglamentos Provinciales](https://transparencia.dipcas.es/es/indicador/informacin-sobre-la-diputacin-provincial/5-ordenanzas-y-reglamentos-provinciales) — página oficial, actualizada según ella el 02/06/2026, que publica la Ordenanza de Transparencia y Gobierno Abierto y el Reglamento del BOP.
- [Ordenanza de Transparencia y Gobierno Abierto, descarga oficial](https://transparencia.dipcas.es/es/transparencia_indicadores/public/descarga?id=hPu1a04snjn6DU7Ro39P8w%3D%3D) — el portal la sirve como ODT; el lector de fuentes no admite ese tipo de contenido. Su texto articulado no se pudo verificar en esta revisión.
- [Aviso Legal de la Diputación de Castellón](https://www.dipcas.es/es/aviso-legal.html) — apartados 5, 7 y 8, sobre ámbito de uso, propiedad intelectual/reproducción y reutilización.
- [Portal de Datos Abiertos de la Diputación: qué son los datos abiertos](https://datosabiertos.dipcas.es/pages/opendata/?flg=es) — describe los datos abiertos como conjuntos puestos a disposición para su uso y señala que los datasets incluyen licencia de uso; sus condiciones dependen de las leyes de reutilización y, en su caso, de derechos/licencias.
- [Ley 5/2002, reguladora de los Boletines Oficiales de las Provincias](https://www.boe.es/buscar/act.php?id=BOE-A-2002-6467) — fuente legislativa oficial BOE.
- [Ley 37/2007, sobre reutilización de la información del sector público](https://www.boe.es/buscar/act.php?id=BOE-A-2007-19814) — texto consolidado oficial consultado; establece modalidades y condiciones generales, no una licencia específica para este BOP.
- [Ley 19/2013, de transparencia, acceso a la información pública y buen gobierno](https://www.boe.es/buscar/act.php?id=BOE-A-2013-12887) y [Ley Orgánica 3/2018, de protección de datos personales](https://www.boe.es/eli/es/lo/2018/12/05/3/con) — marco oficial para separar acceso, reutilización y tratamiento posterior de datos personales.

No se usa el Real Decreto 1495/2011 como autorización aplicable a Diputación: su ámbito de desarrollo es el sector público estatal. Tampoco se usa normativa autonómica de otra comunidad.

## Hallazgos por cuestión

### A. Acceso público y copias oficiales

**Documentado.** La página de Presentación del BOP dice que la edición es electrónica, oficial y auténtica, y que cualquier usuario puede obtener copias oficiales y auténticas libre y gratuitamente mediante el sistema de seguridad del portal. También indica publicación ordinaria martes, jueves y sábados.

La Ley 5/2002 define el BOP como diario oficial y reconoce carácter oficial y auténtico a los textos publicados; además impone consulta pública y gratuita en Diputación y ayuntamientos. Esto acredita acceso/consulta y descarga de copias, **no un permiso separado para republicarlas**.

### B. Reutilización y licencias

**Documentado.** El Aviso Legal de Diputación reproduce condiciones generales de reutilización atribuidas al artículo 8 de la Ley 37/2007: no alterar el contenido, no desnaturalizar su sentido, citar la fuente, indicar la fecha de actualización cuando figure en el original, no sugerir patrocinio o apoyo institucional y conservar los metadatos de actualización y condiciones de reutilización que existan.

**Documentado.** El mismo apartado afirma que se prohíbe la reproducción total o parcial de los contenidos publicados en el Portal. Añade que los conjuntos de datos puestos de forma abierta se usan por cuenta y riesgo del reutilizador y contempla que, excepcionalmente y de forma motivada, Diputación pueda optar por licencia-tipo o reutilización previa solicitud.

**No encontrado/verificado.** No se localizó una licencia explícita específica para el BOP, sus anuncios o su metadata; tampoco una licencia específica asociada a cada anuncio o a los identificadores/títulos. La página de normativa del BOP enumera su Reglamento, pero el articulado no pudo leerse en esta revisión. El Aviso Legal no nombra expresamente “BOP” en el texto revisado.

El Portal de Datos Abiertos de Diputación explica que los conjuntos de datos pueden incorporar licencia de uso. No se encontró allí, en la información oficial revisada, un dataset BOP o una licencia asignada a este conjunto de anuncios; las licencias de otros datasets no se extrapolan al BOP.

### C. Alcance del Aviso Legal y tensión textual

**Documentado.** El BOP enlaza en su pie de página al “Aviso Legal” de `www.dipcas.es`. El Aviso Legal se presenta como condiciones del Portal de Internet de Diputación y advierte, a la vez, que las webs enlazadas desde `www.dipcas.es` pueden quedar sujetas a condiciones propias y fuera de responsabilidad de Diputación.

**No resuelto.** Ese enlace de pie no determina por sí solo si las condiciones del aviso general se extienden al subdominio `bop.dipcas.es`, ni si la prohibición de reproducción cubre los textos oficiales publicados en el boletín, las interfaces/base de datos del portal, la metadata factual o todas esas categorías. En el propio aviso coexisten condiciones generales de reutilización, una prohibición amplia de reproducción y una vía excepcional de licencia/solicitud. No resolvemos esa tensión mediante interpretación jurídica.

La Ley 37/2007 distingue modalidades: reutilización sin condiciones, con licencia-tipo o previa solicitud, entre otras. La ley general no demuestra cuál eligió Diputación para los anuncios o metadata del BOP. Por tanto, no se puede afirmar con estas fuentes que InfoCs necesite siempre una solicitud previa, ni que esté exenta de ella.

### D. Documentos, textos y metadata derivada

| Elemento | Qué se puede afirmar | Decisión InfoCs mientras se aclara |
|---|---|---|
| Consulta del portal y copias oficiales | El BOP declara acceso libre y gratuito a copias oficiales y auténticas. | Puede consultarse técnicamente; no republicar por ese solo hecho. |
| PDF/documento íntegro del boletín o anuncio | Hay enlaces de descarga oficiales; no se encontró permiso específico para redistribuirlos. | No archivar, replicar ni servir PDFs. |
| Texto completo/transcripción | El texto publicado es oficial/auténtico bajo Ley 5/2002; no se halló una licencia BOP que autorice su republicación por InfoCs. | No publicar fulltext ni extractos. |
| Identificadores, fecha, organismo, título u otra metadata factual | No se encontró licencia específica que distinga esta metadata del documento o del contenido del portal. La documentación general no permite resolver su reutilización en este caso. | Mantener `metadata_publication = false` y publicación en HOLD. |
| Categoría, municipio u otro dato transformado | Ser derivado no demuestra por sí solo autorización de reutilización; puede además reflejar contenido del anuncio. | No publicar hasta confirmación y revisión de privacidad. |

Esta tabla expresa la política provisional de InfoCs, no una conclusión de que la ley prohíba cada elemento.

### E. Datos personales

El BOP puede publicar notificaciones, edictos y otros actos con datos personales. Que un dato aparezca oficialmente en un boletín no elimina las obligaciones aplicables al tratamiento posterior que haga InfoCs. La Ley 37/2007 excluye la reutilización cuando, tras ponderar los intereses concurrentes, prevalezcan derechos de protección de datos, salvo disociación en los términos legales. La legislación de transparencia y protección de datos también mantiene un análisis propio para acceso y tratamiento posterior.

Por separado de la decisión de reutilización, InfoCs debe conservar obligatorio el Privacy Gate. La publicación original por el BOP no equivale a aprobación automática para redistribuir en InfoCs; no se aplicará redacción automática ni se usará la existencia de una publicación oficial como excepción de privacidad.

## Condiciones que se pueden exigir si se obtiene autorización

Como mínimo, cualquier publicación futura debe respetar las condiciones expresas que el Aviso Legal sí formula para la reutilización cuando resulten aplicables: atribución clara a la fuente; no alteración ni desnaturalización; fecha de última actualización si está en el original; no insinuar patrocinio o apoyo de Diputación; y conservar metadatos de actualización y de las condiciones de reutilización presentes. La aplicabilidad concreta al BOP debe confirmarse. El Aviso Legal no convierte esas condiciones generales en licencia expresa para el conjunto auditado.

## Consulta recomendada

Solicitar confirmación escrita a la Administración del BOP (`bop@dipcas.es`, contacto publicado en la página oficial del BOP) y, si procede, a la Oficina de Transparencia (`transparencia@dipcas.es`, contacto publicado por Diputación) sobre:

1. si el Aviso Legal de `dipcas.es` se aplica a `bop.dipcas.es` y a qué partes;
2. si la prohibición de reproducción se refiere también a los textos oficiales del BOP o a la reproducción del portal/base de datos;
3. qué modalidad de reutilización de Ley 37/2007 se aplica a metadata estructurada de anuncios BOP, incluyendo identificador, título, fecha, órgano anunciante, URL oficial y campos derivados;
4. si la reutilización requiere solicitud/autorización previa, licencia-tipo o atribución/condiciones adicionales;
5. enlace/versión vigente y artículos aplicables de la Ordenanza de Transparencia y del Reglamento Regulador del BOP.

Hasta resolverlo, 04D.1 debe mantener los anuncios BOP en `hold` por `reuse_policy_unresolved`; no persistir ni publicar metadata BOP real en el dataset público. La consulta técnica y las pruebas con fixtures sintéticas pueden continuar separadas de la redistribución.

## Límites de esta auditoría

- No se encontró una licencia específica de reutilización para BOP metadata.
- El PDF oficial del Reglamento Regulador del BOP y el ODT oficial de la Ordenanza se localizaron, pero el lector empleado no pudo extraer su texto; por ello su contenido material queda pendiente de lectura directa.
- No se descargaron documentos BOP ni se reprodujo el contenido de anuncios.
- No se determina aquí la titularidad de derechos sobre cada texto o documento ni se formula una conclusión jurídica definitiva sobre datos factuales, bases de datos o documentos oficiales.
- La fecha de actualización de la página de ordenanzas es la que publica el portal; la revisión se realizó el 26/09/2026.
