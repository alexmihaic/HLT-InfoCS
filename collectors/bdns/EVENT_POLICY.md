# BDNS — Events de convocatoria

La primera convocatoria BDNS persistida en 04E no recibió su Event create
porque EventStore todavía exigía la revisión manual BOE. En 04F esa barrera
se sustituyó por `PublicationAuthorization`, emitida sólo tras Privacy ALLOW,
Source Eligibility ELIGIBLE y Metadata Publication PUBLISHABLE_METADATA.

El create Event diferido se materializó desde el Record BDNS ya almacenado,
sin red ni reescritura del Record. Su `observed_at` es exactamente el
`dates.detected_at` conservado por ese Record: el contrato Core define ese
timestamp como la primera detección de InfoCs. No representa una nueva
consulta ni una fecha reconstruida de la fuente.

Los Events siguen sin almacenar la autorización ni datos administrativos del
Record; contienen sólo su identidad, hashes y timestamp conforme al schema
Event v1.
