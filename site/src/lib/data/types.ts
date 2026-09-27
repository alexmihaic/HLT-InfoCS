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
