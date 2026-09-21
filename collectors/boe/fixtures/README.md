# Fixture de sumario BOE recortado

- **Origen:** `https://www.boe.es/datosabiertos/api/boe/sumario/20240529`
- **Obtenida:** 2026-09-21 mediante `GET` con `Accept: application/json`.
- **Estado HTTP de origen:** 200, `Content-Type: application/json`.
- **Propósito:** fijar el contrato JSON real mínimo del parser BOE y, en
  particular, el tipo original de `status.code`, que es la cadena `"200"`.

La respuesta original de aproximadamente 315 KB **no** se conserva. Esta
fixture mantiene un único diario, sección, departamento, epígrafe e ítem de
una disposición sobre un tratado internacional. Se han eliminado el PDF de
sumario, todos los demás diarios, secciones, departamentos, epígrafes e ítems.
Los tipos JSON y los valores de los campos que sí se conservan no se han
transformado; las secuencias Unicode se expresan con escapes JSON válidos.

La fixture es un dato de prueba recortado, no una copia de la publicación BOE
ni una fuente de extracción. La procedencia y las condiciones de reutilización
vigentes se documentan en `../SOURCE_AUDIT.md`.
