# BDNS enrichment mapping and gates — 10B-C

Capacidad **offline v2**, no activación productiva. El contrato tipado y el hash
v2 son los aprobados en [CANONICAL_ENRICHMENT_CONTRACT.md](CANONICAL_ENRICHMENT_CONTRACT.md).
No cambia schema, reutilización, territorio ni significado de los Events.

## 1. Ruta y mapping

`enrichment.py` contiene `build_bdns_source_data(detail)` y
`normalize_bdns_enriched(summary, detail, ...)`. El segundo reutiliza el join
Código BDNS, normalización básica y match exacto ES522 existentes; cambia sólo
la extensión y `provenance.normalizer_version=2.0.0`.

| Campo oficial ya parseado | Destino `source_data.bdns` |
| --- | --- |
| descripcionLeng | official_title_coofficial |
| organo.nivel1/nivel2/nivel3 | authority_hierarchy.nivel1/nivel2/nivel3 |
| presupuestoTotal | budget_total.value (Decimal exacto; currency ausente) |
| tipoConvocatoria | call_type |
| instrumentos[].descripcion | instruments |
| tiposBeneficiarios[].codigo/descripcion | eligible_beneficiary_types[].code/label |
| sectores[].codigo/descripcion | sectors[].code/label |
| regiones[].descripcion | impact_regions |
| fechaRecepcion | received_date, nunca published_at |
| fechaInicioSolicitud/fechaFinSolicitud | application.start_date/end_date |
| textInicio/textFin | application.start_text/end_text |
| abierto | application.abierto (literal, incluso false) |
| descripcionFinalidad | purpose |
| descripcionBasesReguladoras/urlBasesReguladoras | regulatory_bases.description/source_locator |
| sedeElectronica | electronic_office_url |
| sePublicaDiarioOficial | extract_published_in_official_diary |
| documentos[].id/descripcion/nombreFic/datPublicacion/datMod | documents[].source_document_id/description/filename/published_date/modified_value |
| anuncios[].cve/desDiarioOficial/url/datPublicacion/titulo/tituloLeng | extracts[].cve/diary/source_url/publication_date/title/title_coofficial |

Ausencia opcional no inventa valores. Fecha estructurada y texto pueden coexistir.
No inferir EUR, estado open/closed, beneficiarios concretos ni finalidad editorial.
Presupuesto no se mapea a `financial.grant_amount`. El título principal conserva
la ruta v1; no existe un objeto distinto inventado desde `descripcion`.
Se excluyen ID interno, longitud documental, numAnuncio como identidad, raw,
fulltext, URLs documentales derivadas, MIME, binarios y relaciones Core inferidas.
Las colecciones se canonizan con las reglas unordered del hash v2, no con un
nuevo algoritmo. No se cambian hash, identity ni diff en esta fase.

## 2. Fallos completos, no descarte silencioso

Cada elemento representable de los campos aprobados se conserva. Si falta el
label de una clasificación, no se deduce desde su código ni se omite el elemento:
falla todo el enriquecimiento antes de Candidate/Privacy. Igual para documento
duplicado, Decimal o metadata inválida, URL rechazada y extracto que sólo conserva
un numAnuncio excluido y no tiene metadata representable.

`BDNSEnrichmentError` sólo contiene un código estático seguro. La ruta no devuelve
un candidato enriquecido incompleto. Campos deliberadamente excluidos por el
contrato no cuentan como errores; no es un parser raw nuevo ni amplía lo que el
parser actual conoce.

## 3. Política de URLs suministradas por BDNS

Sede electrónica y extractos mantienen HTTPS estricto: sin userinfo, controles,
whitespace/backslash, escapes inválidos, IP literal, host de una etiqueta,
.local/.localhost ni DNS/IDNA/puerto inválido. Límite InfoCs 2048, no cuota SNPSAP.

