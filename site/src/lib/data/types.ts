export type AdministrationLevel =
  | 'municipal'
  | 'provincial'
  | 'autonomous'
  | 'state';

export interface FrontendAuthority {
  readonly id: string;
  readonly name: string;
  readonly administrationLevel: AdministrationLevel | null;
}

export interface FrontendGeography {
  readonly municipality?: string;
  readonly province?: string;
}

export interface FrontendGrant {
  readonly callId?: string;
  readonly resolutionId?: string;
}

export interface FrontendMoney {
  readonly value: string;
  readonly currency: string;
}

export type FrontendFinancial = Partial<
  Record<
    | 'baseBudget'
    | 'estimatedValue'
    | 'tenderAmount'
    | 'awardAmount'
    | 'modificationAmount'
    | 'grantAmount',
    FrontendMoney
  >
>;

export interface FrontendDocument {
  readonly sourceUrl: string;
  readonly archiveStatus: 'not_archived' | 'archived';
  readonly hasLocalCopy: boolean;
  readonly publicationAllowed: boolean;
}

export interface FrontendBDNSBudget {
  readonly value: string;
  readonly currency?: string;
}

export interface FrontendBDNSAuthorityHierarchy {
  readonly nivel1?: string;
  readonly nivel2?: string;
  readonly nivel3?: string;
}

export interface FrontendBDNSClassification {
  readonly label: string;
  readonly code?: string;
}

export interface FrontendBDNSApplication {
  readonly startDate?: string;
  readonly endDate?: string;
  readonly startText?: string;
  readonly endText?: string;
  readonly abierto?: boolean;
}

export interface FrontendBDNSRegulatoryBases {
  readonly description?: string;
  readonly sourceLocator?: string;
}

export interface FrontendBDNSDocument {
  readonly sourceDocumentId: number;
  readonly description?: string;
  readonly filename?: string;
  readonly publishedDate?: string;
  readonly modifiedValue?: string;
}

export interface FrontendBDNSExtract {
  readonly cve?: string;
  readonly diary?: string;
  readonly sourceUrl?: string;
  readonly publicationDate?: string;
  readonly title?: string;
  readonly titleCoofficial?: string;
}

/** Literal metadata projection; not Privacy/Publication or navigation authorization. */
export interface FrontendBDNSData {
  readonly extensionVersion: '1.0';
  readonly officialTitleCoofficial?: string;
  readonly authorityHierarchy?: FrontendBDNSAuthorityHierarchy;
  readonly budgetTotal?: FrontendBDNSBudget;
  readonly callType?: string;
  readonly instruments: readonly string[];
  readonly eligibleBeneficiaryTypes: readonly FrontendBDNSClassification[];
  readonly sectors: readonly FrontendBDNSClassification[];
  readonly impactRegions: readonly string[];
  readonly receivedDate?: string;
  readonly application?: FrontendBDNSApplication;
  readonly purpose?: string;
  readonly regulatoryBases?: FrontendBDNSRegulatoryBases;
  readonly electronicOfficeUrl?: string;
  readonly extractPublishedInOfficialDiary?: boolean;
  readonly documents: readonly FrontendBDNSDocument[];
  readonly extracts: readonly FrontendBDNSExtract[];
}

/** Build-time projection of the canonical Record, not a second business model. */
export interface FrontendRecord {
  readonly id: string;
  readonly sourceId: string;
  readonly officialId?: string;
  readonly category: string;
  readonly title: string;
  readonly authority: FrontendAuthority | null;
  readonly administrationLevel: AdministrationLevel | null;
  readonly publishedAt?: string;
  readonly eventAt?: string;
  readonly detectedAt: string;
  readonly lastCheckedAt: string;
  readonly sourceUrl: string;
  readonly geography?: FrontendGeography;
  readonly grant?: FrontendGrant;
  readonly financial?: FrontendFinancial;
  readonly documents?: readonly FrontendDocument[];
  readonly tags: readonly string[];
  readonly contentHash: string;
  readonly bdns?: FrontendBDNSData;
}

export interface FrontendEvent {
  readonly eventId: string;
  readonly type: 'create' | 'update';
  readonly recordId: string;
  readonly sourceId: string;
  readonly observedAt: string;
  readonly contentHash: string;
  readonly previousContentHash?: string;
  readonly changedFields?: readonly string[];
}

export interface SourceMeta {
  readonly sourceId: string;
  readonly name: string;
  readonly responsibleBody: string;
  readonly officialUrl: string;
  readonly accessType: string;
  readonly statusLabel: string;
  readonly summary: string;
  readonly publicationState: 'public_records' | 'publication_pending';
  readonly attribution?: string;
}

export interface FrontendSource extends SourceMeta {
  readonly recordCount: number;
}

export interface PortalData {
  readonly records: readonly FrontendRecord[];
  readonly events: readonly FrontendEvent[];
  readonly sources: readonly FrontendSource[];
  readonly eventsByRecordId: ReadonlyMap<string, readonly FrontendEvent[]>;
}
