import type { PortalData, SourceMeta } from '../data/types';
import { changeItems, type ChangeItemView } from './changes';

interface SourceEditorialDetails {
  readonly sourceId: string;
  readonly slug: string;
  readonly scope: string;
  readonly accessNote: string;
  readonly reuseNote: string;
}

export const SOURCE_EDITORIAL_DETAILS: readonly SourceEditorialDetails[] = [
  {
    sourceId: 'boe',
    slug: 'boe',
    scope: 'Fuente estatal. InfoCs sólo muestra publicaciones que cumplen sus criterios documentados de relevancia territorial.',
    accessNote: 'Consulta oficial del BOE y API OpenData para sumarios y metadatos.',
    reuseNote: 'InfoCs conserva la atribución y el enlace oficial, y no debe desnaturalizar la información ni sugerir respaldo institucional. Esta versión muestra metadatos y enlaces; no reproduce el texto íntegro.',
  },
  {
    sourceId: 'bdns',
    slug: 'bdns',
    scope: 'Convocatorias con impacto provincial de Castellón confirmado mediante la señal territorial oficial definida para BDNS. Un ámbito autonómico o estatal amplio no se reduce automáticamente a la provincia.',
    accessNote: 'API pública oficial del Sistema Nacional de Publicidad de Subvenciones y Ayudas Públicas (SNPSAP).',
    reuseNote: 'InfoCs publica metadata de convocatorias con atribución IGAE y enlace al origen. No incluye concesiones individuales, beneficiarios, documentos copiados ni texto íntegro.',
  },
  {
    sourceId: 'bop_castellon',
    slug: 'bop-castellon',
    scope: 'Boletín oficial de la provincia de Castellón.',
    accessNote: 'Consulta en el portal oficial del BOP de Castellón.',
    reuseNote: 'La base aplicable para republicar metadata del BOP sigue pendiente de confirmación. InfoCs no publica registros de esta fuente hasta resolverlo.',
  },
];

export function sourceDetailPath(sourceId: string): string | null {
  const source = SOURCE_EDITORIAL_DETAILS.find((item) => item.sourceId === sourceId);
  return source ? `/fuentes/${source.slug}/` : null;
}

export interface SourceDetailView {
  readonly source: SourceMeta & { readonly recordCount: number };
  readonly slug: string;
  readonly scope: string;
  readonly accessNote: string;
  readonly reuseNote: string;
  readonly records: PortalData['records'];
  readonly activity: readonly ChangeItemView[];
}

export function sourceDetailBySlug(data: PortalData, slug: string): SourceDetailView | null {
  const editorial = SOURCE_EDITORIAL_DETAILS.find((item) => item.slug === slug);
  if (!editorial) return null;
  const source = data.sources.find((item) => item.sourceId === editorial.sourceId);
  if (!source) throw new Error(`Frontend data contract: falta metadata editorial para la fuente ${editorial.sourceId}.`);
  const records = data.records.filter((record) => record.sourceId === source.sourceId);
  return {
    source,
    slug: editorial.slug,
    scope: editorial.scope,
    accessNote: editorial.accessNote,
    reuseNote: editorial.reuseNote,
    records,
    activity: changeItems(data).filter((item) => item.sourceId === source.sourceId),
  };
}
