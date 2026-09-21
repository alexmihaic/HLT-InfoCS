InfoCs: especificación técnica y estratégica para un portal abierto de transparencia pública de Castellón
Fecha de la investigación: 20 de septiembre de 2026.
Ámbito adoptado: ambos — Castelló de la Plana y provincia de Castellón. Esta elección convierte el marcador territorial de la propuesta en una especificación operativa: las fuentes que ya cubren toda la provincia —como el BOP— se aprovecharían provincialmente desde el principio, mientras que los recolectores municipales específicos empezarían por Castelló de la Plana y se ampliarían progresivamente a otros ayuntamientos.

Criterio de estados usado en este informe: Comprobado significa que existe evidencia primaria u oficial suficiente; Recomendación es una decisión de arquitectura propuesta para InfoCs; Inferencia deriva razonablemente de las fuentes pero no es una capacidad expresamente garantizada por ellas; Pendiente identifica algo que no debe implementarse como hecho hasta una comprobación adicional.

Resumen ejecutivo, viabilidad y alcance
InfoCs es técnicamente viable con un coste recurrente adicional de 0 €/mes si se cumplen cuatro decisiones fundamentales: el repositorio permanece público; los procesos utilizan runners estándar de GitHub Actions; el portal es completamente estático y se publica mediante GitHub Pages; y Git se utiliza principalmente para código, datos estructurados, hashes, manifiestos y trazabilidad, no como almacén masivo de PDFs. GitHub confirma actualmente que el uso de Actions con runners estándar es gratuito en repositorios públicos y para GitHub Pages. 

La arquitectura recomendada es:

text
Copiar
FUENTES OFICIALES
      │
      ▼
RECOLECTORES MODULARES
      │
      ├── API / JSON / XML / CSV / feeds, cuando existan
      └── HTML / PDF, solo cuando sea necesario
      │
      ▼
CONTROL DE ENTRADA
tamaño · MIME · dominio · timeout · hash
      │
      ▼
NORMALIZACIÓN
esquema común de InfoCs
      │
      ▼
IDENTIDAD + DEDUPLICACIÓN + CAMBIOS
      │
      ├── nuevos
      ├── modificados
      ├── reaparecidos
      ├── ausentes en fuente
      └── errores de fuente
      │
      ▼
VALIDACIÓN
JSON Schema · reglas semánticas · privacidad
      │
      ▼
REPOSITORIO GIT PÚBLICO
      │
      ├── estado actual
      ├── eventos
      ├── manifiestos diarios
      ├── hashes
      └── salud de fuentes
      │
      ▼
GENERADOR ESTÁTICO
Astro + índice de búsqueda estático
      │
      ▼
GITHUB PAGES
      │
      ▼
infocs.hazlotuyo.pro
El proyecto no necesita una base de datos en producción. La fuente canónica puede ser un conjunto de JSON/JSONL versionados con Git. SQLite o DuckDB son útiles como artefactos generados para análisis, validación, exportaciones o estadísticas, pero no conviene convertirlos en la fuente canónica porque un fichero binario ofrece diffs de Git mucho peores que datos textuales.

El mayor riesgo de InfoCs no es el coste de cómputo. Son, por este orden, la protección de datos personales, las condiciones de reutilización de cada fuente, la fragilidad de algunos portales administrativos y el crecimiento de almacenamiento si se intentan conservar todos los documentos originales. La Ley 37/2007 permite y fomenta la reutilización de información del sector público, pero mantiene expresamente los límites de protección de datos y establece que determinada información no es reutilizable cuando la ponderación favorece el derecho fundamental a la protección de datos salvo disociación adecuada. 

Por ello, la principal decisión estratégica debería ser:

InfoCs v1 debe archivar exhaustivamente metadatos, procedencia, hashes y cambios, pero no copiar de forma indiscriminada todos los PDFs o páginas originales.

Esto además resuelve el problema económico. GitHub Pages establece actualmente un límite recomendado de 1 GB para el repositorio fuente, un máximo de 1 GB para el sitio publicado, un límite blando de 100 GB de ancho de banda mensual y un timeout de 10 minutos para despliegues. 
 Si se añadiese simplemente 1 MB de documentos nuevos al día, serían unos 365 MB de blobs al año antes de contar la historia de Git; a 5 MB diarios serían aproximadamente 1,8 GB anuales. Un archivo universal de PDFs acabaría chocando rápidamente con la arquitectura gratuita.

Conclusión de viabilidad: sí, InfoCs puede funcionar de forma sostenible con coste adicional recurrente de 0 €, pero el producto correcto no es “un espejo de toda la Administración”. Es un índice verificable, histórico y reproducible de actividad pública, con copias selectivas únicamente cuando su reutilización esté jurídicamente clara.

También debe evitarse un equívoco importante: Git proporciona un excelente historial público de cambios, pero un commit de GitHub no constituye por sí solo un registro inmutable o un sellado de tiempo independiente. Un historial puede reescribirse mediante force-push. El valor probatorio de InfoCs mejora enormemente con hashes, manifiestos encadenados, clones independientes y commits firmados cuando sea conveniente, pero el portal no debe afirmar que GitHub “certifica jurídicamente” que una Administración publicó algo a una hora determinada.

La neutralidad debería estar incorporada a la arquitectura, no solo a la declaración editorial. La portada debe ordenarse cronológicamente; todos los filtros y criterios territoriales han de documentarse; cualquier cálculo debe mostrar fórmula y datos de entrada; y la primera versión debería prescindir por completo de puntuaciones de “relevancia”, análisis de sentimiento, resúmenes políticos automáticos o generación de acusaciones.

Para normativa, además, InfoCs debería evitar presentar automáticamente una norma como “norma que afecta a Castellón”. Eso puede constituir una interpretación jurídica. Son preferibles etiquetas objetivas:

text
Copiar
Ámbito oficial: estatal / autonómico / provincial / municipal
Mención territorial: Castellón
Organismo afectado: Ayuntamiento de Castelló de la Plana
Coincidencia territorial: por organismo / municipio / texto / código oficial
Clasificación InfoCs: potencialmente relevante para el territorio
De ese modo queda claro qué dice la fuente y qué clasificación ha realizado el sistema.

Mapa de fuentes oficiales y estrategia de recopilación
No existe una única fuente capaz de proporcionar toda la actividad institucional solicitada. InfoCs debe construirse como una federación de recolectores especializados, dando prioridad al dato estructurado oficial y recurriendo al scraping únicamente en las áreas donde la administración no proporciona una alternativa mejor.

Fuentes verificadas y prioridad
Nivel	Fuente	Información útil	Mecanismo comprobado	Consulta InfoCs	Dificultad	Prioridad
Estatal	BOE	leyes, decretos, resoluciones, anuncios, normativa	API oficial OpenData para sumarios diarios y legislación consolidada	diaria	baja	MVP
Provincial	BOP Castellón	ordenanzas, presupuestos, empleo, urbanismo, anuncios, acuerdos y actividad local	HTML estructurado + descarga pública de anuncios/documentos	diaria	media	MVP
Municipal	Ayuntamiento de Castelló	plenos, juntas, transparencia, empleo, patrimonio, urbanismo	web/sede pública, principalmente HTML/documentos; API general no confirmada	diaria selectiva	media-alta	Fase pública/ampliación
Estatal/local	Plataforma de Contratación del Sector Público	licitaciones, adjudicaciones, importes, contratistas, modificaciones	infraestructura oficial de datos abiertos/OpenPLACSP	diaria	media	MVP
Estatal	BDNS / SNPSAP	subvenciones, ayudas y convocatorias	API REST oficial + exportación PDF/XLSX/CSV/JSON/XML	diaria	baja-media	MVP
Autonómica	DOGV	leyes, decretos, resoluciones, anuncios, convocatorias	web/PDF + metadatos XML descargables en resultados	diaria	media	MVP
Provincial	Datos abiertos Diputación	datasets provinciales	catálogo de datos abiertos con API expuesta en datasets	según dataset	baja-media	Fase ampliación
Provincial	Transparencia Diputación	contratación, convenios, subvenciones, economía	portal web/documental	diaria/semanal	media	Fase ampliación
Estatal/local	CONPREL Hacienda	presupuestos y liquidaciones EELL	Excel agregado + descarga detallada por entidad	periódica	baja-media	Fase ampliación
Autonómica	Sindicatura de Comptes	fiscalización, cuentas públicas, contratación, información económica	informes y datos declarados reutilizables	periódica	media	Fase ampliación
Autonómica	Portal Transparencia / datos abiertos GVA	múltiples datasets administrativos	catálogo/descargas; mecanismo exacto depende del dataset	variable	variable	Posterior
Estatal	Tribunal de Cuentas	fiscalización y rendición	mecanismo automatizable concreto pendiente de fijar	periódica	media	Posterior
Estatal	Catastro	cartografía/datos catastrales públicos reutilizables	no integrar hasta fijar dataset y condiciones concretas	periódica	alta jurídica	No MVP
Municipal	documentos individualizados de licencias/expedientes	urbanismo y expedientes	heterogéneo	—	alta	Solo tras revisión jurídica