10B-D2.8 sustituye la excepción HTTP de D2.4 por SOURCE LOCATOR + CLICKABLE URL.
D2.7 observó 35 HTTPS, 2 HTTP y 3 valores sin esquema entre 40 locators.
`regulatory_bases.source_locator` conserva el literal validado por
`valid_bdns_regulatory_bases_source_locator`: no vacío, <=2048. 10B-D3.4 permite
exclusivamente U+0020 interno (uno o varios), preservado literalmente; rechaza
U+0020 de borde, otros whitespace, controles C0/C1, DEL/backslash,
escapes/UTF-8 inválidos ni credenciales detectables.
Sin exigir scheme/host/DNS/puerto navegables ni prohibir IP/local por clickability.
Esquemas explícitos no HTTP/HTTPS siguen rechazados por prudencia: no observados.
El constructor, mapping y publication reutilizan esa misma validación canónica.

`clickable_bdns_regulatory_bases_url` es la única función derivada de navegación:
literal si es persistible y pasa HTTPS estricto; None para HTTP/schemeless,
locators con U+0020 interno o no
navegable. No flags UI persistidos, no rewriting/trim, inferencias o visitas.
El locator literal sigue siendo material en hash v2; clickability queda fuera.
No ser clickable no causa HOLD por sí solo. Privacy/source eligibility/resto de
metadata policy y authorization exacta siguen siendo obligatorios.

No se visita el destino, resuelve DNS ni reescribe la URL. Path/query/fragment
se conservan y se inspeccionan por Privacy tanto literales como decodificados.
La query también se inspecciona con separadores form `+` como espacios, sin
aplicar esa transformación al path ni modificar la URL persistida.
Para bases se inspecciona siempre el string completo literal y decodificado,
aunque urlsplit no pueda parsearlo. Los componentes parseables se añaden, nunca
condicionan la inspección del string. Decodificación UTF-8 estricta, hasta cuatro capas; encoding inválido o sin
estabilizar dentro del límite falla cerrado. No persistir las vistas decodificadas.

## 4. Privacy: proyección explícita

El gate añade conscientemente: título cooficial; cada nivel de jerarquía;
tipo; instrumentos; labels/codes de beneficiarios y sectores; regiones;
textos de solicitud; finalidad; descripción/locator de bases; sede; descripción,
filename y datMod textual de documentos; CVE, diario, títulos y URL de extractos.
No recursive walker ni cobertura automática de campos futuros.

Todos estos textos pasan por las reglas existentes DNI/NIE/NIF personal, IBAN,
email personal, teléfono personal contextual y dirección particular estructurada.
URLs/filenames no se consideran seguros por ser metadata. Las razones sólo
incluyen regla + path inspeccionado, nunca el valor.

No se añade NER ni detección genérica de nombres: un nombre aislado no está
garantizado como detectable por las reglas actuales. ALLOW no certifica ausencia
absoluta de datos personales. Las categorías oficiales no se transforman en
personas; beneficiary nominativo Core sigue excluido por publication policy.
La fuente sigue siendo convocatorias, no concesiones/pagos individuales.
Privacy QUARANTINE/REJECT termina antes de source eligibility; no se convierte
en metadata HOLD ni crea una Review Queue.

## 5. Publicación y autorización

V1 conserva su política y `bdns.metadata-publication.v1`. La extensión sólo
puede superar metadata policy si mantiene todos los límites Core v1 y además:

- schema/tipos/binding correctos; hash v2 recalculado coincide;
- normalizer_version 2.0.0 y provenance territorial exacta aprobada;
- impact_regions contiene el label ES522 exacto;
- jerarquía oficial coherente con el authority Core normalizado;
- moneda ausente hasta tener evidencia fuente;
- las tres clases de URLs cumplen esta política;
- Privacy ALLOW y Source ELIGIBLE bajo reutilización con condiciones.

No copias documentales en Core documents, fulltext, beneficiary, resolution_id,
ni nuevos importes Core. Metadata documental tipada dentro de la extensión sí
está autorizada bajo sus gates. No análisis semántico del título ni matching
territorial frontend/textual nuevo.

Resultado: PUBLISHABLE_METADATA o HOLD (`publication_source_data_hold`). No
estado APPROVED humano ni nueva semántica REJECT: REJECT corresponde a Privacy.
`evaluate_bdns_publication` recibe Privacy del caller y no la ejecuta internamente.
El adapter `authorize_bdns_event` comprueba la evaluación vigente y, para v2,
revalida Privacy por defecto sobre el Record exacto: una ALLOW stale ligada sólo
al ID no sirve para textos recién añadidos. Una configuración divergente no
habilita bypass: si discrepa, falla cerrado.

