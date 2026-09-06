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

// ── [DAO-8] 데이터 수집 오케스트레이터 ─────────────────────────────────────
// ★ 새 파일을 만들지 않는다 — 「외부 원천」을 다루는 클라이언트가 둘이 되면 화면마다
//   다른 규약을 쓰게 된다. 경로도 기존 `/api/v1/external` 아래다(지시 11).

export type AcquisitionState =
  | 'DRAFT' | 'DISCOVERING' | 'PLAN_READY' | 'DRY_RUN' | 'REVIEW_REQUIRED'
  | 'APPLYING' | 'ACTIVE' | 'FAILED' | 'NO_DATA' | 'QUARANTINED' | 'DISABLED';

export type ProviderCard = {
  provider_id: string;
  name: string;
  publisher: string;
  source_type: string;
  cost: string;
  requires_credential: boolean;
  /** 자격증명이 실제로 설정돼 있는가. 없으면 `excluded` 에 사유가 함께 온다. */
  credential_configured: boolean;
  default_trust_grade: string;
  refresh_frequency: string;
  coverage_note: string;
  license_url: string;
  allowed_usage: string;
  redistribution_allowed: boolean;
  target_contract_keys: string[];
  data_origin: string;
  /** ★ 「이 값으로 하면 안 되는 것」. 화면이 반드시 함께 보여 준다. */
  known_limits: string[];
};

export type AcquisitionCatalog = {
  providers: ProviderCard[];
  /** 지시 3 — 선택하지 않은 원천과 **제외 사유**. */
  excluded: { provider_id: string; reason: string }[];
  routing_table: Record<string, string>;
  data_origins: string[];
  states: AcquisitionState[];
};

export type InterpretProblem = { field: string; reason: string; got: string };

export type InterpretResult = {
  ok: boolean;
  problems: InterpretProblem[];
  /** 서버가 무시한 값과 그 이유 — 「왜 내가 쓴 대로 안 됐나」의 답. */
  overridden: InterpretProblem[];
  resolved_scope_node_id: string;
  required_grade: string;
  request: Record<string, unknown> | null;
};

