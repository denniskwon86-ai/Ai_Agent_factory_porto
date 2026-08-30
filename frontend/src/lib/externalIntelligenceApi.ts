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

export type ExternalIndicatorProposalInput = {
  name: string;
  category?: string;
  canonical_term?: string;
  unit?: string;
  frequency?: string;
  required_grade: 'gold' | 'silver' | 'bronze';
  acceptable_latency?: string;
  source_hint?: string;
  purpose?: string;
  gap_impact?: string;
  next_action?: string;
  rationale?: string;
};

export type ExternalIndicatorProposal = ExternalIndicatorProposalInput & {
  proposal_id: string;
  fingerprint: string;
  status: 'pending' | 'approved' | 'rejected';
  proposed_by: string;
  reviewed_by: string;
  review_reason: string;
  reviewed_at: string;
  created_at: string;
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

export type ResearchProfileStatus = 'DRAFT' | 'REVIEW_REQUIRED' | 'APPROVED' | 'PAUSED' | 'RETIRED';
export type ResearchProfile = {
  profile_id: string;
  legal_entity_id: string;
  company_name: string;
  official_domains: string[];
  official_urls: string[];
  business_keywords: string[];
  product_keywords: string[];
  regions: string[];
  competitor_names: string[];
  material_keywords: string[];
  required_indicators: string[];
  collection_purpose: string;
  schedule_rule: string;
  owner_id: string;
  retention_days: number;
  status: ResearchProfileStatus;
  approved_by: string;
  approved_at: string;
  fingerprint: string;
  updated_at: string;
};

export type ResearchProfileInput = Omit<ResearchProfile,
  'profile_id' | 'status' | 'approved_by' | 'approved_at' | 'fingerprint' | 'updated_at'>;

export type ResearchJob = {
  job_id: string;
  profile_id: string;
  bot_kind: 'COMPANY_BASE_RESEARCH' | 'INDICATOR_COLLECTOR' |
    'EXTERNAL_EVENT_MONITOR' | 'QUALITY_CHANGE_MONITOR';
  status: 'SCHEDULED' | 'RUNNING' | 'CANDIDATE_READY' | 'ACCEPTED' |
    'REJECTED' | 'FAILED' | 'CANCELLED';
  dry_run: boolean;
  profile_fingerprint: string;
  requested_by: string;
  requested_at: string;
  error: string;
  result_summary: Record<string, unknown>;
};

export type ResearchCandidate = {
  candidate_id: string;
  job_id: string;
  profile_id: string;
  candidate_kind: string;
  source_url: string;
  title: string;
  summary: string;
  evidence: Record<string, unknown>;
  content_hash: string;
  status: 'CANDIDATE_READY' | 'ACCEPTED' | 'REJECTED';
  reviewed_by: string;
  created_at: string;
};

export const externalIntelligenceApi = {
  readiness: () => req<ExternalReadiness>('GET', '/api/v1/external/readiness'),
  collectable: () => req<ExternalCollectable>('GET', '/api/v1/external/collectable'),
  indicators: () => req<ExternalIndicator[]>('GET', '/api/v1/external/indicators'),
  indicatorProposals: (status: 'pending' | 'approved' | 'rejected' | 'all' = 'pending') =>
    req<ExternalIndicatorProposal[]>('GET', `/api/v1/external/indicators/proposals?status=${status}`),
  proposeIndicator: (body: ExternalIndicatorProposalInput) =>
    req<ExternalIndicatorProposal>('POST', '/api/v1/external/indicators/proposals', body),
  approveIndicatorProposal: (proposalId: string, expectedFingerprint: string, reason = '') =>
    req<{ proposal: ExternalIndicatorProposal; indicator: ExternalIndicator }>(
      'POST', `/api/v1/external/indicators/proposals/${encodeURIComponent(proposalId)}/approve`,
      { expected_fingerprint: expectedFingerprint, reason }),
  rejectIndicatorProposal: (proposalId: string, expectedFingerprint: string, reason: string) =>
    req<ExternalIndicatorProposal>(
      'POST', `/api/v1/external/indicators/proposals/${encodeURIComponent(proposalId)}/reject`,
      { expected_fingerprint: expectedFingerprint, reason }),
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
  researchProfiles: () => req<ResearchProfile[]>('GET', '/api/v1/external/research/profiles'),
  saveResearchProfile: (body: ResearchProfileInput) => req<ResearchProfile>(
    'POST', '/api/v1/external/research/profiles', body),
  submitResearchProfile: (profileId: string) => req<ResearchProfile>(
    'POST', `/api/v1/external/research/profiles/${encodeURIComponent(profileId)}/submit`),
  approveResearchProfile: (profileId: string, expectedFingerprint: string) => req<ResearchProfile>(
    'POST', `/api/v1/external/research/profiles/${encodeURIComponent(profileId)}/approve`,
    { expected_fingerprint: expectedFingerprint }),
  researchJobs: (profileId = '') => req<ResearchJob[]>(
    'GET', `/api/v1/external/research/jobs${profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ''}`),
  scheduleResearchJob: (profileId: string, botKind: ResearchJob['bot_kind']) => req<ResearchJob>(
    'POST', '/api/v1/external/research/jobs',
    { profile_id: profileId, bot_kind: botKind, dry_run: true }),
  runResearchJob: (jobId: string) => req<ResearchJob>(
    'POST', `/api/v1/external/research/jobs/${encodeURIComponent(jobId)}/run`),
  researchCandidates: (profileId = '') => req<ResearchCandidate[]>(
    'GET', `/api/v1/external/research/candidates${profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ''}`),
  decideResearchCandidate: (candidateId: string, decision: 'ACCEPTED' | 'REJECTED',
    expectedContentHash: string) => req<{ candidate: ResearchCandidate; registered_source: ExternalSource | null }>(
      'POST', `/api/v1/external/research/candidates/${encodeURIComponent(candidateId)}/decision`,
      { decision, expected_content_hash: expectedContentHash }),
  observations: (code: string) => req<ExternalObservation[]>(
    'GET', `/api/v1/external/observations/${encodeURIComponent(code)}?limit=50`),
  resolveBaseline: (code: string) => req<ResolvedExternalValue>(
    'GET', `/api/v1/external/value/${encodeURIComponent(code)}?purpose=baseline_plan`),
};
