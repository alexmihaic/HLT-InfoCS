# BOE — Política de inclusión territorial v1 (Fase 03C)

## Alcance

Esta política decide si un `BOEItem` del sumario diario contiene una
coincidencia territorial **literal y verificable** con la provincia de
Castellón/Castelló o alguno de los municipios del registro. No decide que un
acto sea aplicable, importante o jurídicamente eficaz en ese territorio.

La salida es source-specific:

```text
BOEItem -> BOETerritorialDecision(include | no_match, coincidencias)
```

No crea `RecordCandidate`, no llama a `finalize_record()` y no persiste nada.

## Registro de entidades

El registro runtime es
[`config/entities/castellon.json`](../../config/entities/castellon.json). Se
elige JSON, no YAML, para poder cargar y validar la configuración con la
biblioteca estándar de Python, sin añadir una dependencia de producción.

La fuente canónica de vigencia municipal es la relación del Instituto Nacional
de Estadística (INE) a 1 de enero de 2026, no la clasificación de la API:

- [Página de la relación de municipios y sus códigos por provincias — datos a 1 de enero de 2026](https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736177031&idp=1254734710990).
- [Fichero vigente “Municipios por provincia con sus códigos”](https://www.ine.es/daco/daco42/codmun/26codmun.xlsx), hoja `12`.
- [Modificaciones desde el 1 de enero de 2026](https://www.ine.es/daco/daco42/codmun/codmun_anual.htm), revisadas el 2026-09-21: sin entradas para Castellón/Castelló.
- [Referencia oficial de la API JSON del INE](https://www.ine.es/dyngs/DAB/index.htm?cid=1100), que documenta `VALORES_HIJOS` como mecanismo auxiliar de consulta.
- [Relación oficial de códigos de provincia](https://www.ine.es/daco/daco42/codmun/cod_provincia.htm), que asigna `12` a `Castellón/Castelló`.

El registro se comprobó el **2026-09-21** contra la hoja `12` de la relación
vigente. Contiene exclusivamente los **135 municipios** de esa relación. La
metadata del fichero incluye `canonical_source`, `reference_date`, `checked_at`,
`expected_municipality_count` y `api_source` para hacer explícita esa jerarquía
de fuentes.

Conserva para cada entidad:

```json
{
  "code": "12040",
  "official_name": "Castelló de la Plana/Castellón de la Plana",
  "official_variants": ["Castelló de la Plana", "Castellón de la Plana"],
  "technical_aliases": []
}
```

`official_name` conserva el literal publicado por INE. Las variantes separadas
por `/` son formas lingüísticas oficiales presentes en ese literal;
`technical_aliases` es una lista distinta, inicialmente vacía, que sólo podrá
ampliarse con justificación y procedencia documentadas. La estructura también
admite `authorities`, pero v1 no añade organismos de producción hasta disponer
de un catálogo oficial y trazable.

### Reconciliación de API y relación vigente

La comparación se realizó contra `GET
https://servicios.ine.es/wstempus/js/ES/VALORES_HIJOS/115/13?det=2`:

| Conjunto | Fuente | Resultado |
| --- | --- | --- |
| A | Hoja `12` de la relación vigente a 01-01-2026 | 135 códigos. |
| B | Valores `MUN` de la respuesta API jerárquica | 136 códigos. |
| B − A | API no vigente | `12066`. |
| A − B | Relación no devuelta por API | Vacío. |

El único valor adicional de la API fue literalmente:

```text
code: 12066
name: Gatova
api_id: 557
variable: { id: 19, name: Municipios, code: MUN }
parent: { id: 13, name: Castellón/Castelló, code: 12,
          variable: { id: 115, name: Provincias, code: PROV } }
```

La explicación oficial está en la [ficha histórica del INE para 12066](https://www.ine.es/intercensal/intercensal.do?btnBuscarCod=Consultar+selecci%C3%B3n&codigoMunicipio=066&codigoProvincia=12&search=3):
Gátova desapareció entre el Censo de 2001 y el anterior al integrarse en la
provincia de Valencia como municipio `46902`. Por tanto es un **municipio
histórico extinguido en la provincia 12**, no un municipio vigente de
Castellón/Castelló. Se excluye del registry productivo y se conserva sólo en
esta auditoría de reconciliación.

## Campos inspeccionados

Sólo se inspeccionan metadatos ya cargados del sumario, en este orden:

1. `heading_name` → `heading`.
2. `department_name` → `department`.
3. `title` → `title`.

No se inspeccionan `section_name`, `official_id`, enlaces o texto de
`url_xml`, `url_html` o `url_pdf`. La política no descarga ningún documento por
ítem.

## Reglas de coincidencia

Cada variante explícita se compara mediante:

- `casefold` Unicode (sin sensibilidad a mayúsculas/minúsculas).
- Descomposición Unicode y retirada de marcas diacríticas sólo para comparar.
- Límites Unicode de palabra a ambos lados de la expresión.
- Coincidencia exacta de la secuencia normalizada, sin distancia, score ni
  sustituciones globales.

El texto BOE no se modifica: `matched_text` conserva el fragmento observado.
Por ejemplo, `PENISCOLA` puede hacer match con la variante oficial `Peníscola`,
pero el resultado conserva `PENISCOLA` como texto observado.

No hay fuzzy matching, IA, embeddings ni heurísticas de similitud. Tampoco se
convierte globalmente `Castellón` en `Castelló` ni a la inversa.

### Castellón/Castelló y Castelló de la Plana

Las formas completas `Castelló de la Plana` y `Castellón de la Plana` son
variantes municipales explícitas del código `12040`. Una coincidencia con el
nombre completo produce `municipality_exact`; la subcadena provincial no añade
una segunda coincidencia redundante.

Las formas aisladas `Castellón` y `Castelló` son variantes de la **provincia**:
producen `province_exact`, nunca una atribución al municipio. Esto mantiene la
ambigüedad explícita y evita interpretar como ciudad una referencia territorial
genérica.

## Decisiones y motivos

Una decisión tiene sólo dos estados: `include` (una o más coincidencias) o
`no_match` (ninguna). Cada coincidencia contiene motivo, entidad, campo, texto
observado y método:

```json
{
  "status": "include",
  "matches": [
    {
      "reason": "municipality_exact",
      "entity_code": "12104",
      "entity_name": "Segorbe",
      "field": "title",
      "matched_text": "Segorbe",
      "method": "official_variant_casefolded_diacritic_insensitive_boundary"
    }
  ]
}
```

Motivos v1:

| Motivo | Hecho que expresa |
| --- | --- |
| `municipality_exact` | El campo contiene una variante municipal explícita. |
| `province_exact` | El campo contiene una variante explícita de la provincia. |
| `authority_exact` | El campo contiene una denominación de organismo registrada explícitamente. |

La deduplicación conserva una sola coincidencia por motivo, código de entidad y
campo; coincidencias distintas, por ejemplo municipio en el epígrafe y
provincia en el título, se conservan. El orden de la salida sigue el orden de
campos indicado arriba.

## Muestras reales y fixtures

No se guarda una respuesta diaria BOE completa ni documentos individuales para
esta fase. La fixture ya existente `summary_20240529_minimal.json` continúa
siendo una respuesta BOE real recortada de 03B y sirve para el parser; no tiene
coincidencia territorial.

Para comprobar la política se hicieron dos lecturas controladas del sumario
diario, sin seguir enlaces:

| Fecha | Ítem observado | Resultado literal |
| --- | --- | --- |
| 2026-09-18 | `BOE-A-2026-19457` | `Segorbe` en `title` (`municipality_exact`); además `Castellón` en el mismo título (`province_exact`). |
| 2026-09-19 | `BOE-B-2026-30223` | `SEGORBE` en `title` (`municipality_exact`). |
| 2026-09-19 | `BOE-B-2026-30232` | `VINAROS` en `title` (`municipality_exact`, tolerancia de acento). |
| 2026-09-19 | `BOE-B-2026-30240` | `CASTELLON DE LA PLANA` en `title` (`municipality_exact`). |

Las pruebas offline añaden casos sintéticos de formas oficiales, mayúsculas,
acentos, nombres compuestos, límites de palabra, provincia, organismos,
duplicados y negativos. Ninguna prueba ordinaria usa Internet.

## Limitaciones y falsos negativos deliberados

- No se detecta una referencia que sólo esté dentro del XML, HTML o PDF;
  requeriría una fase futura con una política separada y peticiones adicionales.
- No se detectan nombres alternativos no presentes en el registro, abreviaturas
  ni errores ortográficos.
- Una alusión indirecta o un texto jurídicamente aplicable sin entidad literal
  no entra en v1.
- La coincidencia prueba presencia textual en un campo del sumario; no prueba
  competencia, aplicabilidad ni relevancia política o jurídica.
- El snapshot reproduce la relación a 01-01-2026. Debe renovarse cuando el INE
  publique una relación posterior o una modificación relevante para la
  provincia 12.
