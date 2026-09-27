# InfoCs — portal estático

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
- `/fuentes/`: fuentes, disponibilidad editorial y metodología breve.

La ficha usa un slug hexadecimal reversible. La antigua ruta `/record/` se
alineó con la IA española aprobada antes de deployment; no se genera un alias.

Las etiquetas y fechas de presentación viven en `src/lib/presentation/`; no
modifican los valores canónicos ni vuelven a decidir su semántica.

`src/lib/data/sources.ts` mantiene metadata editorial que no forma parte del
schema canónico (nombres públicos, estado de publicación y atribución BDNS).
Los recuentos se calculan desde los Records cargados; BOP aparece sólo como
fuente con publicación pendiente y no como dataset.

La capa visual usa temas dark/light, con dark por defecto, y fuentes IBM Plex
servidas localmente. Sólo el control de tema usa JavaScript cliente; las rutas
y el contenido siguen siendo HTML estático y de sólo lectura.

El portal Astro aún no se despliega. No hay configuración de GitHub Pages,
dominio ni workflow de publicación.
