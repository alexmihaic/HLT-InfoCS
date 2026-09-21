# Contrato de trabajo de InfoCs

## Fuente de verdad y alcance

- `docs/INFOCS_SPEC_v1.md` es la especificación funcional principal. Sus estados (`Comprobado`, `Recomendación`, `Inferencia` y `Pendiente`) deben conservarse al interpretar una decisión.
- Antes de implementar una fuente, verificar de nuevo su documentación oficial vigente. No inventar APIs, endpoints, formatos, identificadores oficiales ni capacidades de fuentes administrativas.
- Documentar toda desviación arquitectónica importante y cualquier contradicción o decisión abierta; no resolverla silenciosamente.

## Fuentes y collectors

- Priorizar mecanismos de acceso en este orden: API oficial; datos estructurados JSON/XML/CSV; RSS/Atom/feed; descarga estructurada; HTML; PDF.
- No sustituir silenciosamente una fuente estructurada por scraping. Si fuera necesario cambiar de mecanismo, documentar motivo, impacto y alternativa.
- Cada collector debe ser independiente: descubrir, recuperar, interpretar, normalizar y comprobar su salud sin acoplarse al resto del sistema.
- Una nueva fuente no debe requerir modificar el motor global salvo necesidad arquitectónica justificada y documentada.
- Tratar todo contenido externo como dato no confiable: no ejecutarlo, no importarlo como código, no interpolarlo en una shell ni renderizar HTML no saneado.

## Datos, histórico y fallos

- Los datos canónicos son formatos textuales versionables, principalmente JSON y JSONL. SQLite y DuckDB solo pueden utilizarse como artefactos derivados salvo decisión posterior documentada.
- Mantener separados la identidad estable del registro, el estado normalizado (`content_hash`) y los hashes de documento o respuesta cruda.
- El fallo de una fuente nunca puede eliminar ni invalidar datos anteriores válidos.
- Cuando falle un collector, conservar datos anteriores, registrar el error y no inferir eliminaciones. Una ausencia solo puede procesarse después de comprobaciones completas y exitosas o de un estado oficial explícito.
- Conservar procedencia, URLs oficiales, fechas de detección/comprobación, eventos y manifiestos. No presentar Git como certificación jurídica de publicación.

## Privacidad, reutilización y neutralidad

- No almacenar documentos completos públicamente salvo que la política de la fuente lo permita explícitamente.
- No introducir datos personales de riesgo en Git antes de pasar los controles de privacidad. La minimización, exclusión o cuarentena ocurre antes del commit público.
- Mantener una política de reutilización y archivo por fuente. Que un contenido sea público no implica que pueda republicarse sin restricciones.
- InfoCs es políticamente neutral: recopila, estructura, relaciona, compara datos objetivos, detecta cambios y enlaza fuentes originales. No genera acusaciones, inferencias sobre intenciones políticas ni valoraciones partidistas.
- Diferenciar siempre entre dato oficial, dato normalizado por InfoCs y cálculo realizado por InfoCs. Todo cálculo debe mostrar su fórmula y datos de entrada.

## Coste, infraestructura y calidad

- No añadir servicios SaaS de pago, APIs de pago, VPS, bases de datos externas ni infraestructura con coste recurrente, salvo decisión arquitectónica posterior explícita.
- El diseño de producción previsto es repositorio público, GitHub Actions estándar, build estático y GitHub Pages; no introducir un backend permanente sin una decisión documentada.
- Fijar dependencias y revisar su procedencia antes de incorporarlas. No añadir frameworks ni dependencias por anticipación.
- Todo comportamiento importante debe disponer de tests proporcionados al riesgo: unitarios, de integración, contractuales, de anomalías y smoke tests reales cuando corresponda.
- Antes de declarar una tarea completada: ejecutar las comprobaciones aplicables, revisar cambios e informar de resultados reales, errores y limitaciones pendientes.