BOE. Es una de las mejores fuentes del proyecto. La Agencia Estatal BOE mantiene una API oficial de datos abiertos. Están disponibles, entre otros recursos, la legislación consolidada y el sumario diario del BOE; el sumario puede consultarse por fecha y la API de legislación consolidada permite trabajar con fechas de actualización, búsquedas y paginación. 
 Esto permite construir el recolector sin scraping.

El BOE posee además unas condiciones de reutilización excepcionalmente claras: contempla reproducción, distribución, modificación, adaptación, extracción y reordenación, con condiciones como reconocer la fuente, no insinuar carácter oficial o patrocinio, conservar metadatos, identificar las modificaciones y respetar protección de datos. 
 Es, por tanto, una fuente idónea para la prueba técnica.

Para evitar que el BOE inunde InfoCs con toda la normativa estatal, conviene mantener dos canales:

text
Copiar
Normativa estatal general
└── disponible mediante filtro específico

Normativa con coincidencia territorial
└── Castellón / Castelló / organismos incluidos en entities.yaml
La segunda categoría no debería denominarse automáticamente “normativa aplicable a Castellón” salvo que esa circunstancia proceda explícitamente de los metadatos oficiales.

BOP de Castellón. El portal oficial de la Diputación permite navegar boletines y anuncios organizados por administraciones, ayuntamientos y otras categorías, por lo que existe suficiente estructura HTML para crear un recolector provincial. 
 En la investigación se observó además un endpoint público de descarga de anuncios que recibe un identificador de anuncio y un idioma. 

Ese endpoint no debe documentarse en InfoCs como una “API oficial”, porque no se ha localizado una especificación pública que garantice su estabilidad. Debe tratarse como:

yaml
Copiar
access_type: observed_public_download_endpoint
stability: undocumented
fallback: html_navigation
El BOP debería ser la fuente local más importante de InfoCs porque centraliza publicaciones de muchas administraciones de la provincia. Además permite abordar el ámbito provincial sin mantener inicialmente recolectores independientes para cada ayuntamiento.

Existe, sin embargo, una advertencia jurídica relevante. Las condiciones generales de la Diputación contienen por un lado reglas compatibles con la reutilización —citar la fuente, no alterar el sentido, mantener metadatos— y por otro una prohibición general de reproducción total o parcial de contenidos del portal. 
 Esto constituye una ambigüedad que debe resolverse documentalmente antes de convertir InfoCs en un espejo masivo de PDFs de Diputación/BOP. La estrategia prudente del MVP es almacenar metadatos, URL, hashes cuando se descarguen para procesarlos y datos normalizados; las copias públicas del fichero se activarían fuente por fuente tras comprobar su régimen concreto.

Ayuntamiento de Castelló de la Plana. La sede municipal ofrece categorías públicas relacionadas con órganos colegiados, contratación, transparencia, patrimonio, recursos humanos, subvenciones y urbanismo. 
 También existen páginas municipales de sesiones/órganos colegiados. 
 En esta investigación no se ha confirmado una API municipal general suficientemente documentada como para diseñar el sistema alrededor de ella.

Esto tiene una consecuencia práctica: no conviene empezar el proyecto por el Ayuntamiento, aunque intuitivamente parezca la fuente más importante. Los recolectores HTML municipales serán probablemente los primeros en romper ante rediseños, JavaScript, cambios de sede o reorganizaciones internas.

El orden aconsejado es:

text
Copiar
BOP / BOE / BDNS
        ↓
PCSP / DOGV
        ↓
Ayuntamiento de Castelló: plenos y documentos muy concretos
        ↓
resto del portal municipal
Contratación pública. El Ministerio de Hacienda mantiene la publicación de datos abiertos vinculados a la Plataforma de Contratación del Sector Público y documentación específica de OpenPLACSP. 
 Esta debe ser la fuente preferente para licitaciones y adjudicaciones frente a intentar extraer manualmente cada perfil del contratante municipal.

Durante la implementación conviene fijar en un test contractual la versión y estructura exactas que establezca la documentación vigente de OpenPLACSP. El informe confirma la existencia del canal oficial de datos abiertos, pero no debería congelar aquí un endpoint o formato interno concreto sin hacer esa verificación nuevamente cuando se escriba el recolector; es una dependencia susceptible de evolución.

Para el ámbito territorial, la mejor estrategia no es buscar simplemente la palabra “Castellón”, sino mantener un registro de organismos:

yaml
Copiar
entities:
  - id: castello_city
    names:
      - Castelló de la Plana
      - Castellón de la Plana
    administration_level: municipal
    source_identifiers:
      pcsp: ...
      bdns: ...
Después se irían incorporando Diputación, organismos autónomos, consorcios, empresas públicas y entidades locales de la provincia. El identificador de organismo es mucho más fiable que la coincidencia de texto.

BDNS / Sistema Nacional de Publicidad de Subvenciones y Ayudas Públicas. Es probablemente la segunda mejor fuente técnica después del BOE. El portal oficial proporciona documentación de API REST, recomendaciones de uso y exportaciones en PDF, XLSX, CSV, JSON y XML. 

Por ello, las subvenciones no deberían extraerse mediante scraping de páginas municipales cuando la misma convocatoria pueda identificarse en BDNS. InfoCs puede mantener la referencia original municipal o del BOP como relación adicional.

DOGV. Se ha comprobado el portal oficial del Diari Oficial de la Generalitat Valenciana y que los resultados ofrecen descarga de metadatos en XML. 
 Esto es suficiente para plantear un recolector estructurado antes de recurrir a parsear PDFs.

DOGV será especialmente útil para:

normativa autonómica;
subvenciones y convocatorias autonómicas;
empleo;
planeamiento y autorizaciones cuando se publiquen;
anuncios y resoluciones que mencionen entidades de Castellón.
La clasificación territorial debe registrar por qué se ha incluido cada resultado, por ejemplo authority_match, municipality_match o explicit_text_match, en vez de ocultar el criterio.

Diputación de Castellón. Dispone de portal de datos abiertos y de un portal de transparencia con secciones económicas, contratación, convenios y subvenciones. 
 En páginas de datasets del portal abierto se observa una API de catálogo/registros de estilo Opendatasoft v2.1, por lo que estos datasets pueden recolectarse de forma mucho más robusta que un scraper HTML. 

Presupuestos locales. El servicio CONPREL del Ministerio de Hacienda ofrece presupuestos y liquidaciones de entidades locales; a fecha de la investigación muestra datos de presupuestos de 2026 y liquidaciones de 2025 actualizados el 31 de agosto de 2026, con descargas agregadas en Excel y datos detallados por entidad local en fichero comprimido. 
 No es una fuente “diaria”, pero resulta valiosa para proporcionar una base financiera comparable y oficial.

Esto permite separar dos conceptos:

text
Copiar
Presupuesto aprobado/modificaciones
→ BOP + Ayuntamiento

Datos presupuestarios normalizados y liquidaciones
→ CONPREL

Fiscalización posterior
→ Sindicatura / Tribunal de Cuentas
Sindicatura de Comptes. Su portal proporciona informes y recursos sobre entidades locales, estados contables, contratación y otros datos económico-financieros, presentados expresamente como información abierta/reutilizable. 
 Es una fuente de mucho valor para una fase avanzada, pero su frecuencia natural es de fiscalización y rendición, no una novedad diaria.

Tribunal de Cuentas. Debe formar parte del mapa de fuentes, pero no incorporaría un recolector al MVP sin seleccionar primero el producto concreto —rendición local, informes, contratos u otro— y confirmar su mecanismo automatizable. Pendiente: no se ha verificado en esta investigación un endpoint general que justifique afirmar que existe una API apta para InfoCs.

Catastro. Debe recibir un tratamiento todavía más conservador. No usaría Catastro para construir perfiles de personas, propietarios ni inmuebles individuales. Pendiente: antes de incorporar cualquier producto catastral habría que seleccionar un servicio público concreto, verificar licencia y condiciones de reutilización y demostrar que el dataset no incorpora información personal cuyo tratamiento transforme sustancialmente el riesgo de InfoCs. En consecuencia, Catastro queda fuera del MVP.

