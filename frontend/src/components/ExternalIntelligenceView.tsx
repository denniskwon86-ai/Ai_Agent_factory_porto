import { useCallback, useEffect, useState } from 'react';

import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { EmptyOrError, Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { ConfirmInline, FormField, useConfirm } from '../design/DataFoundationShell';
import {
  externalIntelligenceApi, type ExternalCollectable, type ExternalCollectionResult,
  type ExternalIndicator, type ExternalObservation, type ExternalObservationInput,
  type ExternalReadiness, type ExternalSource, type ExternalSourceInput, type ResolvedExternalValue,
} from '../lib/externalIntelligenceApi';

const SOURCE_TYPES: ExternalSourceInput['source_type'][] =
  ['API', 'CSV', 'RSS', 'WEB', 'REPORT', 'PROVIDER_API'];
const GRADES: ExternalSourceInput['trust_grade'][] = ['gold', 'silver', 'bronze'];

const EMPTY_SOURCE: ExternalSourceInput = {
  name: '', source_type: 'REPORT', base_url: '', license_type: '', allowed_usage: '',
  refresh_frequency: '', owner_department: '', trust_grade: 'silver', note: '',
};

export function ExternalIntelligenceView() {
  const [ready, setReady] = useState<Loaded<ExternalReadiness>>(loading<ExternalReadiness>());
  const [indicators, setIndicators] = useState<Loaded<ExternalIndicator[]>>(loading<ExternalIndicator[]>());
  const [sources, setSources] = useState<Loaded<ExternalSource[]>>(loading<ExternalSource[]>());
  const [collectable, setCollectable] = useState<Loaded<ExternalCollectable>>(loading<ExternalCollectable>());
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
  const approve = useConfirm<string>();
  const commitCollection = useConfirm<'csv' | 'api'>();

  const load = useCallback(async () => {
    setReady(loading<ExternalReadiness>()); setIndicators(loading<ExternalIndicator[]>());
    setSources(loading<ExternalSource[]>()); setCollectable(loading<ExternalCollectable>());
    const [r, i, s, c] = await Promise.allSettled([
      externalIntelligenceApi.readiness(), externalIntelligenceApi.indicators(),
      externalIntelligenceApi.sources(), externalIntelligenceApi.collectable(),
    ]);
    setReady(r.status === 'fulfilled' ? ok(r.value) : failed<ExternalReadiness>(r.reason));
    setIndicators(i.status === 'fulfilled' ? ok(i.value) : failed<ExternalIndicator[]>(i.reason));
    setSources(s.status === 'fulfilled' ? ok(s.value) : failed<ExternalSource[]>(s.reason));
    setCollectable(c.status === 'fulfilled' ? ok(c.value) : failed<ExternalCollectable>(c.reason));
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
