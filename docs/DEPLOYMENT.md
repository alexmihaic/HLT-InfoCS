# Despliegue del portal estático

El portal Astro se construye en GitHub Actions y se publica como artefacto de
GitHub Pages. El workflow no escribe en el repositorio. Cada actualización de
`main`, incluidos los commits automáticos `data(boe)`, puede generar una nueva
versión estática.

## GitHub Pages

En `Settings → Pages`, configurar `Source: GitHub Actions` y el dominio
personalizado `infocs.hazlotuyo.pro`. Activar `Enforce HTTPS` cuando GitHub haya
emitido el certificado. Para un custom workflow, el archivo `CNAME` no configura
por sí solo los ajustes del repositorio; éstos se guardan en Pages Settings o
mediante la API de GitHub.

## DNS

Crear únicamente este registro para el subdominio:

```text
Tipo: CNAME
Host: infocs
Destino: alexmihaic.github.io
```

No modificar el dominio raíz `hazlotuyo.pro`, no añadir registros A para este
subdominio y conservar el TXT de verificación existente
`_github-pages-challenge-alexmihaic`.

El `CNAME` incluido en `site/public/` conserva el nombre de dominio en los
archivos del sitio; la activación efectiva depende de Pages Settings y DNS.