export type AcquisitionJob = {
  job_id: string;
  tenant_id: string;
  scope_node_id: string;
  requested_by: string;
  subject_name: string;
  purpose: string;
  status: AcquisitionState;
  provider_id: string;
  dataset_ref: string;
  target_contract_key: string;
  status_reason: string;
  failure_kind: string;
  schedule_rule: string;
  next_run_at: string;
  last_success_at: string;
  is_schedulable: boolean;
  awaits_human: boolean;
  request: Record<string, unknown>;
  plan: Record<string, unknown>;
  dry_run: Record<string, unknown>;
  checkpoint: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type DryRunReport = {
  job_id: string;
  provider_id: string;
  dataset_ref: string;
  contract_key: string;
  chosen_reason: string;
  excluded_sources: { provider_id: string; reason: string }[];
  ambiguous_with: string[];
  expected_rows: number;
  new_rows: number;
  duplicate_rows: number;
  superseded_rows: number;
  rejected_rows: number;
  /** 결손 필드와 건수. ★ 0 으로 채우지 않았다는 증거다. */
  missing_fields: Record<string, number>;
  mapping_needs_human: string[];
  mapping_failed: { source: string; target: string; reason: string }[];
  unit_conversions: Record<string, unknown>[];
  target_contract_status: string;
  quarantined: { reason: string; detail: string }[];
  estimated_bytes: number;
  refresh_schedule: string;
  readiness_change_note: string;
  validation: { name: string; ok: boolean; detail: string }[];
  /** ★★★ 이 실행이 **하지 않는** 단계와 이유. 화면이 「다 됐다」로 읽지 않게 한다. */
  pending_stages: { name: string; reason: string }[];
};

export type ApplyReport = {
  job_id: string;
  ok: boolean;
  /** 일부만 들어갔다 — **성공이 아니다.** */
  partial: boolean;
  stages: { name: string; ok: boolean; detail: string; count: number }[];
  inserted: number;
  duplicate: number;
  superseded: number;
  rejected: number;
  raw_object_ref: string;
  pending_stages: { name: string; reason: string }[];
  failure_kind: string;
  failure_detail: string;
};

export type ContractProposal = {
  proposal_id: string;
  contract_key: string;
  contract_version: string;
  rationale: string;
  status: 'PROPOSED' | 'APPROVED' | 'REJECTED';
  proposed_by: string;
  reviewed_by: string;
  review_reason: string;
  document: Record<string, unknown>;
};

export type StagedRows = {
  rows: Record<string, unknown>[];
  count: number;
  /** ★★★ 「운영 데이터셋이 아니다」 — 화면이 이 문구를 지우지 않는다. */
  notice: string;
};

const ACQ = '/api/v1/external/acquisition';

export const acquisitionApi = {
  catalog: () => req<AcquisitionCatalog>('GET', `${ACQ}/catalog`),
  interpret: (proposal: Record<string, unknown>, purposeKind = 'scenario') =>
    req<InterpretResult>('POST', `${ACQ}/interpret`,
      { proposal, purpose_kind: purposeKind }),
  createJob: (proposal: Record<string, unknown>, purposeKind = 'scenario') =>
    req<AcquisitionJob>('POST', `${ACQ}/jobs`, { proposal, purpose_kind: purposeKind }),
  jobs: (status = '') =>
    req<AcquisitionJob[]>('GET', `${ACQ}/jobs${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  job: (jobId: string) =>
    req<AcquisitionJob & { raw_objects: Record<string, unknown>[]; history: Record<string, unknown>[] }>(
      'GET', `${ACQ}/jobs/${encodeURIComponent(jobId)}`),
  discover: (jobId: string) =>
    req<AcquisitionJob>('POST', `${ACQ}/jobs/${encodeURIComponent(jobId)}/discover`),
  dryRun: (jobId: string, body: { mapping_proposal?: Record<string, unknown>[]; as_of?: string } = {}) =>
    req<{ job: AcquisitionJob; report: DryRunReport }>(
      'POST', `${ACQ}/jobs/${encodeURIComponent(jobId)}/dry-run`, body),
  apply: (jobId: string, asOf = '') =>
    req<{ job: AcquisitionJob; report: ApplyReport }>(
      'POST', `${ACQ}/jobs/${encodeURIComponent(jobId)}/apply`, { as_of: asOf }),
  stagedRows: (jobId: string, limit = 200) =>
    req<StagedRows>('GET', `${ACQ}/jobs/${encodeURIComponent(jobId)}/rows?limit=${limit}`),
  contractProposals: (status = '') =>
    req<ContractProposal[]>('GET',
      `${ACQ}/contract-proposals${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  proposeContract: (contractKey: string) =>
    req<ContractProposal>('POST', `${ACQ}/contract-proposals/${encodeURIComponent(contractKey)}`),
  decideContract: (proposalId: string, approve: boolean, reason = '') =>
    req<ContractProposal>('POST',
      `${ACQ}/contract-proposals/${encodeURIComponent(proposalId)}/decision`,
      { approve, reason }),
  setSchedule: (jobId: string, scheduleRule: string, nextRunAt: string) =>
    req<AcquisitionJob>('POST', `${ACQ}/jobs/${encodeURIComponent(jobId)}/schedule`,
      { schedule_rule: scheduleRule, next_run_at: nextRunAt }),
  due: (now = '') =>
    req<AcquisitionJob[]>('GET', `${ACQ}/due${now ? `?now=${encodeURIComponent(now)}` : ''}`),
  disable: (jobId: string, reason: string) =>
    req<AcquisitionJob>('POST', `${ACQ}/jobs/${encodeURIComponent(jobId)}/disable`, { reason }),
};
