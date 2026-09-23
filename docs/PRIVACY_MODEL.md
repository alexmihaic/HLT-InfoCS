# Privacy Gate v1

## Frontera obligatoria

La privacidad se evalúa después de `finalize_record()` y antes de cualquier
`RecordStore.write()`:

```text
RecordCandidate -> finalize_record() -> Record -> PrivacyGate -> RecordStore
```

El `RecordStore` crea siempre un `PrivacyGate` (o recibe uno inyectado para una
prueba o política explícita), lo valida y vuelve a evaluar el record antes del
reemplazo atómico. Un collector no puede omitir el control por no invocarlo.
Una configuración ausente, inválida o con reglas desconocidas hace fallar la
construcción/evaluación del gate; nunca equivale a `allow`.

## Decisiones

- `allow`: las reglas automáticas configuradas no detectaron una señal que
  bloquee la escritura.
- `quarantine`: se aísla sólo ese record; no se escribe payload, evento ni
  contenido sensible en Git público.
- `reject`: una regla configurada explícitamente declara el dato no publicable;
  tampoco se escribe. Ninguna regla de la configuración v1 predeterminada lo
  produce; queda disponible para políticas posteriores concretas.

Una decisión de privacidad no cambia `Record.status` ni `content_hash`. En
particular, `quarantine` no es `missing_from_source` y no exige persistir un
record con estado `quarantine`.

Las razones contienen únicamente `rule` y `field`; las clasificaciones fiscales
contienen únicamente el tipo estructural y el campo. Ninguno copia el valor
detectado ni el texto completo.

## Reglas v1

La configuración versionada está en `config/privacy-rules.json`:

| Regla | Señal | Acción predeterminada |
| --- | --- | --- |
| `spanish_personal_identifier` | DNI/NIE personal validado por checksum; formas personales K/L/M cuando validan | quarantine |
| `ambiguous_tax_identifier` | forma fiscal española plausible que no se puede clasificar con seguridad | quarantine sin afirmar que sea de una persona |
| `iban` | IBAN válido por checksum | quarantine |
| `personal_email` | email de un proveedor de consumo configurado | quarantine |
| `personal_phone` | teléfono español con forma clara y señal cercana explícita de carácter personal | quarantine |
| `structured_private_address` | etiqueta explícita de domicilio/dirección particular o personal con número | quarantine |

Se inspeccionan `title`, `description`, `procurement.awardee.name`,
`grant.beneficiary.name` y los `tax_identifier` estructurados que existan. En
los campos de nombre sólo se buscan identificadores personales e IBAN; email,
teléfono y domicilio se evalúan en `title` y `description`, donde el contexto
puede explicar que son contactos publicados. IDs, hashes, timestamps, URLs,
metadatos técnicos, tags, categorías y relaciones quedan fuera.

Un NIF de persona jurídica se clasifica como `legal_entity_tax_identifier`
sólo con prefijo empresarial reconocido y checksum válido. `B00000000` es un
valor sintético de prueba. DNI/NIE y formas personales K/L/M con checksum
válido se clasifican como `personal_identifier`. Una forma española plausible
sin clasificación segura se pone en cuarentena como `ambiguous_tax_identifier`,
sin afirmar que sea de una persona. Otros identificadores fiscales desconocidos
quedan sin clasificar por esta regla. No se usan nombres ni inferencias
contextuales para decidir el tipo.

Un nombre de empresa, organismo o cargo, expediente, CPV, municipio, provincia
o importe no bloquea por sí mismo. Un dominio empresarial o desconocido tampoco
se considera personal: sólo se reconocen proveedores de consumo explícitos en
`personal_email_providers`, una lista deliberadamente pequeña, no exhaustiva.
Un teléfono genérico de organismo o empresa pasa; la sintaxis numérica por sí
sola no demuestra uso particular. La configuración exige que el marcador
«teléfono/móvil particular/personal» aparezca cerca del número. Una dirección
postal genérica pasa; el domicilio requiere una etiqueta explícita.

No se archivan documentos, no se descarga full text, no se hace OCR ni se
redacta contenido automáticamente. Una URL oficial documental no activa estas
reglas.

## Ingesta y fallos

La ingesta aplica la decisión por record: records seguros continúan y un
record sensible cuenta como `privacy_quarantined` o `privacy_rejected` sin
crear `create`, `update` o `missing`. Todo el batch se prepara antes de
escribir. Un error del motor o de configuración del gate aborta el batch y
produce cero escrituras nuevas.

La salida de ingesta conserva `seen`, `included`, `created`, `updated`,
`unchanged`, `excluded` y las métricas `privacy_allowed`,
`privacy_quarantined`, `privacy_rejected`.

## Política BOE

BOE exige `privacy_gate_required: true`, permite publicar metadatos y datos
transformados conforme a su contrato auditado, y mantiene
`mirror_documents: false` y `fulltext_publication: false`. Esta barrera
preventiva no altera las conclusiones legales de la auditoría de fuente.

`allow` significa únicamente que las reglas automáticas v1 no encontraron una
señal bloqueante. Privacy Gate v1 no es garantía de anonimización completa ni
aprobación jurídica de publicación.

## Limitaciones

Esto no es DLP completo: no reconoce nombres por sí solos, no analiza OCR ni
documentos enlazados, no resuelve todos los formatos fiscales y no considera
particular un teléfono por su sintaxis. La lista de proveedores de email puede
tener falsos negativos. Ampliar reglas requiere nuevos tests y una decisión
explícita.
