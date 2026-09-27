# InfoCs Astro Dev Handoff v1

## Estructura vigente

- `site/src/lib/data/`: lectura canónica build-time, adaptación y fuentes.
- `site/src/lib/presentation/`: labels, fechas y view models.
- `site/src/components/`: piezas visuales Astro sin reglas de negocio.
- `site/src/layouts/`: shell, navegación y footer.
- `site/src/styles/`: tokens, temas y foundations CSS.
- `site/src/pages/`: páginas estáticas; nunca runtime API/SSR.

## Reglas de implementación

1. Cambiar la presentación sin alterar Core ni JSON canónico.
2. Mantener fuentes BOE/BDNS reales; excluir los Records BOP.
3. Resolver IDs por el slug reversible hexadecimal existente.
4. Sin requests de datos desde el navegador, sin búsqueda ni filtros en 09C.
5. Mantener dark por defecto; persistir sólo la preferencia visual dark/light.
6. Autoalojar IBM Plex; no solicitar fuentes externas.
7. Navegación esencial funcional sin JavaScript. El único JS de cliente
   permitido en esta slice es el control de tema.
8. Validar con `npm run check` y `npm run build`; nunca escribir en `data/`.

## Referencias y límites

Los boards en `docs/design/reference/` son documentación de implementación,
no recursos publicados por el sitio. Para cualquier campo ausente en el
contrato canónico, registrar un gap en `UI_GAPS.md`; no adaptar backend ni
crear fixtures de producto para llenar el mockup.
