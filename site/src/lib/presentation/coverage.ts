import type { PortalStatus, SourceRunStatus } from '../data/status';
import type { FrontendSource } from '../data/types';
import { formatPortalDateTime } from './dates';
import { sourceLabel } from './labels';
import { SOURCE_EDITORIAL_DETAILS } from './sourceDetails';

/**
 * Presentation of operational coverage. Every timestamp shown here is an InfoCs
 * system observation (a recorded run), never an official publication date and
 * never a real-time freshness guarantee.
 */

export interface CoverageFact {
  readonly label: string;
  readonly value: string;
  readonly datetime?: string;
}

export interface SourceCoverageView {
  readonly sourceId: string;
  readonly name: string;
  readonly published: boolean;
  readonly statusLabel: string;
  readonly statusTone: 'active' | 'pending';
  readonly scope: string;
  readonly recordCountLabel: string;
  readonly facts: readonly CoverageFact[];
  readonly detailPath?: string;
}

export interface NotCoveredItem {
  readonly title: string;
  readonly detail: string;
}

const HEALTH_LABELS = {
  healthy: 'Última ejecución registrada sin incidencias',
  degraded: 'Ejecuciones recientes con incidencias',
  failing: 'Ejecuciones recientes fallidas',
  unknown: 'Estado de ejecución no disponible',
} as const;

export function sourceCoverage(
  sources: readonly FrontendSource[],
  status: PortalStatus,
): SourceCoverageView[] {
  return sources.map((source) => {
    const editorial = SOURCE_EDITORIAL_DETAILS.find((item) => item.sourceId === source.sourceId);
    const run = status.sources.get(source.sourceId);
    const published = source.publicationState === 'public_records';
    const facts: CoverageFact[] = [];
    if (published) {
      facts.push(...runFacts(run));
      if (source.sourceId === 'boe' && status.boePendingReview !== undefined) {
        facts.push({
          label: 'Detectadas y pendientes de revisión (no publicadas)',
          value: String(status.boePendingReview),
        });
      }
    }
    return {
      sourceId: source.sourceId,
      name: sourceLabel(source.sourceId, sources),
      published,
      statusLabel: published ? runStatusLabel(run) : 'Sin registros públicos',
      statusTone: published && run?.health?.status === 'healthy' ? 'active' : 'pending',
      scope: published
        ? editorial?.scope ?? source.summary
        : source.summary,
      recordCountLabel: published
        ? `${source.recordCount} ${source.recordCount === 1 ? 'registro publicado' : 'registros publicados'}`
        : 'No se publican registros',
      facts,
      ...(editorial ? { detailPath: `/fuentes/${editorial.slug}/` } : {}),
    };
  });
}

function runStatusLabel(run: SourceRunStatus | undefined): string {
  if (run?.health === undefined) return 'Estado de ejecución no disponible';
  return HEALTH_LABELS[run.health.status];
}

function runFacts(run: SourceRunStatus | undefined): CoverageFact[] {
  if (run === undefined || (run.health === undefined && run.lastRun === undefined)) {
    return [{ label: 'Ejecuciones registradas', value: 'Sin datos de ejecución publicados' }];
  }
  const facts: CoverageFact[] = [];
  const lastSuccessAt = run.health?.lastSuccessAt;
  facts.push(lastSuccessAt
    ? { label: 'Última ejecución satisfactoria registrada', value: formatPortalDateTime(lastSuccessAt), datetime: lastSuccessAt }
    : { label: 'Última ejecución satisfactoria registrada', value: 'No disponible' });
  const lastAttemptAt = run.health?.lastAttemptAt;
  const failures = run.health?.consecutiveFailures ?? 0;
  // A later attempt is only meaningful to citizens when it did not succeed.
  if (lastAttemptAt && failures > 0) {
    facts.push({
      label: `Último intento registrado, sin éxito (${failures} ${failures === 1 ? 'fallo consecutivo' : 'fallos consecutivos'})`,
      value: formatPortalDateTime(lastAttemptAt),
      datetime: lastAttemptAt,
    });
  }
  // manifestCount is the number of run manifest files found in data/manifests/<source>.
  // Each manifest represents one recorded collector run, not a verified unique execution.
  if (run.manifestCount > 0) {
    facts.push({
      label: 'Manifiestos de ejecución registrados',
      value: String(run.manifestCount),
    });
  }
  return facts;
}

/** Explicit, current gaps. Not a roadmap: nothing here promises future coverage. */
export const NOT_COVERED: readonly NotCoveredItem[] = [
  {
    title: 'Contratación pública estructurada',
    detail: 'La Plataforma de Contratación del Sector Público (PLACSP) no está integrada en InfoCs.',
  },
  {
    title: 'Boletín Oficial de la Provincia de Castellón',
    detail: 'La integración técnica existe, pero sus registros no se publican mientras no se aclaren las condiciones de reutilización.',
  },
  {
    title: 'Boletín autonómico (DOGV) y portales municipales',
    detail: 'No se recopilan en esta versión.',
  },
  {
    title: 'Ayudas de ámbito autonómico o estatal amplio',
    detail: 'De BDNS sólo se incluyen convocatorias cuyo ámbito declarado es la provincia de Castellón; un ámbito más amplio no se atribuye automáticamente.',
  },
  {
    title: 'Textos y documentos íntegros',
    detail: 'InfoCs muestra metadatos y enlaza la fuente oficial; no reproduce documentos completos.',
  },
];