Cobertura temática resultante
Con las fuentes anteriores, el sistema puede cubrir razonablemente:

Categoría InfoCs	Fuentes preferentes
normativa estatal	BOE
normativa autonómica	DOGV
ordenanzas y anuncios locales	BOP + Ayuntamiento
decretos/resoluciones	BOE/DOGV/BOP según nivel
contratación	PCSP/OpenPLACSP
subvenciones y ayudas	BDNS + BOP/DOGV
presupuesto aprobado	BOP/Ayuntamiento
liquidaciones presupuestarias	CONPREL
convenios	portales de transparencia
empleo y oposiciones	BOP/DOGV/sede municipal
urbanismo y planeamiento	BOP/DOGV/Ayuntamiento
plenos y juntas	Ayuntamiento
fiscalización	Sindicatura + posteriormente Tribunal
patrimonio	datasets/portales específicos
subastas	anuncios oficiales correspondientes
cambios posteriores	propio histórico InfoCs

Para urbanismo, empleo y expedientes administrativos debe aplicarse una regla especialmente estricta: publicar la existencia y metadatos del expediente no implica necesariamente que sea apropiado indexar todos los datos personales contenidos en sus anexos.

Marco jurídico, reutilización, privacidad y conservación de fuentes
El principio que debe dirigir InfoCs es sencillo:

“Públicamente accesible” y “reutilizable sin restricciones” no son sinónimos.

La Ley 19/2013 regula el acceso y la transparencia; su artículo 15 establece límites y ponderaciones en presencia de datos personales, y especifica que la normativa de protección de datos sigue siendo aplicable al tratamiento posterior de la información obtenida mediante el derecho de acceso. 

Por separado, la Ley 37/2007 regula la reutilización de información del sector público y admite condiciones como respetar el contenido, no desnaturalizar su sentido, citar la fuente y mencionar la fecha de actualización. También remite el tratamiento de datos personales a la normativa de protección de datos. 

Eso obliga a que InfoCs mantenga una ficha jurídica por fuente, no una única licencia global:

yaml
Copiar
source_id: bop_castellon

reuse:
  status: conditional       # allowed | conditional | unknown | restricted
  metadata_publication: true
  transformed_data: true
  mirror_documents: false
  fulltext_publication: false

terms:
  checked_at: 2026-09-20
  source: official
  notes: >
    Requiere revisión específica antes de habilitar
    mirroring de documentos.

privacy:
  default_document_policy: link_and_hash
  personal_data_review: required
Si mirror_documents es false o unknown, el código debe impedir técnicamente que el recolector haga commit público del PDF. La política jurídica no debería depender de que un programador recuerde una nota en el README.

Propiedad intelectual
Hay una excepción relevante en el texto refundido de la Ley de Propiedad Intelectual: su artículo 13 excluye de la protección por propiedad intelectual las disposiciones legales o reglamentarias y sus proyectos, resoluciones jurisdiccionales y los actos, acuerdos, deliberaciones y dictámenes de organismos públicos, además de sus traducciones oficiales. 

Pero esto no equivale a declarar libre de restricciones cualquier PDF alojado en una web pública. Un documento puede incorporar fotografías, planos, informes de terceros, bases de datos, marcas, datos personales u otros contenidos con un régimen distinto. Además, aunque un acto administrativo no esté protegido por derechos de autor, el tratamiento de datos personales incluido en él sigue sometido a la normativa correspondiente.

Protección de datos
El marco central es el RGPD y la LOPDGDD. La LOPDGDD remite expresamente el derecho de supresión a las reglas del artículo 17 del RGPD. 
 El propio RGPD regula principios como licitud, minimización, limitación de finalidad y conservación, además del derecho de supresión y la necesaria conciliación entre protección de datos y acceso público a documentos oficiales. 

Para InfoCs esto tiene una consecuencia arquitectónica muy importante:

Git no es un buen lugar para introducir datos personales que quizá tengan que ser suprimidos posteriormente.

Eliminar un nombre de main no lo borra del historial. Una eliminación real puede requerir reescribir la historia del repositorio y hacer force-push; además no permite retirar las copias que terceros ya hayan clonado.

Por tanto, el orden correcto es:

text
Copiar
FUENTE
  ↓
zona temporal del workflow
  ↓
detección preventiva de datos personales
  ↓
minimización / exclusión / cuarentena
  ↓
SOLO ENTONCES
  ↓
commit público
No al revés.

La base de datos normalizada debería aplicar estas reglas por defecto:

Tipo de dato	Política recomendada
nombre de cargo público actuando en su función	conservar cuando sea relevante y la publicación tenga respaldo
nombre de adjudicatario persona jurídica	conservar
nombre de persona física contratista/beneficiaria	evaluar fuente, finalidad y necesidad
NIF/DNI/NIE completo de persona física	no republicar por defecto
identificador fiscal de persona jurídica	posible, sujeto a fuente y finalidad
firma manuscrita	no copiar/indexar por defecto
teléfono particular	no republicar
correo particular	no republicar
correo institucional vinculado al cargo	evaluar necesidad
domicilio particular	excluir salvo justificación jurídica excepcional
IBAN	excluir
salud, ideología, afiliación sindical, religión, vida sexual, biometría, etc.	bloquear revisión automática/publicación
listados de opositores con DNI parcial y notas	no convertir automáticamente en base searchable de personas
bases de convocatoria/oposición	sí, normalmente mediante metadatos/enlace
resoluciones de nombramiento	evaluar según contenido y base legal

La Ley de Transparencia diferencia precisamente los datos meramente identificativos relacionados con la organización/actividad pública de otras categorías y exige ponderación en numerosos supuestos. 

Por eso una regla como “si está en Google, InfoCs puede copiarlo” sería jurídicamente inaceptable.

Protección preventiva contra información personal accidental
Antes de guardar texto extraído podrían ejecutarse detectores conservadores de:

text
Copiar
DNI / NIE
IBAN
direcciones de correo
teléfonos
patrones de firmas/certificados
palabras indicadoras de categorías sensibles
Una coincidencia no debería producir una censura automática irreversible; debería convertir el documento en:

json
Copiar
{
  "publication_status": "quarantine",
  "reason": "possible_personal_data",
  "source_url": "...",
  "metadata_public": true,
  "full_text_public": false
}
Para el MVP evitaría directamente OCR de documentos escaneados. Si el PDF no proporciona metadatos/texto accesible de manera segura, InfoCs puede registrar título, fecha, fuente y enlace sin intentar convertir cada página en texto.

Enlazar, almacenar, transformar y republicar
Es esencial distinguir jurídicamente cuatro actividades:

Acción	Qué hace InfoCs	Riesgo
Enlazar	remite a la URL oficial	bajo
Almacenar copia	conserva HTML/PDF original	medio/alto
Transformar	extrae título, fechas, importe, organismo…	variable
Republicar	vuelve a poner el contenido a disposición del público	mayor

La estrategia recomendada para el MVP es:

text
Copiar
Siempre:
  URL oficial
  metadatos
  fecha de comprobación
  hash cuando el fichero haya sido descargado
  estado
  procedencia

Cuando las condiciones lo permitan:
  datos estructurados transformados
  fragmentos estrictamente necesarios

Solo tras política fuente específica:
  documento original
  texto completo
  captura completa de página
El hash SHA-256 es especialmente útil, pero hay que explicarlo correctamente: un hash no permite reconstruir el documento. Sirve para demostrar que una copia posterior es idéntica al contenido observado entonces, pero si ni InfoCs ni nadie conserva la copia original, el hash no demuestra por sí solo qué decía el documento.

El BOE constituye un buen ejemplo del modelo correcto porque sus condiciones de reutilización permiten amplias operaciones siempre que se mantenga procedencia, fecha y diferenciación respecto de la publicación oficial. 

También es recomendable mantener un mecanismo público de rectificación:

text
Copiar
/metodologia
/privacidad
/correcciones
/contacto
y registrar una corrección como evento del sistema sin mantener públicamente el dato personal que se haya decidido retirar.

La Ley 37/2007 además atribuye al reutilizador responsabilidad por el uso que hace de los conjuntos de datos; la existencia de una fuente administrativa no transfiere a la Administración la responsabilidad de las transformaciones propias de InfoCs. 

Neutralidad jurídica y editorial
InfoCs no debería afirmar automáticamente:

“contrato irregular”;
“sobrecoste”;
“favoritismo”;
“corrupción”;
“incumplimiento”;
“esta ley perjudica a Castellón”.
Sí puede afirmar, de forma trazable:

text
Copiar
Importe de adjudicación oficial: X
Importe de licitación oficial: Y
Diferencia calculada por InfoCs: Y - X
Fuente: ...
Fórmula: ...
Lo mismo se aplica a estadísticas. Una página “10 mayores adjudicaciones del mes” es aceptable como cálculo descriptivo si se explica exactamente qué universo de contratos incluye. Una página “las 10 adjudicaciones más sospechosas” introduciría un juicio editorial que contradice el objetivo del proyecto.

Recomendación jurídica global: antes de abrir públicamente el índice de personas o el mirroring de documentos, un profesional especializado en protección de datos y reutilización de información pública debería revisar el modelo. Este informe identifica riesgos y propone controles, pero no sustituye un dictamen jurídico.

Arquitectura, repositorio, modelo de datos e histórico verificable
Elección tecnológica
Para InfoCs recomiendo:

Componente	Elección	Motivo
Recolectores	Python	excelente ecosistema HTTP/XML/HTML/PDF/datos
Validación	JSON Schema + modelos Python	contrato explícito
Datos canónicos	JSON + JSONL	legibles, diffables y portables
Analytics/build	DuckDB opcional, generado	consultas potentes sin servidor
Base SQLite	solo exportación opcional	no usar como verdad canónica
Portal	Astro estático	buena combinación de páginas estáticas y componentes
Búsqueda	índice estático tipo Pagefind	sin backend
Automatización	GitHub Actions	integrado con el repo
Hosting	GitHub Pages	gratuito para repo público
Histórico	Git + eventos + manifiestos	trazabilidad reproducible
Runtime backend	ninguno	menor coste y superficie de ataque

Entre las alternativas:

Astro es mi primera opción porque permite tratar el portal como aplicación de datos pero producir HTML estático. Es más cómodo que Hugo para integrar posteriormente componentes de visualización y más adecuado que Jekyll para un pipeline donde Python prepara muchos datos externos.

Eleventy sería mi segunda elección si se quisiera minimizar todavía más la complejidad del frontend.

Hugo resulta atractivo si el volumen acaba siendo enorme y el tiempo de generación estática se convierte en el principal problema, pero obliga a mantener una separación tecnológica mayor entre Python y plantillas Go.

Jekyll funciona bien con GitHub Pages, pero su ventaja histórica de integración nativa importa menos cuando el proyecto ya necesita GitHub Actions para ejecutar recolectores y validaciones.

SQLite no es necesario como servidor. Un fichero infocs.sqlite podría generarse como descarga para investigadores.

DuckDB sería todavía más útil internamente para consultas analíticas durante el build, pero tampoco debe subirse como estado canónico.

Organización propuesta del repositorio
text
Copiar
infocs/
├── .github/
│   └── workflows/
│       ├── collect.yml
│       ├── deploy.yml
│       ├── audit.yml
│       └── dependency-check.yml
│
├── collectors/
│   ├── boe/
│   │   ├── collector.py
│   │   ├── parser.py
│   │   └── fixtures/
│   ├── bop_castellon/
│   ├── bdns/
│   ├── pcsp/
│   ├── dogv/
│   ├── dipcas_open_data/
│   └── ayuntamiento_castello/
│
├── src/
│   └── infocs/
│       ├── fetch/
│       ├── normalize/
│       ├── identity/
│       ├── dedupe/
│       ├── diff/
│       ├── validate/
│       ├── privacy/
│       ├── manifests/
│       └── exports/
│
├── config/
│   ├── sources.yaml
│   ├── entities.yaml
│   ├── categories.yaml
│   └── privacy-rules.yaml
│
├── schemas/
│   ├── record.schema.json
│   ├── event.schema.json
│   ├── source.schema.json
│   └── manifest.schema.json
│
├── data/
│   ├── records/
│   │   ├── boe/
│   │   ├── bop_castellon/
│   │   ├── bdns/
│   │   └── ...
│   ├── events/
│   │   └── 2026/
│   │       └── 09/
│   │           └── 20.jsonl
│   ├── manifests/
│   │   └── 2026/
│   │       └── 09/
│   ├── health/
│   │   └── sources.json
│   └── exports/
│
├── archive/
│   ├── README.md
│   └── allowed/
│
├── site/
│   ├── src/
│   ├── public/
│   └── astro.config.*
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contracts/
│   └── fixtures/
│
├── docs/
│   ├── methodology.md
│   ├── data-model.md
│   ├── sources.md
│   ├── reuse-policy.md
│   ├── privacy.md
│   └── architecture.md
│
├── LICENSE
├── README.md
└── pyproject.toml
El directorio archive/ debería existir precisamente para dejar claro que hay una política de archivo, pero permanecer casi vacío en el MVP. Un documento solo entra si su fuente tiene una política mirror_documents: true.

Contrato común de cada recolector
Todos los adaptadores deberían exponer la misma interfaz conceptual:

python
Copiar
class Collector:
    source_id: str

    def discover(self, since):
        """Localiza elementos candidatos."""

    def fetch(self, candidate):
        """Recupera contenido oficial de forma segura."""

    def parse(self, response):
        """Convierte el formato origen en campos de la fuente."""

    def normalize(self, item):
        """Convierte el elemento al esquema InfoCs."""

    def healthcheck(self):
        """Comprueba si la fuente sigue siendo utilizable."""
Un nuevo recolector no debería modificar el motor de deduplicación, el generador web ni la lógica de Git.

Modelo de datos recomendado
En vez de una tabla plana gigantesca, conviene utilizar un núcleo obligatorio y bloques opcionales.

Obligatorios:

Campo	Función
schema_version	versión del contrato
id	ID estable InfoCs
source.id	fuente
authority.id/name	organismo
administration_level	municipal/provincial/autonómico/estatal
category	categoría normalizada
title	título oficial o normalizado
published_at	fecha de publicación cuando exista
detected_at	primera detección InfoCs
last_checked_at	última comprobación
source_url	enlace oficial
content_hash	hash del estado normalizado
status	estado

Opcionales pero muy importantes:

text
Copiar
official_id
expediente
event_date
description
municipality
province
cpv
amount
awardee
documents[]
tags[]
territorial_match[]
relations[]
source_license
Metadatos técnicos derivados:

text
Copiar
collector_version
normalizer_version
document_sha256
raw_sha256
extraction_method
changed_fields
Ejemplo:

json
Copiar
{
  "schema_version": "1.0",
  "id": "infocs:pcsp:example-id",

  "source": {
    "id": "pcsp",
    "official_id": "example-id"
  },

  "authority": {
    "id": "castello_city",
    "name": "Ayuntamiento de Castelló de la Plana"
  },

  "administration_level": "municipal",
  "category": "procurement.award",

  "title": "Ejemplo de contrato",

  "dates": {
    "published_at": "2026-09-20",
    "event_at": "2026-09-18",
    "detected_at": "2026-09-20T06:31:20Z",
    "last_checked_at": "2026-09-20T06:31:20Z"
  },

  "procurement": {
    "expediente": "EXAMPLE",
    "cpv": ["00000000"],
    "amount": {
      "value": "12345.67",
      "currency": "EUR",
      "type": "award"
    },
    "awardee": {
      "name": "Ejemplo adjudicatario",
      "type": "legal_entity",
      "tax_identifier": null
    }
  },

  "documents": [
    {
      "source_url": "...",
      "sha256": "...",
      "archived": false
    }
  ],

  "provenance": {
    "collector": "pcsp",
    "collector_version": "1.0.0",
    "territorial_match": ["authority_id"],
    "transformed_by_infocs": true
  },

  "content_hash": "...",
  "status": "active"
}
Los importes deberían representarse mediante decimal exacto —por ejemplo una cadena decimal— y no mediante float, para evitar errores de representación.

El adjudicatario merece un bloque propio porque “importe de licitación”, “valor estimado”, “presupuesto base” e “importe adjudicado” no son equivalentes. El modelo debe evitar mezclarlos en un único importe.

Identidad, duplicados y modificaciones
La prioridad para crear un ID debería ser:

text
Copiar
1. Identificador oficial estable
2. expediente + fuente + organismo
3. URL canónica estable
4. fingerprint compuesto
Nunca:

text
Copiar
hash(title)
como único ID, porque el título puede corregirse.

Un posible fingerprint de último recurso:

python
Copiar
fingerprint = sha256(
    source_id
    + authority_id
    + normalized_title
    + official_date
    + expediente_or_empty
)
Debe mantenerse separado:

text
Copiar
record_id
    identidad conceptual estable

