# InfoCs Design System v1

**Estado:** sistema aprobado, aplicado a la slice Astro actual.
**Fuente:** conversación de diseño InfoCs y boards incluidos en `reference/`.

## Dirección

InfoCs es un portal cívico de información pública: abierto, verificable,
neutral y útil. La interfaz prioriza lectura y procedencia; no reescribe el
contenido oficial ni emite valoraciones. Tema oscuro por defecto y tema claro
manual opcional. Astro estático, CSS nativo y cero frameworks de interfaz.

## Foundations aprobadas

- Paleta dark/light y aliases semánticos implementados en `site/src/styles/`.
- IBM Plex Sans para interfaz; IBM Plex Mono para identificadores y datos
  técnicos. Fuentes servidas localmente, sin petición a Google Fonts.
- Contenedor ancho de hasta 1280 px; gutters 16 px móvil, 24 px tablet y
  32 px escritorio; escala de espacio basada en múltiplos de 4 px.
- Breakpoints de referencia: 480, 768, 1024 y 1280 px. Diseño fluido desde
  320 px, listas apiladas en móvil y objetivo táctil mínimo de 44 px.
- Bordes discretos, radios moderados, foco visible y movimiento reducido
  respetado. El color no es el único portador de estado.

## Temas

Dark permanece por defecto sin consultar `prefers-color-scheme`. La persona
puede elegir dark o light; `localStorage` recuerda esa preferencia. Si el
navegador no permite almacenamiento, el portal conserva dark y el control
sigue siendo operativo durante la sesión.

## Semántica visual

La presentación distingue, cuando aporta claridad:

1. **Datos oficiales:** valores y enlaces procedentes de la fuente.
2. **Procesado por InfoCs:** etiquetas y estructura normalizadas.
3. **Detalles técnicos:** identidad/hash y procedencia técnica, plegados.

Los componentes consumen etiquetas/view models ya preparados; no interpretan
categorías, autoridad, geografía ni políticas de publicación.

## Referencias

- [Wireframes Visual Board v1](reference/infocs-wireframes-visual-board-v1.png)
- [Component Library v1](reference/infocs-component-library-v1.png)

Son referencias de implementación, no assets de páginas públicas.
