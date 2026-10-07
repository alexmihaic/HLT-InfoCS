import type {
  FrontendBDNSApplication,
  FrontendBDNSClassification,
  FrontendBDNSDocument,
  FrontendRecord,
} from '../data/types';
import { formatPortalDate } from './dates';

/** Values remain official; labels, formatting and paths are presentation-derived. */
interface BDNSOfficialView {
  readonly origin: 'official';
  readonly label: string;
  readonly canonicalPath: string;
}

export interface BDNSTextView extends BDNSOfficialView {
  readonly value: string;
}

export interface BDNSDateView extends BDNSOfficialView {
  readonly value: string;
  readonly display: string;
}

export interface BDNSBudgetView extends BDNSOfficialView {
  readonly rawValue: string;
  readonly displayValue: string;
  readonly currency?: string;
  readonly currencyCanonicalPath?: string;
  readonly currencyNotice?: 'Moneda no indicada en los datos';
}

export interface BDNSAuthorityHierarchyLevelView extends BDNSTextView {
  readonly level: 1 | 2 | 3;
}

export interface BDNSAuthorityHierarchyView extends BDNSOfficialView {
  readonly items: readonly BDNSAuthorityHierarchyLevelView[];
}

export interface BDNSStringListView extends BDNSOfficialView {
  readonly items: readonly string[];
}

export interface BDNSClassificationView {
  readonly label: string;
  readonly code?: string;
}

export interface BDNSClassificationListView extends BDNSOfficialView {
  readonly items: readonly BDNSClassificationView[];
}

export interface BDNSApplicationBoundaryView extends BDNSOfficialView {
  readonly date?: BDNSDateView;
  readonly text?: BDNSTextView;
}

export interface BDNSApplicationView extends BDNSOfficialView {
  readonly start?: BDNSApplicationBoundaryView;
  readonly end?: BDNSApplicationBoundaryView;
}

export interface BDNSRegulatoryBasesView extends BDNSOfficialView {
  readonly description?: BDNSTextView;
  readonly sourceLocator?: BDNSTextView;
}

export interface BDNSDocumentView {
  readonly canonicalPath: string;
  readonly description?: BDNSTextView;
  readonly filename?: BDNSTextView;
  readonly publishedDate?: BDNSDateView;
}

export interface BDNSDocumentsView extends BDNSOfficialView {
  readonly items: readonly BDNSDocumentView[];
}

export interface BDNSRecordView {
  readonly kind: 'bdns';
  readonly identity: {
    readonly title: BDNSTextView;
    readonly authority?: BDNSTextView;
    readonly callId?: BDNSTextView;
  };
  readonly officialTitleCoofficial?: BDNSTextView;
  readonly authorityHierarchy?: BDNSAuthorityHierarchyView;
  readonly budget?: BDNSBudgetView;
  readonly callType?: BDNSTextView;
  readonly instruments: BDNSStringListView;
  readonly beneficiaryTypes: BDNSClassificationListView;
  readonly sectors: BDNSClassificationListView;
  readonly impactRegions: BDNSStringListView;
  readonly receivedDate?: BDNSDateView;
  readonly application?: BDNSApplicationView;
  readonly purpose?: BDNSTextView;
  readonly regulatoryBases?: BDNSRegulatoryBasesView;
  readonly electronicOffice?: BDNSTextView;
  readonly documents: BDNSDocumentsView;
}

const BDNS_PATH = 'source_data.bdns';

/** Exact grouping of decimal text, including its original fractional scale. */
export function formatBDNSExactDecimal(value: string): string {
  if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)(\.[0-9]+)?$/.test(value)) {
    throw new Error('BDNS presentation contract: decimal incompatible.');
  }
  const [integer, fraction] = value.split('.');
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return fraction === undefined ? grouped : `${grouped},${fraction}`;
}

