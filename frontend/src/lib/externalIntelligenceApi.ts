import { closedLoopFetch as req } from './closedLoopFetch';

export type ExternalSource = {
  source_id: string;
  name: string;
  source_type: string;
  base_url: string;
  license_type: string;
  allowed_usage: string;
  refresh_frequency: string;
  owner_department: string;
  trust_grade: string;
  enabled: number | boolean;
  approved_by: string;
  note?: string;
};

export type ExternalIndicator = {
  indicator_id: string;
  code: string;
  name: string;
  category: string;
  canonical_term: string;
  unit: string;
  frequency: string;
  required_grade: string;
  acceptable_latency: string;
  source_hint: string;
  purpose: string;
  gap_impact: string;
  next_action: string;
  origin: string;
};

export type ExternalObservation = {
  observation_id: string;
  observed_at: string;
  published_at: string;
  value: number;
  unit: string;
  vintage: string;
  grade: string;
  source_id: string;
  quality_status: string;
};

export type ExternalReadiness = {
  total: number;
  usable_for_baseline: number;
  blocked: number;
  approved_sources: number;
  note: string;
  indicators: Array<{
    code: string; name: string; required_grade: string; acceptable_latency: string;
    source_hint: string; usable_for_baseline: boolean; reason: string;
    gap_impact: string; next_action: string;
  }>;
};

export type ResolvedExternalValue = {
  indicator_code: string;
  allowed: boolean;
  value: number | null;
  unit?: string;
  grade?: string;
  observed_at?: string;
  vintage?: string;
  source_id?: string;
  required_grade?: string;
  reason?: string;
  next_action?: string;
};

export type ExternalSourceInput = {
  name: string;
  source_type: 'API' | 'CSV' | 'RSS' | 'WEB' | 'REPORT' | 'PROVIDER_API';
  base_url?: string;
  license_type?: string;
  allowed_usage?: string;
  refresh_frequency?: string;
  owner_department?: string;
  trust_grade: 'gold' | 'silver' | 'bronze';
  note?: string;
};

export type ExternalObservationInput = {
  indicator_code: string;
  observed_at: string;
  value: number;
  vintage: string;
  grade: 'gold' | 'silver' | 'bronze';
  source_id: string;
  published_at?: string;
  unit?: string;
  source_record_ref?: string;
  quality_status: 'RAW' | 'VALIDATED' | 'REJECTED' | 'SUPERSEDED';
  note?: string;
};

export type ExternalCollectable = {
  ready: boolean;
  approved_total: number;
  auto_collectable: number;
  note: string;
  sources: Array<{
    source_id: string;
    name: string;
    source_type: string;
    trust_grade: string;
    auto: boolean;
  }>;
};

export type ExternalCollectionResult = {
  source_id: string;
  source_name: string;
  grade: string;
  origin: string;
  dry_run: boolean;
  collected_at: string;
  loaded: number;
  skipped: number;
  note: string;
  items: Array<{
    row: number;
    observation_id?: string;
    indicator?: string;
    observed_at?: string;
    value?: number;
    vintage?: string;
    unit?: string;
    grade?: string;
  }>;
  skipped_items: Array<{ row: number; reason: string; raw?: string }>;
};

export type CsvCollectionInput = {
  source_id: string;
  content: string;
  dry_run: boolean;
  default_indicator?: string;
};

export type SourceCollectionInput = {
  dry_run: boolean;
  path?: string;
  indicator_map?: Record<string, string>;
  timeout?: number;
};

export const externalIntelligenceApi = {
  readiness: () => req<ExternalReadiness>('GET', '/api/v1/external/readiness'),
  collectable: () => req<ExternalCollectable>('GET', '/api/v1/external/collectable'),
  indicators: () => req<ExternalIndicator[]>('GET', '/api/v1/external/indicators'),
  sources: () => req<ExternalSource[]>('GET', '/api/v1/external/sources'),
  registerSource: (body: ExternalSourceInput) => req<ExternalSource>(
    'POST', '/api/v1/external/sources', body),
  approveSource: (sourceId: string) => req<ExternalSource>(
    'POST', `/api/v1/external/sources/${encodeURIComponent(sourceId)}/approve`),
  recordObservation: (body: ExternalObservationInput) => req<ExternalObservation>(
    'POST', '/api/v1/external/observations', body),
  collectCsv: (body: CsvCollectionInput) => req<ExternalCollectionResult>(
    'POST', '/api/v1/external/collect/csv', body),
  collectSource: (sourceId: string, body: SourceCollectionInput) => req<ExternalCollectionResult>(
    'POST', `/api/v1/external/collect/${encodeURIComponent(sourceId)}`, body),
  observations: (code: string) => req<ExternalObservation[]>(
    'GET', `/api/v1/external/observations/${encodeURIComponent(code)}?limit=50`),
  resolveBaseline: (code: string) => req<ResolvedExternalValue>(
    'GET', `/api/v1/external/value/${encodeURIComponent(code)}?purpose=baseline_plan`),
};
