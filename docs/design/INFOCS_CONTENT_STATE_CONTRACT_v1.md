# InfoCs Content & State Contract v1

## Contenido y estados

- El registro conserva su título oficial; InfoCs no lo resume ni lo
  reescribe.
- Fuente, categoría, organismo, territorio y fecha se muestran sólo según
  datos canónicos y labels explícitos.
- «Publicado» sólo corresponde a `publishedAt`; «Detectado por InfoCs» es el
  fallback visible basado en `detectedAt`.
- «Historial disponible» se usa únicamente si hay Events. Create se redacta
  como «InfoCs incorporó esta publicación»; update como «InfoCs detectó
  cambios».
- Sin Events no se crea timeline. Sin autoridad, fecha publicada, territorio,
  importe o documentos se omite el campo.
- Fuente activa sin Records: se identifica como activa y se explica que hoy no
  hay registros públicos disponibles. Fuente con publicación bloqueada no se
  representa como fallo técnico.

## Capas de confianza

Los valores de la fuente original, el procesamiento de InfoCs y los detalles
técnicos se distinguen en la ficha. Una etiqueta derivada no se presenta como
texto literal del organismo. El enlace oficial permite consultar la fuente
primaria.

## Exclusiones

No se muestran Records BOP bloqueados, ejemplos PCSP sintéticos, beneficiarios
de convocatorias, importes no normalizados, estados de salud no disponibles ni
before/after que Event v1 no contiene. No se prometen exhaustividad, tiempo
real ni asesoramiento jurídico.
