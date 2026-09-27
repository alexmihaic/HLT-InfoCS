# Arquitectura de información frontend v1

Estado: 09B implementada sobre Astro estático. El frontend lee Records y
Events canónicos en build; no reinterpreta reglas de negocio ni modifica datos.

**Alcance de implementación:** las rutas Astro descritas aquí son la primera
vertical funcional implementada. No sustituyen el sistema de producto/UI de
InfoCs aprobado previamente, que contempla superficies y rutas adicionales
que se integrarán en fases posteriores de la Fase 09.

## Rutas y navegación

- `/`: últimas publicaciones disponibles, ordenadas por `publishedAt` y, si
  falta, por `detectedAt`. Navegación global: Inicio y Fuentes.
- `/record/[slug]`: ficha estática; el slug hexadecimal reversible codifica el
  ID UTF-8 del Record sin exponerlo como segmento literal de URL.
- `/fuentes/`: organismo responsable, tipo de acceso, estado editorial,
  disponibilidad, enlace oficial y metodología resumida.

No se crea una página separada de Acerca o Metodología en v1: la explicación
breve vive en el pie y en Fuentes. Una metodología pública más amplia se podrá
añadir antes de beta. Tampoco se crean rutas por categoría o fuente.

## Portada

La portada explica el propósito de InfoCs, resume las fuentes y enumera
Records cronológicamente. Cada elemento muestra categoría y fuente con
etiquetas legibles, título, autoridad sólo si existe, geografía canónica si
aporta contexto, fecha principal, disponibilidad de historial y enlace oficial.
No muestra IDs técnicos ni hashes. Los recuentos son discretos y se calculan
desde los datos cargados.

La fecha principal es `publishedAt` con etiqueta «Publicado» cuando existe;
si no, usa `detectedAt` con etiqueta «Detectado por InfoCs». La presentación
no altera la fecha canónica. La lista no tiene paginación v1; habrá que valorar
una solución estática antes de beta si el crecimiento vuelve larga la portada.

## Ficha de publicación

Orden: navegación de retorno, fuente y categoría, título, autoridad cuando
exista, datos de fecha y ámbito disponibles, información de convocatoria BDNS
si está estructurada, enlace oficial, nota breve sobre el procesamiento e
historial.

Para `grants.call` se puede mostrar `grant.call_id` como Código BDNS y un
`grant_amount` sólo si el normalizador lo proporcionó; no se deduce presupuesto
ni se exponen beneficiarios. BOE muestra únicamente campos canónicos y no
extrae autoridad o categoría del título.

Los Events describen observaciones de InfoCs: `create` se presenta como
«InfoCs incorporó esta publicación» y `update` como «InfoCs detectó cambios».
Las rutas de campos conocidas se traducen a etiquetas; las no reconocidas se
resumen como información de la ficha. Un Record sin Event muestra una nota
breve y no recibe un historial inventado.

## Fuentes, método y estados editoriales

BOE y BDNS se presentan como activas porque tienen publicaciones disponibles.
BOP Castellón aparece en Fuentes como «Publicación pendiente»: la integración
técnica está preparada, pero sus Records no se publican mientras las
condiciones de reutilización estén pendientes de aclaración. Este estado no es
un diagnóstico de salud técnica. La atribución BDNS aparece en su ficha de
fuente y en sus Records, no de forma indiscriminada en todo el portal.

La metodología breve indica que InfoCs organiza metadatos oficiales, conserva
enlaces de origen, aplica controles de privacidad, no completa campos sin
respaldo y muestra historial cuando existe un Event. El portal no promete
exhaustividad absoluta, tiempo real, superioridad frente a la fuente ni
asesoramiento jurídico.

## Opcionalidad y exclusiones

Autoridad, nivel administrativo, publicación, fecha del acto, importes,
documentos, relaciones y municipio sólo se muestran si existen en el contrato
frontend. No se crean valores de reemplazo ni se repite matching territorial
en TypeScript. El frontend no lee Records BOP, no interpreta Health técnico,
no expone documentos ni texto completo y no incluye búsqueda, feeds o exports
en esta fase.

El portal es HTML estático y no requiere JavaScript cliente para navegar.
