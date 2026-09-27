# InfoCs

InfoCs es un índice abierto, histórico y trazable de actividad pública de
Castelló de la Plana y la provincia de Castellón, elaborado a partir de
fuentes oficiales.

La arquitectura es un **data pipeline estático**:
collectors → normalización → privacidad y políticas de publicación → Records,
Events, Manifests y Health → Git → build estático Astro → GitHub Pages. InfoCs
no tiene ni prevé un backend web/runtime, una API de servicio ni una base de
datos de producción.

Fuentes actuales: BOE (colección operativa con workflow, revisión manual y
observabilidad), BDNS/SNPSAP (collector operativo y publicación condicionada
de metadata) y BOP Castellón (colección y normalización técnicas, publicación
bloqueada mientras se resuelve la reutilización).

## Estado del proyecto

El estado operativo vigente está en [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md).
La hoja de ruta canónica es [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md).
El portal Astro aún no se ha iniciado.

Los contratos y políticas están en `docs/` y `collectors/`; los datos públicos
canónicos están en `data/records/` y `data/events/`. No se publican copias de
documentos BOP ni datos BOP mientras su política siga bloqueada.

## Desarrollo local

Se admite Python `>=3.12,<3.15`. Ejecuta la suite con:

```powershell
python -m unittest discover -s tests -v
```
