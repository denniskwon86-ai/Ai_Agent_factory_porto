import { useCallback, useEffect, useState } from 'react';

import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { EmptyOrError, Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { ConfirmInline, FormField, useConfirm } from '../design/DataFoundationShell';
import {
  externalIntelligenceApi, type ExternalCollectable, type ExternalCollectionResult,
  type ExternalIndicator, type ExternalObservation, type ExternalObservationInput,
  type ExternalReadiness, type ExternalSource, type ExternalSourceInput, type ResolvedExternalValue,
  type ResearchCandidate, type ResearchJob, type ResearchProfile, type ResearchProfileInput,
} from '../lib/externalIntelligenceApi';

const SOURCE_TYPES: ExternalSourceInput['source_type'][] =
  ['API', 'CSV', 'RSS', 'WEB', 'REPORT', 'PROVIDER_API'];
const GRADES: ExternalSourceInput['trust_grade'][] = ['gold', 'silver', 'bronze'];

const EMPTY_SOURCE: ExternalSourceInput = {
  name: '', source_type: 'REPORT', base_url: '', license_type: '', allowed_usage: '',
  refresh_frequency: '', owner_department: '', trust_grade: 'silver', note: '',
};

const EMPTY_RESEARCH_PROFILE: ResearchProfileInput = {
  profile_id: '', legal_entity_id: '', company_name: '', official_domains: [], official_urls: [],
  business_keywords: [], product_keywords: [], regions: [], competitor_names: [],
  material_keywords: [], required_indicators: [], collection_purpose: '', schedule_rule: 'MANUAL',
  owner_id: '', retention_days: 365,
};

const splitValues = (value: string) => value.split(/[,\n]/).map((v) => v.trim()).filter(Boolean);
const BOT_LABELS: Record<ResearchJob['bot_kind'], string> = {
  COMPANY_BASE_RESEARCH: '회사 기초 조사',
  INDICATOR_COLLECTOR: '외부지표 수집',
  EXTERNAL_EVENT_MONITOR: '대외 사건 감시',
  QUALITY_CHANGE_MONITOR: '품질·변경 감시',
};

export function ExternalIntelligenceView() {
  const [ready, setReady] = useState<Loaded<ExternalReadiness>>(loading<ExternalReadiness>());
  const [indicators, setIndicators] = useState<Loaded<ExternalIndicator[]>>(loading<ExternalIndicator[]>());
  const [sources, setSources] = useState<Loaded<ExternalSource[]>>(loading<ExternalSource[]>());
  const [collectable, setCollectable] = useState<Loaded<ExternalCollectable>>(loading<ExternalCollectable>());
  const [researchProfiles, setResearchProfiles] = useState<Loaded<ResearchProfile[]>>(loading<ResearchProfile[]>());
  const [researchJobs, setResearchJobs] = useState<Loaded<ResearchJob[]>>(loading<ResearchJob[]>());
  const [researchCandidates, setResearchCandidates] = useState<Loaded<ResearchCandidate[]>>(loading<ResearchCandidate[]>());
  const [selected, setSelected] = useState('');
  const [observations, setObservations] = useState<Loaded<ExternalObservation[]>>(ok<ExternalObservation[]>([]));
  const [resolved, setResolved] = useState<Loaded<ResolvedExternalValue> | null>(null);
  const [showSourceForm, setShowSourceForm] = useState(false);
  const [showObservationForm, setShowObservationForm] = useState(false);
  const [sourceForm, setSourceForm] = useState<ExternalSourceInput>({ ...EMPTY_SOURCE });
  const [observationForm, setObservationForm] = useState({
    observed_at: '', value: '', vintage: '', grade: 'silver' as ExternalObservationInput['grade'],
    source_id: '', published_at: '', unit: '', source_record_ref: '', note: '',
  });
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState<{ tone: 'info' | 'error'; text: string } | null>(null);
  const [collectionMode, setCollectionMode] = useState<'csv' | 'api'>('csv');
  const [collectionSource, setCollectionSource] = useState('');
  const [csvContent, setCsvContent] = useState('');
  const [defaultIndicator, setDefaultIndicator] = useState('');
  const [apiPath, setApiPath] = useState('');
  const [apiFields, setApiFields] = useState({
    indicator: '', observed_at: '', value: '', vintage: '', unit: '',
  });
  const [collectionPreview, setCollectionPreview] = useState<ExternalCollectionResult | null>(null);
  const [previewSnapshot, setPreviewSnapshot] = useState('');
  const [showResearchForm, setShowResearchForm] = useState(false);
  const [researchForm, setResearchForm] = useState<ResearchProfileInput>({ ...EMPTY_RESEARCH_PROFILE });
  const approve = useConfirm<string>();
  const approveResearch = useConfirm<ResearchProfile>();
  const commitCollection = useConfirm<'csv' | 'api'>();

  const load = useCallback(async () => {
    setReady(loading<ExternalReadiness>()); setIndicators(loading<ExternalIndicator[]>());
    setSources(loading<ExternalSource[]>()); setCollectable(loading<ExternalCollectable>());
    setResearchProfiles(loading<ResearchProfile[]>()); setResearchJobs(loading<ResearchJob[]>());
    setResearchCandidates(loading<ResearchCandidate[]>());
    const [r, i, s, c, rp, rj, rc] = await Promise.allSettled([
      externalIntelligenceApi.readiness(), externalIntelligenceApi.indicators(),
      externalIntelligenceApi.sources(), externalIntelligenceApi.collectable(),
      externalIntelligenceApi.researchProfiles(), externalIntelligenceApi.researchJobs(),
      externalIntelligenceApi.researchCandidates(),
    ]);
    setReady(r.status === 'fulfilled' ? ok(r.value) : failed<ExternalReadiness>(r.reason));
    setIndicators(i.status === 'fulfilled' ? ok(i.value) : failed<ExternalIndicator[]>(i.reason));
    setSources(s.status === 'fulfilled' ? ok(s.value) : failed<ExternalSource[]>(s.reason));
    setCollectable(c.status === 'fulfilled' ? ok(c.value) : failed<ExternalCollectable>(c.reason));
    setResearchProfiles(rp.status === 'fulfilled' ? ok(rp.value) : failed<ResearchProfile[]>(rp.reason));
    setResearchJobs(rj.status === 'fulfilled' ? ok(rj.value) : failed<ResearchJob[]>(rj.reason));
    setResearchCandidates(rc.status === 'fulfilled' ? ok(rc.value) : failed<ResearchCandidate[]>(rc.reason));
    if (i.status === 'fulfilled') setSelected((v) => v || i.value[0]?.code || '');
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!selected) { setObservations(ok<ExternalObservation[]>([])); setResolved(null); return; }
    setObservations(loading<ExternalObservation[]>()); setResolved(loading<ResolvedExternalValue>());
    Promise.allSettled([
      externalIntelligenceApi.observations(selected), externalIntelligenceApi.resolveBaseline(selected),
    ]).then(([o, r]) => {
      setObservations(o.status === 'fulfilled' ? ok(o.value) : failed<ExternalObservation[]>(o.reason));
      setResolved(r.status === 'fulfilled' ? ok(r.value) : failed<ResolvedExternalValue>(r.reason));
    });
  }, [selected]);
  useEffect(() => {
    const approved = (sources.value || []).filter((s) => !!s.enabled);
    const eligible = collectionMode === 'api'
      ? approved.filter((s) => ['API', 'CSV', 'PROVIDER_API'].includes(s.source_type)) : approved;
    setCollectionSource((v) => eligible.some((s) => s.source_id === v)
      ? v : (eligible[0]?.source_id || ''));
  }, [collectionMode, sources.value]);

  const collectionSnapshot = useCallback((mode = collectionMode) => JSON.stringify({
    mode, source_id: collectionSource,
    content: mode === 'csv' ? csvContent : '',
    default_indicator: mode === 'csv' ? defaultIndicator : '',
    path: mode === 'api' ? apiPath : '',
    field_map: mode === 'api' ? apiFields : {},
  }), [collectionMode, collectionSource, csvContent, defaultIndicator, apiPath, apiFields]);

  const invalidatePreview = () => { setCollectionPreview(null); setPreviewSnapshot(''); };

  const refreshSelected = useCallback(async () => {
    await load();
    if (!selected) return;
    const [o, r] = await Promise.all([
      externalIntelligenceApi.observations(selected), externalIntelligenceApi.resolveBaseline(selected),
    ]);
    setObservations(ok(o)); setResolved(ok(r));
  }, [load, selected]);

  const registerSource = async () => {
    if (!sourceForm.name.trim() || !sourceForm.allowed_usage?.trim()
      || !sourceForm.owner_department?.trim()) return;
    setActionBusy(true); setActionMessage(null);
    try {
      await externalIntelligenceApi.registerSource(sourceForm);
      setSourceForm({ ...EMPTY_SOURCE }); setShowSourceForm(false);
      setActionMessage({ tone: 'info', text: '원천을 등록했습니다. 아직 계획에 쓰이지 않으며 별도 승인이 필요합니다.' });
      await load();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '원천을 등록하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const approveSource = async (sourceId: string) => {
    setActionBusy(true); setActionMessage(null);
    try {
      await externalIntelligenceApi.approveSource(sourceId);
      setActionMessage({ tone: 'info', text: '원천을 승인했습니다. 이제 이 원천에 귀속된 관측값을 기록할 수 있습니다.' });
      await load();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '원천을 승인하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const recordObservation = async () => {
    const value = Number(observationForm.value);
    if (!selected || !observationForm.observed_at || !observationForm.vintage.trim()
      || !observationForm.source_id || observationForm.value.trim() === '' || !Number.isFinite(value)) return;
    setActionBusy(true); setActionMessage(null);
    try {
      await externalIntelligenceApi.recordObservation({
        indicator_code: selected, observed_at: observationForm.observed_at, value,
        vintage: observationForm.vintage.trim(), grade: observationForm.grade,
        source_id: observationForm.source_id, published_at: observationForm.published_at,
        unit: observationForm.unit || current?.unit || '',
        source_record_ref: observationForm.source_record_ref,
        quality_status: 'RAW', note: observationForm.note,
      });
      setObservationForm((v) => ({ ...v, observed_at: '', value: '', vintage: '',
        published_at: '', source_record_ref: '', note: '' }));
      setShowObservationForm(false);
      setActionMessage({ tone: 'info', text: '관측값을 RAW 상태로 기록했습니다. 원천·등급 정책을 통과한 경우에만 기준계획 후보가 됩니다.' });
      await refreshSelected();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '관측값을 기록하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const runCollection = async (dryRun: boolean, mode = collectionMode) => {
    if (!collectionSource || (mode === 'csv' && !csvContent.trim())) return;
    setActionBusy(true); setActionMessage(null);
    try {
      const result = mode === 'csv'
        ? await externalIntelligenceApi.collectCsv({
          source_id: collectionSource, content: csvContent, dry_run: dryRun,
          default_indicator: defaultIndicator,
        })
        : await externalIntelligenceApi.collectSource(collectionSource, {
          dry_run: dryRun, path: apiPath, timeout: 10,
          indicator_map: Object.fromEntries(Object.entries(apiFields)
            .filter(([, sourceField]) => sourceField.trim())
            .map(([standardField, sourceField]) => [sourceField.trim(), standardField])),
        });
      setCollectionPreview(result);
      setPreviewSnapshot(dryRun ? collectionSnapshot(mode) : '');
      setActionMessage({ tone: 'info', text: dryRun
        ? `예행을 마쳤습니다. 적재 후보 ${result.loaded}건, 건너뜀 ${result.skipped}건입니다.`
        : `관측값 ${result.loaded}건을 적재했고 ${result.skipped}건은 사유와 함께 건너뛰었습니다.` });
      if (!dryRun) await refreshSelected();
    } catch (e) {
      setCollectionPreview(null); setPreviewSnapshot('');
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '외부정보를 수집하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const saveResearchProfile = async () => {
    if (!researchForm.legal_entity_id.trim() || !researchForm.company_name.trim()
      || !researchForm.owner_id.trim()) return;
    setActionBusy(true); setActionMessage(null);
    try {
      await externalIntelligenceApi.saveResearchProfile(researchForm);
      setShowResearchForm(false); setResearchForm({ ...EMPTY_RESEARCH_PROFILE });
      setActionMessage({ tone: 'info', text: '회사 조사 프로필을 초안으로 저장했습니다. 검토 요청과 승인이 끝나기 전에는 봇이 실행되지 않습니다.' });
      await load();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '회사 조사 프로필을 저장하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const submitResearchProfile = async (profileId: string) => {
    setActionBusy(true); setActionMessage(null);
    try {
      await externalIntelligenceApi.submitResearchProfile(profileId);
      setActionMessage({ tone: 'info', text: '회사 조사 프로필을 검토 요청 상태로 전환했습니다.' });
      await load();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '검토를 요청하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const approveResearchProfile = async (profile: ResearchProfile) => {
    setActionBusy(true); setActionMessage(null);
    try {
      await externalIntelligenceApi.approveResearchProfile(profile.profile_id, profile.fingerprint);
      setActionMessage({ tone: 'info', text: '현재 내용 지문으로 회사 조사 범위를 승인했습니다.' });
      await load();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '프로필을 승인하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const scheduleResearchJob = async (profileId: string) => {
    setActionBusy(true); setActionMessage(null);
    try {
      await externalIntelligenceApi.scheduleResearchJob(profileId, 'COMPANY_BASE_RESEARCH');
      setActionMessage({ tone: 'info', text: '회사 기초 조사 dry-run을 예약했습니다. 실행 전 승인 범위와 URL을 다시 확인하십시오.' });
      await load();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '조사 작업을 예약하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const runResearchJob = async (jobId: string) => {
    setActionBusy(true); setActionMessage(null);
    try {
      await externalIntelligenceApi.runResearchJob(jobId);
      setActionMessage({ tone: 'info', text: '조사를 마쳤습니다. 발견한 정보는 확정값이 아니라 검토 후보로만 저장했습니다.' });
      await load();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '조사 작업을 완료하지 못했습니다.' });
      await load();
    } finally { setActionBusy(false); }
  };

  const decideCandidate = async (candidate: ResearchCandidate, decision: 'ACCEPTED' | 'REJECTED') => {
    setActionBusy(true); setActionMessage(null);
    try {
      await externalIntelligenceApi.decideResearchCandidate(
        candidate.candidate_id, decision, candidate.content_hash);
      setActionMessage({ tone: 'info', text: decision === 'ACCEPTED'
        ? '후보를 채택해 미승인 원천으로 등록했습니다. 실제 사용에는 별도 원천 승인이 필요합니다.'
        : '후보를 기각했습니다. 관측값과 원천 등록부에는 반영되지 않습니다.' });
      await load();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '후보 결정을 저장하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const inds = indicators.value || [];
  const srcs = sources.value || [];
  const approvedSources = srcs.filter((s) => !!s.enabled);
  const autoSources = approvedSources.filter((s) => ['API', 'CSV', 'PROVIDER_API'].includes(s.source_type));
  const collectionSources = collectionMode === 'csv' ? approvedSources : autoSources;
  const previewStillMatches = !!collectionPreview?.dry_run
    && previewSnapshot === collectionSnapshot(collectionMode);
  const current = inds.find((i) => i.code === selected) || null;
  const readiness = ready.value?.indicators.find((i) => i.code === selected) || null;
  const obs = observations.value || [];
  const profiles = researchProfiles.value || [];
  const jobs = researchJobs.value || [];
  const candidates = researchCandidates.value || [];

  return (
    <>
      <ScreenHead kicker="EXTERNAL INTELLIGENCE" title="대외 인텔리전스"
        description="확정된 외부 원천·지표·발표 시점(vintage)을 함께 보며, 기준계획에 쓸 수 있는 값인지 확인합니다."
        chip={{ label: `${ready.value?.usable_for_baseline ?? 0}/${ready.value?.total ?? 0} 사용 가능`,
          tone: ready.value?.blocked ? 'warn' : 'success' }} />

      <Banner tone="info" title="등록된 값과 사용할 수 있는 값은 다릅니다">
        승인된 원천과 요구 신뢰등급을 통과한 값만 기준계획에 사용됩니다. 등급이 부족하거나
        관측값이 없으면 0으로 대체하지 않고 차단 사유와 다음 조치를 표시합니다.
      </Banner>

      {actionMessage && <Banner tone={actionMessage.tone === 'error' ? 'error' : 'info'}
        title={actionMessage.tone === 'error' ? '요청을 완료하지 못했습니다' : '처리 결과'}>
        {actionMessage.text}
      </Banner>}

      <div className="metric-row">
        <Metric label="등록 지표" state={ready.status} value={ready.value?.total} hint="확정 요구사항" />
        <Metric label="기준계획 사용 가능" state={ready.status} value={ready.value?.usable_for_baseline}
          hint="등급·관측값 통과" />
        <Metric label="차단 지표" state={ready.status} value={ready.value?.blocked}
          hint="다음 조치 필요" />
        <Metric label="승인 원천" state={ready.status} value={ready.value?.approved_sources}
          hint="회사 계획에 사용 허용" />
      </div>

      <Panel kicker="COMPANY RESEARCH BOTS" title="회사 기준정보 기반 대외 조사"
        action={<button className="secondary-button" onClick={() => setShowResearchForm((v) => !v)}>
          {showResearchForm ? '등록 취소' : '회사 조사 프로필 등록'}
        </button>}>
        <div className="panel-body">
          <Banner tone="info" title="봇은 승인된 회사와 공식 도메인만 조사합니다">
            웹에서 찾은 문장과 숫자는 확정 대외지표가 아닙니다. 먼저 후보로 저장하고,
            사람이 채택한 원천도 별도 승인을 거쳐야 계획과 시뮬레이션에 사용할 수 있습니다.
          </Banner>

          <div className="metric-row" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
            <Metric label="회사 조사 프로필" state={researchProfiles.status} value={profiles.length}
              hint={`승인 ${profiles.filter((p) => p.status === 'APPROVED').length}건`} />
            <Metric label="수집 작업" state={researchJobs.status} value={jobs.length}
              hint={`검토 후보 생성 ${jobs.filter((j) => j.status === 'CANDIDATE_READY').length}건`} />
            <Metric label="검토 후보" state={researchCandidates.status}
              value={candidates.filter((c) => c.status === 'CANDIDATE_READY').length}
              hint="자동 확정하지 않음" />
            <Metric label="실행 가능한 봇" state="ok" value="1/4"
              hint="회사 기초 조사만 연결" />
          </div>

          {showResearchForm && <div className="request-card" aria-label="회사 조사 프로필 등록">
            <div className="panel-body">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0 14px' }}>
                <FormField label="법인 ID" required>
                  <input className="afs-input" value={researchForm.legal_entity_id}
                    placeholder="예: corp-ls-mnm" onChange={(e) => setResearchForm({ ...researchForm,
                      legal_entity_id: e.target.value })} />
                </FormField>
                <FormField label="회사명" required>
                  <input className="afs-input" value={researchForm.company_name}
                    placeholder="예: LS MnM" onChange={(e) => setResearchForm({ ...researchForm,
                      company_name: e.target.value })} />
                </FormField>
                <FormField label="공식 도메인" required hint="scheme·경로 없이 쉼표로 구분합니다.">
                  <input className="afs-input" value={researchForm.official_domains.join(', ')}
                    placeholder="lsmnm.com" onChange={(e) => setResearchForm({ ...researchForm,
                      official_domains: splitValues(e.target.value) })} />
                </FormField>
                <FormField label="공식 조사 URL" required hint="승인 도메인 아래 HTTPS 주소만 허용합니다.">
                  <input className="afs-input" value={researchForm.official_urls.join(', ')}
                    placeholder="https://www.lsmnm.com/" onChange={(e) => setResearchForm({ ...researchForm,
                      official_urls: splitValues(e.target.value) })} />
                </FormField>
                <FormField label="사업·제품 키워드" hint="쉼표로 구분합니다.">
                  <input className="afs-input"
                    value={[...researchForm.business_keywords, ...researchForm.product_keywords].join(', ')}
                    onChange={(e) => setResearchForm({ ...researchForm,
                      business_keywords: splitValues(e.target.value), product_keywords: [] })} />
                </FormField>
                <FormField label="지역·경쟁사" hint="쉼표로 구분합니다.">
                  <input className="afs-input"
                    value={[...researchForm.regions, ...researchForm.competitor_names].join(', ')}
                    onChange={(e) => setResearchForm({ ...researchForm,
                      regions: splitValues(e.target.value), competitor_names: [] })} />
                </FormField>
                <FormField label="필요 대외지표" hint="등록부 코드 기준, 쉼표로 구분합니다.">
                  <input className="afs-input" value={researchForm.required_indicators.join(', ')}
                    placeholder="LME_CU, FX_USDKRW" onChange={(e) => setResearchForm({ ...researchForm,
                      required_indicators: splitValues(e.target.value) })} />
                </FormField>
                <FormField label="담당자 ID" required>
                  <input className="afs-input" value={researchForm.owner_id}
                    onChange={(e) => setResearchForm({ ...researchForm, owner_id: e.target.value })} />
                </FormField>
              </div>
              <FormField label="수집 목적" required>
                <textarea className="afs-textarea" value={researchForm.collection_purpose}
                  placeholder="어떤 경영 판단의 근거 후보를 찾는지 적습니다."
                  onChange={(e) => setResearchForm({ ...researchForm, collection_purpose: e.target.value })} />
              </FormField>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button className="primary-button" disabled={actionBusy
                  || !researchForm.legal_entity_id.trim() || !researchForm.company_name.trim()
                  || !researchForm.owner_id.trim()} onClick={saveResearchProfile}>초안 저장</button>
              </div>
            </div>
          </div>}

          {researchProfiles.status !== 'ok' ? <EmptyOrError state={researchProfiles.status}
            error={researchProfiles.error} onRetry={load} emptyText="회사 조사 프로필이 없습니다." />
            : profiles.length === 0 ? <div className="empty-note">회사 조사 프로필이 없습니다. 회사·공식 도메인·수집 목적을 먼저 등록하십시오.</div>
              : <div className="afs-table-wrap" style={{ marginTop: 14 }}><table className="afs-table">
                <thead><tr><th>회사·범위</th><th>공식 URL</th><th>목적·담당</th><th>상태</th><th>조치</th></tr></thead>
                <tbody>{profiles.map((p) => <tr key={p.profile_id}>
                  <td><b>{p.company_name}</b><br /><span className="afs-muted">{p.legal_entity_id} · {p.official_domains.join(', ')}</span></td>
                  <td>{p.official_urls.join(', ') || '미등록'}</td>
                  <td>{p.collection_purpose || '목적 미등록'}<br /><span className="afs-muted">{p.owner_id}</span></td>
                  <td><span className={`state-chip ${p.status === 'APPROVED' ? 'success' : 'warn'}`}>{p.status}</span><br />
                    <span className="afs-muted">지문 {p.fingerprint.slice(0, 10)}…</span></td>
                  <td><div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {p.status === 'DRAFT' && <button className="secondary-button" disabled={actionBusy}
                      onClick={() => submitResearchProfile(p.profile_id)}>검토 요청</button>}
                    {p.status === 'REVIEW_REQUIRED' && <button className="primary-button" disabled={actionBusy}
                      onClick={() => approveResearch.ask(p)}>내용 지문 승인</button>}
                    {p.status === 'APPROVED' && <button className="secondary-button" disabled={actionBusy}
                      onClick={() => scheduleResearchJob(p.profile_id)}>회사 조사 예약</button>}
                  </div></td>
                </tr>)}</tbody>
              </table></div>}

          {approveResearch.target && <ConfirmInline open title={`«${approveResearch.target.company_name}» 조사 범위를 승인합니다`}
            danger={false} confirmLabel="현재 지문 승인" onCancel={approveResearch.cancel}
            onConfirm={() => approveResearch.run(approveResearchProfile)}
            changes="승인된 공식 URL에서 회사 기초 조사 작업을 예약할 수 있게 됩니다."
            affects={`${approveResearch.target.official_domains.join(', ')} · 보존 ${approveResearch.target.retention_days}일`}
            reversible="내용이 바뀌면 승인이 자동 해제되고 다시 검토해야 합니다."
            approval={`지문 ${approveResearch.target.fingerprint}`} />}

          <h3 style={{ fontSize: 14, margin: '18px 0 8px' }}>조사 봇과 최근 작업</h3>
          <div className="metric-row" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
            {(Object.entries(BOT_LABELS) as Array<[ResearchJob['bot_kind'], string]>).map(([kind, label]) =>
              <div className="request-card" key={kind}><div className="panel-body">
                <b>{label}</b><p className="hint-line">{kind === 'COMPANY_BASE_RESEARCH'
                  ? '승인 공식 URL → 검토 후보' : '어댑터 미연결 · 실행 차단'}</p>
                <span className={`state-chip ${kind === 'COMPANY_BASE_RESEARCH' ? 'success' : 'warn'}`}>
                  {kind === 'COMPANY_BASE_RESEARCH' ? 'DRY-RUN 가능' : '준비 중'}
                </span>
              </div></div>)}
          </div>
          {jobs.length > 0 && <div className="afs-table-wrap" style={{ marginTop: 12 }}><table className="afs-table">
            <thead><tr><th>봇</th><th>상태</th><th>프로필 지문</th><th>요청</th><th>조치·오류</th></tr></thead>
            <tbody>{jobs.slice(0, 20).map((j) => <tr key={j.job_id}>
              <td>{BOT_LABELS[j.bot_kind]}</td><td>{j.status}</td><td>{j.profile_fingerprint.slice(0, 10)}…</td>
              <td>{j.requested_by}<br /><span className="afs-muted">{j.requested_at}</span></td>
              <td>{j.status === 'SCHEDULED'
                ? <button className="primary-button" disabled={actionBusy} onClick={() => runResearchJob(j.job_id)}>dry-run 실행</button>
                : (j.error || `후보 ${String(j.result_summary.candidate_count ?? 0)}건`)}</td>
            </tr>)}</tbody>
          </table></div>}

          <h3 style={{ fontSize: 14, margin: '18px 0 8px' }}>조사 후보 검토</h3>
          {researchCandidates.status !== 'ok' ? <EmptyOrError state={researchCandidates.status}
            error={researchCandidates.error} onRetry={load} emptyText="조사 후보가 없습니다." />
            : candidates.length === 0 ? <div className="empty-note">조사 후보가 없습니다. 승인된 프로필로 회사 기초 조사를 실행하십시오.</div>
              : <div className="afs-table-wrap"><table className="afs-table">
                <thead><tr><th>종류</th><th>제목·주소</th><th>상태</th><th>조치</th></tr></thead>
                <tbody>{candidates.slice(0, 50).map((c) => <tr key={c.candidate_id}>
                  <td>{c.candidate_kind}</td><td><b>{c.title || '제목 없음'}</b><br />
                    <span className="afs-muted">{c.source_url}</span><br />{c.summary}</td>
                  <td>{c.status}<br /><span className="afs-muted">지문 {c.content_hash.slice(0, 10)}…</span></td>
                  <td>{c.status === 'CANDIDATE_READY' ? <div style={{ display: 'flex', gap: 6 }}>
                    <button className="secondary-button" disabled={actionBusy}
                      onClick={() => decideCandidate(c, 'ACCEPTED')}>원천 후보 채택</button>
                    <button className="danger-ghost" disabled={actionBusy}
                      onClick={() => decideCandidate(c, 'REJECTED')}>기각</button>
                  </div> : `검토자 ${c.reviewed_by || '미상'}`}</td>
                </tr>)}</tbody>
              </table></div>}
        </div>
      </Panel>

      <Panel kicker="SOURCES" title="대외 원천 등록부"
        action={<button className="secondary-button" onClick={() => setShowSourceForm((v) => !v)}>
          {showSourceForm ? '등록 취소' : '새 원천 등록'}
        </button>}>
        {showSourceForm && <div className="panel-body" aria-label="대외 원천 등록">
          <Banner tone="info" title="등록은 승인이 아닙니다">
            원천의 사용 범위와 담당 부서를 기록합니다. 등록 뒤 별도 승인 전까지 어떤 값도 계획에 쓰이지 않습니다.
          </Banner>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0 14px' }}>
            <FormField label="원천 이름" required>
              <input className="afs-input" value={sourceForm.name} placeholder="예: 한국은행 경제통계시스템"
                onChange={(e) => setSourceForm({ ...sourceForm, name: e.target.value })} />
            </FormField>
            <FormField label="원천 유형" required>
              <select className="afs-select" value={sourceForm.source_type}
                onChange={(e) => setSourceForm({ ...sourceForm,
                  source_type: e.target.value as ExternalSourceInput['source_type'] })}>
                {SOURCE_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </FormField>
            <FormField label="원천 주소" hint="자동 수집 주소 또는 사람이 확인할 공식 페이지입니다.">
              <input className="afs-input" value={sourceForm.base_url} placeholder="https://"
                onChange={(e) => setSourceForm({ ...sourceForm, base_url: e.target.value })} />
            </FormField>
            <FormField label="신뢰등급" required>
              <select className="afs-select" value={sourceForm.trust_grade}
                onChange={(e) => setSourceForm({ ...sourceForm,
                  trust_grade: e.target.value as ExternalSourceInput['trust_grade'] })}>
                {GRADES.map((g) => <option key={g}>{g}</option>)}
              </select>
            </FormField>
            <FormField label="허용된 사용 범위" required hint="예: 내부 기준계획·경영 시뮬레이션">
              <input className="afs-input" value={sourceForm.allowed_usage}
                onChange={(e) => setSourceForm({ ...sourceForm, allowed_usage: e.target.value })} />
            </FormField>
            <FormField label="담당 부서" required>
              <input className="afs-input" value={sourceForm.owner_department}
                onChange={(e) => setSourceForm({ ...sourceForm, owner_department: e.target.value })} />
            </FormField>
            <FormField label="라이선스·이용 조건">
              <input className="afs-input" value={sourceForm.license_type}
                onChange={(e) => setSourceForm({ ...sourceForm, license_type: e.target.value })} />
            </FormField>
            <FormField label="갱신 주기">
              <input className="afs-input" value={sourceForm.refresh_frequency} placeholder="예: 월간"
                onChange={(e) => setSourceForm({ ...sourceForm, refresh_frequency: e.target.value })} />
            </FormField>
          </div>
          <FormField label="비고">
            <textarea className="afs-textarea" value={sourceForm.note}
              onChange={(e) => setSourceForm({ ...sourceForm, note: e.target.value })} />
          </FormField>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="primary-button" disabled={actionBusy || !sourceForm.name.trim()
              || !sourceForm.allowed_usage?.trim() || !sourceForm.owner_department?.trim()}
              onClick={registerSource}>미승인 원천으로 등록</button>
          </div>
        </div>}
        {sources.status !== 'ok' ? <EmptyOrError state={sources.status} error={sources.error}
          onRetry={load} emptyText="등록된 대외 원천이 없습니다." />
          : srcs.length === 0 ? <div className="empty-note">등록된 대외 원천이 없습니다. 승인된 원천 없이는 값을 수집하지 않습니다.</div>
            : <div className="afs-table-wrap" style={{ margin: 15 }}><table className="afs-table">
              <thead><tr><th>원천</th><th>유형</th><th>신뢰등급</th><th>승인</th><th>갱신 주기</th><th>담당</th><th>조치</th></tr></thead>
              <tbody>{srcs.map((s) => <tr key={s.source_id}>
                <td><b>{s.name}</b><br /><span className="afs-muted">{s.base_url || '주소 미등록'}</span></td>
                <td>{s.source_type}</td><td>{s.trust_grade}</td>
                <td>{s.enabled ? `승인 · ${s.approved_by || '승인자 미상'}` : '미승인'}</td>
                <td>{s.refresh_frequency || '미정'}</td><td>{s.owner_department || '미정'}</td>
                <td>{s.enabled ? <span className="state-chip success">사용 중</span>
                  : <button className="secondary-button" disabled={actionBusy}
                    onClick={() => approve.ask(s.source_id)}>승인 검토</button>}</td>
              </tr>)}</tbody></table></div>}
        {approve.target && (() => {
          const target = srcs.find((s) => s.source_id === approve.target);
          if (!target) return null;
          return <div className="panel-body"><ConfirmInline open title={`«${target.name}» 원천을 승인합니다`}
            danger={false} confirmLabel="원천 승인" onCancel={approve.cancel}
            onConfirm={() => approve.run(approveSource)}
            changes="이 원천에 귀속된 관측값을 회사 계획의 후보로 사용할 수 있게 됩니다."
            affects={`${target.allowed_usage || '허용 범위 미기재'} · 담당 ${target.owner_department || '미정'}`}
            reversible="현재 API에는 원천 승인 철회 경로가 없습니다. 승인 전 등록 내용을 다시 확인하십시오."
            approval={`현재 사용자 ID가 승인자로 기록됩니다. 원천 등급: ${target.trust_grade}`} />
          </div>;
        })()}
      </Panel>

      <Panel kicker="COLLECTION" title="외부정보 수집 예행·적재">
        <div className="panel-body" aria-label="외부정보 수집">
          {collectable.status !== 'ok'
            ? <EmptyOrError state={collectable.status} error={collectable.error} onRetry={load}
              emptyText="수집 가능 상태를 확인할 수 없습니다." />
            : <Banner tone={collectable.value?.ready ? 'info' : 'warn'}
              title={collectable.value?.ready ? '승인 원천으로 예행할 수 있습니다' : '수집 전 원천 승인이 필요합니다'}>
              {collectable.value?.note || '수집 가능 상태를 확인할 수 없습니다.'}
            </Banner>}

          <div className="filter-pills" role="tablist" aria-label="수집 방식" style={{ marginTop: 12 }}>
            <button role="tab" aria-selected={collectionMode === 'csv'}
              className={collectionMode === 'csv' ? 'active' : ''}
              onClick={() => { setCollectionMode('csv'); invalidatePreview(); }}>CSV 파일</button>
            <button role="tab" aria-selected={collectionMode === 'api'}
              className={collectionMode === 'api' ? 'active' : ''}
              onClick={() => { setCollectionMode('api'); invalidatePreview(); }}>등록 API</button>
          </div>

          <FormField label="승인 원천" required
            hint={collectionMode === 'csv'
              ? '파일의 값도 승인된 출처에 귀속해야 합니다.'
              : '등록된 base_url과 그 아래 상대 경로만 호출합니다.'}>
            <select className="afs-select" value={collectionSource}
              onChange={(e) => { setCollectionSource(e.target.value); invalidatePreview(); }}>
              <option value="">{collectionSources.length ? '원천을 선택하십시오' : '사용 가능한 승인 원천이 없습니다'}</option>
              {collectionSources.map((s) => <option key={s.source_id} value={s.source_id}>
                {s.name} · {s.source_type} · {s.trust_grade}
              </option>)}
            </select>
          </FormField>

          {collectionMode === 'csv' ? <>
            <FormField label="CSV 파일" required
              hint="파일은 브라우저에서 텍스트로 읽고 예행 요청에만 전달합니다. 필수 열은 지표·관측일·값·발표판(vintage)입니다.">
              <input className="afs-input" type="file" accept=".csv,text/csv"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  setCsvContent(file ? await file.text() : ''); invalidatePreview();
                }} />
            </FormField>
            <FormField label="CSV 내용 확인" required
              hint="열 별칭은 indicator/code/지표, observed_at/date/기준일, value/값, vintage/발표일을 지원합니다.">
              <textarea className="afs-textarea" rows={6} value={csvContent}
                placeholder={'indicator,observed_at,value,vintage,unit\next_fx,2026-08-01,1380.5,2026-08 잠정치,KRW/USD'}
                onChange={(e) => { setCsvContent(e.target.value); invalidatePreview(); }} />
            </FormField>
            <FormField label="파일 전체 기본 지표" hint="지표 열이 없는 단일 지표 파일에만 지정합니다. 행의 지표 코드가 있으면 그 값을 씁니다.">
              <select className="afs-select" value={defaultIndicator}
                onChange={(e) => { setDefaultIndicator(e.target.value); invalidatePreview(); }}>
                <option value="">지표 열을 사용합니다</option>
                {inds.map((i) => <option key={i.code} value={i.code}>{i.name} · {i.code}</option>)}
              </select>
            </FormField>
          </> : <>
            <FormField label="등록 주소 아래 상대 경로"
              hint="비우면 등록된 base_url을 그대로 호출합니다. 절대 URL과 '..'는 서버가 거부합니다.">
              <input className="afs-input" value={apiPath} placeholder="예: observations/latest"
                onChange={(e) => { setApiPath(e.target.value); invalidatePreview(); }} />
            </FormField>
            <FormField label="API 응답 필드 매핑"
              hint="응답 필드가 indicator·observed_at·value·vintage·unit과 다를 때만 원천의 필드명을 적습니다. 추측 매핑은 하지 않습니다.">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
                {(Object.keys(apiFields) as Array<keyof typeof apiFields>).map((field) =>
                  <label key={field} className="field-label" style={{ margin: 0 }}>
                    {field}
                    <input className="afs-input" value={apiFields[field]} placeholder={`원천의 ${field} 필드`}
                      onChange={(e) => {
                        setApiFields({ ...apiFields, [field]: e.target.value }); invalidatePreview();
                      }} />
                  </label>)}
              </div>
            </FormField>
            <Banner tone="warn" title="API 예행과 실제 적재는 각각 원천을 다시 호출합니다">
              두 호출 사이에 원천 값이 바뀔 수 있습니다. 실제 적재 결과를 다시 표시하며,
              승인된 계산·기준계획에 바로 반영되는 것은 아닙니다.
            </Banner>
          </>}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button className="primary-button" disabled={actionBusy || !collectionSource
              || (collectionMode === 'csv' && !csvContent.trim())}
              onClick={() => runCollection(true)}>먼저 예행하기</button>
          </div>

          {collectionPreview && <div className="request-card" aria-label="수집 예행 결과">
            <div className="panel-body">
              <ScreenHead kicker={collectionPreview.dry_run ? 'DRY RUN' : 'INGESTED'}
                title={collectionPreview.dry_run ? '수집 예행 결과' : '실제 적재 결과'}
                description={collectionPreview.note}
                chip={{ label: collectionPreview.dry_run ? '아직 적재하지 않음' : '적재 실행됨',
                  tone: collectionPreview.dry_run ? 'warn' : 'success' }} />
              <div className="metric-row" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                <Metric label={collectionPreview.dry_run ? '적재 후보' : '적재 완료'} state="ok"
                  value={collectionPreview.loaded} />
                <Metric label="건너뜀" state="ok" value={collectionPreview.skipped}
                  hint="0이나 오늘 날짜로 보정하지 않음" />
                <Metric label="원천 등급" state="ok" value={collectionPreview.grade} />
              </div>
              {collectionPreview.items.length > 0 && <div className="afs-table-wrap"><table className="afs-table">
                <thead><tr><th>행</th><th>지표</th><th>관측일</th><th>값</th><th>발표판</th><th>등급</th></tr></thead>
                <tbody>{collectionPreview.items.slice(0, 50).map((item) => <tr key={`${item.row}-${item.indicator}`}>
                  <td>{item.row}</td><td>{item.indicator || '미상'}</td><td>{item.observed_at || '미상'}</td>
                  <td>{item.value ?? '미상'} {item.unit || ''}</td><td>{item.vintage || '미상'}</td>
                  <td>{item.grade || collectionPreview.grade}</td>
                </tr>)}</tbody>
              </table></div>}
              {collectionPreview.skipped_items.length > 0 && <>
                <h4 style={{ margin: '14px 0 7px' }}>건너뛴 행과 사유</h4>
                <div className="afs-table-wrap"><table className="afs-table">
                  <thead><tr><th>행</th><th>거부 사유</th><th>원문 일부</th></tr></thead>
                  <tbody>{collectionPreview.skipped_items.slice(0, 50).map((item) => <tr key={item.row}>
                    <td>{item.row}</td><td>{item.reason}</td><td>{item.raw || '—'}</td>
                  </tr>)}</tbody>
                </table></div>
              </>}
              {collectionPreview.dry_run && <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                <button className="danger-ghost" disabled={actionBusy || !previewStillMatches
                  || collectionPreview.loaded === 0}
                  title={!previewStillMatches ? '입력값이 예행 이후 바뀌었습니다. 다시 예행하십시오.' : undefined}
                  onClick={() => commitCollection.ask(collectionMode)}>예행 결과대로 실제 적재 검토</button>
              </div>}
              <ConfirmInline open={commitCollection.open} danger
                title="예행한 외부 관측값을 실제로 적재합니다"
                confirmLabel="실제 적재 실행" onCancel={commitCollection.cancel}
                onConfirm={() => commitCollection.run((mode) => runCollection(false, mode))}
                changes={`적재 후보 ${collectionPreview.loaded}건을 관측값 이력에 기록합니다.`}
                affects={`${collectionPreview.source_name} · ${collectionPreview.grade} 등급 · 포함 지표는 위 예행 결과와 동일`}
                reversible="이 화면에는 일괄 삭제가 없습니다. 잘못된 값은 품질 상태와 후속 이력으로 정정해야 합니다."
                approval="현재 사용자 ID가 적재 행위자로 확인되며, 승인 원천의 등급을 그대로 사용합니다." />
            </div>
          </div>}
        </div>
      </Panel>

      <Panel kicker="INDICATORS" title="확정 대외지표와 관측값">
        <div className="afs-master-detail" style={{ padding: 15 }}>
          <div className="afs-master-list" aria-label="확정 대외지표 목록">
            {indicators.status !== 'ok' ? <EmptyOrError state={indicators.status} error={indicators.error}
              onRetry={load} emptyText="등록된 대외지표가 없습니다." />
              : inds.length === 0 ? <div className="empty-note">등록된 대외지표가 없습니다.</div>
                : inds.map((i) => <button key={i.code} className={selected === i.code ? 'active' : ''}
                  onClick={() => setSelected(i.code)}>
                  <b>{i.name || i.code}</b><small>{i.code} · 최소 {i.required_grade}</small>
                </button>)}
          </div>
          <div className="afs-master-editor" aria-label="선택한 대외지표 상세">
            {!current ? <div className="empty-note">왼쪽에서 확인할 지표를 선택하십시오.</div> : <>
              <ScreenHead kicker={current.code} title={current.name || current.code}
                description={current.purpose || '사용 목적이 등록되지 않았습니다.'}
                chip={{ label: readiness?.usable_for_baseline ? '기준계획 사용 가능' : '기준계획 차단',
                  tone: readiness?.usable_for_baseline ? 'success' : 'warn' }} />
              <div className="metric-row" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                <Metric label="요구 등급" state="ok" value={current.required_grade} />
                <Metric label="허용 지연" state="ok" value={current.acceptable_latency || null} />
                <Metric label="최신 값" state={resolved?.status || 'loading'}
                  value={resolved?.value?.allowed ? resolved.value.value : null}
                  unit={resolved?.value?.allowed ? ` ${resolved.value.unit || current.unit || ''}` : ''}
                  notes={{ empty: resolved?.value?.reason || '사용 가능한 값 없음' }} />
              </div>
              {!readiness?.usable_for_baseline && <Banner tone="warn" title={readiness?.reason || '기준계획에 사용할 수 없습니다'}>
                {readiness?.gap_impact && <p><b>영향:</b> {readiness.gap_impact}</p>}
                <p><b>다음 조치:</b> {readiness?.next_action || current.next_action || '승인 원천과 관측값을 확인하십시오.'}</p>
              </Banner>}
              <dl className="drawer-facts">
                <div><dt>표준 용어</dt><dd>{current.canonical_term || '미정'}</dd></div>
                <div><dt>단위·주기</dt><dd>{current.unit || '미정'} · {current.frequency || '미정'}</dd></div>
                <div><dt>권고 원천</dt><dd>{current.source_hint || '미정'}</dd></div>
                <div><dt>등록 근거</dt><dd>{current.origin || '미상'}</dd></div>
              </dl>
              <h3 style={{ fontSize: 14, marginTop: 16 }}>발표 시점별 관측값</h3>
              {observations.status !== 'ok' ? <EmptyOrError state={observations.status}
                error={observations.error} emptyText="관측값이 없습니다." />
                : obs.length === 0 ? <div className="empty-note">관측값이 없습니다. 0으로 해석하지 않습니다.</div>
                  : <div className="afs-table-wrap"><table className="afs-table">
                    <thead><tr><th>관측일</th><th>값</th><th>발표판</th><th>등급</th><th>원천</th><th>품질</th></tr></thead>
                    <tbody>{obs.map((o) => <tr key={o.observation_id}>
                      <td>{o.observed_at}</td><td>{o.value} {o.unit}</td><td>{o.vintage}</td>
                      <td>{o.grade}</td><td>{o.source_id || '미상'}</td><td>{o.quality_status}</td>
                    </tr>)}</tbody></table></div>}

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
                <button className="secondary-button" disabled={approvedSources.length === 0}
                  title={approvedSources.length === 0 ? '먼저 원천을 등록하고 승인해야 합니다.' : undefined}
                  onClick={() => setShowObservationForm((v) => !v)}>
                  {showObservationForm ? '입력 취소' : '관측값 등록'}
                </button>
              </div>
              {approvedSources.length === 0 && <p className="hint-line" style={{ marginTop: 7 }}>
                승인된 원천이 없어 관측값을 기록할 수 없습니다. 원천 등록부에서 승인 절차를 먼저 완료하십시오.
              </p>}
              {showObservationForm && <div className="request-card" aria-label="대외지표 관측값 등록">
                <div className="panel-body">
                  <Banner tone="info" title="발표판(vintage)과 원천을 함께 기록합니다">
                    같은 관측일의 값도 발표판에 따라 달라질 수 있습니다. 원천 없는 숫자나 오늘 날짜로 보정한 값은 받지 않습니다.
                  </Banner>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0 14px' }}>
                    <FormField label="승인 원천" required>
                      <select className="afs-select" value={observationForm.source_id}
                        onChange={(e) => {
                          const source = approvedSources.find((s) => s.source_id === e.target.value);
                          setObservationForm({ ...observationForm, source_id: e.target.value,
                            grade: (source?.trust_grade || 'silver') as ExternalObservationInput['grade'] });
                        }}>
                        <option value="">선택하십시오</option>
                        {approvedSources.map((s) => <option key={s.source_id} value={s.source_id}>
                          {s.name} · {s.trust_grade}
                        </option>)}
                      </select>
                    </FormField>
                    <FormField label="관측일" required>
                      <input className="afs-input" type="date" value={observationForm.observed_at}
                        onChange={(e) => setObservationForm({ ...observationForm, observed_at: e.target.value })} />
                    </FormField>
                    <FormField label="관측값" required>
                      <input className="afs-input" inputMode="decimal" value={observationForm.value}
                        onChange={(e) => setObservationForm({ ...observationForm, value: e.target.value })} />
                    </FormField>
                    <FormField label="단위">
                      <input className="afs-input" value={observationForm.unit || current.unit}
                        onChange={(e) => setObservationForm({ ...observationForm, unit: e.target.value })} />
                    </FormField>
                    <FormField label="발표판(vintage)" required hint="예: 2026-08 잠정치 · 2026Q2 확정치">
                      <input className="afs-input" value={observationForm.vintage}
                        onChange={(e) => setObservationForm({ ...observationForm, vintage: e.target.value })} />
                    </FormField>
                    <FormField label="발표일">
                      <input className="afs-input" type="date" value={observationForm.published_at}
                        onChange={(e) => setObservationForm({ ...observationForm, published_at: e.target.value })} />
                    </FormField>
                    <FormField label="값의 신뢰등급" required hint="원천 등급보다 높게 지정할 수 없습니다.">
                      <select className="afs-select" value={observationForm.grade}
                        onChange={(e) => setObservationForm({ ...observationForm,
                          grade: e.target.value as ExternalObservationInput['grade'] })}>
                        {GRADES.filter((g) => {
                          const trust = approvedSources.find((s) => s.source_id === observationForm.source_id)?.trust_grade;
                          return !trust || GRADES.indexOf(g) >= GRADES.indexOf(trust as ExternalSourceInput['trust_grade']);
                        }).map((g) => <option key={g}>{g}</option>)}
                      </select>
                    </FormField>
                    <FormField label="원천 레코드 참조">
                      <input className="afs-input" value={observationForm.source_record_ref}
                        placeholder="표·시계열·공표 문서 식별자"
                        onChange={(e) => setObservationForm({ ...observationForm, source_record_ref: e.target.value })} />
                    </FormField>
                  </div>
                  <FormField label="비고">
                    <textarea className="afs-textarea" value={observationForm.note}
                      onChange={(e) => setObservationForm({ ...observationForm, note: e.target.value })} />
                  </FormField>
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button className="primary-button" disabled={actionBusy || !observationForm.source_id
                      || !observationForm.observed_at || !observationForm.vintage.trim()
                      || observationForm.value.trim() === '' || !Number.isFinite(Number(observationForm.value))}
                      onClick={recordObservation}>RAW 관측값 기록</button>
                  </div>
                </div>
              </div>}
            </>}
          </div>
        </div>
      </Panel>
    </>
  );
}
