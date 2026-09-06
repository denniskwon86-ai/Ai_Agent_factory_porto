// [DAO-8] 데이터 수집 오케스트레이터 화면.
//
// ★ 새 최상위 메뉴를 만들지 않는다(지시 11) — 이 패널은 `ExternalIntelligenceView` 안에
//   붙는다. 만들면 「외부 원천」이 두 군데가 되고 사용자는 어느 쪽이 정본인지 알 수 없다.
//
// ★★★ 이 화면이 **지우지 않는** 것 셋. 서버가 준 것을 그대로 보여 준다.
//   ① `known_limits` — 「이 값으로 하면 안 되는 것」.
//   ② `pending_stages` — 이 실행이 **하지 않은** 단계. 없으면 사용자는 「다 됐다」로 읽는다.
//   ③ `notice` — 「격리 적재본이며 운영 데이터셋이 아니다」.
//
// ⚠️ 화면이 문구를 새로 만들지 않는다. 만들면 그 문구와 실제 동작이 갈리고, 갈린 뒤에도
//   아무도 오류를 보지 못한다.
import { useCallback, useEffect, useState } from 'react';

import { Panel } from '../design/HubShell';
import { EmptyOrError, Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { FormField } from '../design/DataFoundationShell';
import {
  acquisitionApi, type AcquisitionCatalog, type AcquisitionJob, type ApplyReport,
  type ContractProposal, type DryRunReport, type InterpretResult, type StagedRows,
} from '../lib/externalIntelligenceApi';

const STATE_LABEL: Record<string, string> = {
  DRAFT: '요청 접수', DISCOVERING: '원천 탐색 중', PLAN_READY: '수집 계획 준비',
  DRY_RUN: '시험 수집', REVIEW_REQUIRED: '사람 검토 대기', APPLYING: '적용 중',
  ACTIVE: '적용됨·정기 갱신', FAILED: '장애', NO_DATA: '해당 자료 없음',
  QUARANTINED: '격리', DISABLED: '중지',
};

//: ★ 「장애」와 「자료 없음」을 화면에서도 다르게 보여 준다. 같은 색이면 사용자는
//:   재시도해도 소용없는 것을 계속 재시도한다.
const STATE_TONE: Record<string, string> = {
  ACTIVE: '#1a7f5a', REVIEW_REQUIRED: '#8a6d1f', QUARANTINED: '#8a3d1f',
  FAILED: '#a32020', NO_DATA: '#5a5a5a', DISABLED: '#5a5a5a',
};

const EMPTY_FORM = {
  subject_name: '', purpose: '', period_from: '', period_to: '',
  indicators: '', provider_ids: '', frequency: 'annual',
  data_origin: 'PUBLIC_DISCLOSED', refresh_frequency: '',
};

function splitList(value: string): string[] {
  return value.split(/[,\n]/).map((v) => v.trim()).filter(Boolean);
}

export function AcquisitionPanel({ canManage }: { canManage: boolean }) {
  const [catalog, setCatalog] = useState<Loaded<AcquisitionCatalog>>(loading());
  const [jobs, setJobs] = useState<Loaded<AcquisitionJob[]>>(loading());
  const [proposals, setProposals] = useState<ContractProposal[]>([]);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [interpreted, setInterpreted] = useState<InterpretResult | null>(null);
  const [selected, setSelected] = useState<AcquisitionJob | null>(null);
  const [report, setReport] = useState<DryRunReport | null>(null);
  const [applied, setApplied] = useState<ApplyReport | null>(null);
  const [staged, setStaged] = useState<StagedRows | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const reload = useCallback(async () => {
    try {
      setCatalog(ok(await acquisitionApi.catalog()));
    } catch (e) { setCatalog(failed(e)); }
    try {
      setJobs(ok(await acquisitionApi.jobs()));
    } catch (e) { setJobs(failed(e)); }
    try {
      setProposals(await acquisitionApi.contractProposals());
    } catch { /* 제안 목록은 없어도 화면이 서야 한다 */ }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  const proposalBody = useCallback(() => ({
    subject_name: form.subject_name.trim(),
    purpose: form.purpose.trim(),
    period_from: form.period_from.trim(),
    period_to: form.period_to.trim(),
    indicators: splitList(form.indicators),
    provider_ids: splitList(form.provider_ids),
    frequency: form.frequency,
    data_origin: form.data_origin,
    refresh_frequency: form.refresh_frequency.trim(),
  }), [form]);

  const run = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }, []);

  const doInterpret = () => run(async () => {
    setInterpreted(await acquisitionApi.interpret(proposalBody()));
  });

  const doCreate = () => run(async () => {
    const job = await acquisitionApi.createJob(proposalBody());
    setSelected(job); setReport(null); setApplied(null); setStaged(null);
    await reload();
  });

  const doDiscover = (jobId: string) => run(async () => {
    setSelected(await acquisitionApi.discover(jobId));
    await reload();
  });

  const doDryRun = (jobId: string) => run(async () => {
    const out = await acquisitionApi.dryRun(jobId, {});
    setSelected(out.job); setReport(out.report);
    await reload();
  });

  const doApply = (jobId: string) => run(async () => {
    const out = await acquisitionApi.apply(jobId);
    setSelected(out.job); setApplied(out.report);
    setStaged(await acquisitionApi.stagedRows(jobId));
    await reload();
  });

  const doProposeContract = (key: string) => run(async () => {
    await acquisitionApi.proposeContract(key);
    setProposals(await acquisitionApi.contractProposals());
  });

  const doDecide = (proposalId: string, approve: boolean) => run(async () => {
    await acquisitionApi.decideContract(proposalId, approve,
      approve ? '공개 재무자료 전용 계약으로 승인' : '반려');
    setProposals(await acquisitionApi.contractProposals());
  });

  return (
    <Panel kicker="DAO" title="데이터 수집 오케스트레이터"
      action={<button className="ghost-button" onClick={() => void reload()} disabled={busy}>
        새로고침</button>}>
      <div className="panel-body">
        {error && <div className="afs-banner afs-banner-error" role="alert">{error}</div>}

        {/* ── 원천 비교 카드 ─────────────────────────────────────── */}
        <h3 style={{ fontSize: 14, margin: '4px 0 8px' }}>쓸 수 있는 원천</h3>
        {catalog.status !== 'ok' || !catalog.value
          ? <EmptyOrError state={catalog.status} error={catalog.error} onRetry={() => void reload()}
            emptyText="등록된 원천이 없습니다." />
          : (() => { const c = catalog.value; return <>
            <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))' }}>
              {c.providers.map((prov) => (
                <div className="request-card" key={prov.provider_id}>
                  <div className="panel-body">
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <strong>{prov.name}</strong>
                      <span style={{ fontSize: 12, color: prov.credential_configured ? '#1a7f5a' : '#a32020' }}>
                        {prov.requires_credential
                          ? (prov.credential_configured ? '인증키 설정됨' : '인증키 없음')
                          : '인증 불필요'}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#555', marginTop: 4 }}>
                      {prov.publisher} · {prov.source_type} · {prov.cost}<br />
                      등급 {prov.default_trust_grade} · 갱신 {prov.refresh_frequency}<br />
                      대상 계약 {prov.target_contract_keys.join(', ') || '(없음)'} · 성격 {prov.data_origin}
                    </div>
                    <div style={{ fontSize: 12, marginTop: 6 }}>{prov.coverage_note}</div>
                    <div style={{ fontSize: 12, marginTop: 6 }}>
                      이용조건: {prov.allowed_usage}
                      {' · '}재배포 {prov.redistribution_allowed ? '가능' : '불가'}
                      {prov.license_url && <> · <a href={prov.license_url} target="_blank"
                        rel="noreferrer noopener">약관</a></>}
                    </div>
                    {/* ★★★ 「이 값으로 하면 안 되는 것」 — 화면이 지우지 않는다. */}
                    {prov.known_limits.length > 0 && (
                      <ul style={{ fontSize: 12, color: '#8a3d1f', margin: '8px 0 0', paddingLeft: 18 }}>
                        {prov.known_limits.map((l) => <li key={l}>{l}</li>)}
                      </ul>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {/* 지시 3 — 고르지 않은 원천과 사유 */}
            {c.excluded.length > 0 && (
              <div style={{ fontSize: 12, color: '#666', marginTop: 8 }}>
                지금 쓸 수 없는 원천:{' '}
                {c.excluded.map((e) => `${e.provider_id}(${e.reason})`).join(' · ')}
              </div>
            )}
          </>; })()}

        {/* ── 데이터 요청 ────────────────────────────────────────── */}
        <h3 style={{ fontSize: 14, margin: '18px 0 8px' }}>데이터 요청</h3>
        <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))' }}>
          <FormField label="대상 회사·조직">
            <input className="afs-input" value={form.subject_name}
              placeholder="예: LS MnM"
              onChange={(e) => setForm({ ...form, subject_name: e.target.value })} />
          </FormField>
          <FormField label="목적">
            <input className="afs-input" value={form.purpose}
              placeholder="예: 원료구매·손익 시뮬레이션"
              onChange={(e) => setForm({ ...form, purpose: e.target.value })} />
          </FormField>
          <FormField label="기간 시작(연도)">
            <input className="afs-input" value={form.period_from} placeholder="2016"
              onChange={(e) => setForm({ ...form, period_from: e.target.value })} />
          </FormField>
          <FormField label="기간 끝(연도)">
            <input className="afs-input" value={form.period_to} placeholder="2025"
              onChange={(e) => setForm({ ...form, period_to: e.target.value })} />
          </FormField>
          <FormField label="필요한 지표(쉼표 구분)">
            <input className="afs-input" value={form.indicators}
              placeholder="매출, 영업이익, 현금흐름"
              onChange={(e) => setForm({ ...form, indicators: e.target.value })} />
          </FormField>
          <FormField label="원천(쉼표 구분)">
            <input className="afs-input" value={form.provider_ids} placeholder="OPENDART"
              onChange={(e) => setForm({ ...form, provider_ids: e.target.value })} />
          </FormField>
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
          <button className="ghost-button" onClick={doInterpret} disabled={busy}>요청 확인</button>
          <button className="primary-button" onClick={doCreate}
            disabled={busy || !form.subject_name.trim() || !form.purpose.trim()}>수집 작업 만들기</button>
        </div>

        {/* 관문 결과 — 통과 못 한 이유와 «서버가 무시한 값» */}
        {interpreted && <div className="panel-body" style={{ marginTop: 8 }}>
          <div style={{ fontSize: 13 }}>
            요청 확인: {interpreted.ok ? '통과' : '통과하지 못했습니다'}
            {' · '}적용 범위 <code>{interpreted.resolved_scope_node_id || '(미배정)'}</code>
            {' · '}필요 등급 <code>{interpreted.required_grade}</code>
          </div>
          {interpreted.problems.length > 0 && <ul style={{ fontSize: 12, color: '#a32020', paddingLeft: 18 }}>
            {interpreted.problems.map((p, i) => <li key={i}><b>{p.field}</b> — {p.reason}</li>)}
          </ul>}
          {/* ★ 「왜 내가 쓴 대로 안 됐나」의 답. 조용히 바꾸지 않는다. */}
          {interpreted.overridden.length > 0 && <ul style={{ fontSize: 12, color: '#8a6d1f', paddingLeft: 18 }}>
            {interpreted.overridden.map((p, i) => <li key={i}><b>{p.field}</b> — {p.reason}</li>)}
          </ul>}
        </div>}

        {/* ── 수집 작업 ──────────────────────────────────────────── */}
        <h3 style={{ fontSize: 14, margin: '18px 0 8px' }}>수집 작업</h3>
        {jobs.status !== 'ok' || !jobs.value
          ? <EmptyOrError state={jobs.status} error={jobs.error} onRetry={() => void reload()}
            emptyText="아직 수집 작업이 없습니다." />
          : (() => { const rows = jobs.value; return rows.length === 0
            ? <div style={{ fontSize: 13, color: '#666' }}>아직 수집 작업이 없습니다.</div>
            : <div className="afs-table-wrap"><table className="afs-table">
              <thead><tr>
                <th>대상</th><th>목적</th><th>상태</th><th>원천</th><th>계약</th><th>다음 단계</th>
              </tr></thead>
              <tbody>{rows.map((j) => (
                <tr key={j.job_id}>
                  <td>{j.subject_name || '-'}</td>
                  <td style={{ fontSize: 12 }}>{j.purpose || '-'}</td>
                  <td>
                    <span style={{ color: STATE_TONE[j.status] || '#333', fontWeight: 600 }}>
                      {STATE_LABEL[j.status] || j.status}
                    </span>
                    {j.status_reason && <div style={{ fontSize: 11, color: '#666' }}>{j.status_reason}</div>}
                  </td>
                  <td style={{ fontSize: 12 }}>{j.provider_id || '-'}</td>
                  <td style={{ fontSize: 12 }}>{j.target_contract_key || '-'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {j.status === 'DRAFT' && <button className="ghost-button" disabled={busy}
                      onClick={() => doDiscover(j.job_id)}>원천 탐색</button>}
                    {j.status === 'PLAN_READY' && <button className="ghost-button" disabled={busy}
                      onClick={() => doDryRun(j.job_id)}>시험 수집</button>}
                    {j.status === 'REVIEW_REQUIRED' && (canManage
                      ? <button className="primary-button" disabled={busy}
                        onClick={() => doApply(j.job_id)}>검토 후 적용</button>
                      : <span style={{ fontSize: 12, color: '#8a6d1f' }}>데이터 관리자 승인 대기</span>)}
                    {j.status === 'ACTIVE' && <span style={{ fontSize: 12, color: '#1a7f5a' }}>
                      정기 갱신 대상</span>}
                    {j.status === 'NO_DATA' && <span style={{ fontSize: 12, color: '#5a5a5a' }}>
                      재시도해도 같습니다</span>}
                  </td>
                </tr>
              ))}</tbody>
            </table></div>; })()}

        {/* ── 새 데이터 계약 제안 ────────────────────────────────── */}
        <h3 style={{ fontSize: 14, margin: '18px 0 8px' }}>데이터 계약 제안</h3>
        <div style={{ fontSize: 12, color: '#666', marginBottom: 6 }}>
          기존 계약과 의미가 다른 자료는 억지로 연결하지 않고 새 계약으로 제안합니다.
          <b> 승인 전에는 적재 대상이 되지 않습니다.</b>
        </div>
        {proposals.length === 0
          ? (canManage && <button className="ghost-button" disabled={busy}
            onClick={() => doProposeContract('PUB-01')}>PUB-01 공개 재무실적 제안하기</button>)
          : <div className="afs-table-wrap"><table className="afs-table">
            <thead><tr><th>계약</th><th>상태</th><th>제안 사유</th><th>결정</th></tr></thead>
            <tbody>{proposals.map((p) => (
              <tr key={p.proposal_id}>
                <td>{p.contract_key}</td>
                <td>{p.status === 'APPROVED' ? '승인됨' : p.status === 'REJECTED' ? '반려' : '검토 대기'}</td>
                <td style={{ fontSize: 12, maxWidth: 420 }}>{p.rationale}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {p.status === 'PROPOSED' && canManage && <>
                    <button className="primary-button" disabled={busy}
                      onClick={() => doDecide(p.proposal_id, true)}>승인</button>{' '}
                    <button className="ghost-button" disabled={busy}
                      onClick={() => doDecide(p.proposal_id, false)}>반려</button>
                  </>}
                  {p.status === 'APPROVED' && <span style={{ fontSize: 12 }}>{p.reviewed_by}</span>}
                </td>
              </tr>
            ))}</tbody>
          </table></div>}

        {/* ── Dry-run 결과 ───────────────────────────────────────── */}
        {report && <>
          <h3 style={{ fontSize: 14, margin: '18px 0 8px' }}>시험 수집 결과 — 아직 적용되지 않았습니다</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            <Metric label="예상 건수" state="ok" value={String(report.expected_rows)} />
            <Metric label="신규" state="ok" value={String(report.new_rows)} />
            <Metric label="중복" state="ok" value={String(report.duplicate_rows)} />
            <Metric label="정정 대체" state="ok" value={String(report.superseded_rows)} />
            <Metric label="제외" state="ok" value={String(report.rejected_rows)} />
            <Metric label="예상 용량" state="ok" unit="B"
              value={report.estimated_bytes.toLocaleString()} />
          </div>
          <div style={{ fontSize: 12, marginTop: 8 }}>
            선택 이유: {report.chosen_reason || '-'}<br />
            대상 계약 <code>{report.contract_key}</code> — {report.target_contract_status}<br />
            갱신 일정: {report.refresh_schedule}
          </div>
          {report.ambiguous_with.length > 0 && <div style={{ fontSize: 12, color: '#8a6d1f', marginTop: 4 }}>
            같은 이름의 다른 후보: {report.ambiguous_with.join(' · ')}
          </div>}
          {Object.keys(report.missing_fields).length > 0 && <div style={{ fontSize: 12, marginTop: 6 }}>
            결손 필드(0 으로 채우지 않았습니다):{' '}
            {Object.entries(report.missing_fields).map(([k, v]) => `${k} ${v}건`).join(' · ')}
          </div>}
          {report.quarantined.length > 0 && <div style={{ fontSize: 12, color: '#8a3d1f', marginTop: 6 }}>
            격리 대상: {report.quarantined.map((q) => `${q.reason}${q.detail ? `(${q.detail})` : ''}`).join(' · ')}
          </div>}
          {report.mapping_needs_human.length > 0 && <div style={{ fontSize: 12, color: '#8a6d1f', marginTop: 6 }}>
            사람이 확인해야 하는 매핑: {report.mapping_needs_human.join(' · ')}
          </div>}
          {report.unit_conversions.length > 0 && <div style={{ fontSize: 12, marginTop: 6 }}>
            단위 환산: {report.unit_conversions.map((u, i) =>
              <span key={i}>{String(u.from)} → {String(u.to)} ×{String(u.factor)} </span>)}
          </div>}
          <div className="afs-table-wrap" style={{ marginTop: 8 }}><table className="afs-table">
            <thead><tr><th>검사</th><th>결과</th><th>상세</th></tr></thead>
            <tbody>{report.validation.map((v) => (
              <tr key={v.name}>
                <td>{v.name}</td>
                <td style={{ color: v.ok ? '#1a7f5a' : '#a32020' }}>{v.ok ? '통과' : '실패'}</td>
                <td style={{ fontSize: 12 }}>{v.detail}</td>
              </tr>
            ))}</tbody>
          </table></div>
          {/* ★★★ 안 하는 단계를 지우지 않는다 — 없으면 사용자는 「다 됐다」로 읽는다. */}
          <div style={{ fontSize: 12, color: '#8a6d1f', marginTop: 8 }}>
            <b>이 실행이 하지 않는 단계</b>
            <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
              {report.pending_stages.map((s) => <li key={s.name}>{s.name} — {s.reason}</li>)}
            </ul>
            {report.readiness_change_note}
          </div>
        </>}

        {/* ── 적용 결과 ──────────────────────────────────────────── */}
        {applied && <>
          <h3 style={{ fontSize: 14, margin: '18px 0 8px' }}>
            적용 결과 {applied.partial && <span style={{ color: '#a32020' }}>— 일부만 들어갔습니다</span>}
          </h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            <Metric label="신규 적재" state="ok" value={String(applied.inserted)} />
            <Metric label="중복" state="ok" value={String(applied.duplicate)} />
            <Metric label="정정 대체" state="ok" value={String(applied.superseded)} />
            <Metric label="제외" state="ok" value={String(applied.rejected)} />
          </div>
          <div className="afs-table-wrap" style={{ marginTop: 8 }}><table className="afs-table">
            <thead><tr><th>단계</th><th>결과</th><th>상세</th></tr></thead>
            <tbody>{applied.stages.map((s) => (
              <tr key={s.name}>
                <td>{s.name}</td>
                <td style={{ color: s.ok ? '#1a7f5a' : '#a32020' }}>{s.ok ? '완료' : '실패'}</td>
                <td style={{ fontSize: 12 }}>{s.detail}</td>
              </tr>
            ))}</tbody>
          </table></div>
          {applied.failure_detail && <div style={{ fontSize: 12, color: '#a32020', marginTop: 6 }}>
            [{applied.failure_kind}] {applied.failure_detail}
          </div>}
          <div style={{ fontSize: 12, color: '#8a6d1f', marginTop: 8 }}>
            <b>하지 않은 단계</b>: {applied.pending_stages.map((s) => s.name).join(' · ')}
          </div>
        </>}

        {/* ── 격리 적재본 ────────────────────────────────────────── */}
        {staged && <>
          <h3 style={{ fontSize: 14, margin: '18px 0 8px' }}>격리 적재본 {staged.count}행</h3>
          {/* ★★★ 서버가 준 고지를 그대로 보여 준다. */}
          <div className="afs-banner" role="note" style={{ fontSize: 12 }}>{staged.notice}</div>
        </>}

        {selected && <div style={{ fontSize: 12, color: '#666', marginTop: 10 }}>
          선택된 작업: {STATE_LABEL[selected.status] || selected.status}
          {selected.dataset_ref && <> · <code>{selected.dataset_ref}</code></>}
        </div>}
      </div>
    </Panel>
  );
}