content_hash
    estado actual de campos relevantes

document_sha256
    contenido exacto de un fichero

raw_sha256
    respuesta cruda observada
Para content_hash hay que excluir propiedades que cambian en cada ejecución:

text
Copiar
last_checked_at
request_duration
workflow_run
HTTP Date header
En cambio deben incluirse:

text
Copiar
title
description
amount
awardee
status
dates oficiales
document URLs
Así, volver a ejecutar el recolector sobre una fuente idéntica produce cero cambios funcionales.

Para cambios posteriores:

text
Copiar
record_id coincide
+
content_hash cambia
=
evento update
y el evento guarda explícitamente:

json
Copiar
{
  "type": "update",
  "record_id": "...",
  "detected_at": "...",
  "changed_fields": [
    "procurement.amount.value",
    "procurement.awardee.name"
  ],
  "previous_content_hash": "...",
  "new_content_hash": "..."
}
Esto es mucho más útil que depender únicamente del diff de Git.

Duplicados entre fuentes distintas
Un mismo hecho puede aparecer en PCSP, BOP, BDNS, DOGV o una sede. No debería eliminarse uno de ellos.

En lugar de:

text
Copiar
PCSP + BOP → borrar duplicado
conviene:

text
Copiar
PCSP record ──same_event_as── BOP record
porque la multiplicidad de fuentes también es información pública.

relations podría soportar:

text
Copiar
same_event_as
supersedes
amends
implements
related_contract
related_grant
related_agenda
related_minutes
Qué significa que algo “ha desaparecido”
Un scraper roto no debe convertirse en una falsa noticia sobre una administración.

Si ayer había un expediente y hoy no aparece, InfoCs debe registrar primero:

text
Copiar
missing_from_source
y no:

text
Copiar
deleted
Solo después de varias comprobaciones exitosas y completas de la misma fuente, o de un estado oficial explícito, se podría mostrar:

text
Copiar
Retirado/no localizado en la fuente desde...
Si el collector ha fallado, ninguna ausencia debe procesarse como eliminación.

Git como archivo histórico
La recomendación es combinar tres capas:

text
Copiar
records/
    estado actual

events/
    qué ocurrió cada día

manifests/
    qué ejecutó InfoCs y qué hashes produjo
Manifiesto diario:

json
Copiar
{
  "date": "2026-09-20",
  "started_at": "...",
  "finished_at": "...",

  "previous_manifest_sha256": "...",

  "sources": {
    "boe": {
      "status": "ok",
      "new": 3,
      "updated": 1
    },
    "bop_castellon": {
      "status": "ok",
      "new": 12,
      "updated": 0
    },
    "ayuntamiento_castello": {
      "status": "error",
      "error_class": "parse_error"
    }
  },

  "records_manifest_sha256": "..."
}
El previous_manifest_sha256 forma una cadena de hashes entre días. No convierte Git en blockchain ni impide una reescritura, pero hace que cualquier modificación retrospectiva sea detectable por cualquier tercero que conserve una versión anterior.

Los commits pueden resumirse así:

text
Copiar
data: 2026-09-20 +32 ~4 restored:1 errors:1
De este modo el propio historial de Git se convierte en una interfaz ciudadana secundaria: cualquiera puede revisar el commit y observar exactamente qué cambió.

Automatización, seguridad, monitorización, portal y dominio
Automatización diaria con GitHub Actions
GitHub Actions puede ejecutar workflows programados. La documentación vigente permite programación mediante cron, incluso con zona horaria, con un intervalo mínimo de cinco minutos. GitHub advierte que los jobs programados pueden retrasarse cuando hay alta demanda, especialmente al comienzo de cada hora, e incluso que determinados jobs en cola pueden descartarse; también desactiva schedules en repositorios públicos que llevan 60 días sin actividad. 

Por esa razón no programaría InfoCs a las 06:00. Utilizaría minutos poco habituales y dos oportunidades diarias, por ejemplo:

yaml
Copiar
on:
  schedule:
    - cron: "17 6 * * *"
      timezone: "Europe/Madrid"
    - cron: "43 18 * * *"
      timezone: "Europe/Madrid"

  workflow_dispatch:
La segunda ejecución proporciona redundancia sin coste de minutos en un repositorio público con runners estándar. 

No hace falta necesariamente publicar dos veces si no hay novedades.

El flujo debe ser:

text
Copiar
collect
  │
  ├── boe
  ├── bop
  ├── bdns
  ├── pcsp
  └── dogv
       │
       ▼
aggregate
       │
       ▼
validate
       │
       ├─ error grave del conjunto → NO commit
       │
       └─ válido
            │
            ▼
          commit
            │
            ▼
          build
            │
            ▼
          deploy
La matriz debe usar:

yaml
Copiar
strategy:
  fail-fast: false
Cada collector escribe un resultado y un health.json, incluso cuando falla.

El agregador debe ejecutarse con semántica equivalente a:

text
Copiar
if: always()
de modo que un Ayuntamiento caído no bloquee el BOE, BOP, BDNS y PCSP.

La lógica crucial es:

python
Copiar
if source_run.status == "failed":
    keep_previous_records(source)
    never_infer_deletions(source)
    publish_health_error(source)
else:
    process_new_updates_and_absences(source)
Esta regla debería estar cubierta por test de integración.

GitHub limita actualmente un job en runner alojado por GitHub a seis horas y un workflow completo a 35 días, límites enormemente superiores a lo que debería consumir una ejecución de InfoCs bien diseñada. 
 Si un recolector diario necesita horas, el problema debe solucionarse en el recolector y no mediante más infraestructura.

Permisos y seguridad de Actions
Las fuentes son de confianza institucional en cuanto a procedencia, pero el contenido descargado debe considerarse datos no confiables desde el punto de vista informático. Un portal oficial comprometido, un PDF malformado o incluso un título que contiene caracteres especiales no debería tener capacidad de ejecutar instrucciones en el runner.

Las reglas mínimas:

text
Copiar
No ejecutar ficheros descargados.
No importar código descargado.
No hacer eval().
No pasar títulos/documentos a shell.
No ejecutar macros.
No abrir documentos mediante aplicaciones ofimáticas.
No seguir enlaces arbitrarios fuera de allowlist.
Cada fuente debe especificar dominios permitidos:

yaml
Copiar
allowed_hosts:
  - boe.es
  - www.boe.es
y después de cualquier redirección debe volverse a comprobar el hostname para impedir SSRF o saltos a infraestructuras no previstas.

Controles recomendados:

text
Copiar
timeout conexión
timeout lectura
máximo de redirecciones
máximo de bytes
MIME esperado
magic bytes cuando proceda
ratio máximo de descompresión
máximo de entradas en ZIP
límites de memoria
límite temporal por parser
User-Agent identificando InfoCs
backoff y reintentos limitados
Nunca se debe construir:

bash
Copiar
curl "$URL" | sh
ni equivalente.

El contenido HTML externo tampoco debe inyectarse mediante mecanismos de HTML sin escapar. InfoCs debería renderizar campos normalizados como texto; si posteriormente se admite HTML administrativo, habrá que sanitizar mediante una allowlist muy estricta.

Los jobs de recopilación deberían tener:

yaml
Copiar
permissions:
  contents: read
y carecer de secretos.

Solo un job final, que procesa artefactos ya validados, necesita:

yaml
Copiar
permissions:
  contents: write
Esto limita el impacto si un parser es comprometido.

GitHub advierte expresamente que workflows que elevan privilegios después de ejecutar código no confiable pueden exponer tokens o permitir ataques como cache poisoning. 
 Para InfoCs conviene evitar pull_request_target o encadenamientos privilegiados innecesarios.

Las dependencias deben fijarse a versiones concretas; las GitHub Actions de terceros deberían fijarse por commit SHA en producción. Dependabot puede proponer actualizaciones, pero no deberían fusionarse automáticamente si afectan a parsers críticos.

Monitorización sin servicios externos
No hace falta UptimeRobot, Sentry ni un SaaS para la primera versión.

Cada fuente debería mantener:

json
Copiar
{
  "source": "bop_castellon",
  "last_attempt": "...",
  "last_success": "...",
  "last_change_detected": "...",
  "consecutive_failures": 0,
  "last_http_status": 200,
  "records_seen": 143,
  "parser_version": "...",
  "status": "healthy"
}
Y el propio portal publicar una página:

text
Copiar
/estado-fuentes/
con:

Fuente	Última comprobación	Último éxito	Estado	Novedades
BOE	hoy	hoy	correcta	4
BOP	hoy	hoy	correcta	12
PCSP	hoy	hoy	correcta	7
Ayuntamiento	hoy	hace 2 días	degradada	—

