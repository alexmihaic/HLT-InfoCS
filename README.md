# InfoCs

Bootstrap documental de InfoCs: un índice abierto, histórico y reproducible de actividad pública de Castellón desde fuentes oficiales.

La especificación funcional principal está en [`docs/INFOCS_SPEC_v1.md`](docs/INFOCS_SPEC_v1.md). Esta fase no implementa collectors, consultas a fuentes, datos reales, portal funcional ni automatización de producción.

## Desarrollo local

Se admite Python `>=3.12,<3.15`. La única dependencia de ejecución es `jsonschema==4.26.0`, usada para validar el contrato JSON Schema portable con las mismas reglas que aceptan las cargas desde JSON. No hay dependencias de desarrollo.

```powershell
python -m unittest discover -s tests -v
```
