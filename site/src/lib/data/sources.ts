import type { FrontendRecord, FrontendSource, SourceMeta } from './types';

/** Editorial source metadata not represented by the canonical Record schema. */
export const SOURCE_METADATA: readonly SourceMeta[] = [
  {
    sourceId: 'boe',
    name: 'Boletín Oficial del Estado',
    responsibleBody: 'Agencia Estatal Boletín Oficial del Estado',
    officialUrl: 'https://www.boe.es/',
    accessType: 'Canales oficiales de consulta',
    statusLabel: 'Activa',
    summary: 'Publica disposiciones y actos oficiales del ámbito estatal.',
    publicationState: 'public_records',
  },
  {
    sourceId: 'bdns',
    name: 'Base de Datos Nacional de Subvenciones (SNPSAP)',
    responsibleBody: 'Intervención General de la Administración del Estado',
    officialUrl: 'https://www.infosubvenciones.es/bdnstrans/GE/es/inicio',
    accessType: 'API pública oficial',
    statusLabel: 'Activa',
    summary: 'Convocatorias de subvenciones con ámbito provincial de Castellón confirmado mediante información territorial estructurada.',
    publicationState: 'public_records',
    attribution: 'Origen de los datos: Intervención General de la Administración del Estado',
  },
  {
    sourceId: 'bop_castellon',
    name: 'Boletín Oficial de la Provincia de Castellón',
    responsibleBody: 'Diputación Provincial de Castellón',
    officialUrl: 'https://bop.dipcas.es/PortalBOP/',
    accessType: 'Portal oficial del boletín',
    statusLabel: 'Publicación pendiente',
    summary: 'La integración técnica está preparada. InfoCs no publica sus registros mientras se aclaran las condiciones de reutilización.',
    publicationState: 'publication_pending',
  },
];

export const PUBLIC_SOURCE_IDS: ReadonlySet<string> = new Set(
  SOURCE_METADATA
    .filter((source) => source.publicationState === 'public_records')
    .map((source) => source.sourceId),
);

export function buildSources(records: readonly FrontendRecord[]): FrontendSource[] {
  const counts = new Map<string, number>();
  for (const record of records) counts.set(record.sourceId, (counts.get(record.sourceId) ?? 0) + 1);

  const configuredIds = new Set(SOURCE_METADATA.map((source) => source.sourceId));
  const configured = SOURCE_METADATA.map((source) => ({
    ...source,
    recordCount: counts.get(source.sourceId) ?? 0,
  }));

  const unknownSources = [...counts.entries()]
    .filter(([sourceId]) => !configuredIds.has(sourceId))
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
    .map(([sourceId, recordCount]) => {
      const record = records.find((item) => item.sourceId === sourceId);
      if (!record) throw new Error(`No se pudo resolver metadata de fuente ${sourceId}.`);
      return {
        sourceId,
        name: 'Fuente oficial',
        responsibleBody: 'Organismo editor de la fuente',
        officialUrl: record.sourceUrl,
        accessType: 'Fuente oficial',
        statusLabel: 'Activa',
        summary: 'Registros públicos disponibles.',
        publicationState: 'public_records' as const,
        recordCount,
      };
    });

  return [...configured, ...unknownSources];
}