Esto cumple simultáneamente monitorización y transparencia metodológica.

Hay que distinguir dos conceptos:

text
Copiar
source.last_success
→ ¿hemos podido consultar la fuente?

source.last_change_detected
→ ¿la fuente publicó algo nuevo?
Un boletín sin publicaciones nuevas durante un festivo no debe generar una alarma. Una fuente que InfoCs no ha podido consultar durante tres días sí.

Pruebas recomendadas:

Contract tests: guardan respuestas oficiales de ejemplo y comprueban que el parser sigue generando la estructura esperada.

Live smoke tests: intentan recuperar uno o dos recursos pequeños de la fuente real.

Anomaly tests: alertan ante situaciones como:

text
Copiar
0 elementos cuando normalmente hay cientos
+500 % de registros respecto de la mediana reciente
todos los títulos vacíos
100 % de los IDs han cambiado
todos los documentos devuelven HTML en lugar de PDF
Ante una anomalía, InfoCs debería detener solo la actualización de esa fuente, conservar el estado anterior y abrir o actualizar automáticamente una GitHub Issue.

El workflow completo puede fallar visiblemente cuando existe un error serio y aun así publicar los datos válidos de otras fuentes. No es necesario elegir entre “ocultar el error” y “parar todo”.

Diseño del portal
La navegación principal debería corresponderse con hechos administrativos, no con instituciones:

text
Copiar
Inicio
Contratación
Subvenciones y ayudas
Presupuestos
Normativa
Urbanismo
Empleo público
Plenos y órganos colegiados
Convenios
Concursos y subastas
Cambios detectados
Fuentes
Datos abiertos
Metodología
La portada:

text
Copiar
INFOCS
Actividad pública de Castellón desde las fuentes oficiales

Última actualización: 20/09/2026 · 06:42
Fuentes correctas: 7/8 · 1 con incidencias

Novedades detectadas hoy

06:31  [Contratación] ...
06:30  [BOP] ...
06:27  [Subvención] ...
...
Sin ranking editorial. Orden temporal descendente.

Cada ficha debería mostrar:

text
Copiar
Título

[Dato oficial] [Fuente: PCSP]

Organismo
Categoría
Fecha oficial
Fecha detectada por InfoCs
Última comprobación
Expediente
Importe
Adjudicatario

Fuente oficial
Documento oficial
Hash del documento

Cambios detectados
─────────────────────────
20/09/2026 Importe modificado
18/09/2026 Detectado por primera vez

Información procesada por InfoCs
─────────────────────────
Municipio normalizado: Castelló de la Plana
Categoría InfoCs: adjudicación
La separación visual entre “Dato oficial” e “InfoCs ha calculado/normalizado” debería formar parte del sistema de diseño.

La búsqueda puede ser completamente estática. Recomiendo generar un índice de texto con Pagefind o una solución equivalente al terminar el build. No habrá servidor de búsqueda, Elasticsearch, Algolia ni base de datos remota.

Los filtros pueden precalcularse:

text
Copiar
organismo
nivel administrativo
municipio
categoría
año/mes
estado
rango de importe
Las exportaciones:

text
Copiar
/data/latest.json
/data/YYYY/MM/DD.jsonl
/data/contracts.csv
/data/grants.csv
/feed.xml
deberían generarse durante el build, no mantenerse manualmente.

RSS merece estar en el MVP porque permite que periodistas, ciudadanos y otras herramientas sigan InfoCs sin depender de redes sociales.

No incorporaría Google Analytics ni un sistema de cuentas en v1. El portal puede funcionar sin cookies, login ni seguimiento de usuarios.

Conexión de infocs.hazlotuyo.pro
La configuración del lado de GitHub está claramente documentada para subdominios: un subdominio personalizado de GitHub Pages debe utilizar un registro CNAME cuyo valor sea el dominio Pages del usuario u organización, del tipo <cuenta>.github.io. 

Conceptualmente:

text
Copiar
Tipo:   CNAME
Nombre: infocs
Valor:  <CUENTA-GITHUB>.github.io
No:

text
Copiar
https://<CUENTA>.github.io/repositorio
y tampoco una IP hardcodeada para este subdominio.

La secuencia recomendada es:

text
Copiar
GitHub
  1. Verificar hazlotuyo.pro mediante el TXT generado por GitHub.
  2. Activar GitHub Pages en el repositorio.
  3. Definir infocs.hazlotuyo.pro como Custom domain.

Hostinger DNS
  4. Eliminar un A/AAAA/CNAME previo que choque con "infocs".
  5. Crear CNAME:
        infocs → <cuenta>.github.io

Comprobación
  6. Verificar propagación DNS.
  7. Activar Enforce HTTPS en Pages.
GitHub permite verificar la propiedad mediante un registro TXT y recomienda conservarlo; la verificación de un dominio protege también sus subdominios inmediatos frente al uso por otras cuentas de GitHub. 

La verificación previa es importante porque GitHub advierte que mantener un registro DNS apuntando a Pages cuando el sitio ya no está correctamente asociado puede permitir domain takeover. También desaconseja expresamente registros DNS wildcard como *.hazlotuyo.pro. 

GitHub Pages permite posteriormente activar HTTPS; la opción puede tardar en aparecer tras la configuración DNS. 

Si se publica mediante un workflow personalizado de GitHub Actions, GitHub indica que no es necesario un fichero CNAME en el artefacto construido; el dominio puede mantenerse desde Settings → Pages. 

Para este proyecto no veo utilidad en www.infocs.hazlotuyo.pro. El nombre público debe ser simplemente infocs.hazlotuyo.pro. Añadir un segundo subdominio no aporta nada y aumenta la configuración DNS.

Pendiente específico de Hostinger: la operación requerida es un CNAME estándar y la configuración exigida por GitHub está verificada en la documentación oficial vigente. En esta investigación no he podido recuperar de forma fiable el artículo actual de la base de conocimiento de Hostinger que documenta el recorrido exacto del hPanel, por lo que no doy por verificados los nombres concretos de sus menús. No debería escribirse en el README algo como “entra en X → Y → Z” hasta comprobarlo en la interfaz actual. La parte DNS necesaria, no obstante, queda inequívocamente definida por la documentación de GitHub.

MVP, proyectos de referencia, hoja de ruta, costes y riesgos
Proyectos similares de los que aprender
No recomiendo adoptar ninguno como base directa; sí estudiar sus decisiones.

Open States Scrapers mantiene un repositorio público específicamente dedicado a scrapers legislativos, escrito principalmente en Python y organizado alrededor de recolectores de fuentes gubernamentales. El repositorio continuaba activo en septiembre de 2026.

El aprendizaje para InfoCs es claro: cada fuente debe ser un módulo independiente con fixtures propios, no un gran scraper monolítico.

Kingfisher Collect, del ecosistema Open Contracting, es un proyecto Python cuyo propósito declarado es descargar datos OCDS y almacenarlos, y también seguía activo en septiembre de 2026.

Su lección más importante es conceptual: separar la recolección de la transformación. InfoCs debería poder guardar la observación de una fuente y normalizarla posteriormente sin acoplar ambos pasos.

Gobierto, desarrollado por Populate, se presenta como una plataforma de gobierno abierto open source, con componentes relacionados con open data, transparencia y visualización; su repositorio también registra actividad reciente en septiembre de 2026.

Su existencia demuestra que existe experiencia española relevante en civic tech y gobierno abierto. Sin embargo, InfoCs no necesita reproducir una plataforma de aplicación completa: su requisito de coste cero favorece deliberadamente una arquitectura mucho más pequeña, estática y orientada al archivo.

La decisión arquitectónica común que merece copiarse no es una interfaz concreta, sino:

text
Copiar
adaptadores independientes
+
esquema común
+
procedencia explícita
+
transformaciones reproducibles
+
código público
MVP recomendado
El MVP debería resistir la tentación de cubrir “todo Castellón” desde el primer día.

Imprescindible en la primera versión:

Componente	MVP
repositorio público	sí
esquema común	sí
histórico de eventos	sí
manifiestos diarios	sí
BOE	sí
BOP Castellón	sí
BDNS	sí
PCSP	sí
DOGV	recomendable ya en MVP público
portal Astro	sí
buscador	sí
filtros	sí
RSS	sí
JSON/CSV abiertos	sí
estado de fuentes	sí
metodología	sí
registro de licencias/condiciones	sí
subdominio	sí
archivo indiscriminado de PDFs	no
usuarios/cuentas	no
IA generativa	no
base de datos online	no

