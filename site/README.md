# InfoCs — portal estático

## Iconos BRAND-01

El maestro vectorial es `public/favicon.svg`: monograma iCs trazado a mano,
sin fuentes, degradados ni recursos externos. Conserva el marino `#07111d`,
blanco `#f4f8fc` y azul `#2f8cff` de la paleta existente. No cambia el wordmark
horizontal. El fondo es opaco; el manifest usa `purpose: any`, no maskable.

Exportaciones reproducibles mediante sharp, ya instalado por Astro y fijado
en package-lock (sin dependencias nuevas):

```powershell
node scripts/brand-assets.mjs
node scripts/brand-assets.mjs --check
npm run check
npm run build
node --test scripts/brand.test.mjs
node scripts/verify-build.mjs
```

El generador regenera sólo los PNG y el ICO propios de BRAND-01. El ICO
contiene frames PNG de 16 y 32 px. Abrir `brand-review.html` directamente para
comparar 16/32/64/180/192/512 px en claro, oscuro y una simulación móvil;
la página de revisión está fuera de public/src y no se despliega. El manifest
no implica service worker, funcionamiento offline ni instalación garantizada.

## Portal

Astro genera HTML estático y de sólo lectura. No hay servidor runtime, API,
SSR ni base de datos. El único JavaScript cliente de esta slice permite
cambiar y recordar el tema visual.

```powershell
npm install
npm run dev
npm run check
npm run build
```

La capa de datos de build lee directamente `../data/records/**/*.json` y
`../data/events/**/*.json`; no copia ni modifica esos ficheros. Los contratos
frontend están en `src/lib/data/`; después, `src/lib/presentation/` prepara
etiquetas y view models para los componentes Astro.

Rutas v1:

- `/`: últimas publicaciones, en orden cronológico.
- `/registro/[slug]/`: ficha estática y Events asociados.
- `/fuentes/` y `/fuentes/[source]/`: índice y fichas de fuentes.
- `/cambios/`: Events públicos reales asociados a sus Records.
- `/metodologia/`: alcance y límites del método InfoCs.
- `404.html`: recuperación hacia Inicio o Fuentes.

La ficha usa un slug hexadecimal reversible. La antigua ruta `/record/` se
alineó con la IA española aprobada antes de deployment; no se genera un alias.

Las etiquetas y fechas de presentación viven en `src/lib/presentation/`; no
modifican los valores canónicos ni vuelven a decidir su semántica.

`src/lib/data/sources.ts` mantiene metadata editorial que no forma parte del
schema canónico (nombres públicos, estado de publicación y atribuciones de
fuente cuando corresponden).
Los recuentos se calculan desde los Records cargados; BOP aparece sólo como
fuente con publicación pendiente y no como dataset.

La capa visual usa temas dark/light, con dark por defecto, y fuentes IBM Plex
servidas localmente. Sólo el control de tema usa JavaScript cliente; las rutas
y el contenido siguen siendo HTML estático y de sólo lectura.

El portal Astro aún no se despliega. No hay configuración de GitHub Pages,
dominio ni workflow de publicación.