Sólo después emite autorización interna `bdns.enriched-metadata-publication.v2`,
ligada a record_id/source_id/content_hash. La autorización v1 no sirve para v2
ni una autorización v2 para otra versión administrativa. El issuer interno
no es un entrypoint público alternativo a los adapters. EventStore no evalúa
políticas de fuente. BOE/BOP no cambian.

## 6. Preflight y Store

`prepare_bdns_enriched_record` encadena mapping → finalize v2 → Privacy →
source eligibility → metadata policy → authorization → RecordStore.validate
y path seguro. Devuelve objetos en memoria y safe_reason; **nunca escribe,
crea Events ni consulta red**. Sólo Stores temporales se escriben en tests.

Se retiran los bloqueos globales preventivos de 10B-B en RecordStore y el
issuer interno. RecordStore conserva validación cerrada, coherencia fuente,
hash y Privacy, no asume funciones de publicación. El caller debe completar
publication policy antes de solicitar write. Schema support/Store validation
**no equivalen a publication authorization**.

BOE/BOP con source_data.bdns y extensiones desconocidas siguen siendo inválidos.
HashContractTransitionError sigue bloqueando diff/update v1↔v2. Create/update
v2→v2 puede construirse con autorización válida; no se escribe ningún Event real
durante 10B-C. No primitive de migración añadida.

## 7. Códigos seguros

| Código | Resultado |
| --- | --- |
| enrichment_invalid_model | entrada tipada incorrecta |
| enrichment_missing_required_label | clasificación sin label |
| enrichment_invalid_decimal | presupuesto no representable/exacto |
| enrichment_duplicate_document_id | ID documental duplicado |
| enrichment_invalid_document_metadata | metadata documental inválida |
| enrichment_invalid_url | URL fuera de política |
| enrichment_contract_invalid | shape/schema/join inválido, diagnóstico saneado |
| enrichment_territorial_not_included | no hay Candidate territorial |
| privacy_source_data_url_encoding_invalid | gate falla cerrado al decodificar URL |
| privacy_source_data_blocked | preflight detenido por Privacy/error del gate |
| privacy_source_data_decision_mismatch | adapter no acepta decisión stale/divergente |
| publication_source_data_hold | metadata no publicable/autorizable |
| enrichment_record_preflight_failed | Store/path no supera preflight |

Los errores contractuales existentes de coherencia siguen siendo excepciones;
no contienen payload fuente en este harness. La estructura de preflight no es
un formato de observabilidad serializable: no volcar Records ni decisiones
completas a logs como safe_reason.

## 8. Firewall productivo y dependencia de 10B-D

**Enrichment capability ready, productive activation pending baseline migration.**
Actualización D1: el selector canónico descrito en
[BASELINE_MIGRATION_CONTRACT.md](BASELINE_MIGRATION_CONTRACT.md) permite v2 sólo
tras marker válido y población migrada. Sin marker real, sigue vigente v1.
Sin marker, ingest, runner y schedule no llaman ninguna ruta enriquecida: Records nuevos y
observaciones siguen v1, sin source_data ni content_hash_version explícita.
Una prueba ejecuta el runner con FakeTransport/Stores temporales y hace fallar
si toca cualquiera de las funciones v2; verifica Record v1 generado.
No CLI force-v2, allow-hash-transition, skip-gates ni flag equivalente.

10B-D deberá aprobar evidencia durable de transición v1→v2, contrastar proyección
v1, preservar identidad/detected_at, definir preflight/idempotencia/recovery
baseline+evidencia sin transacción nueva ni Event administrativo ficticio.
Debe incluir todos los v1 nacidos mientras sigue el schedule y coordinar un
cutover único antes de conectar v2 al runner. No inferir valores históricos de
campos no conservados ni reescribir Events antiguos. Hasta ese cutover, cero
activación productiva v2, migración, refetch/backfill o frontend enriquecido.