La primera prueba técnica podría reducirse incluso a:

text
Copiar
BOE
BOP Castellón
BDNS
porque representan tres situaciones distintas:

text
Copiar
API estructurada madura
portal provincial semi-estructurado
API administrativa especializada
Si esos tres funcionan bajo el mismo contrato, la arquitectura base es válida.

Fase de prueba técnica
Objetivo: demostrar que la cadena completa es reproducible.

Debe entregar:

text
Copiar
repositorio público
Python package
schema v1
sources.yaml
entities.yaml
collector BOE
collector BOP
collector BDNS
deduplicación
eventos
manifiesto
GitHub Action programada
tests
Criterios de aceptación:

text
Copiar
misma entrada ejecutada dos veces → cero duplicados

registro cambiado
→ evento update + changed_fields

fuente caída
→ conserva estado anterior

documento diferente
→ SHA diferente

registro inválido
→ no llega a main

posible dato sensible
→ quarantine

cada registro
→ fuente + URL + fecha detección
Fase de MVP público
Añadir:

text
Copiar
PCSP
DOGV
Astro
búsqueda
filtros
fichas
RSS
CSV/JSON
página de fuentes
página de errores
infocs.hazlotuyo.pro
Y, si la fuente municipal ha demostrado estabilidad suficiente:

text
Copiar
órdenes del día de plenos
actas
acuerdos publicados
El requisito de salida de esta fase no es “tener muchas fuentes”, sino que un ciudadano pueda entender qué ocurrió, cuándo lo detectó InfoCs y dónde está la publicación original.

Fase de ampliación
Incorporar progresivamente:

text
Copiar
Diputación Open Data
Transparencia Diputación
CONPREL
Sindicatura
más secciones del Ayuntamiento
otros municipios de la provincia
convenios
patrimonio
planeamiento
empleo
subastas
Los municipios provinciales deberían añadirse mediante un registro común de entidades, no clonando el proyecto para cada uno.

Fase de transparencia avanzada
Una vez que exista suficiente histórico:

text
Copiar
historial de importes
modificaciones de contratos
relaciones licitación ↔ adjudicación
relaciones convocatoria ↔ resolución
series presupuestarias
estadísticas por CPV
estadísticas por organismo
estadísticas por municipio
cambios de documentos
comparativas temporales
Los gráficos deben enlazar siempre el conjunto de registros que los genera.

Ejemplo correcto:

text
Copiar
Contratación adjudicada registrada por InfoCs en 2026
37,2 M€

[Ver los 314 registros incluidos]
[Descargar CSV]
[Metodología]
Funciones avanzadas que conviene aplazar
archivado universal de PDFs;
mapas catastrales vinculados a personas;
OCR masivo;
perfiles individuales de funcionarios o beneficiarios;
seguimiento de ciudadanos que aparecen en expedientes;
notificaciones personalizadas con cuentas de usuario;
NLP para “detectar corrupción”;
resumen político automático;
scraping completo de todas las sedes de la provincia;
base de datos PostgreSQL o servidor de API permanente;
actualización en tiempo real.
Todas aumentan coste o riesgo mucho más rápidamente que utilidad.

Coste estimado
Elemento	Solución propuesta	Coste adicional recurrente	Límites/riesgo
Código Git	repo público GitHub	0 €	evitar crecimiento de binarios
GitHub Actions	runners estándar, repo público	0 €	6 h/job; schedules no son garantía temporal absoluta
Portal	GitHub Pages	0 €	sitio ≤1 GB; 100 GB/mes soft
Dominio	hazlotuyo.pro existente	0 € adicional	renovación del dominio sigue siendo coste existente
DNS	DNS existente en Hostinger	0 € adicional previsto	depende del servicio de dominio ya contratado
HTTPS	GitHub Pages	0 €	requiere DNS correcto
DB producción	ninguna	0 €	JSON/JSONL
DuckDB	local en build	0 €	no es servicio
Buscador	índice estático	0 €	aumenta tamaño del build
Monitorización	Actions + Issues + health JSON	0 €	sin monitor externo
APIs oficiales	BOE/BDNS/etc.	0 € previsto	respetar condiciones/rate limits
Almacenamiento documental masivo	no incluido	0 € mientras se evite	principal punto de ruptura

GitHub confirma que Pages está disponible para repositorios públicos en GitHub Free. 
 También confirma que los runners estándar son gratuitos en repositorios públicos. 

Hay que prestar atención a los artefactos de Actions. GitHub Free incluye actualmente 500 MB de almacenamiento de artefactos en el plan indicado por su documentación de facturación; runners públicos gratuitos no significan almacenamiento de artefactos ilimitado. 
 Como el objetivo explícito es no introducir tarjeta ni facturación, InfoCs debería:

text
Copiar
no usar Actions artifacts como archivo documental
mantener retention-days muy bajo
no guardar PDFs allí
publicar el resultado definitivo mediante Git
GitHub indica además que si una cuenta no tiene método de pago válido el uso sujeto a cuota deja de funcionar al alcanzar el límite, en vez de ofrecer capacidad ilimitada. 
 Esto refuerza la necesidad de una arquitectura que no dependa de capacidad facturable.

Registro principal de riesgos
Riesgo	Severidad	Mitigación
PDF con datos personales	alta	no archivar por defecto; DLP/quarantine
Git conserva dato posteriormente suprimido	alta	minimizar antes del commit
términos de reutilización ambiguos	alta	policy por fuente; link+metadata
scraper municipal rompe	alta	fixtures + health + fallo aislado
falsa “eliminación”	alta	no inferir desapariciones si collector falla
duplicados	media	ID oficial + fingerprints
misma información en varias fuentes	media	relaciones, no eliminación
crecimiento del repo	alta	no PDFs masivos
Pages llega a 1 GB	media/alta a largo plazo	particionar/exportar, no incluir binarios
build supera 10 min	media a largo plazo	generación incremental/reducir páginas
Schedule omitido por GitHub	media	dos ejecuciones + estado visible
supply-chain dependency	alta	pinning + revisiones
contenido malicioso	alta	no ejecutar datos; límites y allowlists
sesgo editorial	alta reputacional	orden cronológico + metodología pública
interpretación jurídica automática	alta	etiquetas objetivas, no conclusiones
fuente cambia licencia	media	checked_at y auditoría periódica
API cambia formato	media	contract tests
source ID cambia	media	reconciliación y relaciones
dominio Pages secuestrable	alta	verificación TXT + sin wildcard

Transparencia del propio proyecto y especificación final para implementación
InfoCs debería ser casi tan fácil de auditar como las instituciones que observa.

El propio portal debe publicar como mínimo:

text
Copiar
Código fuente
Versión desplegada
Metodología
Modelo de datos
Lista de fuentes
Estado de cada fuente
Fecha de última consulta
Condiciones de reutilización
Historial de cambios del proyecto
Errores de recopilación
Transformaciones realizadas
Criterios territoriales
Política de privacidad
Política de archivo
Limitaciones conocidas
Licencia del código
Licencias/condiciones de los datos
No debe existir un proceso manual invisible mediante el cual ciertos resultados se incluyan y otros no.

Una fuente debería aparecer públicamente con una ficha semejante:

text
Copiar
BOP de Castellón

Nivel: provincial
Estado: operativo

Tipo de acceso:
HTML estructurado + descarga pública de anuncios

Frecuencia InfoCs:
2 comprobaciones diarias

Último intento:
20/09/2026 18:43

Último éxito:
20/09/2026 18:43

Última novedad:
20/09/2026 12:04

Recolector:
bop_castellon v1.4.2

Política documental:
No se archiva copia pública por defecto.

Condiciones revisadas:
20/09/2026

Problemas conocidos:
Endpoint de descarga no documentado como API estable.
Licencias del propio proyecto
Conviene separar tres capas:

Código. Recomiendo una licencia libre explícita como AGPL-3.0 si se desea que desarrollos derivados desplegados como servicios mantengan apertura. Otra opción razonable sería MPL-2.0 si se prefiere un copyleft menos amplio.

Documentación/metodología creada por InfoCs. Puede publicarse con una licencia abierta específica.

Datos. No debería aplicarse ciegamente una única licencia a todo data/, porque los registros proceden de fuentes con condiciones diferentes. Cada elemento debe mantener:

json
Copiar
"reuse": {
  "source_terms": "...",
  "source_license": "...",
  "checked_at": "...",
  "infocs_transformation": true
}
Solo los elementos creados realmente por InfoCs deberían recibir una licencia propia sin reservas.