/** Pure projection; no clock, links, narrative, sorting or mutation. */
export function buildBDNSRecordView(record: FrontendRecord): BDNSRecordView | null {
  if (record.sourceId !== 'bdns') return null;
  if (record.bdns === undefined) {
    throw new Error('BDNS presentation contract: typed projection required.');
  }
  const data = record.bdns;
  const hierarchy: BDNSAuthorityHierarchyLevelView[] = [];
  if (data.authorityHierarchy !== undefined) {
    for (const level of [1, 2, 3] as const) {
      const key = `nivel${level}` as const;
      const value = data.authorityHierarchy[key];
      if (value !== undefined) {
        hierarchy.push({ ...textView(`Nivel ${level}`, value, `${BDNS_PATH}.authority_hierarchy.${key}`), level });
      }
    }
  }
  return {
    kind: 'bdns',
    identity: {
      title: textView('Título oficial', record.title, 'title'),
      ...(record.authority !== null ? { authority: textView('Organismo', record.authority.name, 'authority.name') } : {}),
      ...(record.grant?.callId !== undefined ? { callId: textView('Código BDNS', record.grant.callId, 'grant.call_id') } : {}),
    },
    ...(data.officialTitleCoofficial !== undefined ? {
      officialTitleCoofficial: textView('Título oficial en otra lengua', data.officialTitleCoofficial, `${BDNS_PATH}.official_title_coofficial`),
    } : {}),
    ...(hierarchy.length > 0 ? {
      authorityHierarchy: { ...officialGroup('Jerarquía del organismo', `${BDNS_PATH}.authority_hierarchy`), items: hierarchy },
    } : {}),
    ...(data.budgetTotal !== undefined ? {
      budget: {
        ...officialGroup('Presupuesto de la convocatoria', `${BDNS_PATH}.budget_total.value`),
        rawValue: data.budgetTotal.value,
        displayValue: formatBDNSExactDecimal(data.budgetTotal.value),
        ...(data.budgetTotal.currency !== undefined ? {
          currency: data.budgetTotal.currency, currencyCanonicalPath: `${BDNS_PATH}.budget_total.currency`,
        } : { currencyNotice: 'Moneda no indicada en los datos' as const }),
      },
    } : {}),
    ...(data.callType !== undefined ? { callType: textView('Tipo de convocatoria', data.callType, `${BDNS_PATH}.call_type`) } : {}),
    instruments: stringList('Instrumentos de ayuda', data.instruments, `${BDNS_PATH}.instruments`),
    beneficiaryTypes: classificationList('Tipos de destinatarios elegibles', data.eligibleBeneficiaryTypes, `${BDNS_PATH}.eligible_beneficiary_types`),
    sectors: classificationList('Sectores según BDNS', data.sectors, `${BDNS_PATH}.sectors`),
    impactRegions: stringList('Ámbito declarado en BDNS', data.impactRegions, `${BDNS_PATH}.impact_regions`),
    ...(data.receivedDate !== undefined ? {
      receivedDate: dateView('Fecha de recepción en BDNS', data.receivedDate, `${BDNS_PATH}.received_date`),
    } : {}),
    ...applicationView(data.application),
    ...(data.purpose !== undefined ? { purpose: textView('Finalidad declarada', data.purpose, `${BDNS_PATH}.purpose`) } : {}),
    ...(data.regulatoryBases !== undefined ? {
      regulatoryBases: {
        ...officialGroup('Bases reguladoras', `${BDNS_PATH}.regulatory_bases`),
        ...(data.regulatoryBases.description !== undefined ? {
          description: textView('Bases reguladoras', data.regulatoryBases.description, `${BDNS_PATH}.regulatory_bases.description`),
        } : {}),
        ...(data.regulatoryBases.sourceLocator !== undefined ? {
          sourceLocator: textView('Localizador suministrado por BDNS', data.regulatoryBases.sourceLocator, `${BDNS_PATH}.regulatory_bases.source_locator`),
        } : {}),
      },
    } : {}),
    ...(data.electronicOfficeUrl !== undefined ? {
      electronicOffice: textView('Sede electrónica indicada por BDNS', data.electronicOfficeUrl, `${BDNS_PATH}.electronic_office_url`),
    } : {}),
    documents: {
      ...officialGroup('Documentos oficiales', `${BDNS_PATH}.documents`),
      items: data.documents.map(documentView),
    },
  };
}

function officialGroup(label: string, canonicalPath: string): BDNSOfficialView {
  return { origin: 'official', label, canonicalPath };
}

function textView(label: string, value: string, canonicalPath: string): BDNSTextView {
  return { ...officialGroup(label, canonicalPath), value };
}

function dateView(label: string, value: string, canonicalPath: string): BDNSDateView {
  return { ...officialGroup(label, canonicalPath), value, display: formatPortalDate(value) };
}

function stringList(label: string, items: readonly string[], canonicalPath: string): BDNSStringListView {
  return { ...officialGroup(label, canonicalPath), items: [...items] };
}

function classificationList(label: string, items: readonly FrontendBDNSClassification[], canonicalPath: string): BDNSClassificationListView {
  return { ...officialGroup(label, canonicalPath), items: items.map((item) => ({
    label: item.label, ...(item.code !== undefined ? { code: item.code } : {}),
  })) };
}

function applicationView(data: FrontendBDNSApplication | undefined): { readonly application?: BDNSApplicationView } {
  if (data === undefined) return {};
  const start = applicationBoundary('Inicio de solicitud', 'start', data.startDate, data.startText);
  const end = applicationBoundary('Fin de solicitud', 'end', data.endDate, data.endText);
  if (start === undefined && end === undefined) return {};
  return { application: {
    ...officialGroup('Periodo de solicitud', `${BDNS_PATH}.application`),
    ...(start !== undefined ? { start } : {}), ...(end !== undefined ? { end } : {}),
  } };
}

function applicationBoundary(label: string, side: 'start' | 'end', date: string | undefined, text: string | undefined): BDNSApplicationBoundaryView | undefined {
  if (date === undefined && text === undefined) return undefined;
  return {
    ...officialGroup(label, `${BDNS_PATH}.application`),
    ...(date !== undefined ? { date: dateView(label, date, `${BDNS_PATH}.application.${side}_date`) } : {}),
    ...(text !== undefined ? { text: textView(label, text, `${BDNS_PATH}.application.${side}_text`) } : {}),
  };
}

function documentView(data: FrontendBDNSDocument, index: number): BDNSDocumentView {
  // Indexed paths refer to the supplied canonical order, not a ranking or new ID.
  const path = `${BDNS_PATH}.documents[${index}]`;
  return {
    canonicalPath: path,
    ...(data.description !== undefined ? { description: textView('Descripción del documento', data.description, `${path}.description`) } : {}),
    ...(data.filename !== undefined ? { filename: textView('Nombre de archivo', data.filename, `${path}.filename`) } : {}),
    ...(data.publishedDate !== undefined ? { publishedDate: dateView('Publicación del documento', data.publishedDate, `${path}.published_date`) } : {}),
  };
}

// MVP intentionally excludes extracts, both source flags, document IDs/datMod,
// technical versions, narrative and clickability. They remain in E2's projection.
