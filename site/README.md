# InfoCs — portal estático

Astro genera HTML estático y de sólo lectura. No hay servidor runtime, API,
SSR, base de datos ni JavaScript cliente en esta fase.

```powershell
npm install
npm run dev
npm run check
npm run build
```

La capa de datos de build lee directamente `../data/records/**/*.json` y
`../data/events/**/*.json`; no copia ni modifica esos ficheros. Los contratos
frontend están en `src/lib/data/` y adaptan los JSON canónicos antes de que
las páginas los consuman.

Rutas v1:

- `/`: últimas publicaciones, en orden cronológico.
- `/record/[slug]`: ficha estática y Events asociados.
- `/fuentes/`: fuentes, disponibilidad editorial y metodología breve.

Las etiquetas y fechas de presentación viven en `src/lib/presentation/`; no
modifican los valores canónicos ni vuelven a decidir su semántica.

`src/lib/data/sources.ts` mantiene metadata editorial que no forma parte del
schema canónico (nombres públicos, estado de publicación y atribución BDNS).
Los recuentos se calculan desde los Records cargados; BOP aparece sólo como
fuente con publicación pendiente y no como dataset.

El portal Astro aún no se despliega. No hay configuración de GitHub Pages,
dominio ni workflow de publicación.
