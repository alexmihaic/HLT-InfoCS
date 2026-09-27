# BDNS / SNPSAP — política territorial v1

**Revisión:** 2026-09-26

**Uso:** criterio de alcance para futuras convocatorias BDNS. No implementa filtro ni matching.

## Evidencia oficial

OpenAPI define `GET /regiones` como árbol ordenado de regiones, con nodos `id`, `descripcion` y `children`. El detalle de convocatoria expone `regiones` como regiones de impacto, pero cada elemento contiene sólo `descripcion`; no incluye el ID del catálogo. El parámetro de búsqueda `regiones` sí acepta IDs enteros. El mismo OpenAPI documenta que la descripción de una región no equivale a un código INE.

En una respuesta live del catálogo oficial (`GET https://www.infosubvenciones.es/bdnstrans/api/regiones`) se observó esta jerarquía:

| ID del catálogo BDNS | Etiqueta observada | Lectura prudente |
| --- | --- | --- |
| 1 | `ES - ESPAÑA` | ámbito estatal amplio |
| 48 | `ES5 - ESTE` | región amplia |
| 54 | `ES52 - COMUNIDAD VALENCIANA` | comunidad autónoma, amplia |
| 56 | `ES522 - Castellón / Castelló` | entrada provincial observable |
| 57 | `ES523 - Valencia / València` | entrada provincial observable, ajena al scope InfoCs |

Las etiquetas usan códigos `ES…` compatibles estructuralmente con niveles territoriales NUTS; el OpenAPI no nombra formalmente la taxonomía ni declara versión. Por tanto, la política trata el `id` y la etiqueta como datos del catálogo BDNS. `56` es el ID interno del catálogo BDNS; `ES522` es el código incluido en la etiqueta. Ninguno es el código provincial INE `12`.

La evidencia observada llega a la provincia. Ni el esquema de región de impacto de convocatoria ni la respuesta inspeccionada demuestran un código municipal BDNS, incluido uno para Castelló de la Plana. No se afirma que el árbol completo carezca de otros nodos más finos: su existencia, granularidad y correspondencia municipal quedan sin confirmar. No convertir etiquetas regionales en códigos INE.

## Decisión de alcance

Scope InfoCs: Castelló de la Plana y provincia de Castellón/Castelló. Sólo producir `INCLUDE` con una señal de impacto local determinista:

1. `regiones` de la convocatoria coincide, por etiqueta canónica completa y sin fuzzy matching, con la entrada oficial BDNS de provincia `id=56` / código de etiqueta `ES522`; entonces asignar únicamente `geography.province = Castellón/Castelló` y registrar `OFFICIAL_CODE_MATCH`. No asignar municipio por esa coincidencia.
2. Una futura región de nivel municipal sólo podrá incluirse si el propio catálogo oficial aporta un identificador municipal y existe una correspondencia inequívoca con el registro territorial oficial de InfoCs. Esa vía aún no está demostrada y no está habilitada por esta política.
3. Un órgano convocante podrá ser señal territorial sólo tras asociar su código oficial a una entidad municipal/provincial concreta de Castellón mediante un catálogo oficial verificable. El mero nombre, el nivel jerárquico, `tipoAdministracion=L` o la sede electrónica no prueban ubicación ni ámbito de la convocatoria. Esta correspondencia aún no está auditada.

Si una convocatoria enumera varias regiones, basta con que una sea una coincidencia local/provincial exacta demostrada para establecer relevancia territorial; guardar sólo la geografía que la evidencia permita afirmar.

## No coincidencia y casos pendientes

- `ES52 - COMUNIDAD VALENCIANA` u otra región más amplia que incluye Castellón: **no incluir por sí sola**; resultado conceptual `UNRESOLVED / broad_region_not_local_match`. No reducir la comunidad a una provincia.
- `ES - ESPAÑA`, ámbito estatal u otra región amplia: no incluir por el mero hecho de que Castellón esté dentro; mantener `UNRESOLVED` si el ámbito podría incluirlo pero no individualiza el territorio.
- Región explícita, verificable y disjunta del scope (por ejemplo, únicamente `ES523`): `OUT_OF_SCOPE`.
- `regiones=[]`, campo ausente o etiqueta que no pueda enlazarse exactamente al catálogo: `UNRESOLVED`; no asumir Castellón.
- Órgano local/provincial sin cruce oficial a una entidad concreta de Castellón: `UNRESOLVED`, aunque el texto contenga «Castellón» o una variante.

No son criterios territoriales: título, descripción, finalidad, beneficiarios, substring, fuzzy matching, LLM ni ubicación de la sede por sí sola. Los campos `nivel1`–`nivel3` describen niveles del órgano; no son en sí una declaración del ámbito geográfico de la convocatoria.

## Catálogos y límites

El OpenAPI documenta además `GET /organos` como árbol por tipo de administración, `GET /organos/codigo` y `GET /organos/codigoAdmin`. No se consultó ese catálogo de órganos en esta auditoría; no se creó una tabla de autoridades ni se validó ningún órgano concreto contra Castellón.

**Fuentes oficiales:** [OpenAPI SNPSAP](https://www.infosubvenciones.es/bdnstrans/estaticos/doc/snpsap-api.json), [catálogo oficial de regiones](https://www.infosubvenciones.es/bdnstrans/api/regiones). La salida regional observada se inspeccionó en memoria y no se guardó como fixture.