Registro de fuentes como configuración
Una pieza central debería ser config/sources.yaml:

yaml
Copiar
sources:

  boe:
    name: Boletín Oficial del Estado
    level: state
    collector: boe
    access: official_api
    enabled: true

    schedule:
      expected_check: daily

    legal:
      reuse_status: allowed
      mirror_documents: conditional
      checked_at: 2026-09-20

    security:
      allowed_hosts:
        - boe.es
        - www.boe.es
      max_response_mb: 20

  bop_castellon:
    name: Boletín Oficial de la Provincia de Castellón
    level: provincial
    collector: bop_castellon
    access: structured_html
    enabled: true

    legal:
      reuse_status: conditional
      mirror_documents: false
      checked_at: 2026-09-20
La información jurídica pasa así de una página informativa a una restricción ejecutable.

Registro territorial
entities.yaml debe resolver el mayor problema del ámbito provincial:

yaml
Copiar
castello_city:
  type: municipality
  province: castellon

  official_names:
    - Castelló de la Plana
    - Castellón de la Plana

  aliases:
    - Ajuntament de Castelló
    - Ayuntamiento de Castellón

  identifiers:
    pcsp: null
    bdns: null

diputacion_castellon:
  type: provincial_government

  official_names:
    - Diputación Provincial de Castellón
    - Diputació de Castelló
Los identificadores reales se rellenarán únicamente tras comprobarlos en las respectivas fuentes.

Posteriormente se añadirá un catálogo oficial de municipios y organismos dependientes. Así todo el sistema comparte una única ontología territorial.

Contrato mínimo para un nuevo collector
Un agente que añada:

text
Copiar
collectors/nueva_fuente/
deberá proporcionar obligatoriamente:

text
Copiar
collector.py
parser.py
fixtures/
tests/
README.md
source config
policy legal
y pasar estos tests:

text
Copiar
test_discovery()
test_parse_fixture()
test_normalization()
test_id_is_stable()
test_duplicate_run_is_idempotent()
test_changed_record_creates_update()
test_source_failure_preserves_data()
test_response_size_limit()
test_redirect_allowlist()
test_personal_data_guard()
Pseudocódigo de la ejecución
python
Copiar
for source in enabled_sources:

    health = begin_health_check(source)

    try:
        candidates = collector.discover(state[source])

        observations = []

        for candidate in candidates:
            response = safe_fetch(
                candidate.url,
                allowed_hosts=source.allowed_hosts,
                timeout=source.timeout,
                max_bytes=source.max_response_bytes,
            )

            raw_hash = sha256(response.body)

            parsed = collector.parse(response)

            for item in parsed:
                record = collector.normalize(item)

                validate_schema(record)
                validate_semantics(record)
                validate_privacy(record)
                apply_archive_policy(record, source)

                observations.append(record)

        changes = reconcile(
            previous=current_records(source),
            observed=observations,
            source_run_complete=True,
        )

        write_records(changes)
        write_events(changes)

        health.success()

    except Exception as error:
        health.fail(error)

        # Fundamental:
        # No modificar el dataset previo de esta fuente.
        # No generar desapariciones.
        preserve_previous_records(source)

    finally:
        write_health(health)


validate_complete_repository()

manifest = build_daily_manifest()
manifest.previous_hash = previous_manifest_hash()
write_manifest(manifest)

if repository_changed():
    commit_changes()

build_static_site()
deploy_pages()
Criterios que debe cumplir el repositorio inicial
La primera implementación debería considerarse correcta solo si:

Idempotencia. Dos ejecuciones sobre la misma fuente producen el mismo dataset.

Trazabilidad. Cada campo importante puede remontarse a una fuente oficial.

Independencia. La caída de una fuente no bloquea las demás.

Reversibilidad. Se conserva el estado previo ante errores.

Observabilidad. Toda fuente expone su estado.

Neutralidad. No existen rankings o conclusiones políticas.

Privacidad por diseño. Datos de alto riesgo no entran automáticamente en Git.

Reproducibilidad. Un tercero puede clonar el repo y reconstruir la web.

Coste cero. No se requiere ninguna credencial de un proveedor de pago.

No caja negra. Modelos, transformaciones y fuentes se encuentran en el repo.

Fuentes primarias más relevantes consultadas
Fuente	Qué queda comprobado
BOE OpenData	API oficial, sumarios y legislación consolidada. 
BOE condiciones de reutilización	reutilización amplia con atribución y salvaguardas. 
BOP Castellón	navegación pública estructurada de boletines/anuncios. 
BOP descarga	endpoint público de descarga observado; no documentado como API estable. 
Diputación, aviso legal	condiciones de reutilización y restricciones que requieren cautela. 
Diputación Open Data	catálogo público de datos. 
Diputación Open Data API	endpoint de registros expuesto en datasets. 
Diputación Transparencia	contratación, convenios, subvenciones y economía. 
Sede Ayuntamiento Castelló	categorías públicas institucionales. 
DOGV	portal oficial y metadatos XML. 
Plataforma de Contratación	infraestructura oficial de datos abiertos/OpenPLACSP. 
BDNS/SNPSAP	REST API y múltiples formatos de exportación. 
CONPREL	presupuestos y liquidaciones EELL descargables. 
Sindicatura de Comptes	datos e informes abiertos/reutilizables. 
Ley 37/2007	reutilización y límites, especialmente protección de datos. 
Ley 19/2013	transparencia y ponderación de datos personales. 
Ley de Propiedad Intelectual	exclusión de determinados textos/actos públicos. 
LOPDGDD	derechos de protección de datos y supresión. 
RGPD	marco europeo de tratamiento, derechos y documentos públicos. 
GitHub Actions	gratuidad en repos públicos y límites actuales. 
GitHub schedules	retrasos posibles, mínimo 5 min y desactivación por inactividad. 
GitHub Pages	límites actuales de tamaño, ancho de banda y build. 
GitHub custom domains	CNAME de subdominio y HTTPS. 
GitHub domain verification	TXT y mitigación de takeover. 

Especificación final para el agente que construya InfoCs
El agente de programación que reciba este informe debería recibir como mandato inicial:

text
Copiar
PROYECTO
InfoCs

OBJETIVO
Crear un repositorio público y reproducible que recopile,
normalice, versiona y publique actividad institucional
de Castelló de la Plana y de la provincia de Castellón.

RESTRICCIONES
- coste recurrente adicional: 0 €
- repositorio GitHub público
- GitHub Actions
- GitHub Pages
- dominio: infocs.hazlotuyo.pro
- sin backend permanente
- sin base de datos remota
- sin APIs de pago
- sin IA obligatoria
- sin archivo masivo de PDFs
- sin secretos salvo necesidad demostrada
- no publicar datos personales de alto riesgo automáticamente

STACK
- Python para ingestión
- JSON / JSONL
- JSON Schema
- Astro estático
- búsqueda estática
- GitHub Actions
- GitHub Pages

COLLECTORS INICIALES
1. BOE
2. BOP Castellón
3. BDNS

SIGUIENTES
4. PCSP
5. DOGV

MODELO
records + events + manifests + health

REQUISITOS
- IDs estables
- SHA-256
- deduplicación
- detección de modificaciones
- eventos de cambio
- política por fuente
- pruebas con fixtures
- aislamiento de fallos
- fuente original en cada ficha
- última comprobación
- RSS
- JSON/CSV exportable
- metodología pública

NO IMPLEMENTAR AÚN
- Catastro individual
- perfiles de personas
- mirroring universal
- OCR masivo
- inferencias políticas
- análisis de irregularidades
- cuentas de usuario
- PostgreSQL
- VPS
La arquitectura debería considerarse satisfactoria cuando pueda ejecutarse íntegramente desde un fork público, producir exactamente el mismo modelo a partir de las mismas respuestas de prueba, mostrar sus propios fallos, distinguir datos oficiales de transformaciones de InfoCs y dejar un historial comprensible de qué fue nuevo o cambió cada día.

La idea central que debería preservarse durante toda la evolución es:

InfoCs no debe ser otro medio que decide qué noticia importa. Debe ser infraestructura pública de observación: fuentes oficiales, datos estructurados, cambios visibles, procedencia verificable y metodología abierta.

Con esa restricción, el proyecto puede empezar pequeño, funcionar sin infraestructura de pago y crecer durante años sin perder su característica más valiosa: que cualquier ciudadano pueda ir desde una cifra, un contrato, una subvención, una norma o un acuerdo mostrado por InfoCs hasta el dato oficial que lo originó, la fecha en que el sistema lo detectó y el historial exacto de las transformaciones realizadas.